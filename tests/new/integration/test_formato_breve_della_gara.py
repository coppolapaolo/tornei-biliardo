"""Le righe che descrivono una gara seguono i turni, non la creazione.

Rilievo dalla produzione (gara 50, 08/10/2026): la card in dashboard diceva
«Palla 8 · Esattamente 5 triangoli», il formato con cui la gara era nata,
mentre i tre turni giocavano Palla 8, 9 e 10 a sei e sette triangoli. La
testata della pagina era già stata corretta (#634), ma lo stesso difetto
viveva in ogni riga che leggeva `gara.discipline` e `gara.distance_config`.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path

import pytest

from models import Gara
from models.competition.round_configuration import RoundConfiguration
from models.status_enum import Discipline, GaraStatus
from models.storia.regolamento import regolamento

pytestmark = pytest.mark.integration


def _gara(db_session, rounds=3):
    gara = Gara(
        number=1,
        name="Gara",
        date=date.today() + timedelta(days=3),
        discipline=Discipline.EIGHT_BALL.value,
        distance=5,
        is_race_to=False,
        matchmaking_strategy="amalfi",
        status=GaraStatus.SETUP.value,
        current_round=0,
        rounds_count=rounds,
    )
    db_session.add(gara)
    db_session.commit()
    return gara


def _turno(db_session, gara, n, disciplina, distanza):
    db_session.add(
        RoundConfiguration(
            gara_id=gara.id, round_number=n, discipline=disciplina, distance=distanza
        )
    )
    db_session.commit()


def test_senza_turni_modificati_il_formato_e_quello_della_gara(db_session):
    gara = _gara(db_session)

    assert gara.formato_breve == ("Palla 8", "Esattamente 5 triangoli")


def test_la_gara_50(db_session):
    """Tre discipline, due distanze: i nomi in fila, e le distanze rimandate."""
    gara = _gara(db_session)
    _turno(db_session, gara, 1, Discipline.EIGHT_BALL.value, 6)
    _turno(db_session, gara, 2, Discipline.NINE_BALL.value, 7)
    _turno(db_session, gara, 3, Discipline.TEN_BALL.value, 6)

    assert gara.formato_breve == (
        "Palla 8, Palla 9, Palla 10",
        "distanze diverse per turno",
    )


def test_tutti_i_turni_uguali_ma_diversi_dalla_gara(db_session):
    gara = _gara(db_session)
    for n in (1, 2, 3):
        _turno(db_session, gara, n, Discipline.NINE_BALL.value, 7)

    assert gara.formato_breve == ("Palla 9", "Esattamente 7 triangoli")


def test_un_turno_solo_cambia_la_distanza(db_session):
    gara = _gara(db_session)
    _turno(db_session, gara, 2, None, 3)

    assert gara.formato_breve == ("Palla 8", "distanze diverse per turno")


def test_il_regolamento_non_dice_un_formato_che_nessuno_gioca(db_session):
    """Le regole turno per turno ci sono già: la riga della gara confonderebbe."""
    gara = _gara(db_session)
    _turno(db_session, gara, 1, Discipline.EIGHT_BALL.value, 6)
    _turno(db_session, gara, 2, Discipline.NINE_BALL.value, 7)
    _turno(db_session, gara, 3, Discipline.TEN_BALL.value, 6)

    r = regolamento(gara)

    campi = {imp.campo for imp in r.in_vigore}
    assert not campi & {"discipline", "distance", "is_race_to"}
    assert len(r.per_turno) == 3


def test_il_regolamento_tiene_il_formato_se_un_turno_lo_gioca(db_session):
    gara = _gara(db_session)
    _turno(db_session, gara, 2, Discipline.NINE_BALL.value, 3)

    campi = {imp.campo for imp in regolamento(gara).in_vigore}

    assert {"discipline", "distance"} <= campi


# Presidio statico: le righe di riepilogo non leggono il formato della
# creazione. Le pagine che lo mostrano *come default* — il passo «Turni» della
# preparazione, la testata dietro `formato_della_gara_in_uso`, i moduli di
# modifica — restano fuori di proposito.
_RIEPILOGHI = [
    "components/_tessera_gara.html",
    "components/_tessera_playoff.html",
    "components/_tessera_campionato.html",
    "components/_history_gare_tab.html",
    "components/_unified_cards.html",
    "public/garas_list.html",
    "public/storico_gare.html",
    "direttore/impostazioni.html",
    "direttore/_fase_preparazione.html",
]
_FORMATO_DELLA_CREAZIONE = re.compile(
    r"(gara|entity|riga)\.(distance_config|discipline)\s*\|"
    r"\s*(format_distance|discipline_display)"
)


@pytest.mark.parametrize("template", _RIEPILOGHI)
def test_i_riepiloghi_leggono_il_formato_dei_turni(template):
    testo = (Path("templates") / template).read_text(encoding="utf-8")
    assert not _FORMATO_DELLA_CREAZIONE.search(testo), template
