"""La finale dei playoff non è una delle gare previste (rilievo 2026-09-14).

Su un campionato con 2 gare previste, 2 giocate e la finale conclusa, la
pagina del direttore scriveva «3 di 2»: il numeratore contava tutte le gare,
finale compresa, il denominatore le sole gare previste. La vetrina pubblica
faceva lo stesso con «3 gare» e «3 di 3 giocate».

La regola (SPECIFICHE.md, «Campionati», nota del 2026-09-14): le gare previste
sono quelle della stagione, la gara di playoff è la conclusione e si mostra a
parte — «2 gare + finale». Chi è una gara di playoff lo dice
`Gara.is_playoff`, non il nome.
"""

from __future__ import annotations

import re
from datetime import date

import pytest

from models.base import db
from models.competition.models import Gara
from models.status_enum import Discipline, GaraStatus
from tests.new.integration.test_pagina_campionato_direttore import (
    _campionato,
    _login,
)

pytestmark = pytest.mark.integration


def _stagione_con_finale(db_session):
    """Due gare previste, due giocate, e la finale dei playoff conclusa."""
    dati = _campionato(db_session, terminato=True)
    campionato = dati["campionato"]
    campionato.planned_gare_count = 2
    db_session.add(
        Gara(
            campionato_id=campionato.id,
            number=2,
            name="Gara 2",
            date=date(2026, 1, 22),
            discipline=Discipline.NINE_BALL.value,
            status=GaraStatus.COMPLETED.value,
            rounds_count=1,
            current_round=1,
            distance=5,
        )
    )
    db_session.add(
        # Il nome non dice niente di proposito: la finale si riconosce dal
        # collegamento alla configurazione del playoff.
        Gara(
            campionato_id=campionato.id,
            number=3,
            name="Serata di gala",
            date=date(2026, 2, 1),
            discipline=Discipline.NINE_BALL.value,
            status=GaraStatus.COMPLETED.value,
            rounds_count=1,
            current_round=1,
            distance=5,
            playoff_config_id=dati["cfg"].id,
        )
    )
    db_session.commit()
    return dati


def _senza_spazi(html: str) -> str:
    return re.sub(r"\s+", " ", html)


def test_la_pagina_del_direttore_non_dice_3_di_2(client, db_session):
    dati = _stagione_con_finale(db_session)
    _login(client, dati["direttore"])

    risposta = client.get(f"/admin/campionato/{dati['campionato'].id}")
    assert risposta.status_code == 200
    html = _senza_spazi(risposta.get_data(as_text=True))

    assert "3 di 2" not in html
    assert "2 di 2 · finale" in html
    assert "3 gare concluse" not in html
    assert "2 gare previste" in html


def test_senza_numero_previsto_la_finale_non_diventa_una_gara_prevista(
    client, db_session
):
    dati = _stagione_con_finale(db_session)
    # La colonna è NOT NULL: il ripiego sulle gare in calendario scatta a 0.
    dati["campionato"].planned_gare_count = 0
    db_session.commit()
    _login(client, dati["direttore"])

    html = _senza_spazi(
        client.get(f"/admin/campionato/{dati['campionato'].id}").get_data(as_text=True)
    )

    assert "3 gare previste" not in html
    assert "2 gare previste" in html


def test_la_vetrina_conta_la_finale_a_parte(client, db_session):
    from models.campionato.showcase_view import (
        costruisci_vetrina_campionato,
        descrizione_social_campionato,
    )

    dati = _stagione_con_finale(db_session)
    campionato = dati["campionato"]

    vetrina = costruisci_vetrina_campionato(campionato)

    assert vetrina.prove_totali == 2
    assert vetrina.prove_giocate == 2
    assert vetrina.finali == 1
    assert "2 gare + finale" in descrizione_social_campionato(vetrina)

    pagina = _senza_spazi(
        client.get(f"/c/{campionato.public_token}")
        .get_data(as_text=True)
        .split('<footer class="debug-footer"')[0]
    )
    assert "3 gare" not in pagina
    assert "2 gare + finale" in pagina
    assert "3 di 3 giocate" not in pagina
    assert "2 di 2 giocate · finale" in pagina


def test_la_tessera_conta_la_finale_a_parte(db_session):
    dati = _stagione_con_finale(db_session)
    campionato = db.session.get(type(dati["campionato"]), dati["campionato"].id)

    conteggio = campionato.conteggio_gare

    assert (conteggio.regolari, conteggio.finali) == (2, 1)
    assert conteggio.gare_testo == "2 gare + finale"
