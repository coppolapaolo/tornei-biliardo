"""Il campionato concluso nelle pagine dell'app: direttore e pagina pubblica.

La vetrina (gen.py) mette il campione sulla targa — la A, scelta il
2026-09-14. Qui la stessa idea va nella fascia accento delle due pagine
dentro l'app, con i pezzi del canvas della pagina del direttore
(`canvas-gara-direttore/sorgenti/gen_fasi.py`, schermate 7.1 e 7.3): stesso
guscio, stesse righe, stessa classifica. I dati sono quelli di gen.py.

    python docs/redesign-7c/campionato-concluso/sorgenti/gen_pagine.py

scrive tutti gli artboard (anche quelli della vetrina) e `canvas.json`.
"""

import json
import sys
from datetime import date
from pathlib import Path

QUI = Path(__file__).resolve().parent
OUT = QUI.parent
sys.path.insert(0, str(QUI))
sys.path.insert(0, str(OUT.parent / "canvas-gara-direttore" / "sorgenti"))

import gen as vt  # noqa: E402
import gen_fasi as fasi  # noqa: E402
from gen_gara_direttore import I, desktop, doc, ico, phone, vtabs  # noqa: E402

# ---------------------------------------------------------------- i dati
# (posizione, username, tendenza, vinte, differenza, gare): i primi otto
# sono quelli della vetrina, che si ferma a otto righe.
CLASSIFICA = [
    ("1", "m.rossi", "eq", "21", "+34", "6"),
    ("2", "a.verdi", "up", "20", "+29", "6"),
    ("3", "p.neri", "down", "17", "+12", "6"),
    ("4", "e.furlan", "eq", "15", "+8", "5"),
    ("5", "g.ferri", "up", "12", "+1", "6"),
    ("6", "d.conti", "down", "11", "-4", "5"),
    ("7", "l.berti", "eq", "9", "-10", "5"),
    ("8", "s.moro", "eq", "7", "-15", "4"),
    ("9", "f.costa", "up", "6", "-18", "4"),
    ("10", "r.neri", "down", "5", "-21", "3"),
]
assert [c[1] for c in CLASSIFICA[:8]] == [c[0] for c in vt.CLASSIFICA]

# Il giorno della settimana si calcola: scritto a mano era sbagliato tre volte.
_GIORNI = ["lun", "mar", "mer", "gio", "ven", "sab", "dom"]
_MESI = {"giu": 6, "lug": 7, "set": 9, "ott": 10, "nov": 11}
GARE = [
    (nome, f"{_GIORNI[date(2026, _MESI[m], int(g)).weekday()]} {g} {m}", chi)
    for g, m, nome, chi in reversed(vt.GARE)
]
assert [g[2] for g in reversed(GARE)] == [g[3] for g in vt.GARE]

EXTRA_CSS = """
.cpos{width:24px;height:24px;border-radius:8px;display:grid;place-items:center;font-size:11px;font-weight:800;flex-shrink:0}
.cpos--2{background:var(--c7-argento);color:var(--c7-argento-ink)}
.cpos--3{background:var(--c7-bronzo);color:var(--c7-bronzo-ink)}
.av-oro{background:var(--c7-oro)!important;color:var(--c7-oro-ink)!important}
.card--accent .kicker.campione__k{color:var(--c7-oro)}
.campione__nome{margin-top:3px;font-weight:800;letter-spacing:-.03em;line-height:1.1}
.alt{display:inline-flex;align-items:center;gap:8px;font-weight:700;color:var(--c7-accent-dim)}
"""


def con_stile(html):
    return html.replace("</helmet>", f"<style>{EXTRA_CSS}</style>\n</helmet>")


def iniziali(nome):
    return (nome[0] + nome[2]).upper()


