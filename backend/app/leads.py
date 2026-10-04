"""The lead base: every channel a search has ever turned up, kept on disk.

A search is expensive — 100 quota units per page — and its results used to live
only in the browser tab that ran it. Closing the tab threw away work that cost
real quota, and running a second search replaced the first. Prospecting is
cumulative: the value is the base built over weeks, not one screen of rows.

SQLite is the whole storage layer. It ships with Python, the file sits next to
the app, and a personal base of a few hundred thousand rows is nowhere near its
limits. No server, no dependency, no account.

Note for a future multi-user deployment: this base is per *machine*, not per
session — exactly right for a personal tool and exactly wrong for a shared one.
Keying rows by session would be the change to make.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

from .paths import data_dir
from .status import DEFAULT_STATUS, clean


def _default_path() -> Path:
    """Where the base lives. See :mod:`app.paths` for why not next to the code."""
    return data_dir() / "leads.db"


_SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    id                     TEXT PRIMARY KEY,
    title                  TEXT NOT NULL,
    handle                 TEXT,
    url                    TEXT NOT NULL,
    subscribers            INTEGER NOT NULL DEFAULT 0,
    subscribers_hidden     INTEGER NOT NULL DEFAULT 0,
    video_count            INTEGER NOT NULL DEFAULT 0,
    country                TEXT,
    thumbnail              TEXT,
    email                  TEXT,
    socials                TEXT NOT NULL DEFAULT '[]',
    uploads_per_month      REAL NOT NULL DEFAULT 0,
    cadence                TEXT NOT NULL DEFAULT '[]',
    cadence_trend          REAL NOT NULL DEFAULT 0,
    days_since_last_upload INTEGER,
    last_upload_at         TEXT,
    niche                  TEXT NOT NULL DEFAULT '',
    status                 TEXT NOT NULL DEFAULT 'novo',
    emailed_at             TEXT,
    score                  INTEGER NOT NULL DEFAULT 0,
    score_detail           TEXT NOT NULL DEFAULT '{}',
    first_seen             TEXT NOT NULL,
    last_seen              TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS leads_by_score ON leads (score DESC);
CREATE INDEX IF NOT EXISTS leads_by_seen ON leads (first_seen DESC);
"""

# Columns refreshed when a channel turns up in a later search. ``first_seen``
# is deliberately absent: it records when this lead entered the base, and a
# re-find must not rewrite that history. ``status`` is absent for a stronger
# reason — it is the only column here the *user* wrote. Refreshing it would
# quietly reset "Contatado" to "Não contatado" on the next search, and the
# reader would have no way to know it happened. ``emailed_at`` is absent for
# the same reason: it is the record of a message that really went out.
_REFRESHED = (
    "title", "handle", "url", "subscribers", "subscribers_hidden", "video_count",
    "country", "thumbnail", "email", "socials", "uploads_per_month", "cadence",
    "cadence_trend", "days_since_last_upload", "last_upload_at", "niche",
    "score", "score_detail", "last_seen",
)

