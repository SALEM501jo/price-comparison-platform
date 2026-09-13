"""
How long an emailed link stays usable -- per purpose.

WHY RESET LINKS ARE SHORT. A confirmation link can only confirm an address. A
password-reset link sets the account's password, and for the admin account
that is the whole platform. The window matters more than it looks, because the
link does not live only in the recipient's inbox: the mail provider rewrites
every link for click tracking and cannot be told not to on transactional mail
below its Enterprise plan, so a copy exists in the provider's systems from the
moment the email is sent. Both used to share one 24-hour lifetime.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.config import get_settings
from app.models.email_token import EmailToken
from app.models.user import User
from app.services import password_reset, verification

settings = get_settings()


def _aware(dt):
    """SQLite hands datetimes back without a timezone; they were written as UTC."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


@pytest.fixture
def user(db_session):
    u = User(email="someone@example.com", password_hash="x")
    db_session.add(u)
    db_session.commit()
    return u


@pytest.fixture
def captured(monkeypatch):
    sent = []
    monkeypatch.setattr(password_reset.email_service, "send", lambda m: sent.append(m) or True)
    monkeypatch.setattr(verification.email_service, "send", lambda m: sent.append(m) or True)
    return sent


def _token(db_session, user, purpose):
    return (
        db_session.query(EmailToken)
        .filter(EmailToken.user_id == user.id, EmailToken.purpose == purpose)
        .order_by(EmailToken.id.desc())
        .first()
    )


class TestResetLinksAreShortLived:
    def test_a_reset_link_expires_within_the_hour(self, db_session, user, captured):
        before = datetime.now(timezone.utc)
        password_reset.send_reset(db_session, user)

        expires = _aware(_token(db_session, user, password_reset.PURPOSE_RESET).expires_at)
        lifetime = expires - before
        # The configured hour, with a little room for the time the call took --
        # and nowhere near the 24 hours this used to share with confirmation.
        assert timedelta(minutes=59) <= lifetime <= timedelta(minutes=61)

    def test_a_confirmation_link_keeps_its_longer_lifetime(self, db_session, user, captured):
        """Shortening resets must not quietly shorten confirmation too."""
        before = datetime.now(timezone.utc)
        verification.send_verification(db_session, user)

        expires = _aware(_token(db_session, user, verification.PURPOSE_VERIFY).expires_at)
        hours = settings.email_token_ttl_hours
        assert timedelta(hours=hours) - timedelta(minutes=1) <= expires - before
        assert expires - before <= timedelta(hours=hours) + timedelta(minutes=1)

    def test_the_email_states_the_real_lifetime(self, db_session, user, captured):
        """An email promising 24 hours for a link that dies in 1 would be a lie."""
        password_reset.send_reset(db_session, user)
        (message,) = captured
        assert "expires in 1 hour" in message.text
        assert "expires in 1 hour" in message.html
        assert "24 hours" not in message.text

    def test_the_email_does_not_promise_what_link_tracking_breaks(
        self, db_session, user, captured
    ):
        """
        It used to say nobody could use the link without opening it from the
        inbox. With the provider rewriting links, a copy exists outside the
        inbox too -- so the one reassurance left standing is the expiry.
        """
        password_reset.send_reset(db_session, user)
        (message,) = captured
        assert "without opening it from your inbox" not in message.text


class TestLifetimeWording:
    @pytest.mark.parametrize(
        "minutes, words",
        [(60, "1 hour"), (120, "2 hours"), (30, "30 minutes"), (90, "90 minutes")],
    )
    def test_it_reads_the_way_a_person_would_say_it(self, minutes, words):
        assert password_reset._describe_minutes(minutes) == words