# ---------------------------------------------------------------- i pezzi
def fascia_campione(desktop_=False):
    """La fascia di un campionato concluso: il campione come sulla targa
    della vetrina, secondo e terzo sotto (sul desktop a destra)."""
    campione, secondo, terzo = (c[1] for c in CLASSIFICA[:3])
    alt = "".join(
        f'<span class="alt" style="font-size:{15 if desktop_ else 13}px">'
        f'<span class="cpos cpos--{p}">{p}</span>{nome}</span>'
        for p, nome in (("2", secondo), ("3", terzo))
    )
    if desktop_:
        return f"""
          <section class="card card--accent" style="display:flex;align-items:center;gap:22px;padding:20px 22px">
            <div class="grow">
              <div class="kicker">Campionato concluso</div>
              <div class="row" style="margin-top:12px;gap:16px;align-items:center">
                <div class="avatar av-oro" style="width:60px;height:60px;font-size:17px">{iniziali(campione)}</div>
                <div class="grow">
                  <div class="kicker campione__k">Campione</div>
                  <div class="campione__nome" style="font-size:28px">{campione}</div>
                </div>
              </div>
            </div>
            <div class="stack" style="gap:12px;min-width:190px">{alt}</div>
          </section>"""
    return f"""
      <section class="card card--accent">
        <div class="kicker">Campionato concluso</div>
        <div class="row" style="margin-top:14px;gap:13px;align-items:center">
          <div class="avatar av-oro" style="width:52px;height:52px;font-size:15px">{iniziali(campione)}</div>
          <div class="grow">
            <div class="kicker campione__k">Campione</div>
            <div class="campione__nome" style="font-size:22px">{campione}</div>
          </div>
        </div>
        <div class="row" style="margin-top:14px;gap:18px;flex-wrap:wrap">{alt}</div>
      </section>"""


def classifica_finale(telefono=True):
    """La classifica generale a campionato concluso: niente zona playoff
    (a playoff conclusi non segna piu' niente) e niente freccia di tendenza,
    che in una classifica finale non ha un termine di confronto. Sul telefono
    senza la colonna Gare, che toglierebbe il posto al nome."""
    colonne = [("Vinte", 44), ("Diff", 44)] + ([] if telefono else [("Gare", 40)])
    head = "".join(
        f'<div class="label" style="margin:0;width:{w}px;text-align:right">{c}</div>'
        for c, w in colonne
    )
    body = ""
    for pos, nome, t, *valori in CLASSIFICA:
        colore = "color:var(--c7-accent)" if int(pos) <= 3 else ""
        celle = "".join(
            f'<div class="num" style="width:{w}px;text-align:right;font-size:{15 if j == 0 else 13}px;'
            f'font-weight:{800 if j == 0 else 700};{"" if j == 0 else "color:var(--c7-ink-muted)"}">{v}</div>'
            for j, (v, (_, w)) in enumerate(zip(valori, colonne))
        )
        body += f"""
        <div class="rows__row">
          <div class="num" style="width:20px;font-size:15px;font-weight:800;{colore}">{pos}</div>
          <div class="avatar">{iniziali(nome)}</div>
          <div class="grow"><div class="rows__title">{nome}</div></div>
          {celle}
        </div>"""
    return fasi.rows(f"""
        <div class="rows__row" style="padding-top:11px;padding-bottom:11px">
          <div style="width:20px"></div>
          <div class="grow label" style="margin:0;padding-left:46px">Giocatore</div>{head}
        </div>""" + body)


def gare():
    """Ogni gara conclusa dice chi l'ha vinta; la finale playoff come le altre."""
    return fasi.rows(
        "".join(
            fasi._gara_tessera(nome, quando, "Conclusa", "ok", f"ha vinto {chi}")
            for nome, quando, chi in GARE
        )
    )


FERMO = "<span></span>"


def gestione():
    return fasi.rows(
        fasi.row(
            I["trophy"],
            "Playoff",
            "finale conclusa &middot; campionato + finale, peso 1",
        )
        + fasi.row(I["users"], "Direttori", "tu e m.neri")
        + fasi.row(I["share"], "Vetrina", "locandina caricata")
        + fasi.row(I["gear"], "Impostazioni", "Palla 8 &middot; al 5 &middot; Amalfi")
    )


