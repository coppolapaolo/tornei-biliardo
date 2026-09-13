"""Qual è il comando che una gara aspetta dal suo direttore.

Presidia `models/dashboard/comandi.py`. Dal 2026-09-12 lo legge anche la
pagina della gara del direttore (`templates/direttore/_fase_*.html`) per la
fascia scura in cima — la pagina **esegue**, la dashboard **annuncia**, la
macchina a stati e' questa — quindi questi test sono il punto in cui un caso
mancante si vede: se domani la pagina guadagna uno stato e questo no, la
dashboard mostrerà «Gestisci» dove c'è qualcosa da fare.

Nota su ciò che **non** esiste: non ci sono comandi «chiudi il turno» né
«assegna i tavoli». Un turno finisce quando finiscono le sue partite, e i
tavoli li assegna la gara da sé secondo `available_tables`.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from models.base import utc_now
from models.competition.models import Gara
from models.dashboard.comandi import ComandoDirezione, comando_per
from models.matchmaking.configuration import MatchmakingStrategy
from models.status_enum import GaraStatus, MatchStatus, ProvaDerivedStatus


class _Iscrizioni:
    """Un numero di iscritti attivi, senza toccare il database."""

    def __init__(self, quanti: int):
        self.quanti = quanti


def _gara(
    *,
    status: str,
    iscritti: int = 8,
    minimo: int = 6,
    turno: int = 0,
    strategia: str = MatchmakingStrategy.AMALFI.value,
    inscription_start=None,
    inscription_end=None,
) -> Gara:
    gara = Gara(
        name="Gara",
        number=1,
        date=date.today(),
        status=status,
        min_participants=minimo,
        current_round=turno,
        rounds_count=5,
        matchmaking_strategy=strategia,
        inscription_start=inscription_start,
        inscription_end=inscription_end,
    )
    gara.id = 1
    # `get_active_inscriptions_count` interroga il database: su un oggetto mai
    # salvato si sostituisce col numero che serve al caso.
    gara.get_active_inscriptions_count = lambda: iscritti  # type: ignore[method-assign]
    return gara


@pytest.mark.unit
def test_una_gara_in_preparazione_aspetta_l_apertura_delle_iscrizioni():
    comando = comando_per(_gara(status=GaraStatus.SETUP.value))
    assert comando is not None
    assert comando.tipo == ComandoDirezione.APRI_ISCRIZIONI
    assert not comando.bloccato


@pytest.mark.unit
def test_con_le_iscrizioni_aperte_e_abbastanza_giocatori_si_puo_avviare():
    comando = comando_per(
        _gara(status=GaraStatus.INSCRIPTION.value, iscritti=8, minimo=6)
    )
    assert comando is not None
    assert comando.tipo == ComandoDirezione.AVVIA_GARA
    assert not comando.bloccato


@pytest.mark.unit
def test_senza_abbastanza_iscritti_il_comando_si_annuncia_lo_stesso_ma_bloccato():
    """Annunciarlo comunque è il punto.

    Il direttore deve sapere che quella gara aspetta lui e cosa le manca:
    nasconderle il comando la lascia ferma senza che nessuno sappia perché.
    """
    comando = comando_per(
        _gara(status=GaraStatus.INSCRIPTION.value, iscritti=3, minimo=6)
    )
    assert comando is not None
    assert comando.tipo == ComandoDirezione.AVVIA_GARA
    assert comando.bloccato
    assert comando.iscritti == 3
    assert comando.minimo == 6


@pytest.mark.unit
def test_a_iscrizioni_scadute_e_giocatori_insufficienti_si_estende_la_finestra():
    gara = _gara(
        status=GaraStatus.INSCRIPTION.value,
        iscritti=2,
        minimo=6,
        inscription_start=utc_now() - timedelta(days=10),
        inscription_end=utc_now() - timedelta(days=1),
    )
    assert gara.get_real_status() == ProvaDerivedStatus.INSCRIPTION_CLOSED.value

    comando = comando_per(gara)
    assert comando is not None
    assert comando.tipo == ComandoDirezione.ESTENDI_ISCRIZIONI
    assert comando.bloccato


@pytest.mark.unit
def test_a_iscrizioni_scadute_con_i_giocatori_che_bastano_si_avvia():
    gara = _gara(
        status=GaraStatus.INSCRIPTION.value,
        iscritti=8,
        minimo=6,
        inscription_start=utc_now() - timedelta(days=10),
        inscription_end=utc_now() - timedelta(days=1),
    )
    comando = comando_per(gara)
    assert comando is not None
    assert comando.tipo == ComandoDirezione.AVVIA_GARA
    assert not comando.bloccato


@pytest.mark.unit
def test_con_le_iscrizioni_non_ancora_aperte_non_tocca_a_lui():
    """Si aprono da sole, all'ora fissata."""
    gara = _gara(
        status=GaraStatus.INSCRIPTION.value,
        inscription_start=utc_now() + timedelta(days=3),
        inscription_end=utc_now() + timedelta(days=10),
    )
    assert gara.get_real_status() == ProvaDerivedStatus.INSCRIPTION_NOT_YET_OPEN.value
    assert comando_per(gara) is None


