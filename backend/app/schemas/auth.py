from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator
import re


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str

    # Which side of the platform this account is for. A Literal, NOT the
    # UserRole enum: this value comes from an anonymous request body, and
    # accepting a role name directly would let anyone register as an admin.
    # These two are the only self-selectable options, and the router maps them
    # rather than passing them through.
    account_type: Literal["buyer", "merchant"] = "buyer"

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if len(v) > 128:
            raise ValueError("Password too long")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain an uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain a lowercase letter")
        if not re.search(r"[0-9]", v):
            raise ValueError("Password must contain a number")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

    # NOTE: the refresh token is deliberately absent. It is delivered as an
    # httpOnly cookie instead, so page JavaScript never holds a copy and an
    # XSS payload has nothing to exfiltrate. See app/security/cookies.py.


class UserResponse(BaseModel):
    id: int
    email: str
    role: str
    # Exposed so the UI can prompt an unverified user. A timestamp rather than
    # a flag, so "when" is answerable too.
    email_verified_at: Optional[datetime] = None

    @property
    def is_verified(self) -> bool:
        return self.email_verified_at is not None

    model_config = ConfigDict(from_attributes=True)

class RefreshRequest(BaseModel):
    """Fallback body for clients without a cookie jar (mobile, CLI).

    Browsers send the httpOnly cookie instead and leave this empty.

    SECURITY: never a query parameter -- query strings land in access logs,
    browser history and Referer headers, and this is a multi-day credential.
    """
    refresh_token: str | None = None


class VerifyEmailRequest(BaseModel):
    token: str


class ResendVerificationRequest(BaseModel):
    email: EmailStr

class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    # Same policy as registration, reused rather than restated: a reset that
    # accepted a weaker password than signup would be the easiest way past the
    # policy, and nobody would notice.
    password: str

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        return RegisterRequest.validate_password(v)
