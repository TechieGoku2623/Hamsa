from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any

from fastapi import WebSocket

log = logging.getLogger(__name__)


class Hub:
    """In-process fan-out of events to connected sockets.

    Single-node only; the multi-node design replaces this with NATS subjects per user."""

    def __init__(self) -> None:
        self._sockets: dict[str, dict[str, set[WebSocket]]] = defaultdict(lambda: defaultdict(set))
        self._lock = asyncio.Lock()

    async def add(self, user_id: str, device_id: str, ws: WebSocket) -> None:
        async with self._lock:
            self._sockets[user_id][device_id].add(ws)

    async def remove(self, user_id: str, device_id: str, ws: WebSocket) -> None:
        async with self._lock:
            devs = self._sockets.get(user_id)
            if not devs:
                return
            devs[device_id].discard(ws)
            if not devs[device_id]:
                del devs[device_id]
            if not devs:
                del self._sockets[user_id]

    def online(self, user_id: str) -> bool:
        return bool(self._sockets.get(user_id))

    async def _send(self, sockets: list[WebSocket], event: dict[str, Any]) -> None:
        for ws in sockets:
            try:
                await ws.send_json(event)
            except Exception:  # socket closed mid-send; cleanup happens on disconnect
                log.debug("send failed", exc_info=True)

    async def to_device(self, user_id: str, device_id: str, event: dict[str, Any]) -> None:
        await self._send(list(self._sockets.get(user_id, {}).get(device_id, ())), event)

    async def to_user(self, user_id: str, event: dict[str, Any]) -> None:
        socks = [ws for s in self._sockets.get(user_id, {}).values() for ws in s]
        await self._send(socks, event)

    async def to_users(self, user_ids: list[str], event: dict[str, Any]) -> None:
        for uid in set(user_ids):
            await self.to_user(uid, event)