@pytest.mark.unit
def test_mentre_un_turno_si_gioca_il_direttore_non_ha_niente_da_fare():
    """«Niente» è una risposta, e va data.

    Annunciare un comando qualsiasi mentre si gioca vale meno di zero: fa
    sembrare che la gara sia ferma per colpa sua.
    """
    gara = _gara(status=GaraStatus.PLAYING.value, turno=2)
    assert gara.get_real_status() == GaraStatus.PLAYING.value
    assert comando_per(gara) is None


@pytest.mark.unit
def test_a_turno_finito_si_avvia_il_turno_dopo(monkeypatch):
    gara = _gara(status=GaraStatus.PLAYING.value, turno=2)
    monkeypatch.setattr(
        Gara,
        "get_real_status",
        lambda self: ProvaDerivedStatus.ROUND_COMPLETED.value,
    )

    comando = comando_per(gara)
    assert comando is not None
    assert comando.tipo == ComandoDirezione.AVVIA_TURNO
    assert comando.turno == 3
    assert not comando.bloccato


@pytest.mark.unit
def test_a_turno_finito_con_prove_ed_esercizi_in_sospeso_il_turno_aspetta(
    monkeypatch,
):
    """SPECIFICHE.md, «Cosa deve essere chiuso prima del turno successivo»."""
    from models.competition.pendenze_turno import PendenzeTurno
    from models.dashboard import comandi

    gara = _gara(status=GaraStatus.PLAYING.value, turno=2)
    monkeypatch.setattr(
        Gara,
        "get_real_status",
        lambda self: ProvaDerivedStatus.ROUND_COMPLETED.value,
    )
    monkeypatch.setattr(
        comandi,
        "pendenze_del_turno",
        lambda g, turno: PendenzeTurno(turno=turno, prove_x=1, esercizi=2),
    )

    comando = comando_per(gara)
    assert comando is not None
    assert comando.tipo == ComandoDirezione.AVVIA_TURNO
    assert comando.turno == 3
    assert comando.bloccato
    assert (comando.prove_x, comando.esercizi) == (1, 2)


@pytest.mark.unit
def test_a_gara_finita_senza_parimerito_si_termina(monkeypatch):
    from models.competition.spareggio_service import SpareggioService

    gara = _gara(status=GaraStatus.PLAYING.value, turno=5)
    monkeypatch.setattr(
        Gara,
        "get_real_status",
        lambda self: ProvaDerivedStatus.TOURNAMENT_COMPLETED.value,
    )
    monkeypatch.setattr(
        SpareggioService, "has_unresolved_tiebreakers", staticmethod(lambda _id: False)
    )

    comando = comando_per(gara)
    assert comando is not None
    assert comando.tipo == ComandoDirezione.TERMINA_GARA


@pytest.mark.unit
def test_a_gara_finita_con_un_parimerito_aperto_si_spareggia(monkeypatch):
    from models.competition.spareggio_service import SpareggioService

    gara = _gara(status=GaraStatus.PLAYING.value, turno=5)
    monkeypatch.setattr(
        Gara,
        "get_real_status",
        lambda self: ProvaDerivedStatus.TOURNAMENT_COMPLETED.value,
    )
    monkeypatch.setattr(
        SpareggioService, "has_unresolved_tiebreakers", staticmethod(lambda _id: True)
    )

    comando = comando_per(gara)
    assert comando is not None
    assert comando.tipo == ComandoDirezione.AVVIA_SPAREGGIO


@pytest.mark.unit
def test_in_attesa_di_spareggi_il_comando_e_quello_dello_spareggio(monkeypatch):
    from models.competition.spareggio_service import SpareggioService

    gara = _gara(status=GaraStatus.AWAITING_SSR.value, turno=5)
    monkeypatch.setattr(
        SpareggioService, "has_unresolved_tiebreakers", staticmethod(lambda _id: True)
    )

    comando = comando_per(gara)
    assert comando is not None
    assert comando.tipo == ComandoDirezione.AVVIA_SPAREGGIO


@pytest.mark.unit
def test_una_gara_conclusa_non_aspetta_piu_niente():
    assert comando_per(_gara(status=GaraStatus.COMPLETED.value)) is None


@pytest.mark.unit
def test_nella_formula_casuale_la_gara_e_finita_quando_finiscono_le_partite(
    monkeypatch,
):
    """I turni nascono tutti insieme: non c'è un «turno completato».

    È il ramo che il pannello valuta come `completed_matches == total_matches`,
    e senza di lui una gara casuale finita non annuncerebbe la terminazione.
    """
    from models.competition.spareggio_service import SpareggioService
    from models.match.models import Match

    gara = _gara(
        status=GaraStatus.PLAYING.value,
        turno=1,
        strategia=MatchmakingStrategy.RANDOM.value,
    )
    gara.matches = [
        Match(gara_id=1, round_number=1, status=MatchStatus.CONFIRMED_BY_BOTH.value),
        Match(gara_id=1, round_number=2, status=MatchStatus.CLOSED_UNILATERALLY.value),
    ]
    monkeypatch.setattr(
        SpareggioService, "has_unresolved_tiebreakers", staticmethod(lambda _id: False)
    )

    comando = comando_per(gara)
    assert comando is not None
    assert comando.tipo == ComandoDirezione.TERMINA_GARA
