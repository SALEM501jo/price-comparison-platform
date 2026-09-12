from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator
import re


def _normalise_email(v: str) -> str:
    """
    One spelling per mailbox, decided at the edge.

    THE SPLIT THIS CLOSES: registration and login looked accounts up with
    `User.email == body.email`, which is case-SENSITIVE, while social sign-in
    resolved them with `func.lower(User.email) == email`, which is not. One
    real mailbox could therefore hold two rows differing only in case, and
    which one a provider linked to was then arbitrary.

    That is not merely untidy -- it defeats the account-takeover defence in
    services/oauth/accounts.py. Signing in with Google clears the password on
    the row it links to; the OTHER row keeps its password, so an attacker who
    registered Victim@example.com keeps a working credential on the victim's
    mailbox after the very event that was supposed to evict them.

    Normalising on the way IN rather than lowercasing at each query keeps the
    unique index doing the work, and means a lookup cannot be written
    case-sensitively by accident later.

    Domains are case-insensitive by specification; local parts technically are
    not, but no mail provider this platform's users have treats them
    otherwise, and an address that only differs by case is a support ticket,
    not a feature.
    """
    return v.strip().lower()


class EmailField(BaseModel):
    """
    Mixin for every request body that names an account by address.

    check_fields=False because the mixin itself declares no `email`; each
    subclass does. Without it pydantic refuses to build the model at import
    time rather than at request time, which is at least a loud failure.
    """

    @field_validator("email", check_fields=False)
    @classmethod
    def normalise_email(cls, v: str) -> str:
        return _normalise_email(v)


class RegisterRequest(EmailField):
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


class LoginRequest(EmailField):
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
    # Without it the account page can answer "is this address confirmed" but
    # not "is this the account I opened in March", which is the question
    # somebody with two addresses is actually asking before deleting one of
    # them. Optional because the column carries a server default rather than
    # a NOT NULL, so a row written outside the ORM can arrive without one.
    created_at: Optional[datetime] = None

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


class ResendVerificationRequest(EmailField):
    email: EmailStr


class ForgotPasswordRequest(EmailField):
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


class DeleteAccountRequest(BaseModel):
    """
    Confirmation for an irreversible action: the account's own address, typed.

    NOT the password, which looks like the stronger check until you notice who
    cannot use it. An account created through Google has no password at all --
    `password_hash` is nullable for exactly those users -- so a password
    confirmation would be unusable by the people most likely to be deleting a
    social login they never meant to create. A short-lived access token is
    already required, and 15 minutes of it means possession implies a recent
    login; this field is here to stop a mis-click, not to authenticate.

    A plain string rather than EmailStr: this is text the user must reproduce,
    not an address we are going to send anything to, and parsing it as an
    address would answer the same mistake -- typing the wrong thing -- with a
    422 sometimes and a 400 the rest of the time.
    """

    email: str