def il_campionato():
    """Al posto di Gestione, nella pagina pubblica: i fatti della vetrina."""
    return fasi.rows(
        fasi.row(
            I["trophy"], "Formula", "Amalfi &middot; classifica a vittorie", right=FERMO
        )
        + fasi.row(I["table"], "Dove", "Sala Centrale &middot; Udine", right=FERMO)
        + fasi.row(
            I["users"],
            "Giocatori",
            f"{vt.GIOCATORI} in 5 gare e la finale",
            right=FERMO,
        )
        + fasi.row(I["share"], "Vetrina", "locandina e link da condividere")
    )


TITOLO = vt.CAMPIONATO
SOTTO_DESKTOP = (
    "Biliardo Mimmo &middot; Al 5 &middot; Palla 8 &middot;\n"
    '          <span class="num">gio 3 set 2026, 20:00</span>'
)


def telefono_lungo(html, altezza):
    return html.replace(
        '<div class="phone">', f'<div class="phone" style="height:{altezza}px">'
    )


def desktop_lungo(actions, content, altezza, sotto):
    html = (
        desktop(actions, content)
        .replace('<div class="app">', f'<div class="app" style="height:{altezza}px">')
        .replace(
            '<div class="dcontent">', '<div class="dcontent" style="overflow:visible">'
        )
        .replace("Gara 3 &middot; Gioved&igrave;</h1>", f"{TITOLO}</h1>")
        .replace(SOTTO_DESKTOP, sotto)
    )
    return con_stile(doc(html))


def da_giocatore(html):
    """Il guscio del canvas e' quello del direttore pa: la pagina pubblica
    la guarda un giocatore."""
    return (
        html.replace(
            '<div class="side__role">direzione gara</div>',
            '<div class="side__role">giocatore</div>',
        )
        .replace(
            '<div style="font-size:13px;font-weight:800">pa</div>',
            '<div style="font-size:13px;font-weight:800">g.ferri</div>',
        )
        .replace("direttore &middot; Lv 17", "giocatore &middot; Lv 9")
        .replace('<div class="avatar">PA</div>', '<div class="avatar">GF</div>')
        .replace(
            '<div class="avatar avatar--lg">PA</div>',
            '<div class="avatar avatar--lg">GF</div>',
        )
    )


VETRINA = (
    f'<button class="btn btn--secondary btn--sm">{ico(I["share"], 15)} Vetrina</button>'
)


# ---------------------------------------------------------------- le schermate
def direttore_mobile():
    content = f"""
      {fascia_campione()}
      {fasi.sec("Classifica finale", "definitiva &middot; tutti (18)")}
      {classifica_finale()}
      {fasi.sec("Gare", "5 + finale")}
      {gare()}
      {fasi.sec("Gestione")}
      {gestione()}
"""
    html = phone(
        "Amalfi &middot; concluso",
        vtabs(["Classifica", "Gare", "Gestione"], "Classifica"),
        content,
        title=TITOLO,
    )
    return con_stile(doc(telefono_lungo(html, 2020)))


def direttore_desktop():
    sinistra = f"""
        <div class="stack">
          {fascia_campione(desktop_=True)}
          {fasi.sec("Classifica finale", "definitiva &middot; tutti (18)")}
          {classifica_finale(telefono=False)}
        </div>"""
    destra = f"""
        <div class="stack">
          {fasi.sec("Gare", "5 + finale")}
          {gare()}
          {fasi.sec("Gestione")}
          {gestione()}
        </div>"""
    return desktop_lungo(
        VETRINA,
        f'<div class="cols">{sinistra}{destra}</div>',
        1060,
        "Amalfi &middot; concluso &middot; Sala Centrale &middot; 5 gare + finale",
    )


