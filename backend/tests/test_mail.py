"""Sending e-mail to leads, and the ways it must refuse to.

No test here opens a socket: ``mailer.send`` is replaced by a recorder. What is
being checked is everything around the send — who is allowed to receive one,
how many may go out, and what the base remembers afterwards — because those are
the parts that, wrong, write to the same person twice or burn the mailbox.
"""

from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

from app import main, mailer
from app.leads import LeadStore
from app.store import SecretStore


def channel(cid: str = "UC1", title: str = "Canal", email: str | None = "a@b.com"):
    return {
        "id": cid, "title": title, "handle": "@canal", "url": "https://y/c",
        "subscribers": 48000, "subscribers_hidden": False, "video_count": 10,
        "country": "BR", "thumbnail": None, "email": email, "socials": [],
        "uploads_per_month": 4.0, "cadence": [1, 2], "cadence_trend": 1.0,
        "days_since_last_upload": 3, "last_upload_at": None, "niche": "games",
        "score": {"total": 50, "reachability": 10, "rhythm": 10, "recency": 10, "fit": 20},
    }


ACCOUNT = {"user": "eu@gmail.com", "password": "abcd efgh ijkl mnop", "from_name": "Eu"}


@pytest.fixture
def app(monkeypatch, tmp_path):
    """The API over an empty base, with every send recorded instead of sent."""
    monkeypatch.setattr(main, "leads", LeadStore(str(tmp_path / "leads.db")))
    monkeypatch.setattr(main, "secrets", SecretStore(tmp_path))
    sent: list[dict] = []

    def fake_send(account, to, subject, body):
        sent.append({"from": account.user, "to": to, "subject": subject, "body": body})

    monkeypatch.setattr(mailer, "send", fake_send)
    client = TestClient(main.app, base_url="http://127.0.0.1")
    client.sent = sent
    return client


# ------------------------------------------------------------------ o texto
def test_the_template_is_filled_from_the_lead():
    text = mailer.render("Oi {canal} ({handle}), {nicho}, {inscritos}", channel())
    assert text == "Oi Canal (@canal), games, 48.000"


def test_a_stray_brace_in_the_body_is_left_alone():
    """Free text: a brace that is not a placeholder must not raise."""
    assert mailer.render("{canal} usa {isso} e }", channel()) == "Canal usa {isso} e }"


def test_a_line_break_cannot_smuggle_a_header_in():
    account = mailer.MailAccount("h", 465, "eu@gmail.com", "x", from_name="Eu")
    message = mailer.build_message(account, "a@b.com", "Oi\r\nBcc: todos@x.com", "corpo")
    assert message["Subject"] == "Oi Bcc: todos@x.com"
    assert message["Bcc"] is None


def test_each_message_goes_to_one_address_only():
    account = mailer.MailAccount("h", 465, "eu@gmail.com", "x", from_name="Eu")
    message = mailer.build_message(account, "a@b.com", "Oi", "corpo")
    assert message["To"] == "a@b.com"
    assert message["From"] == "Eu <eu@gmail.com>"


def test_the_default_message_says_where_the_address_came_from():
    """LGPD asks for it, and so does not being reported as spam."""
    assert "descrição pública do canal" in mailer.DEFAULT_BODY
    assert "não escrevo de novo" in mailer.DEFAULT_BODY


# ------------------------------------------------------------------ a conta
def test_nothing_is_configured_at_first(app):
    state = app.get("/api/mail").json()
    assert state["configured"] is False
    assert state["subject"] == mailer.DEFAULT_SUBJECT


def test_a_gmail_address_needs_no_server_typed_in(app):
    state = app.post("/api/mail/account", json=ACCOUNT).json()
    assert state["configured"] is True
    assert (state["host"], state["port"]) == ("smtp.gmail.com", 465)


def test_the_password_never_comes_back(app):
    answer = app.post("/api/mail/account", json=ACCOUNT)
    assert "abcd" not in answer.text and "password" not in answer.json()
    assert "abcd" not in app.get("/api/mail").text


def test_the_password_is_not_on_disk_in_clear_text(app, tmp_path):
    app.post("/api/mail/account", json=ACCOUNT)
    assert "abcdefghijklmnop" not in (tmp_path / "tokens.json").read_text("utf-8")


def test_an_unknown_provider_has_to_name_its_server(app):
    refused = app.post("/api/mail/account", json={**ACCOUNT, "user": "eu@meudominio.com.br"})
    assert refused.status_code == 422
    accepted = app.post(
        "/api/mail/account",
        json={**ACCOUNT, "user": "eu@meudominio.com.br", "host": "mail.meudominio.com.br", "port": 587},
    )
    assert accepted.json()["host"] == "mail.meudominio.com.br"


def test_changing_the_limit_does_not_ask_for_the_password_again(app):
    app.post("/api/mail/account", json=ACCOUNT)
    state = app.post(
        "/api/mail/account", json={"user": "eu@gmail.com", "daily_limit": 10}
    ).json()
    assert state["daily_limit"] == 10 and state["configured"] is True


def test_a_new_address_cannot_inherit_the_old_password(app):
    app.post("/api/mail/account", json=ACCOUNT)
    refused = app.post("/api/mail/account", json={"user": "outro@gmail.com"})
    assert refused.status_code == 422


# ------------------------------------------------------------------- o envio
def test_sending_without_an_account_is_refused(app):
    main.leads.save_many([channel()])
    assert app.post("/api/mail/send", json={"lead_id": "UC1"}).status_code == 428
    assert app.sent == []


