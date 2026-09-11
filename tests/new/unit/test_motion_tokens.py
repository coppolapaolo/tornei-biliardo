"""Il movimento del tema passa dai token, non da millisecondi scritti a mano.

Decisione dell'11 settembre 2026 (`docs/redesign-7c/movimento/`): due durate
e una curva per tutto il design system — 250 ms per ciò che entra o si apre,
150 ms per ciò che esce, si chiude o torna dal tocco, `ease-out` del browser.
Prima di allora `theme-7c.css` aveva cinque durate diverse per lo stesso tipo
di gesto e un `cubic-bezier` isolato, e ognuna portava il suo guard
`prefers-reduced-motion`.

Il presidio legge il **testo** dei due fogli, come `test_migrations_timestamps`
legge le migration: un test di comportamento non vede un `.2s` al posto di
`var(--c7-dur-base)`, perché il browser non c'è. Fuori dal presidio restano i
**battiti** — il pallino live, il pulsare dell'aiuto — che non sono
transizioni: durano quanto vogliono, si ripetono, e tengono il proprio guard.
"""

import re
from pathlib import Path

import pytest

CSS_DIR = Path(__file__).resolve().parents[3] / "static" / "css"
TOKENS = CSS_DIR / "tokens-7c.css"
THEME = CSS_DIR / "theme-7c.css"

# I token del movimento, con il valore deciso.
TOKEN_DECISI = {
    "--c7-dur-base": "250ms",
    "--c7-dur-quick": "150ms",
    "--c7-ease": "ease-out",
    "--c7-press": ".94",
}

# Le animazioni che battono da sole e non seguono la scala: durano quanto
# serve al battito, non quanto serve al gesto. Ognuna dichiara `infinite` o un
# numero di ripetizioni, ed è quello che le distingue da una transizione.
BATTITI = {"c7-pulse", "c7-livepulse", "c7-help-pulse"}


def _senza_commenti(css: str) -> str:
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def _dichiarazioni(css: str, proprieta: str):
    """Le dichiarazioni `proprieta: valore;` con la riga in cui stanno."""
    css = _senza_commenti(css)
    out = []
    for n, riga in enumerate(css.splitlines(), 1):
        for m in re.finditer(rf"(?<![\w-]){proprieta}\s*:\s*([^;}}]+)", riga):
            out.append((n, m.group(1).strip()))
    return out


DURATA_LETTERALE = re.compile(r"(?<![\w-])\d*\.?\d+m?s\b")


@pytest.mark.parametrize("token, valore", TOKEN_DECISI.items())
def test_i_token_del_movimento_hanno_il_valore_deciso(token, valore):
    css = _senza_commenti(TOKENS.read_text(encoding="utf-8"))
    m = re.search(rf"{re.escape(token)}\s*:\s*([^;]+);", css)
    assert m, f"{token} non è in tokens-7c.css"
    assert m.group(1).strip() == valore, (
        f"{token} vale {m.group(1).strip()}, la decisione dell'11/09 dice {valore}: "
        "se è cambiata, aggiorna docs/redesign-7c/movimento/README.md e questo test"
    )


def test_con_riduci_movimento_le_durate_vanno_a_zero():
    """Un solo guard, sui token: chi chiede meno movimento lo ottiene ovunque.

    Prima ogni animazione portava il suo `@media (prefers-reduced-motion)`, e
    quella che se lo dimenticava restava accesa. Azzerando le durate alla
    fonte, ogni transizione e animazione che legge i token finisce all'istante
    senza che nessuno debba ricordarsene.
    """
    css = _senza_commenti(TOKENS.read_text(encoding="utf-8"))
    blocco = re.search(
        r"@media\s*\(prefers-reduced-motion:\s*reduce\)\s*\{(.*?)\n\}", css, re.S
    )
    assert blocco, "tokens-7c.css non ha il blocco prefers-reduced-motion"
    for token in ("--c7-dur-base", "--c7-dur-quick"):
        assert re.search(
            rf"{re.escape(token)}\s*:\s*0m?s\b", blocco.group(1)
        ), f"{token} non va a zero con «riduci movimento»"


