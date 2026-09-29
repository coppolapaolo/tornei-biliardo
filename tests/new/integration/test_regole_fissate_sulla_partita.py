"""Le regole si fissano sulla partita quando nasce (ADR-075).

Un cambio di regola della gara vale dal turno successivo: una partita già
giocata, o in corso, resta con le regole con cui è cominciata. Prima molte
regole la partita le rileggeva dalla gara a ogni accesso, e un ricalcolo
dell'ELO rileggeva le categorie di oggi sulle partite di ieri.
"""

from __future__ import annotations

import importlib.util
import json
import sqlite3
import uuid
from datetime import date, timedelta
from pathlib import Path

import pytest

from models import Gara, Inscription, Match, User
from models.base import utc_now
from models.categoria.service import CategoriaService
from models.competition.inscription_service import InscriptionService
from models.competition.round_service import RoundService
from models.match.break_rules import BreakRule, StartRule
from models.match.regole_fissate import leggi_categorie
from models.rating.eligibility import RatingEligibility, RatingExclusion
from models.user.role_enum import UserRole

pytestmark = pytest.mark.integration


def _giocatori(db_session, n):
    utenti = []
    for _ in range(n):
        u = User(
            username=f"p_{uuid.uuid4().hex[:8]}",
            email=f"p_{uuid.uuid4().hex[:8]}@test.com",
            role=UserRole.PLAYER.value,
        )
        u.set_password("x")
        db_session.add(u)
        utenti.append(u)
    db_session.commit()
    return utenti


def _gara_avviata(db_session, n=4, **campi):
    direttore = _giocatori(db_session, 1)[0]
    direttore.role = UserRole.DIRECTOR.value
    valori = {
        "number": 1,
        "name": f"Gara {uuid.uuid4().hex[:6]}",
        "date": date.today() + timedelta(days=3),
        "discipline": "9_ball",
        "distance": 5,
        "is_race_to": True,
        "rounds_count": 3,
        "min_participants": 2,
        "max_participants": 16,
        "matchmaking_strategy": "amalfi",
        "first_round_policy": "random",
        "odd_number_policy": "bye",
        "director_id": direttore.id,
    }
    valori.update(campi)
    gara = Gara(**valori)
    db_session.add(gara)
    db_session.commit()
    InscriptionService.open_inscriptions(
        gara.id, utc_now() - timedelta(hours=1), utc_now() + timedelta(hours=1)
    )
    giocatori = _giocatori(db_session, n)
    for g in giocatori:
        InscriptionService.inscribe_user(g.id, gara.id)
    db_session.commit()
    RoundService.start_first_round(gara.id)
    db_session.commit()
    return db_session.get(Gara, gara.id), giocatori


class TestLaPartitaNasceConLeSueRegole:
    def test_le_regole_sono_scritte_sulla_partita(self, db_session):
        gara, _ = _gara_avviata(
            db_session,
            start_rule=StartRule.LAG.value,
            break_rule=BreakRule.WINNER_BREAKS.value,
        )
        partita = Match.query.filter_by(gara_id=gara.id, is_bye=False).first()
        assert partita.start_rule == "lag"
        assert partita.break_rule == "winner_breaks"
        assert partita.discipline == "9_ball"
        assert partita.is_race_to is True
        assert partita.has_handicap is False

    def test_cambiare_chi_spacca_non_tocca_le_partite_gia_nate(self, db_session):
        gara, _ = _gara_avviata(db_session, break_rule=BreakRule.ALTERNATE.value)
        partita = Match.query.filter_by(gara_id=gara.id, is_bye=False).first()

        gara.break_rule = BreakRule.WINNER_BREAKS.value
        db_session.commit()

        partita = db_session.get(Match, partita.id)
        assert partita.effective_break_rule == BreakRule.ALTERNATE

    def test_la_partita_nuova_prende_la_regola_nuova(self, db_session):
        gara, (a, b, *_resto) = _gara_avviata(
            db_session, break_rule=BreakRule.ALTERNATE.value
        )
        gara.break_rule = BreakRule.LOSER_BREAKS.value
        db_session.commit()

        nuova = Match(gara_id=gara.id, round_number=2, player1_id=a.id, player2_id=b.id)
        db_session.add(nuova)
        db_session.commit()
        assert nuova.effective_break_rule == BreakRule.LOSER_BREAKS

    def test_una_partita_senza_regola_fissata_ricade_sulla_gara(self, db_session):
        gara, _ = _gara_avviata(db_session, break_rule=BreakRule.ALTERNATE.value)
        partita = Match.query.filter_by(gara_id=gara.id, is_bye=False).first()
        partita.break_rule = None  # come una partita di prima della colonna
        db_session.commit()
        assert partita.effective_break_rule == BreakRule.ALTERNATE

    def test_la_x_resta_quella_che_era(self, db_session):
        gara, _ = _gara_avviata(db_session, n=5, odd_number_policy="bye")
        x = Match.query.filter_by(gara_id=gara.id, is_bye=True).first()
        assert x is not None
        assert x.x_with_challenge is False

        gara.odd_number_policy = "bye_with_challenge"
        db_session.commit()
        assert db_session.get(Match, x.id).is_x_with_challenge is False