def test_a_send_writes_to_the_lead_and_marks_it_contacted(app):
    app.post("/api/mail/account", json=ACCOUNT)
    app.put("/api/mail/template", json={"subject": "Oi {canal}", "body": "Vi o {handle}"})
    main.leads.save_many([channel()])

    answer = app.post("/api/mail/send", json={"lead_id": "UC1"})

    assert answer.status_code == 200
    assert app.sent == [
        {"from": "eu@gmail.com", "to": "a@b.com", "subject": "Oi Canal", "body": "Vi o @canal"}
    ]
    lead = main.leads.get("UC1")
    assert lead["status"] == "contatado"
    assert lead["emailed_at"] is not None


def test_the_same_lead_is_not_written_to_twice(app):
    """The failure that costs a reputation: a second copy of the same pitch."""
    app.post("/api/mail/account", json=ACCOUNT)
    main.leads.save_many([channel()])
    app.post("/api/mail/send", json={"lead_id": "UC1"})

    again = app.post("/api/mail/send", json={"lead_id": "UC1"})

    assert again.status_code == 409
    assert len(app.sent) == 1


def test_writing_again_takes_saying_so(app):
    app.post("/api/mail/account", json=ACCOUNT)
    main.leads.save_many([channel()])
    app.post("/api/mail/send", json={"lead_id": "UC1"})
    assert app.post("/api/mail/send", json={"lead_id": "UC1", "resend": True}).status_code == 200
    assert len(app.sent) == 2


def test_a_channel_with_no_address_is_refused_not_guessed(app):
    app.post("/api/mail/account", json=ACCOUNT)
    main.leads.save_many([channel(email=None)])
    assert app.post("/api/mail/send", json={"lead_id": "UC1"}).status_code == 422
    assert app.sent == []


def test_a_lead_that_is_not_in_the_base_says_so(app):
    app.post("/api/mail/account", json=ACCOUNT)
    assert app.post("/api/mail/send", json={"lead_id": "UC-nao-existe"}).status_code == 404


def test_the_daily_limit_holds(app):
    app.post("/api/mail/account", json={**ACCOUNT, "daily_limit": 2})
    main.leads.save_many([channel("UC1"), channel("UC2"), channel("UC3")])

    first = app.post("/api/mail/send", json={"lead_id": "UC1"}).json()
    app.post("/api/mail/send", json={"lead_id": "UC2"})
    third = app.post("/api/mail/send", json={"lead_id": "UC3"})

    assert first["remaining_today"] == 1
    assert third.status_code == 429
    assert len(app.sent) == 2
    assert main.leads.get("UC3")["status"] == "novo"


def test_a_failed_send_leaves_the_lead_untouched(app, monkeypatch):
    """Marking it contacted would hide a lead that never got the message."""
    app.post("/api/mail/account", json=ACCOUNT)
    main.leads.save_many([channel()])

    def refuse(*_):
        raise mailer.MailError("O servidor recusou o usuário ou a senha.")

    monkeypatch.setattr(mailer, "send", refuse)
    answer = app.post("/api/mail/send", json={"lead_id": "UC1"})

    assert answer.status_code == 502
    assert "recusou" in answer.json()["detail"]
    lead = main.leads.get("UC1")
    assert lead["status"] == "novo" and lead["emailed_at"] is None
    assert app.get("/api/mail").json()["sent_today"] == 0


def test_a_refused_address_is_told_apart_from_a_broken_account(app, monkeypatch):
    """The interface skips a lead on 422 and ends the batch on 502."""
    app.post("/api/mail/account", json=ACCOUNT)
    main.leads.save_many([channel()])

    def refuse(*_):
        raise mailer.MailError("O servidor recusou o destinatário.", recipient=True)

    monkeypatch.setattr(mailer, "send", refuse)
    assert app.post("/api/mail/send", json={"lead_id": "UC1"}).status_code == 422


def test_the_test_message_goes_to_yourself_and_costs_nothing(app):
    app.post("/api/mail/account", json=ACCOUNT)
    assert app.post("/api/mail/test").status_code == 204
    assert app.sent[0]["to"] == "eu@gmail.com"
    assert app.sent[0]["subject"].startswith("[teste] ")
    assert "{canal}" not in app.sent[0]["body"]
    assert app.get("/api/mail").json()["sent_today"] == 0


# --------------------------------------------------------------- a base lembra
def test_a_later_search_does_not_forget_the_message_went_out():
    store = LeadStore(":memory:")
    store.save_many([channel()])
    store.mark_emailed("UC1")
    store.save_many([channel(title="Canal (novo nome)")])
    lead = store.get("UC1")
    assert lead["emailed_at"] is not None and lead["status"] == "contatado"


def test_writing_to_a_lead_that_answered_does_not_send_it_backwards():
    store = LeadStore(":memory:")
    store.save_many([channel()])
    store.set_status("UC1", "respondeu")
    store.mark_emailed("UC1")
    assert store.get("UC1")["status"] == "respondeu"


def test_a_base_written_before_this_column_existed_still_opens(tmp_path):
    path = tmp_path / "leads.db"
    LeadStore(str(path)).save_many([channel()])
    with sqlite3.connect(path) as conn:
        conn.execute("ALTER TABLE leads DROP COLUMN emailed_at")
        conn.commit()

    reopened = LeadStore(str(path))
    assert reopened.get("UC1")["emailed_at"] is None
    assert reopened.mark_emailed("UC1")
    assert reopened.emailed_since("2000-01-01") == 1
