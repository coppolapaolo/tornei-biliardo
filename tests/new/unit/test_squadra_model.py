"""Unit test del modello ``Squadra`` e dei campi squadra correlati (Step 2).

Copre le tre regole che rendono l'elenco squadre usabile senza degenerare in
doppioni o in righe orfane:

1. l'elenco appartiene a **una sola** competizione (campionato XOR gara);
2. i nomi sono unici dentro il proprio elenco, a confronto case-insensitive,
   ma elenchi diversi sono indipendenti;
3. la squadra del profilo è testo libero e non ha alcun legame con l'elenco.
"""

from datetime import date, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from models import Squadra, User, Gara, Campionato, Inscription
from models.squadra.models import normalize_squadra_name
from models.user.role_enum import UserRole

pytestmark = pytest.mark.unit


def _director(db_session, suffix: str) -> User:
    user = User(
        username=f"dir_{suffix}",
        email=f"dir_{suffix}@example.com",
        role=UserRole.DIRECTOR.value,
    )
    user.set_password("pw")
    db_session.add(user)
    db_session.flush()
    return user


def _gara(db_session, director: User, suffix: str, campionato=None) -> Gara:
    gara = Gara(
        campionato_id=campionato.id if campionato else None,
        director_id=None if campionato else director.id,
        number=1,
        name=f"Gara {suffix}",
        date=date.today() + timedelta(days=7),
        discipline="palla_8",
        distance=5,
        rounds_count=3,
    )
    db_session.add(gara)
    db_session.flush()
    return gara


def _campionato(db_session, director: User, suffix: str) -> Campionato:
    camp = Campionato(name=f"Campionato {suffix}")
    db_session.add(camp)
    db_session.flush()
    return camp


class TestNormalizzazione:
    def test_maiuscole_e_spazi_collassano(self):
        assert normalize_squadra_name("  Circolo   Biliardo  ") == "circolo biliardo"
        assert normalize_squadra_name("CIRCOLO BILIARDO") == "circolo biliardo"

    def test_nome_visualizzato_conserva_le_maiuscole(self, db_session):
        squadra = Squadra(name="  Circolo   Biliardo ", gara_id=None, campionato_id=1)
        # Il nome mostrato conserva la forma scelta dall'utente, ripulita dagli
        # spazi ridondanti; solo la forma normalizzata è minuscola.
        assert squadra.name == "Circolo Biliardo"
        assert squadra.normalized_name == "circolo biliardo"

    def test_rename_riallinea_la_forma_normalizzata(self, db_session):
        squadra = Squadra(name="Vecchio", campionato_id=1)
        squadra.rename("  Nuovo  Nome ")
        assert squadra.name == "Nuovo Nome"
        assert squadra.normalized_name == "nuovo nome"


class TestProprietarioEsclusivo:
    """L'elenco vive in una competizione sola: campionato XOR gara."""

    def test_squadra_di_campionato_ok(self, db_session):
        director = _director(db_session, "camp_ok")
        camp = _campionato(db_session, director, "ok")
        db_session.add(Squadra(name="Alfa", campionato_id=camp.id))
        db_session.flush()

    def test_squadra_di_gara_standalone_ok(self, db_session):
        director = _director(db_session, "gara_ok")
        gara = _gara(db_session, director, "ok")
        db_session.add(Squadra(name="Alfa", gara_id=gara.id))
        db_session.flush()

    def test_entrambi_valorizzati_rifiutato(self, db_session):
        director = _director(db_session, "both")
        camp = _campionato(db_session, director, "both")
        gara = _gara(db_session, director, "both", campionato=camp)
        db_session.add(Squadra(name="Alfa", campionato_id=camp.id, gara_id=gara.id))
        with pytest.raises(IntegrityError):
            db_session.flush()
        db_session.rollback()

    def test_nessuno_valorizzato_rifiutato(self, db_session):
        db_session.add(Squadra(name="Orfana"))
        with pytest.raises(IntegrityError):
            db_session.flush()
        db_session.rollback()


