"""Le pagine delle finali per piazzamento (ADR-081, PR 6, ultima parte).

* nelle classifiche per girone, quando gli incroci si sanno, la finale che
  ognuno giocherà — «→ finale 3°/4° posto con … (2° girone B)» — e l'ultimo
  del girone più numeroso «9° diretto» (`finali_dei_giocatori`,
  `segna_le_finali`, puri; `fase_finale_service.finali_dei_giocatori` sul
  database);
* una domanda sola per «che fase finale ha la gara?»
  (`fase_finale_della_gara`): quella scelta finché i gironi non ci sono, poi
  quella che si gioca davvero — nessuna col girone unico;
* la frase dei pari merito della classifica finale: con una fase finale lo
  spareggio SSR non si gioca, e la frase non lo promette più.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from types import SimpleNamespace
from typing import List, Tuple

import pytest

from models import User
from models.base import db, utc_now
from models.classification.gironi_in_pagina import (
    FinaleInPagina,
    GironeInPagina,
    RigaDelGirone,
    finali_dei_giocatori,
    segna_le_finali,
)
from models.competition import fase_finale_service
from models.competition.fase_finale_service import (
    fase_finale_della_gara,
    finali_dei_giocatori as finali_della_gara,
)
from models.competition.inscription_service import InscriptionService
from models.competition.models import Gara
from models.competition.round_service import RoundService
from models.competition.services import GaraService
from models.match.models import Match
from models.match.services import RackService
from models.matchmaking.fase_finale import FaseFinale
from models.status_enum import MatchStatus
from models.storia.regolamento import frase_della_catena, frase_della_fase_finale
from models.user.role_enum import UserRole

pytestmark = pytest.mark.unit


class TestLaFinaleDiOgnuno:
    def test_quattro_piu_quattro_ognuno_ha_la_sua_finale(self):
        finali = finali_dei_giocatori(
            [(1, 5), (2, 6), (3, 7), (4, 8)],
            [],
            {p: 0 if p <= 4 else 1 for p in range(1, 9)},
        )
        assert finali[2] == FinaleInPagina(
            coppia=2, avversario_id=6, girone_avversario=1
        )
        assert finali[6].avversario_id == 2 and finali[6].nome_girone_avversario == "A"
        assert finali[2].nome_girone_avversario == "B"
        assert all(f.vinta is None for f in finali.values())

    def test_cinque_piu_quattro_l_ultimo_e_nono_diretto(self):
        # SPECIFICHE.md, «Finali per piazzamento»: «Con 5 + 4 iscritti il 5º
        # del girone da cinque è 9º».
        finali = finali_dei_giocatori([(1, 6), (2, 7), (3, 8), (4, 9)], [5], {})
        assert finali[5].coppia is None and finali[5].posto_diretto == 9
        assert finali[5].uscita is None

    def test_a_finale_giocata_chi_ha_vinto_e_chi_ha_perso(self):
        finali = finali_dei_giocatori([(1, 5), (2, 6)], [], {}, {0: 5, 1: None})
        assert finali[5].vinta is True and finali[1].vinta is False
        assert finali[2].vinta is None
        # Le parole della classifica finale (`uscita`): chi vince la finale
        # per il 1°/2° posto ha vinto la gara.
        assert finali[5].position == 1 and finali[1].position is None
        assert finali[1].uscita.chiave == "piazzamento"
        assert finali[1].uscita.numero == 1


def _riga(uid: int, posizione: int) -> RigaDelGirone:
    return RigaDelGirone(
        riga=SimpleNamespace(user_id=uid, user=SimpleNamespace(username=f"g{uid}")),
        posizione=posizione,
    )


class TestSegnaLeFinali:
    def test_accanto_a_ogni_riga_la_finale_con_l_avversario(self):
        a = GironeInPagina(0, "A", (_riga(1, 1), _riga(2, 2)))
        b = GironeInPagina(1, "B", (_riga(5, 1), _riga(6, 2), _riga(7, 3)))
        finali = finali_dei_giocatori(
            [(1, 5), (2, 6)], [7], {1: 0, 2: 0, 5: 1, 6: 1, 7: 1}
        )
        segnati = segna_le_finali([a, b], finali)
        due = segnati[0].righe[1].finale
        assert due.coppia == 2 and due.avversario.user.username == "g6"
        assert segnati[1].righe[2].finale.posto_diretto == 5

    def test_finche_non_si_sa_non_cambia_niente(self):
        a = GironeInPagina(0, "A", (_riga(1, 1),))
        assert segna_le_finali([a], None) == [a]
        assert a.righe[0].finale is None


class TestLaDomandaUnica:
    def test_prima_dell_avvio_la_scelta(self):
        for fase in (FaseFinale.TABELLONE, FaseFinale.PIAZZAMENTO):
            gara = SimpleNamespace(id=None, effective_final_phase_mode=fase)
            assert fase_finale_della_gara(gara) is fase

    def test_senza_fase_finale_nessuna(self):
        gara = SimpleNamespace(id=None, effective_final_phase_mode=FaseFinale.NESSUNA)
        assert fase_finale_della_gara(gara) is FaseFinale.NESSUNA
        assert fase_finale_della_gara(SimpleNamespace(id=None)) is FaseFinale.NESSUNA


class TestLaFraseDeiPariMerito:
    def test_con_le_finali_niente_spareggio(self, app, monkeypatch):
        monkeypatch.setattr(
            fase_finale_service,
            "fase_finale_della_gara",
            lambda g: FaseFinale.PIAZZAMENTO,
        )
        with app.test_request_context():
            frase = frase_della_fase_finale(SimpleNamespace(), (), None)
        assert "finale per piazzamento" in frase and "niente spareggio SSR" in frase

    def test_col_tabellone_la_catena_senza_lo_spareggio(self, app, monkeypatch):
        from models.classification.ordinamento import Criterio, Voce
        from models.status_enum import ClassificationSystem

        monkeypatch.setattr(
            fase_finale_service,
            "fase_finale_della_gara",
            lambda g: FaseFinale.TABELLONE,
        )
        catena = (
            Voce(Criterio.DIFFERENZA_RACK),
            Voce(Criterio.SPAREGGIO_SSR, 3),
            Voce(Criterio.SORTEGGIO),
        )
        with app.test_request_context():
            frase = frase_della_fase_finale(
                SimpleNamespace(), catena, ClassificationSystem.WINS
            )
        assert frase.startswith("Il podio lo decide il tabellone, senza spareggio SSR.")
        assert "a pari vittorie conta la differenza triangoli." in frase
        assert "fino al 3" not in frase

    def test_senza_fase_finale_resta_la_catena(self, app, monkeypatch):
        monkeypatch.setattr(
            fase_finale_service, "fase_finale_della_gara", lambda g: FaseFinale.NESSUNA
        )
        with app.test_request_context():
            assert frase_della_fase_finale(SimpleNamespace(), (), None) is None


# ---------------------------------------------------------------------------
# Sul database
# ---------------------------------------------------------------------------


def _utente(role: str, elo=None) -> User:
    uid = uuid.uuid4().hex[:8]
    user = User(username=f"fpp_{role}_{uid}", email=f"fpp_{role}_{uid}@test.com")
    user.role = role
    user.set_password("x")
    user.elo_rating = elo
    db.session.add(user)
    return user


def _gara(n: int, fase: str = "piazzamento") -> Tuple[Gara, List[User]]:
    director = _utente(UserRole.DIRECTOR.value)
    players = [_utente(UserRole.PLAYER.value, elo=2000 - 10 * i) for i in range(n)]
    db.session.commit()
    gara = GaraService.create_gara(
        campionato_id=None,
        number=1,
        name="Finali",
        date=date.today() + timedelta(days=7),
        location="Sala",
        description="",
        rounds_count=3,
        min_participants=3,
        max_participants=32,
        entry_fee=0.0,
        discipline="8_ball",
        distance=3,
        is_race_to=True,
        director_id=director.id,
        matchmaking_strategy="round_robin",
        first_round_policy="random",
        odd_number_policy="bye",
        anti_rematch_enabled=False,
        max_groups=2,
        group_seeding="elo",
        final_phase_mode=fase,
    )
    InscriptionService.open_inscriptions(
        gara.id, utc_now() - timedelta(hours=1), utc_now() + timedelta(hours=1)
    )
    for player in players:
        InscriptionService.inscribe_user(player.id, gara.id)
    return gara, players


def _gioca(gara_id: int, r: int, elo) -> None:
    for match in Match.query.filter_by(gara_id=gara_id, round_number=r).all():
        if match.is_bye or MatchStatus.is_finished(match.status):
            continue
        vince = max((match.player1_id, match.player2_id), key=lambda p: elo[p])
        for _ in range(match.match_distance):
            RackService.add_rack_with_score_update(
                match_id=match.id,
                winner_id=vince,
                reported_by_id=vince,
                validated_by_admin=True,
            )
    db.session.commit()
    RoundService.update_round_progression(gara_id)
    db.session.commit()


class TestSulDatabase:
    def test_si_sanno_a_gironi_finiti_e_poi_dicono_chi_ha_vinto(self, db_session):
        gara, players = _gara(9)
        elo = {p.id: p.elo_rating for p in players}
        assert (
            fase_finale_della_gara(db.session.get(Gara, gara.id))
            is FaseFinale.PIAZZAMENTO
        )
        RoundService.start_first_round(gara.id, groups_count=2)
        _gioca(gara.id, 1, elo)
        assert finali_della_gara(db.session.get(Gara, gara.id)) is None
        gara = db.session.get(Gara, gara.id)
        gironi = fase_finale_service.turni_dei_gironi(gara)
        for r in range(2, gironi + 1):
            RoundService.start_next_round(gara.id, r)
            _gioca(gara.id, r, elo)
        gara = db.session.get(Gara, gara.id)
        finali = finali_della_gara(gara)
        assert finali is not None and len(finali) == 9
        diretti = [p for p, f in finali.items() if f.posto_diretto]
        assert len(diretti) == 1 and finali[diretti[0]].posto_diretto == 9
        # Il più forte gioca la finale per il 1°/2° posto.
        assert finali[players[0].id].coppia == 1

        RoundService.start_next_round(gara.id, gironi + 1)
        _gioca(gara.id, gironi + 1, elo)
        finali = finali_della_gara(db.session.get(Gara, gara.id))
        assert finali[players[0].id].vinta is True
        assert finali[finali[players[0].id].avversario_id].vinta is False

    def test_col_girone_unico_nessuna_fase_finale(self, db_session):
        gara, players = _gara(5)
        RoundService.start_first_round(gara.id, groups_count=1)
        gara = db.session.get(Gara, gara.id)
        assert fase_finale_della_gara(gara) is FaseFinale.NESSUNA
        assert finali_della_gara(gara) is None
        # E la frase dei pari merito torna quella della catena intera.
        frase = frase_della_catena(gara, "catena_gara")
        assert frase is not None and "finale per piazzamento" not in frase

    def test_col_tabellone_la_frase_non_promette_lo_spareggio(self, db_session):
        gara, _players = _gara(8, "tabellone")
        RoundService.start_first_round(gara.id, groups_count=2)
        gara = db.session.get(Gara, gara.id)
        assert fase_finale_della_gara(gara) is FaseFinale.TABELLONE
        frase = frase_della_catena(gara, "catena_gara")
        assert frase.startswith("Il podio lo decide il tabellone")
        assert "SSR fino" not in frase
