"""Mise en page commune des e-mails de PILOT, au style « PILOT 2040 » de l'application :
fond sombre, carte, liseré néon et bouton lumineux.

Les e-mails n'acceptent ni feuille de style ni police web fiables : tout est écrit en styles
en ligne, dans des tableaux, avec une couleur de secours sous chaque dégradé (Outlook ignore
les dégradés). Les textes fournis sont échappés ici ; seul `extra_html` est inséré tel quel
et doit donc être construit avec `html.escape`.
"""

import html

PAGE = "#05060b"
CARD = "#0f1220"
LINE = "#23263a"
INK = "#eef1fb"
SOFT = "#c4cadb"
MUTED = "#8f97ac"
NEON = "linear-gradient(90deg,#ff7a1a,#ff3d81 45%,#8b5cf6 75%,#22d3ee)"
BUTTON = "linear-gradient(135deg,#d9480f,#b0245e)"
# Guillemets doubles : les styles sont écrits entre apostrophes.
FONT = '"Segoe UI",Helvetica,Arial,sans-serif'
MONO = '"SFMono-Regular",Menlo,Consolas,monospace'


def pill(label: str, color: str) -> str:
    """Pastille de couleur (règle d'alerte, statut…)."""
    return (
        f"<span style='display:inline-block;padding:3px 10px;border-radius:999px;"
        f"border:1px solid {color};color:{color};font-family:{MONO};font-size:11px;"
        f"font-weight:600;letter-spacing:.04em;text-transform:uppercase;white-space:nowrap'>"
        f"{html.escape(label)}</span>"
    )


def render_email(
    *,
    kicker: str,
    title: str,
    paragraphs: list[str],
    button_label: str | None = None,
    button_url: str | None = None,
    extra_html: str = "",
    footer: str,
    preheader: str = "",
) -> str:
    """Construit un e-mail complet. `paragraphs`, `kicker`, `title`, `footer` sont du texte."""
    body = "".join(
        f"<p style='margin:0 0 14px;font-size:15px;line-height:1.6;color:{SOFT}'>"
        f"{html.escape(p)}</p>"
        for p in paragraphs
    )
    button = ""
    if button_label and button_url:
        url = html.escape(button_url)
        button = (
            "<table role='presentation' cellpadding='0' cellspacing='0' style='margin:22px 0 6px'>"
            f"<tr><td bgcolor='#d9480f' style='border-radius:12px;background:#d9480f;"
            f"background-image:{BUTTON};box-shadow:0 8px 24px rgba(217,72,15,.35)'>"
            f"<a href='{url}' style='display:inline-block;padding:13px 26px;font-family:{FONT};"
            f"font-size:15px;font-weight:700;color:#ffffff;text-decoration:none;"
            f"border-radius:12px'>{html.escape(button_label)} &rarr;</a></td></tr></table>"
            f"<p style='margin:10px 0 0;font-size:12px;color:{MUTED};word-break:break-all'>"
            f"Si le bouton ne s'ouvre pas, copiez ce lien : "
            f"<a href='{url}' style='color:#ff8a3d'>{url}</a></p>"
        )
    hidden = (
        f"<div style='display:none;max-height:0;overflow:hidden;opacity:0'>"
        f"{html.escape(preheader)}</div>"
        if preheader
        else ""
    )
    return (
        "<!doctype html><html lang='fr'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<meta name='color-scheme' content='dark'><meta name='supported-color-schemes' "
        "content='dark'></head>"
        f"<body style='margin:0;padding:0;background:{PAGE}' bgcolor='{PAGE}'>"
        f"{hidden}"
        f"<table role='presentation' width='100%' cellpadding='0' cellspacing='0' "
        f"bgcolor='{PAGE}' style='background:{PAGE};background-image:"
        "radial-gradient(60% 40% at 15% 0%,rgba(255,122,26,.18),transparent 70%),"
        "radial-gradient(50% 40% at 90% 0%,rgba(139,92,246,.18),transparent 70%)'>"
        "<tr><td align='center' style='padding:32px 14px'>"
        "<table role='presentation' width='100%' cellpadding='0' cellspacing='0' "
        "style='max-width:600px'>"
        # En-tête : logo et nom.
        "<tr><td style='padding:0 6px 16px'>"
        "<table role='presentation' cellpadding='0' cellspacing='0'><tr>"
        "<td bgcolor='#ff7a1a' style='width:34px;height:34px;border-radius:10px;"
        f"background:#ff7a1a;background-image:{BUTTON};text-align:center;"
        f"font-family:{FONT};font-weight:800;font-size:17px;color:#fff'>P.</td>"
        f"<td style='padding-left:10px;font-family:{FONT};font-size:19px;font-weight:800;"
        "letter-spacing:.06em;color:#ff8a3d'>PILOT</td></tr></table></td></tr>"
        # Carte.
        f"<tr><td bgcolor='{CARD}' style='background:{CARD};border:1px solid {LINE};"
        "border-radius:20px;overflow:hidden'>"
        f"<div style='height:3px;background:#ff7a1a;background-image:{NEON}'></div>"
        f"<div style='padding:30px 30px 28px;font-family:{FONT}'>"
        f"<p style='margin:0 0 10px;font-family:{MONO};font-size:11px;letter-spacing:.14em;"
        f"text-transform:uppercase;color:#22d3ee'>&#9679; {html.escape(kicker)}</p>"
        f"<h1 style='margin:0 0 18px;font-size:24px;line-height:1.25;font-weight:700;"
        f"color:{INK}'>{html.escape(title)}</h1>"
        f"{body}{extra_html}{button}"
        "</div></td></tr>"
        # Pied.
        f"<tr><td style='padding:18px 10px 0;font-family:{FONT};font-size:12px;"
        f"line-height:1.6;color:{MUTED};text-align:center'>{html.escape(footer)}"
        f"<br><span style='font-family:{MONO};letter-spacing:.12em'>PILOT &middot; "
        "PILOTAGE DE PROJETS</span></td></tr>"
        "</table></td></tr></table></body></html>"
    )
