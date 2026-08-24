"""The base of hiring posts — a separate table from the channels, on purpose.

A YouTube channel and a hiring post answer different questions and age at
different speeds. A channel found last month is still a lead; a post asking for
an editor last month has long since hired someone. They also share almost no
columns: subscribers and upload cadence mean nothing here, and reply count and
post age mean nothing there.

Keeping them in one table would give a grid where half the columns are empty on
half the rows, and a "score" that measures two different things depending on
which row you read. So: two bases, two screens, one app.
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .paths import data_dir
from .status import DEFAULT_STATUS, clean


def _default_path() -> Path:
    return data_dir() / "posts.db"


_SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
    id                TEXT PRIMARY KEY,
    source            TEXT NOT NULL DEFAULT 'x',
    author            TEXT NOT NULL,
    author_name       TEXT NOT NULL DEFAULT '',
    author_followers  INTEGER NOT NULL DEFAULT 0,
    author_url        TEXT NOT NULL DEFAULT '',
    text              TEXT NOT NULL,
    url               TEXT NOT NULL,
    posted_at         TEXT,
    replies           INTEGER NOT NULL DEFAULT 0,
    likes             INTEGER NOT NULL DEFAULT 0,
    budget            INTEGER NOT NULL DEFAULT 0,
    ongoing           INTEGER NOT NULL DEFAULT 0,
    matched           TEXT NOT NULL DEFAULT '',
    query             TEXT NOT NULL DEFAULT '',
    score             INTEGER NOT NULL DEFAULT 0,
    status            TEXT NOT NULL DEFAULT 'novo',
    first_seen        TEXT NOT NULL,
    last_seen         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS posts_by_posted ON posts (posted_at DESC);
CREATE INDEX IF NOT EXISTS posts_by_score  ON posts (score DESC);
"""

# Refreshed when the same post turns up again. ``first_seen`` is absent for the
# same reason as in the lead base: finding it twice is not finding it anew.
# ``status`` is absent because it is the reader's own note — a search must never
# reset a post already marked as answered.
_REFRESHED = (
    "source", "author", "author_name", "author_followers", "author_url",
    "text", "url", "posted_at", "replies", "likes", "budget", "ongoing",
    "matched", "query", "score", "last_seen",
)