_SORTS = {
    "first_seen": "first_seen DESC",
    "score": "score DESC, subscribers DESC",
    "subscribers": "subscribers DESC",
    "title": "title COLLATE NOCASE ASC",
    "uploads_per_month": "uploads_per_month DESC",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class LeadStore:
    """Every channel ever found, deduplicated by YouTube channel id."""

    TABLE = "leads"

    def __init__(self, path: str | Path | None = None) -> None:
        raw = str(path or os.getenv("PROSPECTOR_DB") or _default_path())
        self.path = raw
        if raw != ":memory:":
            Path(raw).parent.mkdir(parents=True, exist_ok=True)
        # An in-memory database has to keep one connection alive: opening a
        # second one would create a new, empty database and the store would
        # silently forget everything written so far.
        self._shared = (
            sqlite3.connect(raw, check_same_thread=False) if raw == ":memory:" else None
        )
        self._lock = threading.Lock()
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
            self._migrate(conn)


    def _migrate(self, conn) -> None:
        """Add columns that older databases predate.

        The base is the point of the app — it holds work that cost quota and
        money — so a new column has to arrive without asking anyone to start
        over. SQLite has no ADD COLUMN IF NOT EXISTS, hence the lookup.
        """
        have = {row["name"] for row in conn.execute("PRAGMA table_info(%s)" % self.TABLE)}
        if "status" not in have:
            conn.execute(
                "ALTER TABLE %s ADD COLUMN status TEXT NOT NULL DEFAULT '%s'"
                % (self.TABLE, DEFAULT_STATUS)
            )
        if "emailed_at" not in have:
            conn.execute("ALTER TABLE %s ADD COLUMN emailed_at TEXT" % self.TABLE)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        if self._shared is not None:
            with self._lock:
                self._shared.row_factory = sqlite3.Row
                yield self._shared
                self._shared.commit()
            return
        conn = sqlite3.connect(self.path, timeout=10)
        try:
            # WAL lets a read run while a write is in flight, so listing the
            # base never blocks behind a search saving into it.
            conn.execute("PRAGMA journal_mode=WAL")
            conn.row_factory = sqlite3.Row
            yield conn
            conn.commit()
        finally:
            conn.close()

    # ---- writing ---------------------------------------------------------
    def save_many(self, channels: Iterable[dict[str, Any]]) -> tuple[int, int]:
        """Upsert a search's results. Returns (new leads, refreshed leads)."""
        rows = list(channels)
        if not rows:
            return (0, 0)

        now = _now()
        ids = [r["id"] for r in rows]
        with self._connect() as conn:
            known = {
                r[0]
                for chunk in _chunks(ids, 400)
                for r in conn.execute(
                    "SELECT id FROM leads WHERE id IN (%s)" % ",".join("?" * len(chunk)),
                    chunk,
                )
            }
            updates = ", ".join("%s=excluded.%s" % (c, c) for c in _REFRESHED)
            conn.executemany(
                """
                INSERT INTO leads (
                    id, title, handle, url, subscribers, subscribers_hidden,
                    video_count, country, thumbnail, email, socials,
                    uploads_per_month, cadence, cadence_trend,
                    days_since_last_upload, last_upload_at, niche, score,
                    score_detail, first_seen, last_seen
                ) VALUES (
                    :id, :title, :handle, :url, :subscribers, :subscribers_hidden,
                    :video_count, :country, :thumbnail, :email, :socials,
                    :uploads_per_month, :cadence, :cadence_trend,
                    :days_since_last_upload, :last_upload_at, :niche, :score,
                    :score_detail, :first_seen, :last_seen
                )
                ON CONFLICT(id) DO UPDATE SET """
                + updates,
                [_to_row(r, now) for r in rows],
            )
        new = sum(1 for i in ids if i not in known)
        return (new, len(rows) - new)


    def set_status(self, row_id: str, status: str) -> bool:
        """Move one lead along the funnel. False when there is no such lead."""
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE %s SET status = ? WHERE id = ?" % self.TABLE,
                (clean(status), row_id),
            )
            return cur.rowcount > 0

    def mark_emailed(self, row_id: str) -> bool:
        """Record that a message went out to this lead, and move it along.

        One statement, so the timestamp and the funnel step can never disagree.
        A lead that already answered or became a client keeps its step: being
        written to again does not send the conversation backwards.
        """
        with self._connect() as conn:
            cur = conn.execute(
                """
                UPDATE leads
                   SET emailed_at = ?,
                       status = CASE WHEN status = ? THEN 'contatado' ELSE status END
                 WHERE id = ?
                """,
                (_now(), DEFAULT_STATUS, row_id),
            )
            return cur.rowcount > 0

    def delete(self, channel_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM leads WHERE id = ?", (channel_id,))
            return cur.rowcount > 0

    def clear(self) -> int:
        with self._connect() as conn:
            return conn.execute("DELETE FROM leads").rowcount

    # ---- reading ---------------------------------------------------------
    def count(self) -> int:
        with self._connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0])

    def get(self, row_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM leads WHERE id = ?", (row_id,)).fetchone()
        return _from_row(row) if row else None

    def emailed_since(self, moment: str) -> int:
        """How many messages went out at or after an ISO timestamp.

        The stamps are all written by :func:`_now` in one format, so comparing
        them as text orders them as time.
        """
        with self._connect() as conn:
            return int(
                conn.execute(
                    "SELECT COUNT(*) FROM leads WHERE emailed_at >= ?", (moment,)
                ).fetchone()[0]
            )

    def list(
        self,
        *,
        query: str = "",
        sort: str = "first_seen",
        limit: int = 500,
        offset: int = 0,
        with_email: bool = False,
        status: str = "",
    ) -> tuple[list[dict[str, Any]], int]:
        where: list[str] = []
        args: list[Any] = []
        if status.strip():
            # Compared against the cleaned value so an unknown name filters to
            # nothing rather than silently listing the whole base.
            where.append("status = ?")
            args.append(clean(status))
        if query.strip():
            where.append("(title LIKE ? OR handle LIKE ? OR niche LIKE ?)")
            like = "%%%s%%" % query.strip()
            args += [like, like, like]
        if with_email:
            where.append("email IS NOT NULL AND email != ''")
        clause = "WHERE %s" % " AND ".join(where) if where else ""
        order = _SORTS.get(sort, _SORTS["first_seen"])

        with self._connect() as conn:
            total = int(
                conn.execute("SELECT COUNT(*) FROM leads %s" % clause, args).fetchone()[0]
            )
            rows = conn.execute(
                "SELECT * FROM leads %s ORDER BY %s LIMIT ? OFFSET ?" % (clause, order),
                [*args, max(1, min(limit, 2000)), max(0, offset)],
            ).fetchall()
        return ([_from_row(r) for r in rows], total)


def _chunks(items: list[Any], size: int) -> Iterator[list[Any]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def _to_row(channel: dict[str, Any], now: str) -> dict[str, Any]:
    last_upload = channel.get("last_upload_at")
    return {
        "id": channel["id"],
        "title": channel.get("title") or "",
        "handle": channel.get("handle"),
        "url": channel.get("url") or "",
        "subscribers": int(channel.get("subscribers") or 0),
        "subscribers_hidden": 1 if channel.get("subscribers_hidden") else 0,
        "video_count": int(channel.get("video_count") or 0),
        "country": channel.get("country"),
        "thumbnail": channel.get("thumbnail"),
        "email": channel.get("email"),
        "socials": json.dumps(channel.get("socials") or [], ensure_ascii=False),
        "uploads_per_month": float(channel.get("uploads_per_month") or 0),
        "cadence": json.dumps(channel.get("cadence") or []),
        "cadence_trend": float(channel.get("cadence_trend") or 0),
        "days_since_last_upload": channel.get("days_since_last_upload"),
        "last_upload_at": (
            last_upload.isoformat()
            if hasattr(last_upload, "isoformat")
            else last_upload
        ),
        "niche": channel.get("niche") or "",
        "score": int((channel.get("score") or {}).get("total") or 0),
        "score_detail": json.dumps(channel.get("score") or {}),
        "first_seen": now,
        "last_seen": now,
    }


def _from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "title": row["title"],
        "handle": row["handle"],
        "url": row["url"],
        "subscribers": row["subscribers"],
        "subscribers_hidden": bool(row["subscribers_hidden"]),
        "video_count": row["video_count"],
        "country": row["country"],
        "thumbnail": row["thumbnail"],
        "email": row["email"],
        "socials": json.loads(row["socials"]),
        "uploads_per_month": row["uploads_per_month"],
        "cadence": json.loads(row["cadence"]),
        "cadence_trend": row["cadence_trend"],
        "days_since_last_upload": row["days_since_last_upload"],
        "last_upload_at": row["last_upload_at"],
        "niche": row["niche"],
        "status": clean(row["status"]),
        "emailed_at": row["emailed_at"],
        "score": json.loads(row["score_detail"]),
        "first_seen": row["first_seen"],
        "last_seen": row["last_seen"],
    }