class TestUnicitaNome:
    def test_doppione_case_insensitive_rifiutato(self, db_session):
        director = _director(db_session, "dup")
        camp = _campionato(db_session, director, "dup")
        db_session.add(Squadra(name="Circolo X", campionato_id=camp.id))
        db_session.flush()
        db_session.add(Squadra(name="circolo  x", campionato_id=camp.id))
        with pytest.raises(IntegrityError):
            db_session.flush()
        db_session.rollback()

    def test_elenchi_diversi_sono_indipendenti(self, db_session):
        """Lo stesso nome in due campionati diversi non è un doppione.

        È la conseguenza voluta dello scoping: le squadre esistono dentro la
        competizione, quindi due campionati che ospitano la stessa società
        hanno due righe distinte e non si disturbano.
        """
        director = _director(db_session, "scope")
        camp_a = _campionato(db_session, director, "scope_a")
        camp_b = _campionato(db_session, director, "scope_b")
        db_session.add(Squadra(name="Circolo X", campionato_id=camp_a.id))
        db_session.add(Squadra(name="Circolo X", campionato_id=camp_b.id))
        db_session.flush()


class TestCampiCorrelati:
    def test_profilo_e_testo_libero_senza_fk(self, db_session):
        """`user.squadra` non è collegato all'elenco: è solo un suggerimento."""
        user = _director(db_session, "profilo")
        user.squadra = "Una squadra che non esiste in nessun elenco"
        db_session.flush()
        assert user.squadra == "Una squadra che non esiste in nessun elenco"

    def test_iscrizione_senza_squadra_e_stato_legittimo(self, db_session):
        """NULL su `inscription.squadra_id` significa "gioca senza squadra"."""
        director = _director(db_session, "insc")
        gara = _gara(db_session, director, "insc")
        player = User(
            username="p_insc", email="p_insc@example.com", role=UserRole.PLAYER.value
        )
        player.set_password("pw")
        db_session.add(player)
        db_session.flush()

        inscription = Inscription(user_id=player.id, gara_id=gara.id)
        db_session.add(inscription)
        db_session.flush()
        assert inscription.squadra_id is None

    def test_iscrizione_collegata_a_squadra(self, db_session):
        director = _director(db_session, "link")
        gara = _gara(db_session, director, "link")
        squadra = Squadra(name="Alfa", gara_id=gara.id)
        db_session.add(squadra)
        player = User(
            username="p_link", email="p_link@example.com", role=UserRole.PLAYER.value
        )
        player.set_password("pw")
        db_session.add(player)
        db_session.flush()

        inscription = Inscription(
            user_id=player.id, gara_id=gara.id, squadra_id=squadra.id
        )
        db_session.add(inscription)
        db_session.flush()
        assert inscription.squadra.name == "Alfa"


class TestGaraOpzioniTabellone:
    def test_default_non_cambiano_il_comportamento_esistente(self, db_session):
        """Le nuove opzioni nascono spente: nessun impatto su chi non le usa."""
        director = _director(db_session, "defaults")
        gara = _gara(db_session, director, "defaults")
        db_session.refresh(gara)
        assert gara.separate_teammates is False
        assert gara.third_place_match is False
        assert gara.draw_seed is None
        assert gara.seeding_rating == "elo"

    def test_max_participants_obbligatorio_per_tabellone(self, db_session):
        director = _director(db_session, "maxp")
        gara = _gara(db_session, director, "maxp")
        gara.matchmaking_strategy = "direct_elimination"
        gara.max_participants = None
        errors = gara.validate_strategy_configuration()
        assert any("massimo di partecipanti" in e for e in errors)

        gara.max_participants = 16
        errors = gara.validate_strategy_configuration()
        assert not any("massimo di partecipanti" in e for e in errors)

    def test_max_participants_non_richiesto_per_le_altre_strategie(self, db_session):
        director = _director(db_session, "maxp_other")
        gara = _gara(db_session, director, "maxp_other")
        gara.matchmaking_strategy = "amalfi"
        gara.max_participants = None
        errors = gara.validate_strategy_configuration()
        assert not any("massimo di partecipanti" in e for e in errors)


class TestMatchBracketColumns:
    def test_default_null_per_i_match_non_tabellone(self, db_session):
        """NULL su tutte e tre = match che non appartiene a un tabellone."""
        from models import Match

        director = _director(db_session, "bracket")
        gara = _gara(db_session, director, "bracket")
        match = Match(gara_id=gara.id, round_number=1)
        db_session.add(match)
        db_session.flush()
        assert match.bracket_type is None
        assert match.bracket_round is None
        assert match.bracket_slot is None
