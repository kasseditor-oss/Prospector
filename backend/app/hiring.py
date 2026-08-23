"""Telling a client apart from a competitor.

Searching X or Reddit for "video editor" returns two populations mixed
together: people who want to hire one, and editors advertising themselves.
They use nearly the same words —

    "I'm looking for a video editor"       a client
    "I'm a video editor looking for work"  a competitor

— so keyword matching alone produces a list where half the rows are the
reader's own competition. That is worse than an empty list, because it costs
attention before it can be dismissed.

The rule that separates them is not the vocabulary but *who the author says
they are*. An editor advertising describes themselves as the editor; a client
describes the editor as someone else. So self-description is checked first and
wins outright: a post that says "I am an editor" is never a lead, no matter how
many hiring words follow it.

Portuguese and English are both matched, because the reader works in one and
the market speaks the other.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: What the reader sells. Kept apart from the verbs so a new role — motion
#: designer, thumbnail artist — is one line rather than a rewrite.
_ROLE = r"(?:video\s*)?edit(?:or|ora|ors)\b|\beditor\s+de\s+v[ií]deo|\bvideo\s*editing\b"

# Words that hand the role to someone else. Without this guard, "I'm looking
# for a video editor" reads as "I am ... editor" and the best lead in the list
# gets thrown away as a competitor — the single worst failure this module can
# have, because it is silent.
_HANDS_OFF = (
    r"looking|searching|seeking|need|needs|want|wants|hiring|hire|for"
    r"|procur\w*|precis\w*|contrat\w*|busc\w*|quero|queria"
)

#: Up to three words between the self-reference and the role, none of which
#: may be one of the words above.
_GAP = r"(?:(?!(?:" + _HANDS_OFF + r")\b)\w+\s+){0,3}?"

# ---------------------------------------------------------------- competitor
# Checked first and final. "I am the editor" settles the question: whatever
# else the post says, the author is not looking to pay someone.
_OFFERING = (
    # Reddit and forum tags are unambiguous, so they lead.
    r"\[\s*for\s*hire\s*\]",
    r"\[\s*dispon[ií]vel\s*\]",
    # First person + the role. "I'm a video editor", "sou editor de vídeo".
    r"\b(?:i\s*(?:'|’)?\s*a?m|i\s+am)\s+(?:an?\s+)?" + _GAP + r"(?:" + _ROLE + r")",
    r"\b(?:sou|somos)\s+(?:um[ao]?\s+)?" + _GAP + r"(?:" + _ROLE + r")",
    # Selling language, regardless of how the sentence opens.
    r"\bhire\s+me\b",
    r"\bme\s+contrat[ae]\b",
    r"\bmy\s+portfolio\b",
    r"\bmeu\s+portf[óo]lio\b",
    r"\b(?:available|open)\s+for\s+(?:work|hire|commissions|projects)\b",
    r"\bdispon[ií]vel\s+para\s+(?:trabalho|projetos|freela)",
    r"\bofere[çc]o\s+(?:meus\s+)?(?:\w+\s+){0,2}?(?:servi[çc]os|edi[çc][ãaõo]\w*)",
    r"\boffering\s+(?:my\s+)?(?:\w+\s+){0,2}?(?:video\s*)?edit(?:ing|s)?\b",
    r"\bpre[çc]o\s*:\s*",
    r"\bmy\s+rates?\b",
    r"\bdm\s+me\s+(?:for|if\s+you)\b",
    # "quem quiser um editor de vídeo chama dm" — the author is the one being
    # contacted, so the role belongs to them.
    r"\bquem\s+quiser\s+(?:um[ao]?\s+)?" + _GAP + r"(?:" + _ROLE + r")",
    r"\b(?:chama|chame|manda)\s+(?:na\s+)?(?:dm|direct|pv)\b",
    # The advert written as a question aimed at the reader — "Looking for a
    # video editor?" — is the most common disguise in real results: it borrows
    # the client's exact words and flips who is being addressed.
    r"\b(?:looking\s+for|need|needs|hiring|want)\s+(?:an?\s+)?" + _GAP + r"(?:" + _ROLE + r")\s*\?",
    r"\b(?:procur\w+|precis\w+)\s+(?:de\s+)?(?:um[ao]?\s+)?" + _GAP + r"(?:" + _ROLE + r")\s*\?",
    # Conditional addressed to the reader: the need is theirs, not the author's.
    r"\bif\s+(?:you|u)\s*(?:'|’)?\s*(?:re\b|are\b)?\s*(?:need|want|looking)",
    r"\bse\s+(?:voc[êe]|vc)\s+(?:precisa|quer|procura|t[áa]\s+procurando)",
    # "editor for your channel" — selling into the reader's project.
    r"(?:" + _ROLE + r")\s+(?:for|to)\s+your\b",
    r"\bdm(?:'|’)?s?\s+(?:are\s+)?open\b",
    r"\blet(?:'|’)?s\s+work\s+together\b",
    # The need belongs to somebody else in the sentence — "creators who need a
    # video editor", "y'all need a video editor". Either the author is selling
    # to them or is complaining about them; neither is a client. "I need" is
    # deliberately absent from this list.
    r"\b(?:who|that|y[’']?all|you|they|people|creators?|brands?|everyone)\s+needs?\b",
    # "an editor to elevate your content" — the project being pitched is the
    # reader's, so the author is the supplier.
    r"\byour\s+(?:content|channel|videos?|brand|business|project|edits?)\b",
    # An invitation to contact the author, and a CV. Both belong to whoever is
    # being hired, never to whoever is hiring.
    r"\b(?:send|shoot)\s+me\s+(?:a\s+)?dm\b",
    r"\b\d+\+?\s*(?:years?|anos)\s+(?:of\s+)?(?:\w+\s+){0,3}?(?:experience|experi[êe]ncia)\b",
)

# ------------------------------------------------------------------- client
_HIRING = (
    r"\[\s*hiring\s*\]",
    r"\[\s*contratando\s*\]",
    r"\b(?:looking|searching)\s+for\s+(?:an?\s+)?(?:\w+\s+){0,3}?(?:" + _ROLE + r")",
    r"\b(?:need|want)\s+(?:an?\s+)?(?:\w+\s+){0,3}?(?:" + _ROLE + r")",
    r"\bhiring\s+(?:an?\s+)?(?:\w+\s+){0,3}?(?:" + _ROLE + r")",
    # "looking to hire", "trying to hire" — nobody advertising themselves
    # phrases it this way, so the role does not need to be named.
    r"\b(?:looking|want|wanting|need|needing|trying)\s+to\s+hire\b",
    # Spanish: neighbouring markets hire Brazilian editors, and dropping them
    # cost a real lead in testing — "Estoy buscando editor de video".
    r"\b(?:estoy\s+)?busc(?:o|ando)\s+(?:un[ao]?\s+)?" + _GAP + r"(?:" + _ROLE + r"|editor\s+de\s+v[ií]deo)",
    r"\bnecesit(?:o|amos)\s+(?:un[ao]?\s+)?" + _GAP + r"(?:" + _ROLE + r")",
    r"\bprecis(?:o|amos)\s+de\s+(?:um[ao]?\s+)?(?:\w+\s+){0,3}?(?:" + _ROLE + r")",
    r"\bprocur(?:o|ando|amos)\s+(?:por\s+)?(?:um[ao]?\s+)?(?:\w+\s+){0,3}?(?:" + _ROLE + r")",
    r"\bcontrat(?:o|ando|ar)\s+(?:um[ao]?\s+)?(?:\w+\s+){0,3}?(?:" + _ROLE + r")",
    r"\b(?:algu[ée]m|alguem)\s+(?:conhece|indica|recomenda)\s+(?:um[ao]?\s+)?(?:\w+\s+){0,3}?(?:" + _ROLE + r")",
    r"\b(?:anyone|anybody)\s+(?:know|recommend)\s+(?:of\s+)?(?:an?\s+)?(?:\w+\s+){0,3}?(?:" + _ROLE + r")",
    r"\brecommend\s+(?:me\s+)?(?:an?\s+)?(?:\w+\s+){0,3}?(?:" + _ROLE + r")",
)

# ------------------------------------------------------------------- signals
# A post that names money is a post from someone who has decided to spend it.
_BUDGET = (
    r"[R$]{0,2}\s?\$\s?\d",
    r"\bR\$\s?\d",
    r"\b\d+\s*(?:usd|dollars|reais|brl)\b",
    r"\bper\s+(?:video|edit|hour|minute)\b",
    r"\bpor\s+v[ií]deo\b",
    r"\bpaid\b",
    r"\bbudget\b",
    r"\bor[çc]amento\b",
    r"\bpago\b",
)

_LONG_TERM = (
    r"\blong[\s-]?term\b",
    r"\bongoing\b",
    r"\bfixo\b",
    r"\bmensal\b",
    r"\bmonthly\b",
    r"\bfull[\s-]?time\b",
    r"\bper\s+week\b",
    r"\bpor\s+semana\b",
)


def _compile(patterns: tuple[str, ...]) -> list[re.Pattern[str]]:
    return [re.compile(p, re.IGNORECASE) for p in patterns]


_OFFERING_RE = _compile(_OFFERING)
_HIRING_RE = _compile(_HIRING)
_BUDGET_RE = _compile(_BUDGET)
_LONG_TERM_RE = _compile(_LONG_TERM)


@dataclass(frozen=True)
class Verdict:
    """What a post is, and why."""

    #: "hiring", "offering" or "unclear".
    kind: str
    #: Mentions money.
    budget: bool = False
    #: Reads like recurring work rather than one job.
    ongoing: bool = False
    #: The phrase that decided it, so the UI can show its reasoning.
    matched: str = ""
    #: The post carried a keyword list aimed at hijacking client searches.
    stuffed: bool = False

    @property
    def is_lead(self) -> bool:
        return self.kind == "hiring"


# Editors append a keyword list to their own portfolio posts so they surface in
# the searches clients run — "tags: procuro editor de vídeo, hire a video
# editor". Found in real results, where it accounted for three of seven
# supposed leads. The stuffing is not the message, so it is cut off before the
# post is judged: what remains is what the author actually said.
_TAG_DUMP = re.compile(r"\b(?:tags?|hashtags?)\s*[:：]\s*.*$", re.IGNORECASE | re.DOTALL)


#: Naming the role this many times is a keyword list, not a sentence. Real
#: results carry lists with no "tags:" label at all — "Procuro editor, preciso
#: editor, editor de vídeos, video editor/Looking for an editor" — so counting
#: is what catches those.
_STUFFING_REPEATS = 3
_ROLE_RE = re.compile(_ROLE, re.IGNORECASE)


def strip_keyword_stuffing(text: str) -> tuple[str, bool]:
    """The post without its trailing tag list, and whether one was found."""
    cleaned = _TAG_DUMP.sub("", text).strip()
    if cleaned != text.strip():
        return cleaned, True
    if len(_ROLE_RE.findall(cleaned)) >= _STUFFING_REPEATS:
        # A list, and nothing in it is a request. Emptying it means the post is
        # judged on whatever prose surrounds it, which is usually a portfolio.
        return _ROLE_RE.sub("", cleaned), True
    return cleaned, False


def _first_match(text: str, patterns: list[re.Pattern[str]]) -> str:
    for pattern in patterns:
        found = pattern.search(text)
        if found:
            return found.group(0).strip()
    return ""


def classify(title: str, body: str = "") -> Verdict:
    """Read a post and decide whether its author wants to pay for editing.

    ``title`` carries far more weight in practice — Reddit tags live there and
    tweets are all title — but the body is where budgets get mentioned, so
    both are read.
    """
    raw = f"{title}\n{body}".strip()
    if not raw:
        return Verdict(kind="unclear")

    # Judge the message, not the keyword bait glued to the end of it.
    text, stuffed = strip_keyword_stuffing(raw)

    # Self-description first and final. Anything else risks reading a
    # competitor's advertisement as an opportunity.
    offering = _first_match(text, _OFFERING_RE)
    if offering:
        return Verdict(kind="offering", matched=offering, stuffed=stuffed)

    hiring = _first_match(text, _HIRING_RE)
    if not hiring:
        return Verdict(kind="unclear", stuffed=stuffed)

    return Verdict(
        kind="hiring",
        budget=bool(_first_match(text, _BUDGET_RE)),
        ongoing=bool(_first_match(text, _LONG_TERM_RE)),
        matched=hiring,
        stuffed=stuffed,
    )
