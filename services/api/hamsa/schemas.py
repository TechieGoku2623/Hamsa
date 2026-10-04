from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class OtpRequestIn(BaseModel):
    phone: str


class OtpVerifyIn(BaseModel):
    phone: str
    code: str = Field(min_length=6, max_length=6)
    display_name: str = Field(default="", max_length=80)
    birth_year: int | None = Field(default=None, ge=1900, le=2100)


class GuestIn(BaseModel):
    display_name: str = Field(default="Guest", max_length=80)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    display_name: str
    phone: str | None = None
    is_guest: bool = False


class TokenOut(BaseModel):
    token: str
    user: UserOut


class ProfileIn(BaseModel):
    display_name: str = Field(min_length=1, max_length=80)


class DeviceIn(BaseModel):
    name: str = Field(default="", max_length=80)
    public_key: dict[str, Any]

    @field_validator("public_key")
    @classmethod
    def _jwk(cls, v: dict[str, Any]) -> dict[str, Any]:
        if v.get("kty") != "EC" or v.get("crv") != "P-256" or not v.get("x") or not v.get("y") or "d" in v:
            raise ValueError("public_key must be a public P-256 JWK")
        return {k: v[k] for k in ("kty", "crv", "x", "y")}


class DeviceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    user_id: str
    name: str
    public_key: dict[str, Any]


class ConversationCreate(BaseModel):
    kind: Literal["direct", "group"]
    peer_user_id: str | None = None
    title: str = Field(default="", max_length=120)
    member_user_ids: list[str] = Field(default_factory=list)


class MemberOut(BaseModel):
    user_id: str
    display_name: str
    phone: str | None
    role: str


class BusinessBrief(BaseModel):
    id: str
    handle: str
    name: str


class ConversationOut(BaseModel):
    id: str
    kind: str
    title: str
    members: list[MemberOut]
    business: BusinessBrief | None = None
    ai_enabled: bool
    needs_human: bool
    updated_at: datetime
    last_text: str | None = None


class EnvelopeItem(BaseModel):
    recipient_device_id: str
    payload: dict[str, Any]


class EnvelopesIn(BaseModel):
    message_id: str = Field(min_length=8, max_length=64)
    sender_device_id: str
    envelopes: list[EnvelopeItem] = Field(min_length=1, max_length=2048)


class EnvelopeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    message_id: str
    conversation_id: str
    sender_user_id: str
    sender_device_id: str
    recipient_device_id: str
    payload: dict[str, Any]
    created_at: datetime


class AckIn(BaseModel):
    device_id: str
    ids: list[str] = Field(max_length=1000)


class MembersAddIn(BaseModel):
    user_ids: list[str] = Field(min_length=1, max_length=256)


class ContactsLookupIn(BaseModel):
    phones: list[str] = Field(max_length=500)


class FaqEntry(BaseModel):
    q: str = Field(max_length=300)
    a: str = Field(max_length=1000)


class BusinessIn(BaseModel):
    handle: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{2,39}$")
    name: str = Field(min_length=2, max_length=120)
    category: str = Field(default="kirana", max_length=40)
    vpa: str = Field(default="", max_length=80)
    address: str = Field(default="", max_length=500)
    hours: str = Field(default="", max_length=120)
    delivery_note: str = Field(default="", max_length=200)
    faq: list[FaqEntry] = Field(default_factory=list, max_length=50)


class BusinessPatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    category: str | None = None
    vpa: str | None = None
    address: str | None = None
    hours: str | None = None
    delivery_note: str | None = None
    faq: list[FaqEntry] | None = None


class BusinessOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    handle: str
    name: str
    category: str
    vpa: str
    address: str
    hours: str
    delivery_note: str
    faq: list[dict[str, str]]


class ItemIn(BaseModel):
    sku: str = Field(pattern=r"^[A-Za-z0-9_-]{1,40}$")
    name: str = Field(min_length=1, max_length=120)
    aliases: list[str] = Field(default_factory=list, max_length=20)
    price_paise: int = Field(gt=0, le=10_000_000)
    unit: Literal["kg", "g", "l", "pc", "pkt", "dozen"] = "pc"
    stock: int | None = Field(default=None, ge=0)
    active: bool = True


class ItemPatch(BaseModel):
    name: str | None = None
    aliases: list[str] | None = None
    price_paise: int | None = Field(default=None, gt=0, le=10_000_000)
    unit: Literal["kg", "g", "l", "pc", "pkt", "dozen"] | None = None
    stock: int | None = Field(default=None, ge=0)
    active: bool | None = None


class ItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    sku: str
    name: str
    aliases: list[str]
    price_paise: int
    unit: str
    stock: int | None
    active: bool


class PublicBusinessOut(BaseModel):
    business: BusinessOut
    items: list[ItemOut]


class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    conversation_id: str
    sender_type: str
    sender_user_id: str | None
    text: str
    meta: dict[str, Any]
    created_at: datetime


class AiToggleIn(BaseModel):
    enabled: bool


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    code: str
    business_id: str
    conversation_id: str
    customer_user_id: str
    items: list[dict[str, Any]]
    total_paise: int
    status: str
    upi_link: str
    created_at: datetime
    updated_at: datetime


class OrderStatusIn(BaseModel):
    status: Literal["paid", "preparing", "ready", "delivered", "cancelled"]
