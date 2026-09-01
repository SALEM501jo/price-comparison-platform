"""
Turning a file a stranger uploaded into an image this site is willing to serve.

THE RULE: nothing a merchant sends is ever stored as sent. Every upload is
decoded to pixels and re-encoded from those pixels, and only the result is
kept. That single decision does most of the security work here:

  - A POLYGLOT FILE -- a valid JPEG that is also a valid HTML page, or that
    carries a PHP payload in a comment segment -- survives only if the bytes
    survive. Re-encoding writes a new file from a pixel buffer, so whatever
    was hidden in the container is simply not copied forward.
  - EXIF DIES WITH IT. Shop photos are taken on phones, and phone photos carry
    GPS coordinates, the device serial, and a timestamp. Jordan's PDPL covers
    exactly that, and this project stores no personal data anywhere else --
    it would be absurd to start by accident, in a field nobody looks at.
  - THE DECLARED TYPE IS NEVER BELIEVED. Content-Type and the filename come
    from the client. What the file *is* is decided by decoding it.

WHAT IS DELIBERATELY NOT HERE: an SVG path. SVG is a script container -- it
can carry <script>, and it executes on the origin that serves it. There is no
sanitiser worth trusting for it, so it is not decoded, not converted, and not
accepted. Pillow would refuse it anyway; the explicit rejection exists so the
error a merchant sees names the reason.
"""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass

from PIL import Image, ImageOps, UnidentifiedImageError

# --- Limits ----------------------------------------------------------------

# The largest upload accepted, before decoding. A phone photo is 2-5MB, so
# this is generous for the real case and still bounds what one request can
# make the process hold.
MAX_UPLOAD_BYTES = 8 * 1024 * 1024

# The largest DECODED image accepted, in pixels. This is the one that matters:
# a 2MB PNG can decompress to 30000x30000, which is 3.6GB of RGBA in memory --
# a decompression bomb that needs no exploit, just a file. Pillow's own
# default only warns; this refuses.
#
# 50 megapixels is well beyond any phone camera (a 48MP sensor writes 8000x6000
# = 48MP) and far below anything that threatens the machine.
MAX_PIXELS = 50_000_000

# What gets stored. A product photo is displayed at a few hundred pixels on
# the widest layout, so 1400 on the long edge is already generous for a
# retina display, and it keeps a stored photo around 100-200KB.
MAX_DIMENSION = 1400

# WebP at this quality is visually indistinguishable from the source at
# display size and roughly half the bytes of equivalent JPEG. Bytes matter
# more than usual here because these live in Postgres, where the free tier is
# the budget -- see docs on ListingPhoto.
WEBP_QUALITY = 82

STORED_CONTENT_TYPE = "image/webp"

# Formats Pillow will be asked to decode. An allowlist, not a blocklist: the
# question "is this one of the four formats a shop photo is actually in" has
# a stable answer, while "is this one of the dozens of formats Pillow can be
# talked into opening" does not. PIL can open ICO, FLI, MSP and more, several
# of which have had parser CVEs and none of which a merchant needs.
#
# HEIC IS NOT LISTED, and that is not an oversight. Pillow cannot decode it
# without the pillow-heif plugin, so naming it here would promise a format
# every upload would then fail on. It is also rarely the real case: iOS
# transcodes HEIC to JPEG when a photo goes through a web file input, which is
# how a shop owner on an iPhone will actually send one. If a real merchant
# ever hits this, the fix is the plugin plus a test, not a wider allowlist.
ALLOWED_FORMATS = frozenset({"JPEG", "PNG", "WEBP"})


class ImageRejected(ValueError):
    """
    The upload is not something we will serve.

    Carries a machine-readable `code` as well as a message: the client turns
    the code into a sentence in the shopper's language, the same way match
    differences work. A raw English string from the server would be the exact
    bug that was just fixed elsewhere.
    """

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ProcessedImage:
    """A photo that is safe to store, with what the serving layer needs."""

    data: bytes
    content_type: str
    width: int
    height: int
    checksum: str

    @property
    def byte_size(self) -> int:
        return len(self.data)


def _looks_like_svg(raw: bytes) -> bool:
    """
    SVG sniffed before decoding, so the refusal can say why.

    Checked on the leading bytes only, and tolerant of an XML declaration or a
    byte-order mark in front of the tag, because that is how real files are
    written.
    """
    head = raw[:1024].lstrip().lstrip(b"\xef\xbb\xbf").lower()
    return head.startswith(b"<?xml") and b"<svg" in head[:1024] or head.startswith(b"<svg")


