from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from .agent.core import BusinessAgent
from .agent.llm import LLMClient, from_settings
from .auth import decode_token
from .config import settings
from .db import Database
from .models import Conversation, Device, Member, User
from .realtime import Hub
from .routes import auth as auth_routes
from .routes import business as business_routes
from .routes import chat as chat_routes

log = logging.getLogger("hamsa")


def create_app(database_url: str | None = None, llm: LLMClient | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await app.state.db.create_all()
        yield
        if app.state.agent.llm is not None:
            await app.state.agent.llm.aclose()
        await app.state.db.dispose()

    app = FastAPI(title="Hamsa API", version="0.1.0", lifespan=lifespan)
    app.state.db = Database(database_url or settings.database_url)
    app.state.hub = Hub()
    app.state.agent = BusinessAgent(llm if llm is not None else from_settings())
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins), allow_credentials=True,
                       allow_methods=["*"], allow_headers=["*"])
    for r in (auth_routes.router, chat_routes.router, business_routes.router):
        app.include_router(r, prefix="/api")

    @app.get("/api/health")
    async def health():
        return {"ok": True, "llm": app.state.agent.llm is not None}

    @app.websocket("/api/ws")
    async def ws(websocket: WebSocket, token: str, device_id: str = ""):
        try:
            user_id = decode_token(token)
        except Exception:
            await websocket.close(code=4401)
            return
        async with app.state.db.sessionmaker() as s:
            user = await s.get(User, user_id)
            dev = await s.get(Device, device_id) if device_id else None
        if user is None or (device_id and (dev is None or dev.user_id != user_id or dev.revoked)):
            await websocket.close(code=4403)
            return
        await websocket.accept()
        key = device_id or "nodevice"
        hub: Hub = app.state.hub
        await hub.add(user_id, key, websocket)
        try:
            while True:
                event = await websocket.receive_json()
                await _client_event(app, user_id, event, websocket)
        except WebSocketDisconnect:
            pass
        except Exception:
            log.debug("ws closed", exc_info=True)
        finally:
            await hub.remove(user_id, key, websocket)

    return app


async def _client_event(app: FastAPI, user_id: str, event: dict, websocket: WebSocket) -> None:
    kind = event.get("type")
    if kind == "ping":
        await websocket.send_json({"type": "pong"})
        return
    if kind not in {"signal", "typing"}:
        return
    cid = str(event.get("conversation_id", ""))
    async with app.state.db.sessionmaker() as s:
        conv = await s.get(Conversation, cid)
        members = list(await s.scalars(select(Member.user_id).where(Member.conversation_id == cid))) if conv else []
    if user_id not in members:
        return
    if kind == "typing":
        await app.state.hub.to_users([m for m in members if m != user_id], {"type": "typing", "conversation_id": cid, "user_id": user_id})
        return
    # WebRTC call signalling (offer/answer/ICE) between members of a personal chat. Media is DTLS-SRTP peer-to-peer.
    to_user = str(event.get("to_user", ""))
    if conv.kind == "business" or to_user not in members or to_user == user_id:
        return
    await app.state.hub.to_user(to_user, {"type": "signal", "conversation_id": cid, "from_user": user_id, "data": event.get("data")})


app = create_app()
