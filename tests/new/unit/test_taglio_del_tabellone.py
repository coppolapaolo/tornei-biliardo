"""Chi va al tabellone dopo i gironi, nelle classifiche per girone (ADR-081).

Decisione dell'utente del 2026-10-11: quando si sa chi passa, accanto a chi
va al tabellone c'è «al tabellone», accanto agli altri «fuori», e fra i due
la riga del taglio. Serve soprattutto con due «2º pari merito» (posizione
mostrata, #661) di cui ne passa uno solo: chi passa lo decide la catena di
turno all'ultimo turno dei gironi (`fase_finale_service.semina`).

* `segna_il_taglio`, puro: l'ordine dentro il girone e i segni;
* `chi_va_al_tabellone`, sul database: None finché si giocano i gironi, poi
  la classifica del taglio, poi i giocatori del tabellone sorteggiato; mai
  con il girone unico.
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
    GironeInPagina,
    RigaDelGirone,
    segna_il_taglio,
)
from models.competition.fase_finale_service import chi_va_al_tabellone, semina
from models.competition.inscription_service import InscriptionService
from models.competition.models import Gara, Inscription
from models.competition.round_service import RoundService
from models.competition.services import GaraService
from models.match.models import Match
from models.match.services import RackService
from models.status_enum import MatchStatus
from models.user.role_enum import UserRole

pytestmark = pytest.mark.unit


def _riga(uid: int, posizione: int) -> RigaDelGirone:
    return RigaDelGirone(riga=SimpleNamespace(user_id=uid), posizione=posizione)


class TestSegnaIlTaglio:
    def test_due_secondi_pari_merito_ne_passa_uno(self):
        # Il 2 e il 3 sono «2º» entrambi; il taglio ha scelto il 3, che sale
        # sopra la riga del taglio. Le posizioni mostrate non cambiano.
        girone = GironeInPagina(
            0, "A", (_riga(1, 1), _riga(2, 2), _riga(3, 2), _riga(4, 4))
        )
        (segnato,) = segna_il_taglio([girone], {1, 3})
        assert [v.riga.user_id for v in segnato.righe] == [1, 3, 2, 4]
        assert [v.posizione for v in segnato.righe] == [1, 2, 2, 4]
        assert [v.taglio for v in segnato.righe] == [True, True, False, False]
        assert [v.primo_fuori for v in segnato.righe] == [False, False, True, False]

    def test_finche_non_si_sa_non_cambia_niente(self):
        girone = GironeInPagina(0, "A", (_riga(1, 1), _riga(2, 2)))
        assert segna_il_taglio([girone], None) == [girone]
        assert all(v.taglio is None for v in girone.righe)

    def test_un_girone_senza_qualificati_non_ha_la_riga(self):
        girone = GironeInPagina(1, "B", (_riga(5, 1), _riga(6, 2)))
        (segnato,) = segna_il_taglio([girone], {1})
        assert [v.taglio for v in segnato.righe] == [False, False]
        assert not any(v.primo_fuori for v in segnato.righe)


# ---------------------------------------------------------------------------
# Sul database
# ---------------------------------------------------------------------------


def _utente(role: str, elo=None) -> User:
    uid = uuid.uuid4().hex[:8]
    user = User(username=f"tg_{role}_{uid}", email=f"tg_{role}_{uid}@test.com")
    user.role = role
    user.set_password("x")
    user.elo_rating = elo
    db.session.add(user)
    return user


def _gara(n: int = 8) -> Tuple[Gara, List[User]]:
    director = _utente(UserRole.DIRECTOR.value)
    players = [_utente(UserRole.PLAYER.value, elo=2000 - 10 * i) for i in range(n)]
    db.session.commit()
    gara = GaraService.create_gara(
        campionato_id=None,
        number=1,
        name="Taglio",
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
        final_phase_mode="tabellone",
        qualifiers_per_group=2,
        third_place_match=True,
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


class TestChiVaAlTabellone:
    def test_nei_gironi_no_a_gironi_finiti_il_taglio_poi_il_tabellone(self, db_session):
        gara, players = _gara()
        elo = {p.id: p.elo_rating for p in players}
        RoundService.start_first_round(gara.id, groups_count=2)
        _gioca(gara.id, 1, elo)
        assert chi_va_al_tabellone(db.session.get(Gara, gara.id)) is None
        for r in (2, 3):
            RoundService.start_next_round(gara.id, r)
            _gioca(gara.id, r, elo)
        gara = db.session.get(Gara, gara.id)
        qualificati = chi_va_al_tabellone(gara)
        assert qualificati == frozenset(semina(gara)[0])
        assert len(qualificati) == 4
        # Due per girone.
        girone_di = {
            i.user_id: i.group_index
            for i in Inscription.query.filter_by(gara_id=gara.id).all()
        }
        assert sorted(girone_di[p] for p in qualificati) == [0, 0, 1, 1]

        RoundService.start_next_round(gara.id, 4)
        gara = db.session.get(Gara, gara.id)
        semifinalisti = {
            p
            for m in Match.query.filter_by(gara_id=gara.id, round_number=4).all()
            for p in (m.player1_id, m.player2_id)
        }
        assert chi_va_al_tabellone(gara) == semifinalisti == qualificati

    def test_col_girone_unico_non_si_segna_niente(self, db_session):
        gara, players = _gara(5)
        elo = {p.id: p.elo_rating for p in players}
        RoundService.start_first_round(gara.id, groups_count=1)
        gara = db.session.get(Gara, gara.id)
        for r in range(1, gara.rounds_count + 1):
            if r > 1:
                RoundService.start_next_round(gara.id, r)
            _gioca(gara.id, r, elo)
        assert chi_va_al_tabellone(db.session.get(Gara, gara.id)) is None
