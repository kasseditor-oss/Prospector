"""Opportunity score for a prospected channel.

The score answers one question an editor actually has: *how likely is this
channel to reply and become a client?* Sorting by subscriber count does not
answer it — the biggest channels already employ a full-time editor.

Four signals, 25 points each, deliberately kept independent:

- reachability: is there a public email to write to at all
- rhythm:       how often the channel ships (more output, more editing pain)
- recency:      how recently it shipped (a dormant channel will not hire)
- fit:          the size band where an editor is affordable but not on staff

The weights are a starting heuristic, not a fitted model. They are here in one
place so they can be tuned once real reply-rate data exists.
"""

from __future__ import annotations

from dataclasses import dataclass

MAX_SCORE = 99
MIN_SCORE = 1


@dataclass(frozen=True)
class ScoreBreakdown:
    """Per-signal contribution, so the UI can explain the number."""

    reachability: int
    rhythm: int
    recency: int
    fit: int

    @property
    def total(self) -> int:
        raw = self.reachability + self.rhythm + self.recency + self.fit
        return max(MIN_SCORE, min(MAX_SCORE, raw))


def _reachability(has_email: bool) -> int:
    # No email is not disqualifying — some channels are reachable through a
    # linked site or Instagram — but it is a much colder start.
    return 25 if has_email else 4


def _rhythm(uploads_per_month: float) -> int:
    # 10+ uploads a month saturates: past that the channel almost certainly
    # already outsources editing.
    if uploads_per_month <= 0:
        return 0
    return min(25, round(uploads_per_month / 10 * 25))


def _recency(days_since_last_upload: int | None) -> int:
    if days_since_last_upload is None:
        return 5  # unknown, not zero — absence of data is not evidence of death
    if days_since_last_upload <= 7:
        return 25
    if days_since_last_upload <= 30:
        return 20
    if days_since_last_upload <= 60:
        return 13
    if days_since_last_upload <= 120:
        return 7
    return 2


def _fit(subscribers: int) -> int:
    """The affordability band.

    Below ~3k a channel rarely pays for editing. Above ~800k it almost always
    has staff or an agency already, so a cold pitch lands badly.
    """
    if subscribers < 3_000:
        return 6
    if subscribers < 10_000:
        return 15
    if subscribers <= 300_000:
        return 25
    if subscribers <= 800_000:
        return 14
    return 7


def score_channel(
    *,
    subscribers: int,
    uploads_per_month: float,
    days_since_last_upload: int | None,
    has_email: bool,
) -> ScoreBreakdown:
    """Score one channel. Pure function — no I/O, trivially testable."""
    return ScoreBreakdown(
        reachability=_reachability(has_email),
        rhythm=_rhythm(uploads_per_month),
        recency=_recency(days_since_last_upload),
        fit=_fit(subscribers),
    )
