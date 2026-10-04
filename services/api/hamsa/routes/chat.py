from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import current_user, get_session
from ..config import settings
from ..models import Business, BusinessMessage, Conversation, Device, Envelope, Member, User, now
from ..schemas import (
    AckIn, BusinessBrief, ConversationCreate, ConversationOut, DeviceIn, DeviceOut, EnvelopeOut, EnvelopesIn, MemberOut,
    MembersAddIn, MessageIn, MessageOut,
)
from ..services import handle_business_message, member_ids, require_member

router = APIRouter(tags=["chat"])


async def conversation_out(session: AsyncSession, conv: Conversation) -> ConversationOut:
    rows = (await session.execute(
        select(Member, User).join(User, User.id == Member.user_id).where(Member.conversation_id == conv.id)
    )).all()
    members = [MemberOut(user_id=u.id, display_name=u.display_name, phone=u.phone, role=m.role) for m, u in rows]
    biz = None
    last_text = None
    if conv.business_id:
        b = await session.get(Business, conv.business_id)
        biz = BusinessBrief(id=b.id, handle=b.handle, name=b.name)
        last_text = await session.scalar(
            select(BusinessMessage.text).where(BusinessMessage.conversation_id == conv.id)
            .order_by(BusinessMessage.created_at.desc()).limit(1)
        )
    return ConversationOut(id=conv.id, kind=conv.kind, title=conv.title, members=members, business=biz,
                           ai_enabled=conv.ai_enabled, needs_human=conv.needs_human, updated_at=conv.updated_at, last_text=last_text)


# ---- devices ---------------------------------------------------------------

@router.post("/devices", response_model=DeviceOut)
async def register_device(body: DeviceIn, request: Request, user: User = Depends(current_user),
                          session: AsyncSession = Depends(get_session)):
    dev = Device(user_id=user.id, name=body.name, public_key=body.public_key)
    session.add(dev)
    await session.commit()
    peers = set()
    for cid in await session.scalars(select(Member.conversation_id).where(Member.user_id == user.id)):
        peers.update(await member_ids(session, cid))
    await request.app.state.hub.to_users(list(peers), {"type": "devices_changed", "user_id": user.id})
    return DeviceOut.model_validate(dev)


