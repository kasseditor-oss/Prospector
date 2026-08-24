"""The author's picture, from the tweet to the table.

Small surface, but two things here are easy to get wrong quietly: reading a
field name that the actor does not actually use (the column just stays empty and
nobody notices), and rewriting somebody else's URL scheme badly (a whole column
of broken images). The URLs below are the shape a real run returned.
"""

from __future__ import annotations

import sqlite3

import pytest

from app.posts import PostStore
from app.xsearch import _avatar, to_post

REAL_URL = "https://pbs.twimg.com/profile_images/2090955442595725312/SSQmFD7x_normal.jpg"
BIGGER = "https://pbs.twimg.com/profile_images/2090955442595725312/SSQmFD7x_bigger.jpg"


def tweet(picture: object = REAL_URL) -> dict:
    author = {"userName": "alguem", "name": "Alguém", "followers": 900}
    if picture is not None:
        author["profilePicture"] = picture
    return {
        "id": "1",
        "text": "preciso de um editor de vídeo pro meu canal",
        "url": "https://x.com/alguem/status/1",
        "createdAt": "Wed Aug 20 12:00:00 +0000 2025",
        "author": author,
    }


# ------------------------------------------------------------------ a URL
def test_the_small_default_is_asked_for_at_a_size_worth_drawing():
    """X serves _normal at 48px, which is soft in a 32px slot on any modern
    display. _bigger is the same image at 73."""
    assert _avatar(REAL_URL) == BIGGER


def test_a_url_without_that_suffix_is_left_exactly_as_it_came():
    """Guessing at another host's URL scheme is how a column of broken images
    happens. Anything unfamiliar passes through untouched."""
    other = "https://example.com/foto.png"
    assert _avatar(other) == other


def test_only_the_size_marker_is_replaced_not_any_matching_text():
    """The account id could contain the same letters; only the suffix moves."""
    tricky = "https://pbs.twimg.com/profile_images/_normal_fan_99/pic_normal.jpg"
    assert _avatar(tricky).endswith("pic_bigger.jpg")
    assert "_normal_fan_99" in _avatar(tricky)


@pytest.mark.parametrize("value", [None, "", 12345, {}])
def test_a_missing_or_odd_picture_is_no_picture(value):
    assert _avatar(value) is None


# ------------------------------------------------- from the tweet to the row
def test_the_field_the_actor_actually_uses_is_the_one_read():
    """profilePicture, measured against a live run. A wrong name here fails
    silently: the column simply stays empty."""
    post = to_post(tweet())
    assert post is not None
    assert post["author_avatar"] == BIGGER


def test_an_author_with_no_picture_still_becomes_a_post():
    post = to_post(tweet(picture=None))
    assert post is not None
    assert post["author_avatar"] is None


def test_the_picture_survives_a_round_trip_through_the_base(tmp_path):
    store = PostStore(tmp_path / "posts.db")
    store.save_many([to_post(tweet())])
    rows, _ = store.list()
    assert rows[0]["author_avatar"] == BIGGER


def test_a_new_picture_replaces_the_old_one(tmp_path):
    """Unlike the status, this is not the reader's note — an out-of-date
    picture is simply wrong, so a later search overwrites it."""
    store = PostStore(tmp_path / "posts.db")
    store.save_many([to_post(tweet())])

    trocada = tweet(picture=REAL_URL.replace("SSQmFD7x", "OUTRAFOTO"))
    store.save_many([to_post(trocada)])

    rows, _ = store.list()
    assert "OUTRAFOTO" in rows[0]["author_avatar"]


def test_a_base_written_before_the_column_existed_still_opens(tmp_path):
    """The 194 posts already saved cost real money. They keep working, and
    simply show initials until a later search finds them again."""
    path = tmp_path / "posts.db"
    store = PostStore(path)
    store.save_many([to_post(tweet())])

    with sqlite3.connect(path) as conn:
        conn.execute("ALTER TABLE posts DROP COLUMN author_avatar")
        conn.commit()

    reopened = PostStore(path)
    rows, total = reopened.list()
    assert total == 1
    assert rows[0]["author_avatar"] is None
    # And a later search fills it back in.
    reopened.save_many([to_post(tweet())])
    assert reopened.list()[0][0]["author_avatar"] == BIGGER


# ------------------------------------------------- o contrato com a resposta
def test_the_response_model_does_not_silently_drop_a_stored_column(tmp_path):
    """The bug this test exists for.

    The column was added to the table, the mapper, the refresh list and the
    scraper — and forgotten in the response model. Everything looked right:
    the value sat in the database, 206 tests passed, and the field simply never
    reached the browser, because pydantic drops what it was not told about.
    Nothing failed; the pictures just did not appear.

    So this asserts the whole contract rather than one field: whatever the
    store returns, the model has to carry.
    """
    from app.schemas import PostOut

    store = PostStore(tmp_path / "posts.db")
    store.save_many([to_post(tweet())])
    row = store.list()[0][0]

    esquecidos = set(row) - set(PostOut(**row).model_dump())
    assert not esquecidos, f"PostOut descarta: {sorted(esquecidos)}"


def test_the_channel_response_model_carries_everything_too(tmp_path):
    from app.leads import LeadStore
    from app.schemas import LeadOut
    from tests.test_status import channel

    store = LeadStore(str(tmp_path / "leads.db"))
    store.save_many([channel()])
    row = store.list()[0][0]

    esquecidos = set(row) - set(LeadOut(**row).model_dump())
    assert not esquecidos, f"LeadOut descarta: {sorted(esquecidos)}"
