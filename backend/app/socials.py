"""Other networks a channel links to, read from its description.

An editor pitching a channel wants to know where else its owner is reachable:
a Discord invite is a faster way in than a business email, and an Instagram
account often means the channel already buys short-form edits.

The YouTube Data API does not expose the links section of a channel's About
tab, so these come from the description text — the one place a creator writes
them out. That means the list is *what the channel published*, never a guess:
a channel with an Instagram it never mentions will show nothing here, and that
is the honest answer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Path segments that look like a profile but are not one. Without these,
# a "share this on X" link would be read as the channel owning an X account.
_NOT_A_PROFILE = {
    "share", "sharer", "intent", "home", "p", "reel", "reels", "explore",
    "hashtag", "tv", "watch", "groups", "events", "pages", "story", "stories",
    "permalink", "dialog", "login", "signup", "help", "about", "privacy",
    "terms", "policies", "search", "i", "channel", "video", "embed", "download",
}

# One pattern per network, capturing the handle. Ordered by how useful the
# network is to someone selling editing work, because that is the order the
# icons are shown in.
_PATTERNS: tuple[tuple[str, str, str], ...] = (
    ("instagram", r"instagram\.com/([A-Za-z0-9_.]{1,30})", "https://instagram.com/{h}"),
    ("tiktok", r"tiktok\.com/@([A-Za-z0-9_.]{1,30})", "https://tiktok.com/@{h}"),
    ("x", r"(?:twitter|x)\.com/([A-Za-z0-9_]{1,15})", "https://x.com/{h}"),
    ("discord", r"(?:discord\.gg|discord\.com/invite)/([A-Za-z0-9-]{2,32})", "https://discord.gg/{h}"),
    ("twitch", r"twitch\.tv/([A-Za-z0-9_]{2,30})", "https://twitch.tv/{h}"),
    ("telegram", r"(?:t\.me|telegram\.me)/([A-Za-z0-9_]{2,32})", "https://t.me/{h}"),
    ("threads", r"threads\.(?:net|com)/@?([A-Za-z0-9_.]{1,30})", "https://threads.net/@{h}"),
    ("facebook", r"(?:web\.|m\.)?facebook\.com/([A-Za-z0-9_.-]{2,50})", "https://facebook.com/{h}"),
    ("linkedin", r"linkedin\.com/(?:in|company)/([A-Za-z0-9_-]{2,60})", "https://linkedin.com/in/{h}"),
    ("kick", r"kick\.com/([A-Za-z0-9_-]{2,30})", "https://kick.com/{h}"),
)

_COMPILED = tuple(
    (name, re.compile(r"(?:https?://)?(?:www\.)?" + pattern, re.IGNORECASE), template)
    for name, pattern, template in _PATTERNS
)

#: The order icons appear in a row, so every row reads the same way.
NETWORK_ORDER = [name for name, _, _ in _PATTERNS]

# More than this and the column stops being scannable.
MAX_PER_CHANNEL = 6


@dataclass(frozen=True)
class Social:
    network: str
    handle: str
    url: str


def extract_socials(description: str) -> list[Social]:
    """Profile links a channel published in its description.

    At most one per network — a creator who pastes the same Instagram three
    times has one Instagram, and the column should say so.
    """
    if not description:
        return []

    found: dict[str, Social] = {}
    for name, pattern, template in _COMPILED:
        for match in pattern.finditer(description):
            handle = match.group(1).rstrip(".,;:/")
            if not handle or handle.lower() in _NOT_A_PROFILE:
                continue
            found[name] = Social(network=name, handle=handle, url=template.format(h=handle))
            break

    ordered = [found[name] for name in NETWORK_ORDER if name in found]
    return ordered[:MAX_PER_CHANNEL]


def merge_from_videos(
    channel_socials: list[Social],
    video_descriptions: list[str],
    *,
    min_repeats: int = 2,
) -> list[Social]:
    """Add networks a creator repeats across their own video descriptions.

    Most creators never write their links in the channel description — they
    paste them under every video instead. Those descriptions already arrive
    with the upload history, so reading them costs no extra quota.

    A video description also carries links that are *not* the creator's: a
    sponsor, a collaborator, a track credit. Requiring the same profile to
    appear in at least ``min_repeats`` videos separates the creator's own
    links, which repeat on every upload, from a one-off mention.
    """
    counts: dict[tuple[str, str], int] = {}
    seen: dict[tuple[str, str], Social] = {}
    for description in video_descriptions:
        # Counted once per video, so a link pasted three times inside a single
        # description cannot pass the repeat test on its own.
        for social in extract_socials(description):
            token = (social.network, social.handle.lower())
            counts[token] = counts.get(token, 0) + 1
            seen.setdefault(token, social)

    # The channel description is the creator speaking about the channel, so
    # anything found there is trusted immediately and wins on handle.
    merged = {s.network: s for s in channel_socials}
    for (network, _), hits in counts.items():
        if hits >= min_repeats and network not in merged:
            merged[network] = seen[(network, _)]

    ordered = [merged[name] for name in NETWORK_ORDER if name in merged]
    return ordered[:MAX_PER_CHANNEL]
