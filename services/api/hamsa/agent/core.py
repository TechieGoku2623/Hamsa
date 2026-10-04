"""Business agent: deterministic tiers first, Hamsa-LM only when they cannot answer.

Cascade (memo §4): FAQ match -> rules (intent keywords + catalog matcher) -> LLM with tools -> fallback.
Every state change goes through tools.py, whose verifier owns prices, SKUs and stock."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from rapidfuzz import fuzz
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Business, BusinessMessage, CatalogItem, Conversation, Order, now
from ..payments import format_inr
from . import tools
from .lang import detect_in_context, script_of
from .lexicon import GROCERY_SYNONYMS
from .llm import TOOLS, LLMClient, parse_args
from .nlu import convert_qty, detect_intents, find_mentions, group_overlaps, prepare
from .templates import LANG_SCRIPT, status_name, t, template_lang, unit_name

log = logging.getLogger(__name__)

_LANG_DESC = {
    "en": "English", "hi": "Hindi in Devanagari", "hi_latn": "Hinglish (Hindi in Latin letters)", "mr": "Marathi in Devanagari",
    "ta": "Tamil in Tamil script", "ta_latn": "Tanglish (Tamil in Latin letters)", "te": "Telugu in Telugu script",
    "te_latn": "Telugu in Latin letters", "bn": "Bengali in Bengali script", "bn_latn": "Bengali in Latin letters",
    "kn": "Kannada in Kannada script", "gu": "Gujarati", "pa": "Punjabi in Gurmukhi", "ml": "Malayalam", "or": "Odia",
}
_INR_RE = re.compile(r"(?:₹|rs\.?|inr)\s?([\d,]+(?:\.\d{1,2})?)", re.IGNORECASE)
MENU_LIMIT = 30


@dataclass
class AgentReply:
    text: str
    lang: str
    tier: str
    order: Order | None = None
    handoff: bool = False
    actions: list[dict[str, Any]] = field(default_factory=list)
    trace: dict[str, Any] = field(default_factory=dict)


class BusinessAgent:
    def __init__(self, llm: LLMClient | None = None) -> None:
        self.llm = llm

    async def respond(
        self, session: AsyncSession, conv: Conversation, biz: Business, customer_id: str, text: str,
        history: list[BusinessMessage] | None = None,
    ) -> AgentReply:
        previous = next((m.meta.get("lang") for m in reversed(history or []) if m.sender_type == "agent" and m.meta), None)
        lang = detect_in_context(text, previous)
        catalog_rows = await tools.load_catalog(session, biz.id)
        catalog = {c.sku: c for c in catalog_rows}
        ctx = _Ctx(self, session, conv, biz, customer_id, lang, catalog)

        intents = detect_intents(text)
        groups = group_overlaps(find_mentions(text, tools.to_entries(catalog_rows)))
        ctx.trace.update(intents=sorted(intents), mentions=[[m.sku for m in g] for g in groups])

        if not groups:
            faq = _best_faq(text, biz.faq or [])
            if faq is not None:
                return ctx.reply(faq, "faq")

        reply = await ctx.rules(text, intents, groups)
        if reply is not None:
            return reply
        if self.llm is not None:
            try:
                return await ctx.llm_turn(text, history or [])
            except Exception:
                log.warning("LLM tier failed; using fallback", exc_info=True)
                ctx.trace["llm_error"] = True
        return ctx.reply(t(lang, "fallback"), "fallback")


def _best_faq(text: str, faq: list[dict[str, str]]) -> str | None:
    q = prepare(text)
    best, score = None, 0.0
    for entry in faq:
        s = fuzz.token_set_ratio(q, prepare(entry.get("q", "")))
        if s > score:
            best, score = entry.get("a"), s
    return best if score >= 80 and best else None


class _Ctx:
    def __init__(self, agent: BusinessAgent, session: AsyncSession, conv: Conversation, biz: Business, customer_id: str,
                 lang: str, catalog: dict[str, CatalogItem]) -> None:
        self.agent, self.session, self.conv, self.biz = agent, session, conv, biz
        self.customer_id, self.lang, self.catalog = customer_id, lang, catalog
        self.trace: dict[str, Any] = {"lang": lang}
        self.order: Order | None = None
        self.handoff = False
        self.actions: list[dict[str, Any]] = []

    # ---- presentation -------------------------------------------------
    def reply(self, text: str, tier: str) -> AgentReply:
        return AgentReply(text, self.lang, tier, self.order, self.handoff, self.actions, self.trace)

    def name(self, sku: str, fallback: str) -> str:
        item = self.catalog.get(sku)
        target = LANG_SCRIPT.get(template_lang(self.lang))
        if item is None or target is None:
            return fallback
        if script_of(item.name) == target:
            return item.name
        candidates = list(item.aliases or [])
        for word in re.findall(r"[a-z]+", item.name.lower()):
            candidates += GROCERY_SYNONYMS.get(word, [])
        for c in candidates:
            if script_of(c) == target:
                return c
        return item.name

    def unit(self, unit: str) -> str:
        return unit_name(self.lang, unit)

    def lines_text(self, lines: list[tools.LineItem]) -> str:
        return tools.describe_lines(lines, self.unit, self.name)

    async def cart(self):
        cart = await tools.get_cart(self.session, self.conv.id)
        return cart, tools.cart_lines(cart, self.catalog)

    def menu(self) -> str:
        rows = [f"• {self.name(i.sku, i.name)} — {format_inr(i.price_paise)}/{self.unit(i.unit)}"
                + ("" if i.stock is None or i.stock > 0 else " ✗") for i in list(self.catalog.values())[:MENU_LIMIT]]
        return "\n".join([t(self.lang, "menu_header", biz=self.biz.name), *rows])

    def _order_placed(self, order: Order) -> str:
        self.order = order
        key = "order_placed_upi" if order.upi_link else "order_placed_cod"
        if order.upi_link:
            self.actions.append({"type": "upi_pay", "link": order.upi_link, "amount_paise": order.total_paise, "order_code": order.code})
        return t(self.lang, key, code=order.code, total=format_inr(order.total_paise), biz=self.biz.name)

    def _handoff(self) -> None:
        self.handoff = True
        self.conv.needs_human = True

    # ---- rules tier ---------------------------------------------------
    async def rules(self, text: str, intents: set[str], groups) -> AgentReply | None:
        lang = self.lang
        ambiguous = [g for g in groups if len(g) > 1]
        chosen = [g[0] for g in groups if len(g) == 1]

        if "cancel" in intents or "remove" in intents:
            cart, lines = await self.cart()
            if chosen:
                skus = {m.sku for m in chosen}
                removed = [li for li in lines if li.sku in skus]
                tools.remove_items(cart, skus)
                _, lines = await self.cart()
                return self.reply(t(lang, "removed", items=self.lines_text(removed) or ", ".join(self.name(s, s) for s in skus),
                                    total=format_inr(tools.cart_total(lines))), "rules")
            if "cancel" in intents:
                order = await tools.latest_order(self.session, self.conv.id)
                if order and order.status != "cancelled":
                    if await tools.cancel_order(self.session, order):
                        self.order = order
                        return self.reply(t(lang, "cancelled", code=order.code), "rules")
                    return self.reply(t(lang, "cannot_cancel", code=order.code, status=status_name(lang, order.status)), "rules")
                if lines:
                    tools.remove_items(cart, {li.sku for li in lines})
                    return self.reply(t(lang, "cart_cleared"), "rules")
                return self.reply(t(lang, "no_orders"), "rules")

        if "paid" in intents:
            order = await tools.latest_order(self.session, self.conv.id)
            if order and order.status == "pending_payment":
                order.status, order.updated_at = "payment_claimed", now()
                self.order = order
                return self.reply(t(lang, "paid_claimed", biz=self.biz.name, code=order.code), "rules")
            if order:
                return self.reply(t(lang, "status", code=order.code, status=status_name(lang, order.status)), "rules")
            return self.reply(t(lang, "no_orders"), "rules")

        if "status" in intents and not chosen:
            order = await tools.latest_order(self.session, self.conv.id)
            if order:
                self.order = order
                return self.reply(t(lang, "status", code=order.code, status=status_name(lang, order.status)), "rules")
            return self.reply(t(lang, "no_orders"), "rules")

        if "human" in intents:
            self._handoff()
            return self.reply(t(lang, "human"), "rules")

        if ambiguous:
            options = " / ".join(f"{self.name(m.sku, self.catalog[m.sku].name)} ({format_inr(self.catalog[m.sku].price_paise)})"
                                 for m in ambiguous[0])
            return self.reply(t(lang, "ambiguous", options=options), "rules")

        wants_checkout = "checkout" in intents or ("pay" in intents and not chosen)
        if chosen and ("price" not in intents or "order" in intents or wants_checkout or any(m.qty_explicit for m in chosen)):
            cart, _ = await self.cart()
            try:
                added = await tools.add_items(self.session, cart, self.catalog,
                                              [(m.sku, convert_qty(m.qty, m.qty_unit, self.catalog[m.sku].unit)) for m in chosen])
            except tools.ToolError as e:
                if str(e) == "out_of_stock":
                    bad = next(m for m in chosen if self.catalog[m.sku].stock is not None)
                    return self.reply(t(lang, "out_of_stock", name=self.name(bad.sku, self.catalog[bad.sku].name)), "rules")
                return self.reply(t(lang, "fallback"), "rules")
            _, lines = await self.cart()
            if wants_checkout:
                return await self._checkout()
            return self.reply(t(lang, "added", items=self.lines_text(added), total=format_inr(tools.cart_total(lines))), "rules")

        if chosen:  # price question
            parts = [t(lang, "price", name=self.name(m.sku, self.catalog[m.sku].name), price=format_inr(self.catalog[m.sku].price_paise),
                       unit=self.unit(self.catalog[m.sku].unit)) for m in chosen]
            return self.reply(" ".join(parts), "rules")

        if wants_checkout:
            return await self._checkout()
        if "cart" in intents:
            _, lines = await self.cart()
            if not lines:
                return self.reply(t(lang, "cart_empty"), "rules")
            return self.reply(t(lang, "cart", items=self.lines_text(lines), total=format_inr(tools.cart_total(lines))), "rules")
        if "browse" in intents or "price" in intents:
            return self.reply(self.menu(), "rules")
        if "hours" in intents:
            if self.biz.hours:
                return self.reply(t(lang, "hours", biz=self.biz.name, hours=self.biz.hours), "rules")
            self._handoff()
            return self.reply(t(lang, "no_info"), "rules")
        if "location" in intents:
            if self.biz.address:
                return self.reply(t(lang, "location", biz=self.biz.name, address=self.biz.address), "rules")
            self._handoff()
            return self.reply(t(lang, "no_info"), "rules")
        if "greet" in intents:
            return self.reply(t(lang, "greet", biz=self.biz.name), "rules")
        if "thanks" in intents:
            return self.reply(t(lang, "thanks"), "rules")
        if "order" in intents and not self.agent.llm:
            return self.reply(t(lang, "not_found"), "rules")
        return None

    async def _checkout(self) -> AgentReply:
        cart, lines = await self.cart()
        if not lines:
            return self.reply(t(self.lang, "cart_empty"), "rules")
        order = await tools.place_order(self.session, self.biz, self.conv.id, self.customer_id, lines)
        tools.remove_items(cart, {li.sku for li in lines})
        return self.reply(self._order_placed(order), "rules")

    # ---- LLM tier -----------------------------------------------------
    def _system_prompt(self, lines: list[tools.LineItem]) -> str:
        cat = "\n".join(
            f"{i.sku} | {i.name} | {', '.join(i.aliases or [])} | {format_inr(i.price_paise)} | {i.unit}"
            + ("" if i.stock is None else f" | stock {i.stock}") for i in self.catalog.values()
        )
        faq = "\n".join(f"Q: {f.get('q')}\nA: {f.get('a')}" for f in (self.biz.faq or []))
        cart = self.lines_text(lines) or "empty"
        return (
            f"You are the ordering assistant for {self.biz.name}, a {self.biz.category} in India, chatting on Hamsa.\n"
            f"Reply in {_LANG_DESC.get(self.lang, 'the customer’s language')}, matching the customer's script. Under 60 words.\n"
            "Only sell catalog items. Use tools to change the cart, place orders or check status; never invent prices, "
            "discounts, delivery times or policies. If unsure, ask one short clarifying question or call handoff_to_owner.\n"
            f"Hours: {self.biz.hours or 'unknown'}. Address: {self.biz.address or 'unknown'}. Delivery: {self.biz.delivery_note or 'ask owner'}.\n"
            f"Catalog (sku | name | aliases | price | unit):\n{cat}\nFAQ:\n{faq or 'none'}\nCurrent cart: {cart}"
        )

    async def _run_tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        try:
            if name == "add_to_cart":
                cart, _ = await self.cart()
                req = [(str(i.get("sku")), float(i.get("qty", 1))) for i in args.get("items", []) if isinstance(i, dict)]
                added = await tools.add_items(self.session, cart, self.catalog, req)
                _, lines = await self.cart()
                return {"ok": True, "added": [li.__dict__ for li in added], "cart_total": format_inr(tools.cart_total(lines))}
            if name == "remove_from_cart":
                cart, _ = await self.cart()
                tools.remove_items(cart, {str(s) for s in args.get("skus", [])})
                _, lines = await self.cart()
                return {"ok": True, "cart_total": format_inr(tools.cart_total(lines))}
            if name == "view_cart":
                _, lines = await self.cart()
                return {"ok": True, "lines": [li.__dict__ for li in lines], "total": format_inr(tools.cart_total(lines))}
            if name == "place_order":
                cart, lines = await self.cart()
                order = await tools.place_order(self.session, self.biz, self.conv.id, self.customer_id, lines)
                tools.remove_items(cart, {li.sku for li in lines})
                self._order_placed(order)
                return {"ok": True, "order_code": order.code, "total": format_inr(order.total_paise),
                        "payment": "upi_button_shown" if order.upi_link else "pay_on_delivery"}
            if name == "order_status":
                order = await tools.latest_order(self.session, self.conv.id)
                return {"ok": True, "order": None if order is None else {"code": order.code, "status": order.status,
                                                                          "total": format_inr(order.total_paise)}}
            if name == "handoff_to_owner":
                self._handoff()
                return {"ok": True}
        except tools.ToolError as e:
            return {"ok": False, "error": str(e)}
        except (TypeError, ValueError):
            return {"ok": False, "error": "bad_arguments"}
        return {"ok": False, "error": "unknown_tool"}

    def _allowed_amounts(self, lines: list[tools.LineItem]) -> set[int]:
        allowed = {i.price_paise for i in self.catalog.values()}
        allowed |= {li.total_paise for li in lines}
        allowed.add(tools.cart_total(lines))
        if self.order is not None:
            allowed.add(self.order.total_paise)
        return allowed

    async def llm_turn(self, text: str, history: list[BusinessMessage]) -> AgentReply:
        _, lines = await self.cart()
        messages: list[dict[str, Any]] = [{"role": "system", "content": self._system_prompt(lines)}]
        for m in history[-8:]:
            messages.append({"role": "user" if m.sender_type == "customer" else "assistant", "content": m.text})
        messages.append({"role": "user", "content": text})
        calls: list[str] = []
        content = ""
        for _ in range(4):
            msg = await self.agent.llm.chat(messages, TOOLS)
            tool_calls = msg.get("tool_calls") or []
            if not tool_calls:
                content = (msg.get("content") or "").strip()
                break
            messages.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": tool_calls})
            for tc in tool_calls:
                fn = tc.get("function", {})
                result = await self._run_tool(fn.get("name", ""), parse_args(fn.get("arguments")))
                calls.append(fn.get("name", ""))
                messages.append({"role": "tool", "tool_call_id": tc.get("id", ""), "content": json.dumps(result, ensure_ascii=False)})
        self.trace["tool_calls"] = calls
        _, lines = await self.cart()
        if not content or not self._amounts_ok(content, lines):
            self.trace["verifier"] = "replaced"
            if self.order is not None:
                content = t(self.lang, "order_placed_upi" if self.order.upi_link else "order_placed_cod",
                            code=self.order.code, total=format_inr(self.order.total_paise), biz=self.biz.name)
            elif lines:
                content = t(self.lang, "cart", items=self.lines_text(lines), total=format_inr(tools.cart_total(lines)))
            else:
                content = t(self.lang, "fallback")
        return self.reply(content, "llm")

    def _amounts_ok(self, content: str, lines: list[tools.LineItem]) -> bool:
        allowed = self._allowed_amounts(lines)
        for m in _INR_RE.finditer(content):
            try:
                paise = round(float(m.group(1).replace(",", "")) * 100)
            except ValueError:
                return False
            if paise not in allowed:
                return False
        return True
