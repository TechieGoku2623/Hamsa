"""Client for an OpenAI-compatible chat endpoint (vLLM / SGLang serving Hamsa-LM)."""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from ..config import settings

log = logging.getLogger(__name__)

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "add_to_cart",
            "description": "Add or set catalog items in the customer's cart. Use exact SKUs from the catalog.",
            "parameters": {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {"sku": {"type": "string"}, "qty": {"type": "number", "exclusiveMinimum": 0}},
                            "required": ["sku", "qty"],
                        },
                    }
                },
                "required": ["items"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remove_from_cart",
            "description": "Remove items from the cart by SKU.",
            "parameters": {"type": "object", "properties": {"skus": {"type": "array", "items": {"type": "string"}}}, "required": ["skus"]},
        },
    },
    {"type": "function", "function": {"name": "view_cart", "description": "Show the cart and total.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "place_order", "description": "Place the order for the current cart after the customer confirms.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "order_status", "description": "Status of the customer's latest order.", "parameters": {"type": "object", "properties": {}}}},
    {
        "type": "function",
        "function": {
            "name": "handoff_to_owner",
            "description": "Ask the human owner to take over, e.g. complaints, refunds, custom requests or anything not in the catalog/FAQ.",
            "parameters": {"type": "object", "properties": {"reason": {"type": "string"}}, "required": ["reason"]},
        },
    },
]


class LLMClient:
    def __init__(self, base_url: str, model: str, api_key: str, timeout: float, transport: httpx.AsyncBaseTransport | None = None):
        self.model = model
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"), timeout=timeout, transport=transport, headers={"Authorization": f"Bearer {api_key}"}
        )

    async def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"model": self.model, "messages": messages, "temperature": 0.2, "max_tokens": 300}
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        r = await self._client.post("/chat/completions", json=body)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]

    async def aclose(self) -> None:
        await self._client.aclose()


def parse_args(raw: str | dict | None) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    try:
        v = json.loads(raw or "{}")
        return v if isinstance(v, dict) else {}
    except json.JSONDecodeError:
        return {}


def from_settings() -> LLMClient | None:
    if not settings.llm_base_url:
        return None
    return LLMClient(settings.llm_base_url, settings.llm_model, settings.llm_api_key, settings.llm_timeout_s)