class TestLeCategorieDellELO:
    def test_le_categorie_sono_fissate_alla_nascita(self, db_session):
        direttore = _giocatori(db_session, 1)[0]
        direttore.role = UserRole.DIRECTOR.value
        gara = Gara(
            number=1,
            name="Handicap",
            date=date.today() + timedelta(days=3),
            discipline="9_ball",
            distance=5,
            is_race_to=True,
            rounds_count=1,
            min_participants=2,
            matchmaking_strategy="amalfi",
            first_round_policy="random",
            odd_number_policy="bye",
            has_handicap=True,
            director_id=direttore.id,
        )
        db_session.add(gara)
        db_session.commit()
        InscriptionService.open_inscriptions(
            gara.id, utc_now() - timedelta(hours=1), utc_now() + timedelta(hours=1)
        )
        tutti = _giocatori(db_session, 4)
        for g in tutti:
            InscriptionService.inscribe_user(g.id, gara.id)
        db_session.commit()
        for g in tutti:
            ins = Inscription.query.filter_by(gara_id=gara.id, user_id=g.id).one()
            CategoriaService.set_inscription_categoria_by_name(gara, ins, "B")
        db_session.commit()
        RoundService.start_first_round(gara.id)
        db_session.commit()

        partita = Match.query.filter_by(gara_id=gara.id, is_bye=False).first()
        a = db_session.get(User, partita.player1_id)
        fissate = leggi_categorie(partita)
        assert set(fissate) == {partita.player1_id, partita.player2_id}
        assert RatingEligibility.exclusion_reason(partita) is None

        # A gara avviata la categoria di Rossi cambia, ma senza `force`: vale
        # per le partite che nasceranno, non per questa.
        ins_a = Inscription.query.filter_by(gara_id=gara.id, user_id=a.id).one()
        ins_a.categoria_id = None
        db_session.commit()
        partita = db_session.get(Match, partita.id)
        assert RatingEligibility.exclusion_reason(partita) is None
        indice = RatingEligibility.build_index([partita])
        assert RatingEligibility.exclusion_reason(partita, indice) is None

        # Una correzione (`force=True`, lo script di riparazione) invece
        # arriva anche alla partita giocata.
        CategoriaService.set_inscription_categoria_by_name(gara, ins_a, "A", force=True)
        db_session.commit()
        partita = db_session.get(Match, partita.id)
        assert (
            RatingEligibility.exclusion_reason(partita)
            == RatingExclusion.HANDICAP_DIFFERENT_CATEGORY
        )


class TestPartiteASet:
    def test_i_triangoli_per_set_del_turno_restano_sulla_partita(self, db_session):
        gara, (a, b, *_resto) = _gara_avviata(
            db_session, is_multi_set=True, match_distance=2, distance=4
        )
        partita = Match.query.filter_by(gara_id=gara.id, is_bye=False).first()
        assert partita.set_distance == 4

        gara.distance = 7
        db_session.commit()
        partita = db_session.get(Match, partita.id)
        assert partita.distance_config.racks == 4


class TestLaMigration:
    def _migration(self):
        percorso = (
            Path(__file__).resolve().parents[3]
            / "migrations"
            / "20260929_regole_fissate.py"
        )
        spec = importlib.util.spec_from_file_location("regole_fissate_mig", percorso)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        return modulo

    def test_riempie_con_i_valori_di_oggi_e_si_puo_rilanciare(self, tmp_path):
        percorso = tmp_path / "db.sqlite"
        conn = sqlite3.connect(percorso)
        conn.executescript("""
            CREATE TABLE campionato (id INTEGER PRIMARY KEY, has_handicap BOOLEAN,
                default_start_rule VARCHAR, default_break_rule VARCHAR);
            CREATE TABLE gara (id INTEGER PRIMARY KEY, campionato_id INTEGER,
                is_race_to BOOLEAN, is_race_to_sets BOOLEAN, discipline VARCHAR,
                has_handicap BOOLEAN, start_rule VARCHAR, break_rule VARCHAR,
                distance INTEGER, odd_number_policy VARCHAR);
            CREATE TABLE inscription (id INTEGER PRIMARY KEY, gara_id INTEGER,
                user_id INTEGER, categoria_id INTEGER, is_withdrawn BOOLEAN);
            CREATE TABLE trio_match (id INTEGER PRIMARY KEY, match_id INTEGER,
                player1_id INTEGER, player2_id INTEGER, player3_id INTEGER);
            CREATE TABLE match (id INTEGER PRIMARY KEY, gara_id INTEGER,
                player1_id INTEGER, player2_id INTEGER, is_bye BOOLEAN,
                is_multi_set BOOLEAN, is_race_to BOOLEAN, is_race_to_sets BOOLEAN,
                discipline VARCHAR, has_handicap BOOLEAN);
            INSERT INTO campionato VALUES (1, 1, 'lag', NULL);
            INSERT INTO gara VALUES (10, 1, 1, NULL, '8_ball', NULL, NULL,
                'winner_breaks', 5, 'bye_with_challenge');
            INSERT INTO inscription VALUES (1, 10, 100, 7, 0), (2, 10, 101, NULL, 0);
            INSERT INTO match VALUES (1000, 10, 100, 101, 0, 0, NULL, NULL,
                NULL, NULL);
            INSERT INTO match VALUES (1001, 10, 100, NULL, 1, 1, NULL, NULL,
                '9_ball', NULL);
            """)
        conn.commit()
        conn.close()

        migration = self._migration()
        migration.upgrade_sqlite(str(percorso))
        migration.upgrade_sqlite(str(percorso))

        conn = sqlite3.connect(percorso)
        riga = conn.execute(
            "SELECT is_race_to, discipline, has_handicap, start_rule, break_rule, "
            "categories_snapshot FROM match WHERE id = 1000"
        ).fetchone()
        assert riga[0] == 1
        assert riga[1] == "8_ball"
        assert riga[2] == 1  # dal campionato
        assert riga[3] == "lag"  # dal campionato
        assert riga[4] == "winner_breaks"  # dalla gara
        assert json.loads(riga[5]) == {"100": 7, "101": None}

        x = conn.execute(
            "SELECT discipline, set_distance, x_with_challenge FROM match "
            "WHERE id = 1001"
        ).fetchone()
        assert x == ("9_ball", 5, 1)
        conn.close()
