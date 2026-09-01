"""
Request and response models for merchant self-service.

EVERYTHING HERE IS UNTRUSTED INPUT. The scraped side of the platform reads
prices from a feed we chose to trust; this side accepts them from whoever
signed up ten seconds ago. The validators below are the only thing between a
typo -- or a competitor -- and a wrong number on a comparison page, which is
the one thing a price comparison site must never show.
"""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Jordanian numbers, written the several ways people actually write them:
# 0791234567, +962791234567, 00962 79 123 4567, with spaces or dashes.
# Stored normalised so two spellings of one number are one number.
_PHONE_CLEAN = re.compile(r"[\s\-()]")
_PHONE_SHAPE = re.compile(r"^(?:\+962|00962|0)?7[789]\d{7}$")

# Only a facebook.com page URL. Accepting any URL would turn a store profile
# into an open redirect advertised to every shopper on the product page.
_FACEBOOK_URL = re.compile(
    r"^https://(?:www\.|m\.|web\.)?facebook\.com/[A-Za-z0-9._\-/%]+/?$"
)

# Same reasoning, same shape. Instagram handles are a single path segment, so
# this is tighter than the Facebook pattern: no slashes inside the name.
_INSTAGRAM_URL = re.compile(
    r"^https://(?:www\.)?instagram\.com/[A-Za-z0-9._]+/?$"
)


