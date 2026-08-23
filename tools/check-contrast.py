"""Contrast check for every pair the interface actually renders.

Ratios come from WCAG 2.x relative luminance. Text needs 4.5:1 (3:1 when it is
large), and non-text boundaries - borders, meter fills, focus rings - need 3:1.
"""

import sys


def luminance(hex_colour: str) -> float:
    hex_colour = hex_colour.lstrip("#")
    channels = [int(hex_colour[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def ratio(a: str, b: str) -> float:
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


DARK = {
    "bay": "#06070A",
    "panel": "#10131A",
    "panel-2": "#171B23",
    "panel-3": "#1F242E",
    "rule": "#272D38",
    "rule-2": "#626D7C",
    "ink": "#EDF1F6",
    "ink-2": "#9BA6B4",
    "ink-3": "#7C8794",
    "signal": "#4C8DFF",
    "signal-bright": "#75A9FF",
    "signal-soft": "#0F1B2F",
    "signal-ink": "#03070F",
    "meter-lo": "#69737F",
    "meter-mid": "#E0A03A",
    "meter-hi": "#4C8DFF",
    "warn": "#E8A33D",
    "warn-soft": "#2A1F0C",
    "danger": "#F0736A",
    "danger-soft": "#2C1310",
}

LIGHT = {
    "bay": "#E9ECEF",
    "panel": "#FFFFFF",
    "panel-2": "#F2F4F7",
    "panel-3": "#E4E8ED",
    "rule": "#C7D0DA",
    "rule-2": "#7E8896",
    "ink": "#12161B",
    "ink-2": "#4B5663",
    "ink-3": "#5F6A76",
    "signal": "#1B57D6",
    "signal-bright": "#2E6BF0",
    "signal-soft": "#E3ECFD",
    "signal-ink": "#FFFFFF",
    "meter-lo": "#7A8590",
    "meter-mid": "#8A5D14",
    "meter-hi": "#1B57D6",
    "warn": "#8A5D14",
    "warn-soft": "#F7EBD7",
    "danger": "#B03A2E",
    "danger-soft": "#F8E3E0",
}

# (foreground, background, minimum, what renders it)
TEXT = [
    ("ink", "bay", 4.5, "corpo sobre o fundo da página"),
    ("ink", "panel", 4.5, "corpo em painel"),
    ("ink", "panel-2", 4.5, "linha da tabela em hover"),
    ("ink-2", "panel", 4.5, "texto secundário"),
    ("ink-2", "panel-2", 4.5, "secundário no cabeçalho da tabela"),
    ("ink-2", "bay", 4.5, "subtítulo da página"),
    ("ink-3", "panel", 4.5, "rótulos e dicas (10-12px)"),
    ("ink-3", "panel-2", 4.5, "cabeçalho de coluna"),
    ("ink-3", "bay", 4.5, "rodapé da barra lateral"),
    ("signal", "panel", 4.5, "link e valor em destaque"),
    ("signal", "bay", 4.5, "item ativo da barra lateral"),
    ("signal", "panel-2", 4.5, "coluna ordenada"),
    ("signal", "signal-soft", 4.5, "chip de nicho"),
    ("signal-ink", "signal", 4.5, "texto do botão primário"),
    ("warn", "panel", 4.5, "aviso"),
    ("warn", "warn-soft", 4.5, "faixa de aviso"),
    ("danger", "panel", 4.5, "erro"),
    ("danger", "danger-soft", 4.5, "faixa de erro"),
]

# WCAG 1.4.11 covers what is *required to identify* a control. A field border
# qualifies - without it the input is invisible. A hairline between table rows
# does not: the rows are told apart by their content and spacing, so it is
# reported below as decoration rather than enforced.
NON_TEXT = [
    ("rule-2", "panel", 3.0, "borda de campo de formulário"),
    ("rule-2", "panel-2", 3.0, "borda de campo em painel elevado"),
    ("signal", "panel", 3.0, "anel de foco"),
    ("signal", "bay", 3.0, "anel de foco sobre o fundo"),
    ("meter-hi", "panel", 3.0, "barra de score alta"),
    ("meter-mid", "panel", 3.0, "barra de score média"),
    ("meter-lo", "panel", 3.0, "barra de score baixa / cadência"),
    ("meter-lo", "panel-2", 3.0, "cadência em hover"),
]


DECORATIVE = [
    ("rule", "panel", "borda de painel"),
    ("rule", "bay", "divisória entre linhas"),
]


def check(name: str, palette: dict) -> int:
    print(f"\n=== {name} ===")
    failures = 0
    for group, pairs in (("texto", TEXT), ("não-texto", NON_TEXT)):
        for fg, bg, minimum, what in pairs:
            value = ratio(palette[fg], palette[bg])
            ok = value >= minimum
            if not ok:
                failures += 1
            mark = "  " if ok else "XX"
            print(f"{mark} {value:5.2f}:1  (min {minimum})  {fg} sobre {bg:9} - {what}")
    for fg, bg, what in DECORATIVE:
        print(f"    {ratio(palette[fg], palette[bg]):5.2f}:1  (decorativo)  {fg} sobre {bg:9} - {what}")
    return failures


# Brand marks (--br-*). A logo has to look like itself, so these are the real
# brand colours per theme. They are meaningful graphics, not text, so 3:1.
BRANDS = {
    "instagram": ("#E1306C", "#C1275C"),
    "tiktok": ("#25F4EE", "#0F6F6B"),
    "x": ("#9CA9BC", "#15181C"),
    "discord": ("#7C8BF5", "#4A57C8"),
    "twitch": ("#A970FF", "#7B36E8"),
    "telegram": ("#3FA3E0", "#1B7FB4"),
    "threads": ("#C0C8D4", "#1A1D21"),
    "facebook": ("#1877F2", "#1266D6"),
    "linkedin": ("#38A0DC", "#0A66C2"),
    "kick": ("#53FC18", "#3B8F12"),
}


def check_brands() -> int:
    print("\n=== MARCAS (icones de redes) ===")
    failures = 0
    for name, (dark, light) in BRANDS.items():
        rd = ratio(dark, DARK["panel"])
        rl = ratio(light, LIGHT["panel"])
        ok = rd >= 3.0 and rl >= 3.0
        failures += 0 if ok else 1
        print(f"{'  ' if ok else 'XX'} {name:11} escuro {rd:5.2f}:1   claro {rl:5.2f}:1")
    return failures


total = check("ESCURO", DARK) + check("CLARO", LIGHT) + check_brands()
print(f"\n{'TUDO PASSOU' if total == 0 else f'{total} PARES REPROVADOS'}")
sys.exit(1 if total else 0)
