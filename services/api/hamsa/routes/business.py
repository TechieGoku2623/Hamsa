from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import current_user, get_session
from ..models import Business, CatalogItem, Conversation, Member, Order, User, now
from ..payments import valid_vpa
from ..schemas import (
    AiToggleIn, BusinessIn, BusinessOut, BusinessPatch, ConversationOut, ItemIn, ItemOut, ItemPatch, OrderOut, OrderStatusIn,
    PublicBusinessOut,
)
from ..services import set_order_status
from .chat import conversation_out

router = APIRouter(tags=["business"])


async def _owned(session: AsyncSession, business_id: str, user: User) -> Business:
    biz = await session.get(Business, business_id)
    if biz is None or biz.owner_user_id != user.id:
        raise HTTPException(404, "business not found")
    return biz


def _check_vpa(vpa: str | None) -> None:
    if vpa and not valid_vpa(vpa):
        raise HTTPException(422, "invalid UPI ID (expected name@bank)")


@router.post("/businesses", response_model=BusinessOut)
async def create_business(body: BusinessIn, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    if user.is_guest:
        raise HTTPException(403, "register with a phone number to create a business")
    _check_vpa(body.vpa)
    biz = Business(owner_user_id=user.id, **body.model_dump(exclude={"faq"}), faq=[f.model_dump() for f in body.faq])
    session.add(biz)
    try:
        await session.commit()
    except IntegrityError as exc:
        raise HTTPException(409, "handle already taken") from exc
    return BusinessOut.model_validate(biz)


@router.get("/businesses/mine", response_model=list[BusinessOut])
async def my_businesses(user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    rows = await session.scalars(select(Business).where(Business.owner_user_id == user.id).order_by(Business.created_at))
    return [BusinessOut.model_validate(b) for b in rows]


@router.patch("/businesses/{business_id}", response_model=BusinessOut)
async def update_business(business_id: str, body: BusinessPatch, user: User = Depends(current_user),
                          session: AsyncSession = Depends(get_session)):
    biz = await _owned(session, business_id, user)
    _check_vpa(body.vpa)
    data = body.model_dump(exclude_unset=True)
    if "faq" in data:
        data["faq"] = [dict(f) for f in data["faq"]]
    for k, v in data.items():
        setattr(biz, k, v)
    await session.commit()
    return BusinessOut.model_validate(biz)


@router.get("/businesses/{business_id}/items", response_model=list[ItemOut])
async def list_items(business_id: str, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    await _owned(session, business_id, user)
    rows = await session.scalars(select(CatalogItem).where(CatalogItem.business_id == business_id).order_by(CatalogItem.name))
    return [ItemOut.model_validate(i) for i in rows]


@router.post("/businesses/{business_id}/items", response_model=ItemOut)
async def add_item(business_id: str, body: ItemIn, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    await _owned(session, business_id, user)
    item = CatalogItem(business_id=business_id, **body.model_dump())
    session.add(item)
    try:
        await session.commit()
    except IntegrityError as exc:
        raise HTTPException(409, "SKU already exists") from exc
    return ItemOut.model_validate(item)


@router.patch("/items/{item_id}", response_model=ItemOut)
async def update_item(item_id: str, body: ItemPatch, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    item = await session.get(CatalogItem, item_id)
    if item is None:
        raise HTTPException(404, "item not found")
    await _owned(session, item.business_id, user)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(item, k, v)
    await session.commit()
    return ItemOut.model_validate(item)


@router.delete("/items/{item_id}")
async def delete_item(item_id: str, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    item = await session.get(CatalogItem, item_id)
    if item is None:
        raise HTTPException(404, "item not found")
    await _owned(session, item.business_id, user)
    item.active = False  # keep for order history
    await session.commit()
    return {"ok": True}


@router.get("/public/b/{handle}", response_model=PublicBusinessOut)
async def public_business(handle: str, session: AsyncSession = Depends(get_session)):
    biz = await session.scalar(select(Business).where(Business.handle == handle))
    if biz is None:
        raise HTTPException(404, "business not found")
    items = await session.scalars(
        select(CatalogItem).where(CatalogItem.business_id == biz.id, CatalogItem.active.is_(True)).order_by(CatalogItem.name)
    )
    return PublicBusinessOut(business=BusinessOut.model_validate(biz), items=[ItemOut.model_validate(i) for i in items])


@router.post("/public/b/{handle}/chat", response_model=ConversationOut)
async def open_business_chat(handle: str, request: Request, user: User = Depends(current_user),
                             session: AsyncSession = Depends(get_session)):
    biz = await session.scalar(select(Business).where(Business.handle == handle))
    if biz is None:
        raise HTTPException(404, "business not found")
    if biz.owner_user_id == user.id:
        raise HTTPException(400, "owners reply from the business inbox")
    key = f"biz:{biz.id}:{user.id}"
    conv = await session.scalar(select(Conversation).where(Conversation.direct_key == key))
    if conv is None:
        conv = Conversation(kind="business", business_id=biz.id, title=biz.name, created_by=user.id, direct_key=key)
        session.add(conv)
        await session.flush()
        session.add_all([Member(conversation_id=conv.id, user_id=user.id, role="customer"),
                         Member(conversation_id=conv.id, user_id=biz.owner_user_id, role="owner")])
        await session.commit()
        out = await conversation_out(session, conv)
        await request.app.state.hub.to_users([user.id, biz.owner_user_id], {"type": "conversation", "conversation": out.model_dump(mode="json")})
        return out
    return await conversation_out(session, conv)


@router.get("/businesses/{business_id}/conversations", response_model=list[ConversationOut])
async def business_inbox(business_id: str, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    await _owned(session, business_id, user)
    convs = await session.scalars(
        select(Conversation).where(Conversation.business_id == business_id).order_by(Conversation.needs_human.desc(), Conversation.updated_at.desc())
    )
    return [await conversation_out(session, c) for c in convs]


@router.post("/conversations/{conversation_id}/ai", response_model=ConversationOut)
async def toggle_ai(conversation_id: str, body: AiToggleIn, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    conv = await session.get(Conversation, conversation_id)
    if conv is None or conv.kind != "business":
        raise HTTPException(404, "conversation not found")
    await _owned(session, conv.business_id, user)
    conv.ai_enabled = body.enabled
    if body.enabled:
        conv.needs_human = False
    conv.updated_at = now()
    await session.commit()
    return await conversation_out(session, conv)


@router.get("/businesses/{business_id}/orders", response_model=list[OrderOut])
async def business_orders(business_id: str, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    await _owned(session, business_id, user)
    rows = await session.scalars(select(Order).where(Order.business_id == business_id).order_by(Order.created_at.desc()).limit(200))
    return [OrderOut.model_validate(o) for o in rows]


@router.patch("/orders/{order_id}", response_model=OrderOut)
async def update_order(order_id: str, body: OrderStatusIn, request: Request, user: User = Depends(current_user),
                       session: AsyncSession = Depends(get_session)):
    order = await session.get(Order, order_id)
    if order is None:
        raise HTTPException(404, "order not found")
    await _owned(session, order.business_id, user)
    return OrderOut.model_validate(await set_order_status(request.app, session, order, body.status))


@router.get("/orders/mine", response_model=list[OrderOut])
async def my_orders(user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    rows = await session.scalars(select(Order).where(Order.customer_user_id == user.id).order_by(Order.created_at.desc()).limit(100))
    return [OrderOut.model_validate(o) for o in rows]
