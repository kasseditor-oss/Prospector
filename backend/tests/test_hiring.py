"""Client or competitor.

The pairs below are the whole problem: nearly identical wording, opposite
meaning. Every "offering" case here is a post that a keyword search would
hand the reader as a lead, and every one of those is a wasted minute plus the
small insult of being sold to by your own search tool.
"""

from __future__ import annotations

import pytest

from app.hiring import classify


# ------------------------------------------------------- the confusable pairs
@pytest.mark.parametrize(
    "text",
    [
        "I'm looking for a video editor for my gaming channel",
        "Looking for a video editor, long term",
        "I need a video editor for weekly uploads",
        "[Hiring] Video Editor for Minecraft content",
        "hiring a video editor, DM your rates",
        "Preciso de um editor de vídeo para meu canal",
        "Procuro editor de vídeo para cortes",
        "procurando por um editor de video",
        "Contratando editor de vídeo para canal de games",
        "Alguém indica um editor de vídeo bom?",
        "anyone know a good video editor?",
        "Can anyone recommend a video editor for shorts?",
        "We want a video editor to join our team",
        # Found by stress-testing, not by design: the ask is "looking TO HIRE",
        # never "looking FOR", and the role is not named at all.
        "Looking to hire a video editor for my podcast",
        "trying to hire someone to edit my videos",
    ],
)
def test_a_client_is_recognised(text):
    assert classify(text).is_lead, text


@pytest.mark.parametrize(
    "text",
    [
        "I'm a video editor looking for work",
        "I am a video editor, available for hire",
        "[For Hire] Video Editor, 5 years experience",
        "Video editor here — hire me for your next project",
        "I'm an experienced video editor looking for long term clients",
        "Sou editor de vídeo e estou procurando clientes",
        "Sou um editor de vídeo disponível para projetos",
        "editor de vídeo, meu portfólio: youtube.com/exemplo",
        "Ofereço serviços de edição de vídeo, preço: R$ 50 por vídeo",
        "Video editor available for work. My rates start at $30",
        "DM me for video editing, fast turnaround",
        # Also from stress-testing: sells the service without the word
        # "serviços", which the first pass required.
        "Ofereço edição de vídeo para YouTubers, orçamento sob consulta",
        "Offering video editing for small channels",
    ],
)
def test_a_competitor_is_rejected(text):
    verdict = classify(text)
    assert verdict.kind == "offering", f"{text} -> {verdict.kind}"
    assert not verdict.is_lead


def test_the_hardest_pair_of_all():
    """One word apart, opposite meaning. If anything regresses, it is this."""
    client = classify("I'm looking for a video editor")
    rival = classify("I'm a video editor looking for work")

    assert client.is_lead
    assert not rival.is_lead


def test_self_description_beats_hiring_words():
    """A competitor's advert often quotes the hiring language it answers."""
    text = (
        "I'm a video editor. If you're looking for a video editor "
        "for long term work, DM me for my rates."
    )
    assert classify(text).kind == "offering"


# -------------------------------------------------------------------- signals
def test_money_in_the_post_is_flagged():
    assert classify("[Hiring] video editor - $50 per video").budget
    assert classify("Preciso de um editor de vídeo, pago R$ 200").budget


def test_a_post_without_money_is_not_flagged_as_paid():
    assert not classify("Looking for a video editor for my channel").budget


def test_recurring_work_is_flagged():
    assert classify("Looking for a video editor, long term").ongoing
    assert classify("Procuro editor de vídeo, trabalho mensal").ongoing


def test_one_off_work_is_not_flagged_as_recurring():
    assert not classify("Need a video editor for one video").ongoing


# -------------------------------------------------------------------- unclear
@pytest.mark.parametrize(
    "text",
    [
        "Just finished editing my new video, what do you think?",
        "What software do you use for video editing?",
        "My video editor quit and I don't know what to do",
        "",
        "   ",
    ],
)
def test_everything_else_is_unclear_not_a_lead(text):
    """Unclear is its own answer. Guessing here is how the list fills up
    with noise the reader has to sort by hand."""
    verdict = classify(text)
    assert not verdict.is_lead
    assert verdict.kind in ("unclear", "offering")


