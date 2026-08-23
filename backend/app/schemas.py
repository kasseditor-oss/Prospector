"""Request and response models.

Pydantic validates the filters at the edge so the search code can assume a
coherent query — the subscriber floor is never above the ceiling, the niche
list is never empty, and the country is one we actually support.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

# regionCode values accepted by search.list, limited to the markets the product
# claims to cover.
SUPPORTED_COUNTRIES = {
    "BR", "US", "PT", "MX", "AR", "ES", "FR", "DE", "IT", "GB", "CA", "AU",
}

ActivityWindow = Literal[30, 90, 365, 0]


class SearchFilters(BaseModel):
    niches: list[str] = Field(min_length=1, max_length=3)
    country: str = "BR"
    language: str | None = "pt"
    min_subscribers: int = Field(default=0, ge=0)
    max_subscribers: int = Field(default=1_000_000, ge=1)
    activity_days: ActivityWindow = 90
    email_only: bool = False
    deep: bool = False

    @field_validator("niches")
    @classmethod
    def _clean_niches(cls, value: list[str]) -> list[str]:
        cleaned = [n.strip() for n in value if n and n.strip()]
        if not cleaned:
            raise ValueError("Provide at least one niche.")
        return cleaned

    @field_validator("country")
    @classmethod
    def _known_country(cls, value: str) -> str:
        upper = value.upper()
        if upper not in SUPPORTED_COUNTRIES:
            raise ValueError(f"Unsupported country: {value}")
        return upper

    @model_validator(mode="after")
    def _range_is_sane(self) -> "SearchFilters":
        if self.min_subscribers > self.max_subscribers:
            raise ValueError("min_subscribers cannot exceed max_subscribers.")
        return self

    @property
    def pages(self) -> int:
        """search.list pages per niche. Deep mode trades quota for reach."""
        return 5 if self.deep else 2

    @property
    def enrich_last_upload(self) -> bool:
        """Recency data is only worth its unit cost when we filter on it."""
        return self.activity_days != 0


class ScoreDetail(BaseModel):
    total: int
    reachability: int
    rhythm: int
    recency: int
    fit: int


class SocialOut(BaseModel):
    """One other network the channel links to from its description."""

    network: str
    handle: str
    url: str


class ChannelOut(BaseModel):
    id: str
    title: str
    handle: str | None
    url: str
    subscribers: int
    subscribers_hidden: bool
    video_count: int
    country: str | None
    thumbnail: str | None
    email: str | None
    #: Other networks the channel published, in a fixed display order.
    socials: list[SocialOut]
    uploads_per_month: float
    #: Uploads per month over the trailing window, oldest first. Shorter than
    #: 12 when the channel published enough to exhaust one page of history.
    cadence: list[int]
    #: Last quarter's rate over the preceding three. >1 means accelerating,
    #: 0 means not enough history to say.
    cadence_trend: float
    days_since_last_upload: int | None
    last_upload_at: datetime | None
    niche: str
    score: ScoreDetail


class LeadOut(ChannelOut):
    """A saved lead: a channel plus when it entered and last refreshed."""

    first_seen: datetime
    last_seen: datetime


class LeadsResponse(BaseModel):
    leads: list[LeadOut]
    total: int


class SearchResponse(BaseModel):
    channels: list[ChannelOut]
    units_spent: int
    units_remaining: int
    examined: int
    filtered_out: int
    #: How many of these channels were not already in the lead base.
    saved_new: int = 0
    #: How many were already there and had their numbers refreshed.
    saved_updated: int = 0
    #: Size of the whole base after this search.
    total_saved: int = 0


class EstimateResponse(BaseModel):
    units: int
    units_remaining: int
    affordable: bool


class KeyIn(BaseModel):
    key: str = Field(min_length=20, max_length=200)
    label: str | None = Field(default=None, max_length=60)


class KeyOut(BaseModel):
    label: str
    masked: str
    used: int
    remaining: int
    disabled_reason: str | None


class QuotaOut(BaseModel):
    keys: int
    units_remaining: int
    units_total: int
    quota_day: str
    #: How keys are kept between launches, in words the user can act on. The
    #: keys screen states the actual guarantee rather than a generic promise.
    key_storage: str = "não são salvas (some ao fechar)"