def pubblica_mobile():
    content = f"""
      {fascia_campione()}
      {fasi.sec("Classifica finale", "definitiva &middot; tutti (18)")}
      {classifica_finale()}
      {fasi.sec("Gare", "5 + finale")}
      {gare()}
      {fasi.sec("Il campionato")}
      {il_campionato()}
"""
    html = phone(
        "Amalfi &middot; concluso",
        vtabs(["Classifica", "Gare", "Il campionato"], "Classifica"),
        content,
        title=TITOLO,
    )
    return da_giocatore(con_stile(doc(telefono_lungo(html, 2020))))


def pubblica_desktop():
    sinistra = f"""
        <div class="stack">
          {fascia_campione(desktop_=True)}
          {fasi.sec("Classifica finale", "definitiva &middot; tutti (18)")}
          {classifica_finale(telefono=False)}
        </div>"""
    destra = f"""
        <div class="stack">
          {fasi.sec("Gare", "5 + finale")}
          {gare()}
          {fasi.sec("Il campionato")}
          {il_campionato()}
        </div>"""
    return da_giocatore(
        desktop_lungo(
            VETRINA,
            f'<div class="cols">{sinistra}{destra}</div>',
            1060,
            "Amalfi &middot; concluso &middot; Sala Centrale &middot; 5 gare + finale",
        )
    )


PAGINE = [
    {"id": "page-1", "name": "Vetrina"},
    {"id": "page-2", "name": "Pagina del direttore"},
    {"id": "page-3", "name": "Pagina pubblica"},
    {"id": "page-4", "name": "Vetrina · alternative"},
]


