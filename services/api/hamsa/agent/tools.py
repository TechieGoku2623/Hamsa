"""Agent tools. Prices and stock always come from the catalog, never from the model."""

from __future__ import annotations

import secrets
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Business, Cart, CatalogItem, Order, now
from ..payments import format_inr, upi_intent, valid_vpa
from .nlu import CatalogEntry, clean_qty

MAX_QTY = 100.0
_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


class ToolError(Exception):
    pass


@dataclass
class LineItem:
    sku: str
    name: str
    qty: float
    unit: str
    price_paise: int

    @property
    def total_paise(self) -> int:
        return round(self.price_paise * self.qty)


async def load_catalog(session: AsyncSession, business_id: str) -> list[CatalogItem]:
    rows = await session.scalars(
        select(CatalogItem).where(CatalogItem.business_id == business_id, CatalogItem.active.is_(True)).order_by(CatalogItem.name)
    )
    return list(rows)


def to_entries(items: list[CatalogItem]) -> list[CatalogEntry]:
    return [CatalogEntry(i.sku, i.name, i.unit, i.price_paise, list(i.aliases or []), i.stock) for i in items]


async def get_cart(session: AsyncSession, conversation_id: str) -> Cart:
    cart = await session.get(Cart, conversation_id)
    if cart is None:
        cart = Cart(conversation_id=conversation_id, items=[])
        session.add(cart)
    return cart


def cart_lines(cart: Cart, catalog: dict[str, CatalogItem]) -> list[LineItem]:
    lines = []
    for row in cart.items or []:
        item = catalog.get(row["sku"])
        if item is None:
            continue
        lines.append(LineItem(item.sku, item.name, float(row["qty"]), item.unit, item.price_paise))
    return lines


def verify_line(item: CatalogItem | None, qty: float) -> float:
    """Verifier: reject unknown/inactive SKUs, absurd quantities and out-of-stock items."""
    if item is None or not item.active:
        raise ToolError("unknown_item")
    if not (0 < qty <= MAX_QTY):
        raise ToolError("bad_quantity")
    q = clean_qty(qty, item.unit)
    if item.stock is not None and q > item.stock:
        raise ToolError("out_of_stock")
    return q


async def add_items(session: AsyncSession, cart: Cart, catalog: dict[str, CatalogItem], items: list[tuple[str, float]]) -> list[LineItem]:
    current = {r["sku"]: float(r["qty"]) for r in cart.items or []}
    added = []
    for sku, qty in items:
        item = catalog.get(sku)
        q = verify_line(item, qty)
        current[sku] = q
        added.append(LineItem(item.sku, item.name, q, item.unit, item.price_paise))
    cart.items = [{"sku": s, "qty": q} for s, q in current.items()]
    cart.updated_at = now()
    return added


def remove_items(cart: Cart, skus: set[str]) -> None:
    cart.items = [r for r in cart.items or [] if r["sku"] not in skus]
    cart.updated_at = now()


def cart_total(lines: list[LineItem]) -> int:
    return sum(li.total_paise for li in lines)


def _code() -> str:
    return "H" + "".join(secrets.choice(_CODE_ALPHABET) for _ in range(5))


async def place_order(
    session: AsyncSession, business: Business, conversation_id: str, customer_user_id: str, lines: list[LineItem]
) -> Order:
    if not lines:
        raise ToolError("empty_cart")
    total = cart_total(lines)
    code = _code()
    while await session.scalar(select(Order.id).where(Order.code == code)):
        code = _code()
    link = ""
    if valid_vpa(business.vpa):
        link = upi_intent(business.vpa, business.name, total, ref=code, note=f"Hamsa order {code}")
    order = Order(
        code=code,
        business_id=business.id,
        conversation_id=conversation_id,
        customer_user_id=customer_user_id,
        items=[{"sku": li.sku, "name": li.name, "qty": li.qty, "unit": li.unit, "price_paise": li.price_paise} for li in lines],
        total_paise=total,
        status="pending_payment",
        upi_link=link,
    )
    session.add(order)
    # Reserve stock at order time; released on cancel.
    for li in lines:
        item = await session.scalar(select(CatalogItem).where(CatalogItem.business_id == business.id, CatalogItem.sku == li.sku))
        if item is not None and item.stock is not None:
            item.stock = max(0, int(item.stock - li.qty))
    return order


async def latest_order(session: AsyncSession, conversation_id: str) -> Order | None:
    return await session.scalar(
        select(Order).where(Order.conversation_id == conversation_id).order_by(Order.created_at.desc()).limit(1)
    )


async def cancel_order(session: AsyncSession, order: Order, by_owner: bool = False) -> bool:
    """Customers may cancel only before payment; the owner may cancel anything not yet delivered."""
    allowed = {"pending_payment", "payment_claimed"} | ({"paid", "preparing"} if by_owner else set())
    if order.status not in allowed:
        return False
    order.status = "cancelled"
    order.updated_at = now()
    for li in order.items:
        item = await session.scalar(select(CatalogItem).where(CatalogItem.business_id == order.business_id, CatalogItem.sku == li["sku"]))
        if item is not None and item.stock is not None:
            item.stock = int(item.stock + li["qty"])
    return True


def fmt_qty(qty: float) -> str:
    return str(int(qty)) if qty == int(qty) else f"{qty:g}"


def describe_lines(lines: list[LineItem], unit_label, name_label) -> str:
    return ", ".join(f"{fmt_qty(li.qty)} {unit_label(li.unit)} {name_label(li.sku, li.name)} ({format_inr(li.total_paise)})" for li in lines)
