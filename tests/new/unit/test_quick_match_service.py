"""Unit test dell'avvio rapido (issue #176).

L'avvio rapido nasce per togliere domande, quindi la maggior parte di questi
test verifica **cosa succede quando non si risponde a niente**: quali valori si
ereditano, e in che stato nasce la partita.
"""

from datetime import timedelta

import pytest

from models.base import db, utc_now
from models.exceptions import ConflictError, NotFoundError, ValidationError
from models.individual_match.models import IndividualMatch
from models.individual_match.quick_match_service import QuickMatchService
from models.status_enum import Discipline, MatchStatus


def _played_match(player1, player2, **kwargs):
    """Una partita gia' giocata, da cui l'avvio rapido erediterà le abitudini."""
    defaults = dict(
        player1_id=player1.id,
        player2_id=player2.id,
        location="Sala Regina",
        scheduled_at=utc_now() - timedelta(days=1),
        status=MatchStatus.CONFIRMED_BY_BOTH,
        discipline=Discipline.NINE_BALL.value,
        distance=7,
        is_race_to=True,
        break_rule="winner_breaks",
    )
    defaults.update(kwargs)
    match = IndividualMatch(**defaults)
    db.session.add(match)
    db.session.commit()
    return match


class TestDefaults:
    """Le precompilazioni: quando, dove, come."""

    def test_senza_storico_usa_i_default_di_sistema(
        self, app, db_session, isolated_players
    ):
        player = isolated_players[0]

        defaults = QuickMatchService.get_defaults(player.id)

        assert defaults["discipline"] == Discipline.EIGHT_BALL.value
        assert defaults["match_format"] == "single"
        assert defaults["distance"] == 5
        assert defaults["is_race_to"] is True
        assert defaults["location"] == ""
        assert defaults["billiard_hall_id"] is None

    def test_eredita_dall_ultima_partita(self, app, db_session, isolated_players):
        player1, player2 = isolated_players[:2]
        _played_match(player1, player2)

        defaults = QuickMatchService.get_defaults(player1.id)

        assert defaults["location"] == "Sala Regina"
        assert defaults["discipline"] == Discipline.NINE_BALL.value
        assert defaults["distance"] == 7
        assert defaults["break_rule"] == "winner_breaks"
        assert defaults["match_format"] == "single"

    def test_eredita_anche_da_avversario(self, app, db_session, isolated_players):
        """L'ultima partita conta anche quando il giocatore era il secondo."""
        player1, player2 = isolated_players[:2]
        _played_match(player1, player2)

        defaults = QuickMatchService.get_defaults(player2.id)

        assert defaults["location"] == "Sala Regina"
        assert defaults["distance"] == 7

    def test_ultima_partita_vince_sulla_penultima(
        self, app, db_session, isolated_players
    ):
        player1, player2 = isolated_players[:2]
        _played_match(player1, player2, location="Sala Vecchia", distance=5)
        _played_match(player1, player2, location="Sala Nuova", distance=9)

        defaults = QuickMatchService.get_defaults(player1.id)

        assert defaults["location"] == "Sala Nuova"
        assert defaults["distance"] == 9

    def test_eredita_il_formato_libero(self, app, db_session, isolated_players):
        player1, player2 = isolated_players[:2]
        _played_match(player1, player2, distance=None)

        defaults = QuickMatchService.get_defaults(player1.id)

        assert defaults["match_format"] == "free"
        assert defaults["distance"] is None

    def test_eredita_il_multi_set(self, app, db_session, isolated_players):
        player1, player2 = isolated_players[:2]
        _played_match(player1, player2, is_multi_set=True, distance=5, match_distance=3)

        defaults = QuickMatchService.get_defaults(player1.id)

        assert defaults["match_format"] == "multi"
        assert defaults["distance"] == 5
        assert defaults["match_distance"] == 3

    def test_senza_partite_ripiega_sulla_sala_dove_sei_disponibile(
        self, app, db_session, isolated_players
    ):
        from models.location.models import BilliardHall, UserLocationAvailability

        player = isolated_players[0]
        hall = BilliardHall(name="Sala Disponibile", city="Udine")
        db_session.add(hall)
        db_session.commit()
        db_session.add(
            UserLocationAvailability(
                user_id=player.id, billiard_hall_id=hall.id, is_available=True
            )
        )
        db_session.commit()

        defaults = QuickMatchService.get_defaults(player.id)

        assert defaults["location"] == "Sala Disponibile"
        assert defaults["billiard_hall_id"] == hall.id