@router.get("/devices", response_model=list[DeviceOut])
async def my_devices(user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    rows = await session.scalars(select(Device).where(Device.user_id == user.id, Device.revoked.is_(False)))
    return [DeviceOut.model_validate(d) for d in rows]


@router.delete("/devices/{device_id}")
async def revoke_device(device_id: str, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    dev = await session.get(Device, device_id)
    if dev is None or dev.user_id != user.id:
        raise HTTPException(404, "device not found")
    dev.revoked = True
    await session.execute(delete(Envelope).where(Envelope.recipient_device_id == device_id))
    await session.commit()
    return {"ok": True}


async def _active_devices(session: AsyncSession, user_ids: list[str]) -> list[Device]:
    return list(await session.scalars(select(Device).where(Device.user_id.in_(user_ids), Device.revoked.is_(False))))


@router.get("/conversations/{conversation_id}/devices", response_model=list[DeviceOut])
async def conversation_devices(conversation_id: str, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    await require_member(session, conversation_id, user.id)
    return [DeviceOut.model_validate(d) for d in await _active_devices(session, await member_ids(session, conversation_id))]


# ---- conversations ---------------------------------------------------------

@router.post("/conversations", response_model=ConversationOut)
async def create_conversation(body: ConversationCreate, request: Request, user: User = Depends(current_user),
                              session: AsyncSession = Depends(get_session)):
    if user.is_guest:
        raise HTTPException(403, "register with a phone number to start personal chats")
    if body.kind == "direct":
        peer = await session.get(User, body.peer_user_id or "")
        if peer is None or peer.id == user.id or peer.is_guest:
            raise HTTPException(404, "user not found")
        key = ":".join(sorted([user.id, peer.id]))
        conv = await session.scalar(select(Conversation).where(Conversation.direct_key == key))
        if conv is None:
            conv = Conversation(kind="direct", created_by=user.id, direct_key=key, ai_enabled=False)
            session.add(conv)
            await session.flush()
            session.add_all([Member(conversation_id=conv.id, user_id=user.id, role="member"),
                             Member(conversation_id=conv.id, user_id=peer.id, role="member")])
            await session.commit()
        notify = [user.id, peer.id]
    else:
        ids = list(dict.fromkeys(i for i in body.member_user_ids if i != user.id))
        if not body.title.strip():
            raise HTTPException(422, "group title required")
        if len(ids) + 1 > settings.max_group_members:
            raise HTTPException(422, "group too large")
        found = list(await session.scalars(select(User.id).where(User.id.in_(ids), User.is_guest.is_(False))))
        if len(found) != len(ids):
            raise HTTPException(404, "some users not found")
        conv = Conversation(kind="group", title=body.title.strip(), created_by=user.id, ai_enabled=False)
        session.add(conv)
        await session.flush()
        session.add(Member(conversation_id=conv.id, user_id=user.id, role="admin"))
        session.add_all([Member(conversation_id=conv.id, user_id=i, role="member") for i in ids])
        await session.commit()
        notify = [user.id, *ids]
    out = await conversation_out(session, conv)
    await request.app.state.hub.to_users(notify, {"type": "conversation", "conversation": out.model_dump(mode="json")})
    return out


@router.get("/conversations", response_model=list[ConversationOut])
async def list_conversations(user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    convs = await session.scalars(
        select(Conversation).join(Member, Member.conversation_id == Conversation.id)
        .where(Member.user_id == user.id).order_by(Conversation.updated_at.desc())
    )
    return [await conversation_out(session, c) for c in convs]


@router.get("/conversations/{conversation_id}", response_model=ConversationOut)
async def get_conversation(conversation_id: str, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    conv = await require_member(session, conversation_id, user.id)
    return await conversation_out(session, conv)


@router.post("/conversations/{conversation_id}/members", response_model=ConversationOut)
async def add_members(conversation_id: str, body: MembersAddIn, request: Request, user: User = Depends(current_user),
                      session: AsyncSession = Depends(get_session)):
    conv = await require_member(session, conversation_id, user.id)
    role = await session.scalar(select(Member.role).where(Member.conversation_id == conv.id, Member.user_id == user.id))
    if conv.kind != "group" or role != "admin":
        raise HTTPException(403, "only group admins can add members")
    existing = set(await member_ids(session, conv.id))
    new = [i for i in dict.fromkeys(body.user_ids) if i not in existing]
    if len(existing) + len(new) > settings.max_group_members:
        raise HTTPException(422, "group too large")
    found = list(await session.scalars(select(User.id).where(User.id.in_(new), User.is_guest.is_(False))))
    session.add_all([Member(conversation_id=conv.id, user_id=i, role="member") for i in found])
    conv.updated_at = now()
    await session.commit()
    out = await conversation_out(session, conv)
    await request.app.state.hub.to_users([*existing, *found], {"type": "conversation", "conversation": out.model_dump(mode="json")})
    return out


@router.post("/conversations/{conversation_id}/leave")
async def leave(conversation_id: str, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    conv = await require_member(session, conversation_id, user.id)
    if conv.kind != "group":
        raise HTTPException(400, "only groups can be left")
    await session.execute(delete(Member).where(Member.conversation_id == conv.id, Member.user_id == user.id))
    await session.commit()
    return {"ok": True}


# ---- end-to-end encrypted relay -------------------------------------------

@router.post("/conversations/{conversation_id}/envelopes")
async def send_envelopes(conversation_id: str, body: EnvelopesIn, request: Request, user: User = Depends(current_user),
                         session: AsyncSession = Depends(get_session)):
    conv = await require_member(session, conversation_id, user.id)
    if conv.kind == "business":
        raise HTTPException(400, "business chats use /messages")
    sender = await session.get(Device, body.sender_device_id)
    if sender is None or sender.user_id != user.id or sender.revoked:
        raise HTTPException(403, "unknown sender device")
    devices = await _active_devices(session, await member_ids(session, conv.id))
    expected = {d.id for d in devices if d.id != sender.id}
    given = {e.recipient_device_id for e in body.envelopes}
    if given != expected or len(given) != len(body.envelopes):
        # Client's device list is stale: it must re-encrypt for exactly the current set.
        raise HTTPException(409, {"error": "device_mismatch", "devices": [DeviceOut.model_validate(d).model_dump() for d in devices]})
    owners = {d.id: d.user_id for d in devices}
    rows = []
    for e in body.envelopes:
        if len(str(e.payload)) > settings.max_envelope_bytes:
            raise HTTPException(413, "envelope too large")
        rows.append(Envelope(message_id=body.message_id, conversation_id=conv.id, sender_user_id=user.id,
                             sender_device_id=sender.id, recipient_device_id=e.recipient_device_id, payload=e.payload))
    session.add_all(rows)
    conv.updated_at = now()
    await session.commit()
    hub = request.app.state.hub
    for env in rows:
        await hub.to_device(owners[env.recipient_device_id], env.recipient_device_id,
                            {"type": "envelope", "envelope": EnvelopeOut.model_validate(env).model_dump(mode="json")})
    return {"message_id": body.message_id, "delivered_to": len(rows)}


@router.get("/devices/{device_id}/envelopes", response_model=list[EnvelopeOut])
async def pending_envelopes(device_id: str, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    dev = await session.get(Device, device_id)
    if dev is None or dev.user_id != user.id or dev.revoked:
        raise HTTPException(404, "device not found")
    rows = await session.scalars(select(Envelope).where(Envelope.recipient_device_id == device_id).order_by(Envelope.created_at).limit(500))
    return [EnvelopeOut.model_validate(r) for r in rows]


@router.post("/envelopes/ack")
async def ack(body: AckIn, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    dev = await session.get(Device, body.device_id)
    if dev is None or dev.user_id != user.id:
        raise HTTPException(404, "device not found")
    res = await session.execute(delete(Envelope).where(Envelope.recipient_device_id == dev.id, Envelope.id.in_(body.ids)))
    await session.commit()
    return {"deleted": res.rowcount}


# ---- business chats (processed by the business's agent) -------------------

@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageOut])
async def business_history(conversation_id: str, limit: int = 100, user: User = Depends(current_user),
                           session: AsyncSession = Depends(get_session)):
    conv = await require_member(session, conversation_id, user.id)
    if conv.kind != "business":
        raise HTTPException(400, "personal chats are end-to-end encrypted; history lives on devices")
    rows = list(await session.scalars(
        select(BusinessMessage).where(BusinessMessage.conversation_id == conv.id)
        .order_by(BusinessMessage.created_at.desc()).limit(min(limit, 500))
    ))
    return [MessageOut.model_validate(m) for m in reversed(rows)]


@router.post("/conversations/{conversation_id}/messages")
async def business_send(conversation_id: str, body: MessageIn, request: Request, user: User = Depends(current_user),
                        session: AsyncSession = Depends(get_session)):
    conv = await require_member(session, conversation_id, user.id)
    if conv.kind != "business":
        raise HTTPException(400, "personal chats must be sent as encrypted envelopes")
    msg, reply = await handle_business_message(request.app, session, conv, user, body.text)
    return {"message": MessageOut.model_validate(msg), "reply": None if reply is None else MessageOut.model_validate(reply)}
