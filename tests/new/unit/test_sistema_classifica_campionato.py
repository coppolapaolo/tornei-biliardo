"""Il sistema di classifica del campionato arriva a ogni sua gara.

La regola sta in `SPECIFICHE.md` riga 289 ed è presidiata in
`test_specifiche_conformita.py`. Qui i dettagli che la specifica non nomina:
chi decide il sistema di una gara a tabellone, cosa succede se il sistema nuovo
rende invalida una gara ancora da aprire, quali gare non contano.
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest

from models import Campionato
from models.campionato.tournament_service import TournamentService
from models.competition.models import Gara
from models.exceptions import ValidationError
from models.matchmaking.configuration import resolve_classification_system
from models.playoff.models import PlayoffConfiguration, PlayoffType
from models.playoff.services import PlayoffService
from models.status_enum import Discipline, GaraStatus


def _campionato(db_session, sistema: str) -> Campionato:
    campionato = Campionato(
        name=f"Camp {uuid.uuid4().hex[:8]}",
        campionato_type="amalfi",
        is_active=True,
        default_classification_system=sistema,
    )
    db_session.add(campionato)
    db_session.flush()
    return campionato


def _gara(db_session, campionato, *, numero: int, stato: str, dispari: str) -> Gara:
    gara = Gara(
        campionato_id=campionato.id,
        name=f"Gara {numero}",
        number=numero,
        date=date(2026, 1, numero),
        discipline=Discipline.NINE_BALL.value,
        distance=5,
        is_race_to=False,
        status=stato,
        rounds_count=3,
        classification_system=campionato.default_classification_system,
        matchmaking_strategy="amalfi",
        odd_number_policy=dispari,
    )
    db_session.add(gara)
    db_session.flush()
    return gara


@pytest.mark.unit
class TestRisolutoreDelSistema:
    def test_il_tabellone_classifica_sempre_per_posizione(self):
        for strategia in ("direct_elimination", "double_knockout"):
            assert resolve_classification_system(strategia, "WINS") == "POSITION"
            assert resolve_classification_system(strategia, "RACK") == "POSITION"

    def test_fuori_dal_tabellone_vale_il_sistema_richiesto(self):
        assert resolve_classification_system("amalfi", "RACK") == "RACK"
        assert resolve_classification_system("random", "WINS") == "WINS"

    def test_fuori_dal_tabellone_la_posizione_non_ha_senso(self):
        assert resolve_classification_system("amalfi", "POSITION") == "WINS"


@pytest.mark.unit
class TestCambioDelSistema:
    def test_una_gara_che_il_sistema_nuovo_renderebbe_invalida_blocca_tutto(
        self, db_session
    ):
        """A triangoli totali la X semplice è vietata: il cambio si ferma e dice
        quale gara lo impedisce, senza lasciare metà campionato aggiornato."""
        campionato = _campionato(db_session, "WINS")
        _gara(
            db_session,
            campionato,
            numero=1,
            stato=GaraStatus.SETUP.value,
            dispari="bye_with_challenge",
        )
        _gara(
            db_session,
            campionato,
            numero=2,
            stato=GaraStatus.SETUP.value,
            dispari="bye",
        )
        db_session.commit()
        campionato_id = campionato.id

        with pytest.raises(ValidationError, match="Gara 2"):
            TournamentService().update_campionato(
                campionato_id=campionato_id, default_classification_system="RACK"
            )

        db_session.expire_all()
        rimasto = db_session.get(Campionato, campionato_id)
        assert rimasto.default_classification_system == "WINS"
        assert {g.classification_system for g in rimasto.gare} == {"WINS"}

    def test_la_gara_annullata_non_blocca_e_non_cambia(self, db_session):
        campionato = _campionato(db_session, "WINS")
        annullata = _gara(
            db_session,
            campionato,
            numero=1,
            stato=GaraStatus.CANCELLED.value,
            dispari="bye",
        )
        da_aprire = _gara(
            db_session,
            campionato,
            numero=2,
            stato=GaraStatus.SETUP.value,
            dispari="bye_with_challenge",
        )
        db_session.commit()
        annullata_id, da_aprire_id = annullata.id, da_aprire.id

        TournamentService().update_campionato(
            campionato_id=campionato.id, default_classification_system="RACK"
        )

        db_session.expire_all()
        assert db_session.get(Gara, annullata_id).classification_system == "WINS"
        assert db_session.get(Gara, da_aprire_id).classification_system == "RACK"

    def test_senza_cambio_di_sistema_le_gare_restano_come_sono(self, db_session):
        """Il form di modifica rimanda sempre il sistema: salvare il nome non
        deve riscrivere le gare."""
        campionato = _campionato(db_session, "WINS")
        gara = _gara(
            db_session,
            campionato,
            numero=1,
            stato=GaraStatus.SETUP.value,
            dispari="bye",
        )
        gara.classification_system = "RACK"  # dato storico discordante
        db_session.commit()
        gara_id = gara.id

        TournamentService().update_campionato(
            campionato_id=campionato.id,
            name="Nome nuovo",
            default_classification_system="WINS",
        )

        db_session.expire_all()
        assert db_session.get(Gara, gara_id).classification_system == "RACK"


@pytest.mark.unit
class TestPlayoffATabellone:
    @pytest.mark.xfail(
        strict=True,
        raises=ValueError,
        reason=(
            "Il sistema ora è quello giusto, POSITION, ma la finale eredita la "
            "distanza «esattamente N» delle gare di serata, che un tabellone "
            "rifiuta. Nessuna interfaccia sceglie oggi `strategy_type`, quindi "
            "il caso si raggiunge solo scrivendo la configurazione a mano."
        ),
    )
    def test_nasce_a_posizioni_anche_in_un_campionato_a_vittorie(self, db_session):
        campionato = _campionato(db_session, "WINS")
        _gara(
            db_session,
            campionato,
            numero=1,
            stato=GaraStatus.COMPLETED.value,
            dispari="bye",
        )
        configurazione = PlayoffConfiguration(
            campionato_id=campionato.id,
            name="Finale",
            playoff_type=PlayoffType.TOP_N,
            max_participants=8,
            positions_from=1,
            positions_to=8,
            is_active=True,
            auto_generate=True,
            min_garas_played=0,
            strategy_type="direct_elimination",
        )
        db_session.add(configurazione)
        db_session.commit()

        gara = PlayoffService.create_playoff_gara(configurazione.id)

        assert gara.classification_system == "POSITION"