def test_the_deciding_phrase_is_reported():
    """The UI shows why a post was picked, so a bad rule is visible."""
    verdict = classify("[Hiring] Video Editor for weekly uploads")
    assert verdict.matched
    assert "hiring" in verdict.matched.lower()


# ============================================ isca de palavra-chave (do X real)
# Textos colhidos numa busca real. Três de sete supostos leads eram editores
# grudando a lista de buscas do cliente no fim do próprio anúncio.
REAL_STUFFED = [
    "+1 projeto terminado com sucesso tags: busco editor, editor de video, "
    "procuro editor de video https://t.co/aD8PjDzVRi",
    "somente um teste mas feito com qualidade quem quiser um editor de video "
    "chama dm TAGS: procuro editor de vídeo, edição de video, hire a video "
    "editor, video editor, video edit",
    "vídeo autoral pro perfil nao ficar tao parado qr algo assim? entra em "
    "contato tags: procuro editor de vídeo, edição de video, hire a video "
    "editor, video editor, video edit",
]


@pytest.mark.parametrize("text", REAL_STUFFED)
def test_keyword_bait_is_not_a_lead(text):
    """The phrase a client would type, planted by a competitor to be found."""
    assert not classify(text).is_lead


@pytest.mark.parametrize("text", REAL_STUFFED)
def test_keyword_bait_is_reported_as_such(text):
    assert classify(text).stuffed


def test_a_genuine_request_is_untouched_by_the_tag_rule():
    """Real asks from the same search must survive the fix."""
    for text in [
        "Preciso de um editor de vídeo que saiba fazer motion gráfico animado",
        "Procuro editor de vídeo curto (tiktok/reels) para conteúdo de futebol",
        "Procuro Editor de vídeo para canal de Futebol, quero alguém que possa "
        "fazer uma parceria de longo prazo",
        "Procuro editor de vídeo (não é relacionado a games/esports)",
    ]:
        verdict = classify(text)
        assert verdict.is_lead, text
        assert not verdict.stuffed


def test_a_client_who_happens_to_write_tags_is_still_a_client():
    """Cutting the tail must not cut the request itself."""
    assert classify("Preciso de um editor de vídeo. tags: edicao, freela").is_lead


def test_a_keyword_list_without_the_word_tags_is_still_bait():
    """Real bait carries no label — just the role, over and over."""
    text = (
        "mais uma edição feita para o @TheBieeLkk, essa é a parte final. "
        "Procuro editor, preciso editor, editor de vídeos, video editor/"
        "Looking for an editor"
    )
    verdict = classify(text)
    assert not verdict.is_lead
    assert verdict.stuffed


# ================================================= mais casos colhidos do X real
@pytest.mark.parametrize(
    "text",
    [
        # A necessidade é de terceiros, e o autor está vendendo para eles.
        "Algorithm, you can push this to sports creators who need a video editor, okay?",
        # Vendendo para o leitor: o projeto é dele, não do autor.
        "Custom subtitles, Sound Effects and dynamic pacing. Need a video editor "
        "to elevate your content like this?",
        # Reclamação, não contratação.
        "@NFL Who tf has been posting videos lately? Y'all need a video editor or sum shit?",
        # Currículo: anos de experiência pertencem a quem é contratado.
        "Need a video editor who can work under pressure? 10+ years of TV broadcasting experience",
        "Recent sample edit What do you think? Hiring a video editor, send me a dm",
    ],
)
def test_more_real_competitors_are_rejected(text):
    assert not classify(text).is_lead


@pytest.mark.parametrize(
    "text",
    [
        "Hiring a video editor for my League of Legends documentary channel. $300/video",
        "@AdegbemboB I need a video editor for my YouTube channel 250k naira up",
        "Still need a video editor for my past stream, 4h of footage",
        "preciso de um editor de videos pra videos de roblox - 1 video por semana",
        "I will need a video editor for my small team soon",
        # Espanhol: mercado vizinho, e perder isto custou um lead real no teste.
        "Estoy buscando editor de video para mi equipo de YouTube. Pagamos caro",
        "Necesito un editor de video para mi canal",
    ],
)
def test_more_real_clients_are_kept(text):
    assert classify(text).is_lead


def test_the_body_is_read_not_just_the_title():
    verdict = classify("Need help with my channel", "Looking for a video editor, $40 per edit")
    assert verdict.is_lead
    assert verdict.budget
