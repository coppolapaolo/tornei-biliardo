"""La vetrina di una gara a turni misti dice come si gioca **ogni** turno.

Rilievo del 17/09/2026: una gara Amalfi con un turno a Palla 8, uno a Palla 9
e uno a Palla 10 si presentava, nella vetrina pubblica, con la sola disciplina
predefinita della gara. `_formato_di_gioco` leggeva `gara.discipline` e
`gara.distance` e non sapeva che esistessero le configurazioni per turno
(`RoundConfiguration`, ADR-027): chi arrivava dal link leggeva un formato che
in due turni su tre non era quello giocato.
"""

from datetime import date, timedelta

import pytest

from models import Gara
from models.competition.round_configuration import RoundConfiguration
from models.competition.showcase_view import costruisci_vetrina, descrizione_social
from models.status_enum import Discipline, GaraStatus


def _gara(db_session, **campi):
    dati = dict(
        number=1,
        name="Gara a turni misti",
        date=date.today() + timedelta(days=7),
        discipline=Discipline.EIGHT_BALL.value,
        distance=4,
        is_race_to=True,
        matchmaking_strategy="amalfi",
        status=GaraStatus.INSCRIPTION.value,
        rounds_count=3,
        min_participants=4,
    )
    dati.update(campi)
    gara = Gara(**dati)
    db_session.add(gara)
    db_session.commit()
    return gara


def _formato(vetrina):
    return next(r for r in vetrina.righe if r.icona == "fa-trophy")


@pytest.mark.unit
class TestFormatoDellaVetrina:
    def test_senza_override_resta_il_formato_della_gara(self, db_session):
        gara = _gara(db_session)

        riga = _formato(costruisci_vetrina(gara))

        assert riga.valore == "Palla 8 — al 4"
        assert riga.dettaglio == "3 turni"

    def test_discipline_diverse_si_vedono_tutte(self, db_session):
        gara = _gara(db_session)
        RoundConfiguration.create_or_update(
            gara.id, 2, discipline=Discipline.NINE_BALL.value, distance=5
        )
        RoundConfiguration.create_or_update(
            gara.id, 3, discipline=Discipline.TEN_BALL.value
        )
        db_session.commit()

        riga = _formato(costruisci_vetrina(gara))

        assert riga.valore == "Palla 8, Palla 9, Palla 10"
        assert riga.dettaglio == (
            "Turno 1: Palla 8 — al 4 · Turno 2: Palla 9 — al 5 · "
            "Turno 3: Palla 10 — al 4"
        )

    def test_stessa_disciplina_distanze_diverse(self, db_session):
        gara = _gara(db_session)
        RoundConfiguration.create_or_update(gara.id, 3, distance=6)
        db_session.commit()

        riga = _formato(costruisci_vetrina(gara))

        assert riga.valore == "Palla 8 — distanze diverse per turno"
        assert riga.dettaglio == ("Turno 1: al 4 · Turno 2: al 4 · Turno 3: al 6")

    def test_override_uguale_su_tutti_i_turni_non_e_misto(self, db_session):
        """Tre turni tutti a Palla 9: un formato solo, e non quello della gara."""
        gara = _gara(db_session)
        for turno in (1, 2, 3):
            RoundConfiguration.create_or_update(
                gara.id, turno, discipline=Discipline.NINE_BALL.value, distance=5
            )
        db_session.commit()

        riga = _formato(costruisci_vetrina(gara))

        assert riga.valore == "Palla 9 — al 5"
        assert riga.dettaglio == "3 turni"

    def test_un_override_oltre_i_turni_della_gara_non_conta(self, db_session):
        gara = _gara(db_session, rounds_count=2)
        RoundConfiguration.create_or_update(
            gara.id, 5, discipline=Discipline.NINE_BALL.value
        )
        db_session.commit()

        riga = _formato(costruisci_vetrina(gara))

        assert riga.valore == "Palla 8 — al 4"

    def test_l_anteprima_social_porta_le_discipline(self, db_session):
        gara = _gara(db_session)
        RoundConfiguration.create_or_update(
            gara.id, 2, discipline=Discipline.NINE_BALL.value
        )
        db_session.commit()

        testo = descrizione_social(costruisci_vetrina(gara))

        assert "Palla 8, Palla 9" in testo


@pytest.mark.unit
class TestDistanzaDelTurnoNelleGareASet:
    """Difetto parente, trovato leggendo: `to_match_overrides` ripiegava i
    **set** da vincere su `gara.distance`, che sono i triangoli del set. In una
    gara «al 2 set, ogni set al 4» un turno a cui il direttore aveva cambiato
    solo la disciplina si presentava, in testata e nella preparazione, come
    «al 4 set»."""

    def test_i_set_ripiegano_sui_set_della_gara(self, db_session):
        gara = _gara(db_session, is_multi_set=True, match_distance=2, distance=4)
        rc = RoundConfiguration.create_or_update(
            gara.id, 2, discipline=Discipline.NINE_BALL.value
        )
        db_session.commit()

        distanza = rc.effective_distance_config(gara)

        assert distanza.sets == 2
        assert distanza.racks == 4

    def test_a_set_unico_la_distanza_e_quella_del_turno(self, db_session):
        gara = _gara(db_session)
        rc = RoundConfiguration.create_or_update(gara.id, 2, distance=6)
        db_session.commit()

        assert rc.to_match_overrides(gara)["match_distance"] == 6
