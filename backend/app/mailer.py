"""Writing to the channels that published an address.

The app already knew who to write to and where; the last step — opening a mail
client, pasting the address, pasting the text, coming back to mark the row —
was being done by hand, once per lead. This sends that message through the
user's own mailbox over SMTP.

Three decisions shape the module:

* **The user's own account, nothing else.** No relay and no sending service:
  the message leaves from the address the reply will come back to, and the
  password sits in the same vault as the API keys.
* **One message per recipient.** Never a shared To or a Bcc list. Each lead
  gets a message addressed to them alone, with their own channel named in it.
* **A daily ceiling the sender cannot talk past.** A mailbox that sends two
  hundred near-identical messages in an afternoon gets flagged, and a flagged
  mailbox stops delivering the ordinary mail too. The cap is enforced here, in
  the backend, so a stuck loop in the interface cannot exceed it.

smtplib is blocking, so callers run :func:`send` in a thread.
"""

from __future__ import annotations

import json
import smtplib
import ssl
from dataclasses import asdict, dataclass
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from typing import Any

#: Messages per rolling 24 hours unless the user picks another number. Well
#: under what any provider allows; the limit that matters is the spam filter's.
DEFAULT_DAILY_LIMIT = 40

#: The most a user can raise it to. Gmail's own ceiling is 500 a day.
MAX_DAILY_LIMIT = 300

#: Names the template can use, and what each one is replaced by.
PLACEHOLDERS = ("canal", "handle", "nicho", "inscritos")

DEFAULT_SUBJECT = "Edição de vídeo para o {canal}"

# The last paragraph is not decoration. LGPD asks the sender to say how the
# address was obtained and to honour a request to stop, and a message that does
# both is also the one least likely to be reported as spam.
DEFAULT_BODY = """Olá, pessoal do {canal}!

Acompanho o canal e vi que vocês publicam com frequência. Sou editor de vídeo e trabalho com canais de {nicho}: cortes, ritmo, legendas e thumbnail.

Posso editar um vídeo de vocês como teste, sem compromisso, para verem o resultado antes de decidir qualquer coisa.

Se fizer sentido, é só responder este e-mail.

Abraço,
[seu nome]

—
Encontrei este endereço na descrição pública do canal no YouTube. Se preferir não receber mensagens minhas, responda pedindo e eu não escrevo de novo."""


class MailError(Exception):
    """Sending failed, with a message written for the person at the screen.

    ``recipient`` separates the two kinds of failure a batch has to tell apart:
    one bad address is a reason to skip a lead, a broken account is a reason to
    stop before the same error repeats for every lead left.
    """

    def __init__(self, message: str, *, recipient: bool = False) -> None:
        super().__init__(message)
        self.recipient = recipient


@dataclass
class MailAccount:
    host: str
    port: int
    user: str
    password: str
    from_name: str = ""
    daily_limit: int = DEFAULT_DAILY_LIMIT

    def dumps(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def loads(cls, raw: str) -> "MailAccount | None":
        """The saved account, or None when nothing usable is stored."""
        try:
            data = json.loads(raw)
            return cls(
                host=str(data["host"]),
                port=int(data["port"]),
                user=str(data["user"]),
                password=str(data["password"]),
                from_name=str(data.get("from_name") or ""),
                daily_limit=int(data.get("daily_limit") or DEFAULT_DAILY_LIMIT),
            )
        except (ValueError, KeyError, TypeError):
            return None


#: Where the big providers listen, keyed by the domain of the address. Saves
#: the user from looking up a host name for the three cases that cover most
#: people; anything else is typed in.
KNOWN_HOSTS: dict[str, tuple[str, int]] = {
    "gmail.com": ("smtp.gmail.com", 465),
    "googlemail.com": ("smtp.gmail.com", 465),
    "outlook.com": ("smtp-mail.outlook.com", 587),
    "hotmail.com": ("smtp-mail.outlook.com", 587),
    "live.com": ("smtp-mail.outlook.com", 587),
    "yahoo.com": ("smtp.mail.yahoo.com", 465),
    "yahoo.com.br": ("smtp.mail.yahoo.com", 465),
    "icloud.com": ("smtp.mail.me.com", 587),
    "zoho.com": ("smtp.zoho.com", 465),
}


def guess_host(address: str) -> tuple[str, int] | None:
    domain = address.rsplit("@", 1)[-1].strip().lower()
    return KNOWN_HOSTS.get(domain)


def _one_line(text: str) -> str:
    """A header value. A line break in one would start a header of its own."""
    return " ".join(text.split())


def render(template: str, lead: dict[str, Any]) -> str:
    """Fill the template's placeholders from one lead.

    Plain replacement rather than ``str.format``: a body is free text, and a
    stray brace in it must stay a brace instead of raising.
    """
    subscribers = int(lead.get("subscribers") or 0)
    values = {
        "canal": lead.get("title") or "",
        "handle": lead.get("handle") or "",
        "nicho": lead.get("niche") or "",
        "inscritos": f"{subscribers:,}".replace(",", "."),
    }
    out = template
    for name in PLACEHOLDERS:
        out = out.replace("{%s}" % name, str(values[name]))
    return out


def build_message(
    account: MailAccount, to: str, subject: str, body: str
) -> EmailMessage:
    message = EmailMessage()
    message["From"] = formataddr((_one_line(account.from_name), account.user))
    message["To"] = _one_line(to)
    message["Subject"] = _one_line(subject)
    message["Date"] = formatdate(localtime=True)
    message["Message-ID"] = make_msgid(domain=account.user.rsplit("@", 1)[-1])
    message.set_content(body)
    return message


def _connect(account: MailAccount) -> smtplib.SMTP:
    context = ssl.create_default_context()
    # 465 speaks TLS from the first byte; every other port starts in the clear
    # and is upgraded. Nothing is ever sent before the channel is encrypted.
    if account.port == 465:
        server: smtplib.SMTP = smtplib.SMTP_SSL(
            account.host, account.port, timeout=20, context=context
        )
    else:
        server = smtplib.SMTP(account.host, account.port, timeout=20)
        server.starttls(context=context)
    server.login(account.user, account.password)
    return server


def send(account: MailAccount, to: str, subject: str, body: str) -> None:
    """Send one message to one address. Raises MailError with the reason."""
    message = build_message(account, to, subject, body)
    try:
        server = _connect(account)
        try:
            server.send_message(message)
        finally:
            try:
                server.quit()
            except smtplib.SMTPException:
                pass
    except smtplib.SMTPAuthenticationError as error:
        raise MailError(
            "O servidor recusou o usuário ou a senha. No Gmail e no Outlook a "
            "senha da conta não serve: é preciso gerar uma senha de app."
        ) from error
    except smtplib.SMTPRecipientsRefused as error:
        raise MailError(
            f"O servidor recusou o destinatário {to}.", recipient=True
        ) from error
    except smtplib.SMTPServerDisconnected as error:
        # Measured against Gmail: a login it does not like is not always
        # answered with an authentication error — the server may just hang up.
        raise MailError(
            "O servidor encerrou a conexão sem aceitar o envio. Quase sempre é "
            "o e-mail ou a senha de app errados; se os dois estiverem certos, "
            "um antivírus ou a rede pode estar bloqueando o envio."
        ) from error
    except smtplib.SMTPException as error:
        raise MailError(f"O servidor de e-mail respondeu com erro: {error}") from error
    except (OSError, ssl.SSLError) as error:
        raise MailError(
            f"Não foi possível conectar em {account.host}:{account.port}. "
            "Confira o servidor, a porta e a sua internet."
        ) from error