def canvas():
    tel, desk = (390, 1440)

    def ab(file, page, x, w, h, title):
        return {
            "file": file,
            "page": page,
            "x": x,
            "y": 0,
            "w": w,
            "h": h,
            "title": title,
        }

    def nota(id_, page, x, w, text, y=-300):
        return {"id": id_, "page": page, "x": x, "y": y, "w": w, "text": text}

    return {
        "pages": PAGINE,
        "artboards": [
            ab("Main.dc.html", "page-1", 0, tel, 1900, "Vetrina · telefono"),
            ab(
                "VetrinaDesktop.dc.html", "page-1", 470, desk, 1720, "Vetrina · desktop"
            ),
            ab(
                "DirettoreMobile.dc.html",
                "page-2",
                0,
                tel,
                2020,
                "Direttore · telefono",
            ),
            ab(
                "DirettoreDesktop.dc.html",
                "page-2",
                470,
                desk,
                1060,
                "Direttore · desktop",
            ),
            ab("PubblicaMobile.dc.html", "page-3", 0, tel, 2020, "Pubblica · telefono"),
            ab(
                "PubblicaDesktop.dc.html",
                "page-3",
                470,
                desk,
                1060,
                "Pubblica · desktop",
            ),
            ab("Oggi.dc.html", "page-4", 0, tel, 1900, "Oggi · com'è adesso"),
            ab(
                "ComeFinita.dc.html",
                "page-4",
                470,
                tel,
                2050,
                "B · Com'è finita, come la gara conclusa",
            ),
            ab(
                "Classifica.dc.html",
                "page-4",
                940,
                tel,
                1900,
                "C · Il podio è la classifica",
            ),
        ],
        "annotations": [
            nota(
                "premessa",
                "page-1",
                0,
                1910,
                (
                    "Un campionato concluso in tre pagine: la vetrina, la pagina del direttore e la pagina "
                    "pubblica. Stessi dati ovunque: il campione è m.rossi, primo della classifica finale; la "
                    "finale playoff l'ha vinta a.verdi e sta fra le gare come tutte le altre.\n\nLa forma è la A, "
                    "scelta sulla vetrina: il campione in cima, dentro la superficie scura che apre la pagina, "
                    "con secondo e terzo sotto (nella fascia desktop dell'app, a destra)."
                ),
                y=-560,
            ),
            nota(
                "nota-vetrina",
                "page-1",
                470,
                1440,
                (
                    "VETRINA DESKTOP\nIl campione resta sulla targa. La colonna di destra, che oggi contiene "
                    "solo il riquadro delle iscrizioni, prende la classifica finale: sul telefono sta prima delle "
                    "gare, qui accanto. In fondo alla colonna, Condividi e chi organizza."
                ),
            ),
            nota(
                "nota-direttore",
                "page-2",
                0,
                1910,
                (
                    "PAGINA DEL DIRETTORE\nLa fascia dice chi ha vinto il campionato, come la targa della "
                    "vetrina. Oggi dice «Classifica definitiva · Playoff Elite: vince player2», con il pulsante "
                    "«Risultati della finale».\n• Il pulsante sparisce: la finale sta fra le gare con «ha vinto "
                    "a.verdi», come tutte.\n• «Classifica generale · dopo la gara N» diventa «Classifica "
                    "finale», e perde la zona playoff (a playoff conclusi non segna più niente) e le frecce di tendenza. Sul telefono senza la colonna Gare, per lasciare posto al nome.\n• Ogni gara "
                    "conclusa dice chi l'ha vinta: oggi la riga dice data, sala e iscritti.\n\nRILIEVO: oggi la "
                    "sezione Gare scrive «3 di 2», perché le gare previste non contano la finale ma l'elenco sì. "
                    "Qui «5 + finale», in tutte e tre le pagine."
                ),
                y=-420,
            ),
            nota(
                "nota-pubblica",
                "page-3",
                0,
                1910,
                (
                    "PAGINA PUBBLICA\nOggi è ancora la vecchia pagina Bootstrap: Informazioni, Statistiche, "
                    "classifica con la zona playoff, tabella delle gare, nessun vincitore. Qui è la pagina del "
                    "direttore in sola lettura: stessa fascia col campione, stessa classifica finale, stesse "
                    "gare. Al posto di Gestione, «Il campionato»: formula, sala, giocatori e il link alla "
                    "vetrina.\n\nDA DECIDERE DOPO: con la vetrina, il campionato ha due pagine pubbliche. "
                    "Questa serve a chi è dentro l'app, la vetrina a chi arriva da un link condiviso."
                ),
                y=-420,
            ),
            nota(
                "nota-oggi",
                "page-4",
                0,
                tel,
                (
                    "OGGI\nIn cima c'è solo «Campionato concluso». Chi ha vinto si deduce dalla classifica "
                    "«dopo 6 gare», che viene dopo il calendario, e in fondo resta il riquadro delle iscrizioni."
                ),
            ),
            nota(
                "nota-b",
                "page-4",
                470,
                tel,
                (
                    "B · COM'È FINITA\nUna card accento sotto la targa con il podio a tre posti, il primo al "
                    "centro e più grande: è lo stesso podio della gara conclusa.\nPro: chi ha visto una gara "
                    "finita riconosce il campionato finito.\nContro: la classifica scende di circa 250px, e i "
                    "primi tre compaiono due volte."
                ),
            ),
            nota(
                "nota-c",
                "page-4",
                940,
                tel,
                (
                    "C · IL PODIO È LA CLASSIFICA\nNessun blocco nuovo: la classifica finale sale sotto la "
                    "targa, i primi tre prendono i colori delle medaglie e il primo la scritta «Campione».\n"
                    "Pro: niente di ripetuto.\nContro: il campione è una riga, non un annuncio."
                ),
            ),
        ],
        "launch": {"view": "canvas", "page": "page-2"},
    }


SCHERMATE = [
    ("DirettoreMobile", direttore_mobile),
    ("DirettoreDesktop", direttore_desktop),
    ("PubblicaMobile", pubblica_mobile),
    ("PubblicaDesktop", pubblica_desktop),
]


if __name__ == "__main__":
    scritti = vt.scrivi()
    for nome, fn in SCHERMATE:
        (OUT / f"{nome}.dc.html").write_text(fn(), encoding="utf-8")
        scritti.append(f"{nome}.dc.html")
    (OUT / "canvas.json").write_text(
        json.dumps(canvas(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("--artboard " + " --artboard ".join(scritti))
