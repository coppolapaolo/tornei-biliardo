"""I presidi per i contenuti caricati (issue #445).

Oggi i file li caricano **solo i gestori**: esercizi con `@director_required`,
foto delle sale con `@venue_manager_required`, locandine di campionato e gara
con i loro. I controlli sono di forma — estensione e dimensione massima — e
sono proporzionati a chi carica: nessun giocatore può caricare niente.

Quello che mancava era un canale dichiarato per segnalare un contenuto
illecito. Chi ospita materiale altrui non ne risponde a priori, a condizione di
non esserne a conoscenza e di rimuoverlo prontamente quando gli viene
segnalato: quella protezione **presuppone che qualcuno possa avvisare**. Senza
un recapito il meccanismo non si innesca, e il problema si scopre tardi.

Il test è statico, sul testo dei template, per la stessa ragione del presidio
CSRF: una frase che sparisce da un form non rompe niente, non fallisce alla
build e non fa fallire nessuna prova di comportamento. Si accorge solo chi
guarda la pagina — cioè, qui, nessuno prima di un problema legale.

Il giorno in cui il caricamento si aprirà ai giocatori — un avatar, una foto
del profilo — questi due presidi vanno **prima**, non dopo.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

TEMPLATES = Path(__file__).resolve().parents[3] / "templates"

#: Il recapito delle segnalazioni. Volutamente diverso da `privacy@`, che
#: raccoglie le richieste sui dati personali: mescolare i due scopi manda una
#: segnalazione urgente nella coda sbagliata.
RECAPITO = "info@torneibiliardo.it"

#: L'ancora della sezione nella pagina privacy, a cui punta il footer.
ANCORA = "contenuti"

#: Il nocciolo della frase che deve comparire dove si sceglie un file. Si cerca
#: un frammento e non la stringa intera perche' il testo e' tradotto e puo'
#: essere riformulato: quello che non deve sparire e' l'avvertimento.
AVVISO = "di cui hai i diritti"

#: Quanto lontano dall'`<input type="file">` puo' stare l'avviso. Largo
#: abbastanza per un input scritto su piu' righe, stretto abbastanza da non
#: pescare il testo di un altro riquadro.
FINESTRA = 700


def _template(nome: str) -> str:
    return (TEMPLATES / nome).read_text(encoding="utf-8")


def _form_di_caricamento() -> list[tuple[Path, int, str]]:
    """Ogni `<input type="file">` dei template, col suo contorno."""
    trovati = []
    for path in sorted(TEMPLATES.rglob("*.html")):
        testo = path.read_text(encoding="utf-8")
        for match in re.finditer(r"""<input[^>]*type=["']file["']""", testo):
            riga = testo.count("\n", 0, match.start()) + 1
            contorno = testo[match.start() : match.start() + FINESTRA]
            trovati.append((path, riga, contorno))
    return trovati


def test_ci_sono_ancora_i_form_di_caricamento_che_conosciamo():
    """Se ne nasce uno nuovo il test sotto lo trova da solo; questo lo dice.

    Serve a distinguere «tutti in regola» da «non ne ho trovato nessuno», che
    con una ricerca testuale sono lo stesso risultato.
    """
    assert len(_form_di_caricamento()) >= 4


def test_ogni_caricamento_avverte_sui_diritti():
    """Dove si sceglie un file, si ricorda di che materiale si può caricare.

    È l'unico punto in cui l'avvertimento arriva a chi sta per caricare, nel
    momento in cui decide. Una pagina di termini che nessuno apre non ha lo
    stesso effetto.
    """
    root = TEMPLATES.parent
    mancanti = [
        f"{path.relative_to(root)}:{riga}"
        for path, riga, contorno in _form_di_caricamento()
        if AVVISO not in contorno
    ]
    assert (
        not mancanti
    ), "Caricamento senza avviso sui diritti d'uso del materiale:\n  " + "\n  ".join(
        mancanti
    )


def test_la_privacy_dichiara_il_recapito_per_le_segnalazioni():
    privacy = _template("privacy.html")
    assert RECAPITO in privacy
    assert f'id="{ANCORA}"' in privacy
    # Il recapito dei dati personali resta il suo, e resta distinto.
    assert "privacy@torneibiliardo.it" in privacy


def test_il_recapito_si_raggiunge_da_ogni_pagina():
    """Il footer è in `base.html`, quindi in tutte le pagine dell'app.

    Un canale che c'è ma non si trova vale quanto un canale che non c'è.
    """
    assert f"#{ANCORA}" in _template("base.html")
