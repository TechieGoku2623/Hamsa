from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import current_user, decode_token, get_session, hash_otp, issue_token, new_otp, normalize_phone
from ..config import settings
from ..models import BusinessMessage, Conversation, Member, OtpRequest, Order, User
from ..schemas import ContactsLookupIn, GuestIn, OtpRequestIn, OtpVerifyIn, ProfileIn, TokenOut, UserOut

log = logging.getLogger(__name__)
router = APIRouter(tags=["auth"])

MIN_AGE = 18


@router.post("/auth/otp/request")
async def otp_request(body: OtpRequestIn, session: AsyncSession = Depends(get_session)):
    phone = normalize_phone(body.phone)
    code = new_otp()
    row = await session.get(OtpRequest, phone)
    expires = datetime.now(timezone.utc) + timedelta(seconds=settings.otp_ttl_seconds)
    if row is None:
        session.add(OtpRequest(phone=phone, code_hash=hash_otp(phone, code), expires_at=expires, attempts=0))
    else:
        row.code_hash, row.expires_at, row.attempts = hash_otp(phone, code), expires, 0
    await session.commit()
    out = {"phone": phone, "expires_in": settings.otp_ttl_seconds}
    if settings.dev_otp:
        out["dev_code"] = code
    else:  # pragma: no cover - needs a DLT-registered SMS provider
        log.info("OTP for %s would be sent via SMS provider", phone[:-4] + "****")
    return out


@router.post("/auth/otp/verify", response_model=TokenOut)
async def otp_verify(body: OtpVerifyIn, request: Request, session: AsyncSession = Depends(get_session)):
    phone = normalize_phone(body.phone)
    row = await session.get(OtpRequest, phone)
    if row is None or row.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(400, "code expired; request a new one")
    if row.attempts >= settings.otp_max_attempts:
        raise HTTPException(429, "too many attempts; request a new code")
    if row.code_hash != hash_otp(phone, body.code):
        row.attempts += 1
        await session.commit()
        raise HTTPException(400, "wrong code")
    await session.delete(row)

    user = await session.scalar(select(User).where(User.phone == phone))
    if user is None:
        if body.birth_year is not None and datetime.now().year - body.birth_year < MIN_AGE:
            # DPDP Rules: under-18s need verifiable parental consent, which this build does not implement yet.
            await session.commit()
            raise HTTPException(403, "parental consent required for users under 18")
        user = User(phone=phone, display_name=body.display_name or phone[-4:], birth_year=body.birth_year)
        session.add(user)
        await session.flush()

    guest = await _guest_from_header(request, session)
    if guest is not None and guest.id != user.id:
        await _merge_guest(session, guest, user)
    await session.commit()
    return TokenOut(token=issue_token(user.id), user=UserOut.model_validate(user))


@router.post("/auth/guest", response_model=TokenOut)
async def guest(body: GuestIn, session: AsyncSession = Depends(get_session)):
    user = User(display_name=body.display_name or "Guest", is_guest=True)
    session.add(user)
    await session.commit()
    return TokenOut(token=issue_token(user.id), user=UserOut.model_validate(user))


async def _guest_from_header(request: Request, session: AsyncSession) -> User | None:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        return None
    try:
        uid = decode_token(header[7:])
    except HTTPException:
        return None
    user = await session.get(User, uid)
    return user if user is not None and user.is_guest else None


async def _merge_guest(session: AsyncSession, guest: User, user: User) -> None:
    """A guest who chatted with a business via link and then registered keeps their chats and orders."""
    existing = set(await session.scalars(select(Member.conversation_id).where(Member.user_id == user.id)))
    for m in list(await session.scalars(select(Member).where(Member.user_id == guest.id))):
        if m.conversation_id in existing:
            await session.delete(m)
        else:
            m.user_id = user.id
    await session.execute(update(Order).where(Order.customer_user_id == guest.id).values(customer_user_id=user.id))
    await session.execute(update(BusinessMessage).where(BusinessMessage.sender_user_id == guest.id).values(sender_user_id=user.id))
    for conv in list(await session.scalars(select(Conversation).where(Conversation.created_by == guest.id))):
        conv.created_by = user.id
        if conv.kind == "business" and conv.direct_key and conv.business_id:
            new_key = f"biz:{conv.business_id}:{user.id}"
            if await session.scalar(select(Conversation.id).where(Conversation.direct_key == new_key)) is None:
                conv.direct_key = new_key
    await session.flush()
    await session.delete(guest)


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(current_user)):
    return UserOut.model_validate(user)


@router.patch("/me", response_model=UserOut)
async def update_me(body: ProfileIn, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    user.display_name = body.display_name
    await session.commit()
    return UserOut.model_validate(user)


@router.post("/contacts/lookup", response_model=list[UserOut])
async def contacts_lookup(body: ContactsLookupIn, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    if user.is_guest:
        raise HTTPException(403, "register with a phone number to find contacts")
    phones = set()
    for p in body.phones:
        try:
            phones.add(normalize_phone(p))
        except HTTPException:
            continue
    if not phones:
        return []
    rows = await session.scalars(select(User).where(User.phone.in_(phones), User.id != user.id))
    return [UserOut.model_validate(u) for u in rows]
