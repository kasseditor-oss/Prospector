"""Where a lead stands with you.

Four steps, because that is the whole funnel for one person selling editing:
you have not written yet, you wrote, they answered, it turned into work. A
fifth step would be someone else's process, and every extra option is one more
decision at the moment the reader just wants to mark a row and move on.

The vocabulary lives here rather than in either store because a channel and a
hiring post are followed up identically — the thing being tracked is the
conversation, not the kind of lead — and two copies of this list would drift
the first time one of them gained a step.
"""

from __future__ import annotations

#: Stored value -> what the interface calls it.
STATUSES: dict[str, str] = {
    "novo": "Não contatado",
    "contatado": "Contatado",
    "respondeu": "Respondeu",
    "parceria": "Parceria",
}

#: What a lead is before anyone touches it.
DEFAULT_STATUS = "novo"


def is_valid(status: str) -> bool:
    return status in STATUSES


def clean(status: str | None) -> str:
    """A stored value the interface can render, whatever came in.

    A row written before this column existed, or by a newer version that added
    a step, still has to draw as something rather than as a blank cell.
    """
    value = (status or "").strip().lower()
    return value if value in STATUSES else DEFAULT_STATUS
