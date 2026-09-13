"""
What the platform's own emails may contain.

WHY THIS FILE EXISTS. Once the site sends real mail, every message leaves as
noreply@ahsanse3r.com, DKIM-signed and passing DMARC -- the most trustworthy
envelope a message can have. That is exactly what makes injected content
dangerous: text that is not ours reaching an email's HTML becomes a phishing
email delivered BY the platform.

The website is not the risk here. React escapes text itself. The emails build
HTML by string interpolation, and two of the strings are not ours: product
names come from scraped retailer pages and from merchant listings (a
merchant's listing name becomes the canonical name when nobody else sells the
product), and store names are typed by merchants. Neither schema rejects
markup, so escaping at output is the control.
"""

from email.message import EmailMessage
from types import SimpleNamespace

import pytest

from app.services import notifications
from app.services import verification

HOSTILE_NAME = '<a href="https://evil.example/login">Your account is locked - confirm now</a>'
HOSTILE_STORE = '<img src="https://evil.example/pixel.gif">Trusted Store'


def _alert(name=HOSTILE_NAME, store=HOSTILE_STORE):
    return notifications._message(
        SimpleNamespace(email="shopper@example.com"),
        SimpleNamespace(id=7, canonical_name=name),
        target="700.000",
        current="649.000",
        store=store,
    )


class TestPriceAlertHtmlIsEscaped:
    def test_a_hostile_product_name_cannot_add_a_link(self):
        html = _alert().html
        assert 'href="https://evil.example' not in html
        # Rendered as visible text instead, so the recipient can still see
        # what the product is called -- nothing is silently dropped.
        assert "&lt;a href=" in html

    def test_the_only_link_in_the_email_is_ours(self):
        html = _alert().html
        assert html.count("<a ") == 1
        # Against the configured site address rather than a hard-coded scheme:
        # the test environment runs on http://localhost, production on https.
        own = notifications.settings.app_base_url.rstrip("/")
        assert f'<a href="{own}/product/7">' in html

    def test_a_hostile_store_name_cannot_add_an_image(self):
        """An image is a tracking pixel: it tells the sender who opened it."""
        html = _alert().html
        assert "<img" not in html
        assert "&lt;img" in html

    def test_an_ordinary_name_is_unchanged(self):
        """Escaping must not mangle the names people actually use."""
        html = _alert(name="Samsung Galaxy S24 128GB", store="SmartBuy").html
        assert "Samsung Galaxy S24 128GB" in html
        assert "SmartBuy" in html

    def test_ampersands_in_real_names_survive_as_text(self):
        """"4GB & 64GB" is a real listing name here, not an attack."""
        html = _alert(name="Honor X5c 4GB & 64GB", store=None).html
        assert "4GB &amp; 64GB" in html

    def test_the_plain_text_part_shows_the_name_as_written(self):
        """
        Text parts are displayed as text by every client, so escaping them
        would only put visible "&lt;" noise in front of the recipient.
        """
        assert HOSTILE_NAME in _alert().text


class TestHeadersCannotBeInjected:
    def test_the_email_library_refuses_a_newline_in_the_subject(self):
        """
        The price-alert subject interpolates the product name. The escaping
        above deliberately does not touch it, relying on EmailMessage's
        default policy to refuse the CR/LF that header injection needs --
        e.g. adding a Bcc to send the message somewhere else. This pins that
        assumption, so a future change to how messages are built cannot
        quietly remove it.
        """
        message = EmailMessage()
        with pytest.raises(ValueError):
            message["Subject"] = "Price drop: phone\r\nBcc: attacker@evil.example"


class TestTheBrandIsCurrent:
    def test_the_confirmation_email_does_not_use_the_old_name(
        self, db_session, monkeypatch
    ):
        """
        The first email a new account receives said "PriceCompare" -- the
        working name -- while the site and the sender say Ahsan Se3r. A
        confirmation from an unfamiliar name reads as phishing, and a deleted
        or spam-reported confirmation leaves the account unconfirmed.
        """
        from app.models.user import User

        user = User(email="new@example.com", password_hash="x")
        db_session.add(user)
        db_session.commit()

        sent = []
        monkeypatch.setattr(verification.email_service, "send", lambda m: sent.append(m) or True)
        verification.send_verification(db_session, user)

        (message,) = sent
        assert "Ahsan Se3r" in message.subject
        for part in (message.subject, message.text, message.html):
            assert "PriceCompare" not in part