def test_le_transizioni_del_tema_leggono_i_token():
    """Nessuna durata scritta a mano in `transition:`, e niente `transition: all`.

    `all` fa viaggiare anche i cambi che nessuno voleva animare (un colore che
    cambia al caricamento, una larghezza) — ogni transizione elenca le
    proprietà che muove.
    """
    fuori = []
    for n, valore in _dichiarazioni(THEME.read_text(encoding="utf-8"), "transition"):
        if valore in ("none", "none !important"):
            continue
        if DURATA_LETTERALE.search(valore) or re.search(r"(^|,)\s*all\b", valore):
            fuori.append(f"riga {n}: transition: {valore}")
        if "var(--c7-dur-" not in valore or "var(--c7-ease)" not in valore:
            fuori.append(
                f"riga {n}: transition: {valore} (durata o curva non dai token)"
            )
    assert not fuori, "Transizioni fuori dalla scala del movimento:\n" + "\n".join(
        fuori
    )


def test_le_animazioni_del_tema_leggono_i_token_salvo_i_battiti():
    fuori = []
    for n, valore in _dichiarazioni(THEME.read_text(encoding="utf-8"), "animation"):
        if valore == "none":
            continue
        nome = valore.split()[0]
        if nome in BATTITI:
            assert "infinite" in valore or re.search(r"\s\d+\s*$", valore), (
                f"riga {n}: {nome} è fra i battiti ma non si ripete: "
                "allora è una transizione e segue la scala"
            )
            continue
        if DURATA_LETTERALE.search(valore) or "var(--c7-dur-" not in valore:
            fuori.append(f"riga {n}: animation: {valore}")
    assert not fuori, (
        "Animazioni con durata scritta a mano (se è un battito, aggiungilo a "
        "BATTITI):\n" + "\n".join(fuori)
    )


def _blocchi_media(css: str, condizione: str):
    """I corpi dei blocchi `@media (prefers-reduced-motion: <condizione>) { … }`."""
    corpi = []
    for m in re.finditer(
        rf"@media\s*\(prefers-reduced-motion:\s*{condizione}\)\s*\{{", css
    ):
        depth, i = 1, m.end()
        while i < len(css) and depth:
            depth += {"{": 1, "}": -1}.get(css[i], 0)
            i += 1
        corpi.append(css[m.end() : i - 1])
    return corpi


@pytest.mark.parametrize("nome", sorted(BATTITI))
def test_i_battiti_tengono_il_proprio_guard(nome):
    """I token a zero non fermano un `infinite`: il battito ha bisogno del suo guard.

    O sta dentro `prefers-reduced-motion: no-preference`, e allora non parte
    proprio, oppure un blocco `reduce` gli mette `animation: none`.
    """
    css = _senza_commenti(THEME.read_text(encoding="utf-8"))
    usi = re.findall(rf"([^{{}}]+)\{{[^}}]*animation:\s*{re.escape(nome)}\b", css)
    assert usi, f"nessuna regola usa il battito {nome}: toglilo da BATTITI"
    dentro_no_preference = any(
        nome in corpo for corpo in _blocchi_media(css, "no-preference")
    )
    spenti = "".join(_blocchi_media(css, "reduce"))
    for selettore in usi:
        selettore = selettore.strip().splitlines()[-1].strip()
        assert dentro_no_preference or re.search(
            rf"{re.escape(selettore)}[^{{]*\{{[^}}]*animation:\s*none", spenti
        ), f"il battito {nome} su «{selettore}» non ha un guard prefers-reduced-motion"


def test_il_tocco_premuto_e_istantaneo():
    """Lo schiacciamento a 0 ms, il ritorno alla durata `quick`.

    Se anche la pressione avesse una durata, il pulsante risponderebbe al dito
    con un ritardo percepibile: è il ritorno che si vede, non l'andata.
    """
    css = _senza_commenti(THEME.read_text(encoding="utf-8"))
    m = re.search(r"\.c7-rackpad__btn:active[^{]*\{([^}]*)\}", css)
    assert m, "il rackpad non ha uno stato premuto"
    corpo = m.group(1)
    assert "scale(var(--c7-press))" in corpo
    assert re.search(
        r"transition-duration:\s*0m?s", corpo
    ), "la pressione deve essere istantanea"
