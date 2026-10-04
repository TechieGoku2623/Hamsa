from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field


def _bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    database_url: str = field(default_factory=lambda: os.environ.get("HAMSA_DATABASE_URL", "sqlite+aiosqlite:///./hamsa.db"))
    jwt_secret: str = field(default_factory=lambda: os.environ.get("HAMSA_JWT_SECRET") or secrets.token_urlsafe(32))
    token_ttl_days: int = field(default_factory=lambda: int(os.environ.get("HAMSA_TOKEN_TTL_DAYS", "30")))
    # Dev mode returns the OTP in the API response instead of sending an SMS.
    dev_otp: bool = field(default_factory=lambda: _bool("HAMSA_DEV_OTP", True))
    otp_ttl_seconds: int = 300
    otp_max_attempts: int = 5
    cors_origins: tuple[str, ...] = field(
        default_factory=lambda: tuple(o for o in os.environ.get("HAMSA_CORS_ORIGINS", "http://localhost:5173").split(",") if o)
    )
    # OpenAI-compatible endpoint (vLLM / SGLang serving Hamsa-LM). Empty = rules-only agent.
    llm_base_url: str = field(default_factory=lambda: os.environ.get("HAMSA_LLM_BASE_URL", ""))
    llm_model: str = field(default_factory=lambda: os.environ.get("HAMSA_LLM_MODEL", "sarvamai/sarvam-30b"))
    llm_api_key: str = field(default_factory=lambda: os.environ.get("HAMSA_LLM_API_KEY", "EMPTY"))
    llm_timeout_s: float = 20.0
    max_envelope_bytes: int = 64 * 1024
    max_group_members: int = 256


settings = Settings()