_SORTS = {
    "posted_at": "posted_at DESC",
    "score": "score DESC, posted_at DESC",
    "author_followers": "author_followers DESC",
    "replies": "replies ASC, posted_at DESC",
    "first_seen": "first_seen DESC",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def hours_old(posted_at: str | None, now: datetime | None = None) -> float | None:
    """Age in hours, or None when the post carries no date."""
    if not posted_at:
        return None
    try:
        when = datetime.fromisoformat(posted_at)
    except ValueError:
        try:
            when = datetime.strptime(posted_at, "%a %b %d %H:%M:%S %z %Y")
        except ValueError:
            return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    reference = now or datetime.now(timezone.utc)
    return max(0.0, (reference - when).total_seconds() / 3600)


def score_post(post: dict[str, Any], now: datetime | None = None) -> int:
    """1–99, weighted almost entirely by how fast this needs answering.

    A post asking for an editor collects replies within hours. Being early
    beats being a better fit, so age dominates: a perfect post from last week
    scores below a plain one from this morning.
    """
    age = hours_old(post.get("posted_at"), now)
    if age is None:
        freshness = 10
    elif age <= 6:
        freshness = 45
    elif age <= 24:
        freshness = 36
    elif age <= 72:
        freshness = 22
    elif age <= 168:
        freshness = 10
    else:
        freshness = 2

    # Few replies means the reader is not the twentieth person answering.
    replies = int(post.get("replies") or 0)
    crowd = 20 if replies == 0 else 15 if replies <= 3 else 8 if replies <= 10 else 2

    # Money named is money decided.
    money = 20 if post.get("budget") else 0
    recurring = 8 if post.get("ongoing") else 0

    followers = int(post.get("author_followers") or 0)
    reach = 2 if followers < 500 else 4 if followers < 5_000 else 6

    return max(1, min(99, freshness + crowd + money + recurring + reach))


class PostStore:
    """Hiring posts kept on this machine, growing with every search."""

    TABLE = "posts"

    def __init__(self, path: Path | str | None = None) -> None:
        raw = str(path) if path else str(_default_path())
        if raw != ":memory:":
            Path(raw).parent.mkdir(parents=True, exist_ok=True)
        self._path = raw
        self._lock = threading.Lock()
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
            self._migrate(conn)
            conn.commit()

    def _migrate(self, conn: sqlite3.Connection) -> None:
        """Add columns that an older database predates.

        This base holds posts that cost real money to find, so a new column has
        to arrive without throwing them away. SQLite has no ADD COLUMN IF NOT
        EXISTS, hence the lookup.
        """
        have = {row["name"] for row in conn.execute("PRAGMA table_info(%s)" % self.TABLE)}
        if "status" not in have:
            conn.execute(
                "ALTER TABLE %s ADD COLUMN status TEXT NOT NULL DEFAULT '%s'"
                % (self.TABLE, DEFAULT_STATUS)
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path, timeout=10)
        conn.row_factory = sqlite3.Row
        if self._path != ":memory:":
            conn.execute("PRAGMA journal_mode=WAL")
        return conn

    # -- writing ---------------------------------------------------------
    def save_many(self, posts: Iterable[dict[str, Any]]) -> tuple[int, int]:
        """Store posts, returning (new, refreshed)."""
        rows = list(posts)
        if not rows:
            return (0, 0)
        now = _now()
        prepared = [_to_row(p, now) for p in rows]
        ids = [p["id"] for p in prepared]

        with self._lock, self._connect() as conn:
            known = {
                r["id"]
                for r in conn.execute(
                    "SELECT id FROM posts WHERE id IN (%s)" % ",".join("?" * len(ids)),
                    ids,
                )
            }
            assignments = ", ".join(f"{c} = excluded.{c}" for c in _REFRESHED)
            conn.executemany(
                """
                INSERT INTO posts (
                    id, source, author, author_name, author_followers, author_url,
                    text, url, posted_at, replies, likes, budget, ongoing,
                    matched, query, score, first_seen, last_seen
                ) VALUES (
                    :id, :source, :author, :author_name, :author_followers, :author_url,
                    :text, :url, :posted_at, :replies, :likes, :budget, :ongoing,
                    :matched, :query, :score, :first_seen, :last_seen
                )
                ON CONFLICT(id) DO UPDATE SET %s
                """
                % assignments,
                prepared,
            )
        new = sum(1 for i in ids if i not in known)
        return (new, len(ids) - new)

    def set_status(self, post_id: str, status: str) -> bool:
        """Move one post along the funnel. False when there is no such post."""
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                "UPDATE posts SET status = ? WHERE id = ?", (clean(status), post_id)
            )
            conn.commit()
            return cur.rowcount > 0

    def delete(self, post_id: str) -> bool:
        with self._lock, self._connect() as conn:
            return conn.execute("DELETE FROM posts WHERE id = ?", (post_id,)).rowcount > 0

    def clear(self) -> int:
        with self._lock, self._connect() as conn:
            return conn.execute("DELETE FROM posts").rowcount

    def count(self) -> int:
        with self._connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0])

    # -- reading ---------------------------------------------------------
    def list(
        self,
        *,
        query: str = "",
        sort: str = "posted_at",
        limit: int = 500,
        offset: int = 0,
        with_budget: bool = False,
        min_followers: int = 0,
        status: str = "",
    ) -> tuple[list[dict[str, Any]], int]:
        where: list[str] = []
        args: list[Any] = []
        if status.strip():
            # Cleaned first, so an unknown name filters to nothing instead of
            # quietly listing everything.
            where.append("status = ?")
            args.append(clean(status))
        if query.strip():
            where.append("(text LIKE ? OR author LIKE ? OR author_name LIKE ?)")
            like = "%%%s%%" % query.strip()
            args += [like, like, like]
        if with_budget:
            where.append("budget = 1")
        if min_followers > 0:
            where.append("author_followers >= ?")
            args.append(min_followers)
        clause = "WHERE %s" % " AND ".join(where) if where else ""
        order = _SORTS.get(sort, _SORTS["posted_at"])

        with self._connect() as conn:
            total = int(
                conn.execute("SELECT COUNT(*) FROM posts %s" % clause, args).fetchone()[0]
            )
            rows = conn.execute(
                "SELECT * FROM posts %s ORDER BY %s LIMIT ? OFFSET ?" % (clause, order),
                [*args, max(1, min(limit, 2000)), max(0, offset)],
            ).fetchall()
        return ([_from_row(r) for r in rows], total)


def _to_row(post: dict[str, Any], now: str) -> dict[str, Any]:
    return {
        "id": str(post["id"]),
        "source": post.get("source") or "x",
        "author": post.get("author") or "",
        "author_name": post.get("author_name") or "",
        "author_followers": int(post.get("author_followers") or 0),
        "author_url": post.get("author_url") or "",
        "text": post.get("text") or "",
        "url": post.get("url") or "",
        "posted_at": post.get("posted_at"),
        "replies": int(post.get("replies") or 0),
        "likes": int(post.get("likes") or 0),
        "budget": 1 if post.get("budget") else 0,
        "ongoing": 1 if post.get("ongoing") else 0,
        "matched": post.get("matched") or "",
        "query": post.get("query") or "",
        "score": int(post.get("score") or score_post(post)),
        "first_seen": now,
        "last_seen": now,
    }


def _from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "source": row["source"],
        "author": row["author"],
        "author_name": row["author_name"],
        "author_followers": row["author_followers"],
        "author_url": row["author_url"],
        "text": row["text"],
        "url": row["url"],
        "posted_at": row["posted_at"],
        "replies": row["replies"],
        "likes": row["likes"],
        "budget": bool(row["budget"]),
        "ongoing": bool(row["ongoing"]),
        "matched": row["matched"],
        "query": row["query"],
        "score": row["score"],
        "status": clean(row["status"]),
        "hours_old": hours_old(row["posted_at"]),
        "first_seen": row["first_seen"],
        "last_seen": row["last_seen"],
    }