def process_upload(raw: bytes) -> ProcessedImage:
    """
    Validate, normalise and re-encode an uploaded image.

    Raises ImageRejected with a code the UI can translate. Every failure path
    is a rejection rather than a fallback: storing something we could not
    fully parse would defeat the point of parsing it.
    """
    if not raw:
        raise ImageRejected("empty", "The file is empty.")

    if len(raw) > MAX_UPLOAD_BYTES:
        raise ImageRejected(
            "too_large",
            f"The file is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)}MB.",
        )

    if _looks_like_svg(raw):
        raise ImageRejected(
            "svg",
            "SVG files are not accepted. Upload a photo, not a drawing file.",
        )

    try:
        # Opened twice on purpose. verify() checks structural integrity but
        # leaves the file object unusable for reading pixels, which is a
        # documented Pillow quirk -- so the first open validates and the
        # second one does the work.
        with Image.open(io.BytesIO(raw)) as probe:
            image_format = probe.format
            probe.verify()
    except Image.DecompressionBombError:
        # Pillow's own ceiling, which is higher than ours and is reached while
        # the header is being read -- before the explicit MAX_PIXELS check
        # below ever runs. Same rejection, so a bomb gets the same answer
        # whichever limit catches it first.
        raise ImageRejected(
            "too_many_pixels", "The image's resolution is too high."
        ) from None
    except UnidentifiedImageError:
        raise ImageRejected(
            "not_an_image", "That file is not an image we can read."
        ) from None
    except Exception:
        # A truncated or corrupt file. Deliberately not distinguished from the
        # above for the merchant: both mean "send a different file".
        raise ImageRejected(
            "not_an_image", "That file is not an image we can read."
        ) from None

    if image_format not in ALLOWED_FORMATS:
        raise ImageRejected(
            "unsupported_format",
            "Use a JPEG, PNG or WebP photo.",
        )

    try:
        with Image.open(io.BytesIO(raw)) as image:
            width, height = image.size
            if width * height > MAX_PIXELS:
                raise ImageRejected(
                    "too_many_pixels",
                    "The image's resolution is too high.",
                )

            # Apply the EXIF orientation BEFORE the metadata is dropped.
            # Phone cameras record a sideways sensor and set a rotation flag
            # rather than rotating the pixels; strip the flag without acting
            # on it and every photo taken in portrait arrives on its side.
            # This is the one piece of EXIF that has to be honoured in order
            # to be safely thrown away.
            image = ImageOps.exif_transpose(image)

            # Flatten to RGB. Re-encoding an RGBA or palette image straight to
            # WebP keeps an alpha channel that product photos never need, and
            # a transparent background renders black on a dark-mode card.
            if image.mode not in ("RGB", "L"):
                background = Image.new("RGB", image.size, (255, 255, 255))
                converted = image.convert("RGBA")
                background.paste(converted, mask=converted.split()[-1])
                image = background
            elif image.mode == "L":
                image = image.convert("RGB")

            # Downscale only. Enlarging a small photo to hit a target size
            # invents detail and makes the result look worse than the original.
            image.thumbnail((MAX_DIMENSION, MAX_DIMENSION), Image.LANCZOS)

            out = io.BytesIO()
            # No exif= and no icc_profile= argument: what is not passed is not
            # written. This is where the metadata actually goes away.
            image.save(out, format="WEBP", quality=WEBP_QUALITY, method=4)
            data = out.getvalue()
            final_width, final_height = image.size
    except ImageRejected:
        raise
    except Image.DecompressionBombError:
        raise ImageRejected(
            "too_many_pixels", "The image's resolution is too high."
        ) from None
    except Exception:
        raise ImageRejected(
            "not_an_image", "That file is not an image we can read."
        ) from None

    return ProcessedImage(
        data=data,
        content_type=STORED_CONTENT_TYPE,
        width=final_width,
        height=final_height,
        # Content hash, used as the ETag. Two merchants uploading the same
        # press photo produce the same string, and a browser that already has
        # it revalidates with a 304 instead of pulling the bytes again --
        # which matters more than usual when the bytes come from the database.
        checksum=hashlib.sha256(data).hexdigest(),
    )
