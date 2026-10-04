from __future__ import annotations

from fastapi import FastAPI, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .agent.templates import status_name, t
from .agent.tools import cancel_order
from .models import Business, BusinessMessage, Conversation, Member, Order, User, now
from .payments import format_inr
from .schemas import MessageOut, OrderOut


async def require_member(session: AsyncSession, conversation_id: str, user_id: str) -> Conversation:
    conv = await session.get(Conversation, conversation_id)
    if conv is None:
        raise HTTPException(404, "conversation not found")
    if await session.scalar(select(Member.user_id).where(Member.conversation_id == conv.id, Member.user_id == user_id)) is None:
        raise HTTPException(404, "conversation not found")
    return conv


async def member_ids(session: AsyncSession, conversation_id: str) -> list[str]:
    return list(await session.scalars(select(Member.user_id).where(Member.conversation_id == conversation_id)))


async def push_message(app: FastAPI, session: AsyncSession, msg: BusinessMessage) -> None:
    await app.state.hub.to_users(await member_ids(session, msg.conversation_id),
                                 {"type": "business_message", "message": MessageOut.model_validate(msg).model_dump(mode="json")})


async def push_order(app: FastAPI, session: AsyncSession, order: Order) -> None:
    await app.state.hub.to_users(await member_ids(session, order.conversation_id),
                                 {"type": "order", "order": OrderOut.model_validate(order).model_dump(mode="json")})


async def last_customer_lang(session: AsyncSession, conversation_id: str) -> str:
    meta = await session.scalar(
        select(BusinessMessage.meta).where(BusinessMessage.conversation_id == conversation_id, BusinessMessage.sender_type == "agent")
        .order_by(BusinessMessage.created_at.desc()).limit(1)
    )
    return (meta or {}).get("lang", "en")


async def handle_business_message(app: FastAPI, session: AsyncSession, conv: Conversation, user: User, text: str):
    biz = await session.get(Business, conv.business_id)
    sender_type = "owner" if biz.owner_user_id == user.id else "customer"
    msg = BusinessMessage(conversation_id=conv.id, sender_type=sender_type, sender_user_id=user.id, text=text, meta={})
    session.add(msg)
    conv.updated_at = now()
    await session.commit()
    await push_message(app, session, msg)
    if sender_type != "customer" or not conv.ai_enabled:
        return msg, None

    history = list(await session.scalars(
        select(BusinessMessage).where(BusinessMessage.conversation_id == conv.id, BusinessMessage.id != msg.id)
        .order_by(BusinessMessage.created_at.desc()).limit(8)
    ))[::-1]
    result = await app.state.agent.respond(session, conv, biz, user.id, text, history)
    meta = {"lang": result.lang, "tier": result.tier, "actions": result.actions, "trace": result.trace}
    if result.order is not None:
        meta["order_code"] = result.order.code
    if result.handoff:
        conv.ai_enabled = False
    reply = BusinessMessage(conversation_id=conv.id, sender_type="agent", text=result.text, meta=meta)
    session.add(reply)
    conv.updated_at = now()
    await session.commit()
    await push_message(app, session, reply)
    if result.order is not None:
        await session.refresh(result.order)
        await push_order(app, session, result.order)
    if result.handoff:
        await app.state.hub.to_user(biz.owner_user_id, {"type": "needs_human", "conversation_id": conv.id})
    return msg, reply


_TRANSITIONS = {
    "pending_payment": {"paid", "cancelled", "preparing"},
    "payment_claimed": {"paid", "cancelled", "pending_payment"},
    "paid": {"preparing", "ready", "delivered", "cancelled"},
    "preparing": {"ready", "delivered", "cancelled"},
    "ready": {"delivered"},
    "delivered": set(),
    "cancelled": set(),
}


async def set_order_status(app: FastAPI, session: AsyncSession, order: Order, status: str) -> Order:
    if status not in _TRANSITIONS[order.status]:
        raise HTTPException(409, f"cannot move order from {order.status} to {status}")
    if status == "cancelled":
        await cancel_order(session, order, by_owner=True)
    else:
        order.status = status
        order.updated_at = now()
    lang = await last_customer_lang(session, order.conversation_id)
    note = BusinessMessage(conversation_id=order.conversation_id, sender_type="system",
                           text=t(lang, "status", code=order.code, status=status_name(lang, order.status)),
                           meta={"order_code": order.code, "status": order.status, "total": format_inr(order.total_paise)})
    session.add(note)
    await session.commit()
    await push_message(app, session, note)
    await push_order(app, session, order)
    return order
