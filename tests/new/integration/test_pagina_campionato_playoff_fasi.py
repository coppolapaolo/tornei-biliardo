"""La pagina del campionato dopo gli inviti: playoff in corso e playoff conclusi.

Rilievo del 2026-09-13. A finale cominciata gli invitati restavano in pagina e
la fascia diceva ancora «Inviti chiusi»; a finale conclusa mostrava «Vai alla
gara playoff» invece di dire che il campionato è concluso. La fase la decide
`models/playoff/fase.py`; qui si guarda cosa legge il direttore.
"""

from __future__ import annotations

from datetime import date

import pytest

from models.base import utc_now
from models.competition.models import Gara
from models.playoff.models import PlayoffQualification, QualificationStatus
from models.status_enum import Discipline, GaraStatus
from tests.new.integration.test_pagina_campionato_direttore import (
    _campionato,
    _login,
)

pytestmark = pytest.mark.integration


def _con_gara_di_playoff(db_session, status: str, turno: int):
    dati = _campionato(db_session, terminato=True)
    cfg = dati["cfg"]
    for posizione, giocatore in enumerate(dati["giocatori"][:2], start=1):
        db_session.add(
            PlayoffQualification(
                configuration_id=cfg.id,
                user_id=giocatore.id,
                qualifying_position=posizione,
                qualification_reason=f"Posizione {posizione}",
                status=QualificationStatus.CONFIRMED,
                invited_at=utc_now(),
            )
        )
    gara = Gara(
        campionato_id=dati["campionato"].id,
        number=2,
        name="Finale",
        date=date(2026, 2, 1),
        discipline=Discipline.NINE_BALL.value,
        status=status,
        rounds_count=1,
        current_round=turno,
        distance=5,
        playoff_config_id=cfg.id,
    )
    db_session.add(gara)
    db_session.commit()
    return dati, gara


def _pagina(client, dati) -> str:
    _login(client, dati["direttore"])
    risposta = client.get(f"/admin/campionato/{dati['campionato'].id}")
    assert risposta.status_code == 200
    return risposta.get_data(as_text=True)


def test_prima_dell_avvio_della_finale_gli_invitati_restano(client, db_session):
    dati, _gara = _con_gara_di_playoff(db_session, GaraStatus.SETUP.value, 0)

    html = _pagina(client, dati)

    assert "Fase playoff" in html and "Inviti chiusi" in html
    assert "c7-invitato" in html


def test_a_finale_cominciata_gli_invitati_spariscono(client, db_session):
    dati, gara = _con_gara_di_playoff(db_session, GaraStatus.PLAYING.value, 1)

    html = _pagina(client, dati)

    assert "Playoff in corso" in html
    assert "Vai alla gara playoff" in html
    assert "Inviti chiusi" not in html and "Inviti in attesa" not in html
    assert "c7-invitato" not in html
    assert f"/admin/gara/{gara.id}" in html


def test_a_finale_conclusa_il_campionato_e_concluso(client, db_session):
    dati, gara = _con_gara_di_playoff(db_session, GaraStatus.COMPLETED.value, 1)

    html = _pagina(client, dati)

    assert "Campionato concluso" in html and "Classifica definitiva" in html
    assert "Fase playoff" not in html
    assert "Vai alla gara playoff" not in html
    assert "c7-invitato" not in html
    # Resta la strada per rileggere com'è andata la finale.
    assert "Risultati della finale" in html
    assert f"/admin/gara/{gara.id}" in html
    # La linguetta «Playoff» del telefono torna a essere «Gestione».
    assert 'data-c7-tab-btn="playoff"' not in html