class TestStart:
    """L'avvio vero: una partita che nasce gia' cominciata."""

    def test_parte_subito_senza_proposta(self, app, db_session, isolated_players):
        player1, player2 = isolated_players[:2]
        player2.gamification_override = True
        db_session.commit()

        prima = utc_now()
        match = QuickMatchService.start(player1.id, player2.id)

        assert match.proposal_id is None
        assert match.status == MatchStatus.IN_PROGRESS
        assert match.started_at is not None
        # "Adesso": la domanda che l'issue voleva smettere di fare.
        assert match.scheduled_at >= prima - timedelta(minutes=1)
        assert match.scheduled_at <= utc_now() + timedelta(minutes=1)
        assert match.player1_id == player1.id
        assert match.player2_id == player2.id

    def test_usa_le_precompilazioni_senza_che_le_si_chieda(
        self, app, db_session, isolated_players
    ):
        player1, player2, player3 = isolated_players[:3]
        player3.gamification_override = True
        db_session.commit()
        _played_match(player1, player2)

        match = QuickMatchService.start(player1.id, player3.id)

        assert match.location == "Sala Regina"
        assert match.discipline == Discipline.NINE_BALL.value
        assert match.distance == 7
        assert match.break_rule == "winner_breaks"

    def test_la_configurazione_esplicita_vince_sul_default(
        self, app, db_session, isolated_players
    ):
        player1, player2 = isolated_players[:2]
        player2.gamification_override = True
        db_session.commit()
        _played_match(player1, player2)

        match = QuickMatchService.start(
            player1.id,
            player2.id,
            {"discipline": Discipline.EIGHT_BALL.value, "distance": 3},
        )

        assert match.discipline == Discipline.EIGHT_BALL.value
        assert match.distance == 3

    def test_multi_set_apre_il_primo_set(self, app, db_session, isolated_players):
        player1, player2 = isolated_players[:2]
        player2.gamification_override = True
        db_session.commit()

        match = QuickMatchService.start(
            player1.id,
            player2.id,
            {"match_format": "multi", "distance": 4, "match_distance": 2},
        )

        assert match.is_multi_set is True
        assert match.match_distance == 2
        assert match.distance == 4
        assert len(match.sets) == 1

    def test_formato_libero_azzera_la_distanza(self, app, db_session, isolated_players):
        player1, player2 = isolated_players[:2]
        player2.gamification_override = True
        db_session.commit()

        match = QuickMatchService.start(
            player1.id, player2.id, {"match_format": "free"}
        )

        assert match.distance is None
        assert match.is_multi_set is False

    def test_un_secondo_avvio_torna_alla_partita_in_corso(
        self, app, db_session, isolated_players
    ):
        """Due partite in corso fra le stesse due persone non esistono."""
        player1, player2 = isolated_players[:2]
        player1.gamification_override = True
        player2.gamification_override = True
        db_session.commit()

        primo = QuickMatchService.start(player1.id, player2.id)
        secondo = QuickMatchService.start(player2.id, player1.id)

        assert secondo.id == primo.id
        assert IndividualMatch.query.count() == 1

    def test_non_si_gioca_contro_se_stessi(self, app, db_session, isolated_players):
        player = isolated_players[0]

        with pytest.raises(ValidationError):
            QuickMatchService.start(player.id, player.id)

    def test_avversario_inesistente(self, app, db_session, isolated_players):
        player = isolated_players[0]

        with pytest.raises(NotFoundError):
            QuickMatchService.start(player.id, 999999)

    def test_avversario_che_non_ha_sbloccato_le_sfide(
        self, app, db_session, isolated_players
    ):
        """Stesso filtro dell'elenco avversari: chi non ce l'ha non si sceglie."""
        player1, player2 = isolated_players[:2]
        player2.gamification_override = False
        db_session.commit()

        with pytest.raises(ConflictError):
            QuickMatchService.start(player1.id, player2.id)

    def test_disciplina_ignota_rifiutata(self, app, db_session, isolated_players):
        player1, player2 = isolated_players[:2]
        player2.gamification_override = True
        db_session.commit()

        with pytest.raises(ValidationError):
            QuickMatchService.start(
                player1.id, player2.id, {"discipline": "biliardino"}
            )

    def test_distanza_a_zero_rifiutata(self, app, db_session, isolated_players):
        player1, player2 = isolated_players[:2]
        player2.gamification_override = True
        db_session.commit()

        with pytest.raises(ValidationError):
            QuickMatchService.start(player1.id, player2.id, {"distance": 0})

    def test_la_sala_scelta_diventa_una_fk(self, app, db_session, isolated_players):
        from models.location.models import BilliardHall

        player1, player2 = isolated_players[:2]
        player2.gamification_override = True
        hall = BilliardHall(name="Sala Centrale", city="Trieste")
        db_session.add(hall)
        db_session.commit()

        match = QuickMatchService.start(
            player1.id, player2.id, {"location": "Sala Centrale"}
        )

        assert match.billiard_hall_id == hall.id
        assert match.location == "Sala Centrale"

    def test_il_risultato_resta_da_confermare_in_due(
        self, app, db_session, isolated_players
    ):
        """Il punto dell'issue: nessuno accetta prima, ma nessuno vince da solo.

        Finche' entrambi non confermano la partita non e' ``CONFIRMED_BY_BOTH``,
        e senza quello l'ELO globale non si muove
        (``RatingEventHandlers.handle_individual_match_completed``).
        """
        player1, player2 = isolated_players[:2]
        player2.gamification_override = True
        db_session.commit()

        match = QuickMatchService.start(player1.id, player2.id, {"distance": 2})
        match.add_rack_result(player1.id)
        match.add_rack_result(player1.id)
        db_session.commit()

        assert match.is_ready_for_validation() is True
        assert match.status == MatchStatus.IN_PROGRESS

        match.confirm_result(player1.id)
        assert match.status == MatchStatus.IN_PROGRESS

        match.confirm_result(player2.id)
        assert match.status == MatchStatus.CONFIRMED_BY_BOTH