def _normalise_phone(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    cleaned = _PHONE_CLEAN.sub("", value.strip())
    if not cleaned:
        return None
    if not _PHONE_SHAPE.match(cleaned):
        raise ValueError(
            "Enter a Jordanian mobile number, e.g. 0791234567 or +962791234567"
        )
    # Canonical form: local 07XXXXXXXX. One number, one spelling.
    digits = cleaned.lstrip("+")
    if digits.startswith("00962"):
        digits = digits[5:]
    elif digits.startswith("962"):
        digits = digits[3:]
    return digits if digits.startswith("0") else "0" + digits


class StoreContact(BaseModel):
    """The contact details a shopper is given instead of a checkout."""

    phone: Optional[str] = Field(None, max_length=32)
    whatsapp: Optional[str] = Field(None, max_length=32)
    facebook_url: Optional[str] = Field(None, max_length=500)
    # Optional, like the others. Many of these shops have an Instagram and no
    # Facebook page at all.
    instagram_url: Optional[str] = Field(None, max_length=500)

    @field_validator("phone", "whatsapp")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        return _normalise_phone(v)

    @field_validator("facebook_url")
    @classmethod
    def validate_facebook(cls, v: Optional[str]) -> Optional[str]:
        if v is None or not v.strip():
            return None
        v = v.strip()
        if not _FACEBOOK_URL.match(v):
            raise ValueError(
                "Enter a full Facebook page URL, e.g. https://facebook.com/yourshop"
            )
        return v

    @field_validator("instagram_url")
    @classmethod
    def validate_instagram(cls, v: Optional[str]) -> Optional[str]:
        if v is None or not v.strip():
            return None
        v = v.strip()
        if not _INSTAGRAM_URL.match(v):
            raise ValueError(
                "Enter a full Instagram profile URL, "
                "e.g. https://instagram.com/yourshop"
            )
        return v


class StoreRegisterRequest(StoreContact):
    """Claim a store. The name is what shoppers will see next to a price."""

    name: str = Field(..., min_length=2, max_length=100)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = " ".join(v.split())
        if not v:
            raise ValueError("Store name is required")
        return v


class StoreUpdateRequest(StoreContact):
    """Edit contact details. The name is fixed once claimed -- see the router."""


class StoreResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    phone: Optional[str] = None
    whatsapp: Optional[str] = None
    facebook_url: Optional[str] = None
    instagram_url: Optional[str] = None
    is_verified: bool
    verified_at: Optional[datetime] = None
    listing_count: int = 0


class ConditionDetails(BaseModel):
    """
    What state the unit is in, and everything that follows from that.

    A second-hand phone is not a cheaper new phone -- it is a different object
    whose worth depends on wear the listing has to disclose. A shopper choosing
    between two sealed handsets needs a price; one considering a used handset
    needs battery health and whether the screen is cracked, or the listing is
    not an offer, it is a guess.

    So the used fields are REQUIRED when the condition is second-hand. Leaving
    them optional produced listings that were technically valid and useless,
    and a shopper cannot tell "no damage" from "the seller did not say".
    """

    condition: Literal["new", "used", "refurbished"] = "new"

    # 1-100. Null only when the unit is new.
    battery_health: Optional[int] = Field(None, ge=1, le=100)
    has_damage: Optional[bool] = None
    damage_notes: Optional[str] = Field(None, max_length=500)
    warranty_months: Optional[int] = Field(None, ge=0, le=60)
    listing_notes: Optional[str] = Field(None, max_length=1000)

    @field_validator("damage_notes", "listing_notes")
    @classmethod
    def tidy_text(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = " ".join(v.split())
        return v or None

    @model_validator(mode="after")
    def check_second_hand_disclosure(self) -> "ConditionDetails":
        second_hand = self.condition != "new"

        if second_hand:
            if self.battery_health is None:
                raise ValueError(
                    "Battery health is required for a used or refurbished phone"
                )
            if self.has_damage is None:
                raise ValueError(
                    "Say whether the phone has any damage, even if it has none"
                )
            if self.has_damage and not self.damage_notes:
                raise ValueError("Describe the damage so a buyer knows what to expect")
        else:
            # Silently ignoring these would let a listing claim to be sealed
            # while carrying 82% battery, and a shopper would see both.
            if self.battery_health is not None:
                raise ValueError("A new phone cannot have a battery health figure")
            if self.has_damage:
                raise ValueError("A new phone cannot be listed as damaged")

        if not self.has_damage:
            self.damage_notes = None

        return self


class ListingCreate(ConditionDetails):
    """
    One product this shop sells, at one price.

    `name` is free text on purpose. The merchant types the product the way
    they say it, exactly as a scraped listing arrives in the store's own
    words, and the same parser resolves it to a canonical product. A dropdown
    of our catalogue would be easier to validate and would stop a merchant
    listing anything we have not already scraped -- which is most of what
    these shops sell.
    """

    name: str = Field(..., min_length=3, max_length=255)

    # Decimal, never float. Money in this app is Numeric(10,3) because JOD has
    # three decimals and these values are summed and then compared to decide
    # which store is cheapest.
    price: Decimal = Field(..., gt=0, le=Decimal("1000000"), decimal_places=3)
    delivery_cost: Decimal = Field(
        Decimal("0"), ge=0, le=Decimal("1000"), decimal_places=3
    )
    availability: bool = True

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = " ".join(v.split())
        if len(v) < 3:
            raise ValueError("Product name is too short")
        return v


class ListingUpdate(BaseModel):
    """
    Everything optional: the common edit is a price change alone.

    Condition is NOT editable. A listing's condition is part of what it is --
    changing it would move the unit between two comparison groups while
    keeping its price history, and a "used" row that silently became "new"
    is precisely the edit an unscrupulous seller would want. Relisting is the
    honest path.
    """

    price: Optional[Decimal] = Field(
        None, gt=0, le=Decimal("1000000"), decimal_places=3
    )
    delivery_cost: Optional[Decimal] = Field(
        None, ge=0, le=Decimal("1000"), decimal_places=3
    )
    availability: Optional[bool] = None

    # Wear changes over time even when the condition does not.
    battery_health: Optional[int] = Field(None, ge=1, le=100)
    has_damage: Optional[bool] = None
    damage_notes: Optional[str] = Field(None, max_length=500)
    listing_notes: Optional[str] = Field(None, max_length=1000)


class ListingResponse(BaseModel):
    id: int
    name: str
    price: float
    delivery_cost: float
    availability: bool
    last_updated: Optional[datetime] = None

    condition: str = "new"
    battery_health: Optional[int] = None
    has_damage: Optional[bool] = None
    damage_notes: Optional[str] = None
    warranty_months: Optional[int] = None
    listing_notes: Optional[str] = None

    # What the matching engine made of the name, echoed back so a merchant can
    # see why their listing did or did not join an existing product. A listing
    # that resolves to no category is invisible to search, and silently
    # dropping it would look like the form was broken.
    matched_product_id: Optional[int] = None
    matched_product_name: Optional[str] = None
    match_category: Optional[str] = None
    is_searchable: bool = True

    # Whether this listing carries a photo. A flag rather than a URL: the
    # dashboard fetches the image from the authenticated per-listing route,
    # which is the only one that will serve a pending shop its own picture.
    has_photo: bool = False
