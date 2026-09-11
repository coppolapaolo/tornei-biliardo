"""Competizione di prova (ADR-058), tappa 3: il campionato di prova.

Un campionato con il flag, le cui gare lo ereditano; i **fittizi sono del
campionato** e giocano tutte le sue gare, altrimenti la classifica generale
non si formerebbe mai; le date delle gare proposte nei prossimi giorni e in
ordine (ADR-016); e il playoff, dove il direttore risponde agli inviti per
ciascun fittizio — con i servizi della route del giocatore, con l'id del
fittizio — e un rifiuto fa scattare il sostituto (SPECIFICHE.md, «primo degli
esclusi»).

Fuori da una richiesta le prove sono invisibili: `prova_visibili()` ovunque.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest

from models.base import db, utc_now
from models.campionato.models import Campionato
from models.campionato.tournament_service import TournamentService
from models.classification.models import Classification
from models.competition.models import Gara, Inscription
from models.competition.services import GaraService
from models.exceptions import ConflictError, NotFoundError, ValidationError
from models.playoff.models import (
    PlayoffConfiguration,
    PlayoffQualification,
    PlayoffType,
    QualificationStatus,
)
from models.prova.service import LIMITE_PROVE_ATTIVE, ProvaService
from models.prova.simulation_service import SimulationService
from models.prova.visibility import prova_visibili
from models.status_enum import Discipline, GaraStatus
from models.user.models import User
from models.user.role_enum import UserRole

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------- fixture


def _direttore(db_session) -> User:
    sigla = uuid.uuid4().hex[:8]
    utente = User(
        username=f"dir_{sigla}",
        email=f"dir_{sigla}@test.local",
        role=UserRole.DIRECTOR.value,
    )
    utente.set_password("prova1234")
    db_session.add(utente)
    db_session.commit()
    return utente


def _campionato(db_session, direttore: User, *, prova: bool = True) -> Campionato:
    extra = ProvaService.campi_di_creazione() if prova else {}
    with prova_visibili():
        campionato = TournamentService().create_campionato_with_director(
            name=f"Campionato {uuid.uuid4().hex[:4]}",
            creator_user_id=direttore.id,
            **extra,
        )
        db_session.commit()
    return campionato


def _gara(db_session, campionato: Campionato, numero: int, **extra) -> Gara:
    campi = {
        "campionato_id": campionato.id,
        "number": numero,
        "name": f"Gara {numero}",
        "date": date.today() + timedelta(days=numero),
        "discipline": Discipline.NINE_BALL.value,
        "distance": 5,
        "min_participants": 4,
        "max_participants": 8,
        "status": GaraStatus.INSCRIPTION.value,
    }
    campi.update(extra)
    with prova_visibili():
        gara = GaraService.create_gara(**campi)
        db_session.commit()
    return gara


def _fittizi(campionato_id: int) -> list[User]:
    return ProvaService.fittizi_della_radice(campionato_id=campionato_id)


# ------------------------------------------------------------ creazione


class TestCreazione:
    def test_il_campionato_nasce_di_prova_con_la_scadenza(self, db_session):
        direttore = _direttore(db_session)
        campionato = _campionato(db_session, direttore)
        assert campionato.is_prova is True
        assert campionato.prova_expires_at is not None
        assert ProvaService.prove_attive(direttore.id) == [campionato]

    def test_il_limite_e_condiviso_con_le_gare_singole(self, db_session):
        direttore = _direttore(db_session)
        _campionato(db_session, direttore)
        for numero in range(LIMITE_PROVE_ATTIVE - 1):
            with prova_visibili():
                GaraService.create_gara(
                    campionato_id=None,
                    number=1,
                    name=f"Prova singola {numero}",
                    date=date.today() + timedelta(days=1),
                    discipline=Discipline.NINE_BALL.value,
                    distance=5,
                    director_id=direttore.id,
                    **ProvaService.campi_di_creazione(),
                )
                db_session.commit()
        assert len(ProvaService.prove_attive(direttore.id)) == LIMITE_PROVE_ATTIVE
        with pytest.raises(ConflictError):
            ProvaService.verifica_limite(direttore.id)


# -------------------------------------------------------------- fittizi


class TestIFittiziSonoDelCampionato:
    def test_la_seconda_gara_riusa_i_fittizi_della_prima(self, db_session):
        campionato = _campionato(db_session, _direttore(db_session))
        gara1 = _gara(db_session, campionato, 1)
        gara2 = _gara(db_session, campionato, 2)
        with prova_visibili():
            assert ProvaService.iscrivi_fittizi(gara1.id, "minimo") == 4
            assert ProvaService.iscrivi_fittizi(gara2.id, "minimo") == 4
            fittizi = _fittizi(campionato.id)
            assert len(fittizi) == 4, "la seconda gara non deve crearne di nuovi"
            for gara in (gara1, gara2):
                iscritti = {
                    i.user_id
                    for i in Inscription.query.filter_by(gara_id=gara.id).all()
                }
                assert iscritti == {f.id for f in fittizi}

    def test_ne_crea_di_nuovi_solo_quando_quelli_del_campionato_non_bastano(
        self, db_session
    ):
        campionato = _campionato(db_session, _direttore(db_session))
        gara1 = _gara(db_session, campionato, 1, min_participants=4)
        gara2 = _gara(db_session, campionato, 2, min_participants=6)
        with prova_visibili():
            ProvaService.iscrivi_fittizi(gara1.id, "minimo")
            assert ProvaService.iscrivi_fittizi(gara2.id, "minimo") == 6
            fittizi = _fittizi(campionato.id)
            assert len(fittizi) == 6
            # I nomi proseguono dalla tabella: il quinto e' sempre il quinto.
            assert [f.username for f in fittizi][:2] == ["Maria Rossi", "Mario Bianchi"]
            assert Inscription.query.filter_by(gara_id=gara1.id).count() == 4
            assert Inscription.query.filter_by(gara_id=gara2.id).count() == 6

    def test_uno_in_piu_riusa_prima_di_creare(self, db_session):
        campionato = _campionato(db_session, _direttore(db_session))
        gara1 = _gara(db_session, campionato, 1, min_participants=5)
        gara2 = _gara(db_session, campionato, 2, min_participants=4)
        with prova_visibili():
            ProvaService.iscrivi_fittizi(gara1.id, "minimo")  # 5 fittizi
            ProvaService.iscrivi_fittizi(gara2.id, "minimo")  # 4 dei 5
            ProvaService.iscrivi_fittizi(gara2.id, "uno")  # il quinto, non un sesto
            assert len(_fittizi(campionato.id)) == 5
            assert Inscription.query.filter_by(gara_id=gara2.id).count() == 5


# ---------------------------------------------------------------- date


class TestLeDateDelleGare:
    def test_nella_prova_la_prima_gara_e_domani_e_le_altre_seguono(self, db_session):
        campionato = _campionato(db_session, _direttore(db_session))
        with prova_visibili():
            assert TournamentService.data_proposta_gara(
                campionato.id
            ) == date.today() + timedelta(days=1)
            _gara(db_session, campionato, 1, date=date.today() + timedelta(days=3))
            assert TournamentService.data_proposta_gara(
                campionato.id
            ) == date.today() + timedelta(days=4)

    def test_un_campionato_inesistente_solleva(self, db_session):
        """Rilievo sulla #319: `None` non è un campionato vero, è un id sbagliato."""
        with pytest.raises(NotFoundError):
            TournamentService.data_proposta_gara(987654321)

    def test_in_un_campionato_vero_oggi_e_poi_una_settimana_dopo(self, db_session):
        """SPECIFICHE.md: «oggi per la prima gara o una settimana più avanti
        rispetto all'ultima gara aggiunta al campionato»."""
        campionato = _campionato(db_session, _direttore(db_session), prova=False)
        assert TournamentService.data_proposta_gara(campionato.id) == date.today()
        _gara(db_session, campionato, 1, date=date.today() + timedelta(days=2))
        assert TournamentService.data_proposta_gara(
            campionato.id
        ) == date.today() + timedelta(days=9)


# ------------------------------------------------------------- playoff


def _playoff_con_inviti(db_session, direttore: User) -> dict:
    """Un campionato di prova terminato, quattro fittizi in classifica, un
    playoff da due posti con i primi due invitati."""
    campionato = _campionato(db_session, direttore)
    gara = _gara(db_session, campionato, 1, status=GaraStatus.COMPLETED.value)
    with prova_visibili():
        fittizi = ProvaService.crea_fittizi(gara, 4)
        for posizione, fittizio in enumerate(fittizi, start=1):
            db_session.add(Inscription(user_id=fittizio.id, gara_id=gara.id))
            db_session.add(
                Classification(
                    campionato_id=campionato.id,
                    user_id=fittizio.id,
                    position=posizione,
                    total_matches_won=10 - posizione,
                    total_point_difference=20 - posizione,
                    gare_played=1,
                )
            )
        config = PlayoffConfiguration(
            campionato_id=campionato.id,
            name="Finale",
            playoff_type=PlayoffType.TOP_N,
            max_participants=2,
            positions_from=1,
            positions_to=2,
            is_active=True,
        )
        db_session.add(config)
        db_session.flush()
        inviti = []
        for posizione, fittizio in enumerate(fittizi[:2], start=1):
            invito = PlayoffQualification(
                configuration_id=config.id,
                user_id=fittizio.id,
                qualifying_position=posizione,
                qualification_reason=f"Posizione {posizione}",
                status=QualificationStatus.PENDING,
                invited_at=utc_now(),
            )
            db_session.add(invito)
            inviti.append(invito)
        campionato.terminated_at = utc_now()
        db_session.commit()
    return {
        "campionato": campionato,
        "config": config,
        "fittizi": fittizi,
        "inviti": inviti,
    }


class TestGliInvitiAlPlayoff:
    def test_accetta_come_farebbe_il_fittizio(self, db_session):
        scenario = _playoff_con_inviti(db_session, _direttore(db_session))
        invito = scenario["inviti"][0]
        with prova_visibili():
            sostituto = SimulationService.rispondi_invito(invito.id, accetta=True)
            assert sostituto is None
            assert invito.status == QualificationStatus.CONFIRMED
            # Ha risposto «lui», non il direttore per suo conto.
            assert invito.responded_by_id == invito.user_id
            assert not invito.answered_on_behalf

    def test_un_rifiuto_fa_scattare_il_primo_degli_esclusi(self, db_session):
        scenario = _playoff_con_inviti(db_session, _direttore(db_session))
        invito = scenario["inviti"][1]
        terzo = scenario["fittizi"][2]
        with prova_visibili():
            sostituto = SimulationService.rispondi_invito(invito.id, accetta=False)
            assert invito.status == QualificationStatus.DECLINED
            assert sostituto is not None
            assert sostituto.user_id == terzo.id
            assert sostituto.status == QualificationStatus.PENDING

    def test_accetta_tutti_i_rimanenti(self, db_session):
        scenario = _playoff_con_inviti(db_session, _direttore(db_session))
        campionato = scenario["campionato"]
        with prova_visibili():
            SimulationService.rispondi_invito(scenario["inviti"][1].id, accetta=False)
            accettati = SimulationService.accetta_tutti_gli_inviti(campionato.id)
            assert accettati == 2  # il primo e il sostituto
            stati = [
                q.status
                for q in PlayoffQualification.query.filter_by(
                    configuration_id=scenario["config"].id
                ).all()
            ]
            assert stati.count(QualificationStatus.CONFIRMED) == 2
            assert stati.count(QualificationStatus.DECLINED) == 1
            assert SimulationService.accetta_tutti_gli_inviti(campionato.id) == 0

    def test_un_invito_gia_risposto_rifiuta(self, db_session):
        scenario = _playoff_con_inviti(db_session, _direttore(db_session))
        invito = scenario["inviti"][0]
        with prova_visibili():
            SimulationService.rispondi_invito(invito.id, accetta=True)
            with pytest.raises(ConflictError):
                SimulationService.rispondi_invito(invito.id, accetta=False)

    def test_solo_per_i_fittizi(self, db_session):
        """Un invito a un giocatore vero non si risponde da qui: e' suo."""
        direttore = _direttore(db_session)
        vero = _campionato(db_session, direttore, prova=False)
        gara = _gara(db_session, vero, 1, status=GaraStatus.COMPLETED.value)
        giocatore = _direttore(db_session)
        db_session.add(Inscription(user_id=giocatore.id, gara_id=gara.id))
        config = PlayoffConfiguration(
            campionato_id=vero.id,
            name="Finale",
            playoff_type=PlayoffType.TOP_N,
            max_participants=2,
            positions_from=1,
            positions_to=2,
            is_active=True,
        )
        db_session.add(config)
        db_session.flush()
        invito = PlayoffQualification(
            configuration_id=config.id,
            user_id=giocatore.id,
            qualifying_position=1,
            qualification_reason="Posizione 1",
            status=QualificationStatus.PENDING,
            invited_at=utc_now(),
        )
        db_session.add(invito)
        db_session.commit()
        with pytest.raises(ValidationError):
            SimulationService.rispondi_invito(invito.id, accetta=True)
        assert SimulationService.accetta_tutti_gli_inviti(vero.id) == 0
        assert invito.status == QualificationStatus.PENDING


# -------------------------------------------------------- cancellazione


class TestEliminazione:
    def test_sparisce_tutto_playoff_compreso(self, db_session):
        scenario = _playoff_con_inviti(db_session, _direttore(db_session))
        campionato_id = scenario["campionato"].id
        config_id = scenario["config"].id
        fittizi_ids = [f.id for f in scenario["fittizi"]]
        with prova_visibili():
            ProvaService.elimina_prova(campionato_id=campionato_id)
            db_session.expire_all()
            assert db.session.get(Campionato, campionato_id) is None
            assert Gara.query.filter_by(campionato_id=campionato_id).count() == 0
            assert db.session.get(PlayoffConfiguration, config_id) is None
            assert (
                PlayoffQualification.query.filter_by(configuration_id=config_id).count()
                == 0
            )
            assert (
                Classification.query.filter_by(campionato_id=campionato_id).count() == 0
            )
            assert User.query.filter(User.id.in_(fittizi_ids)).count() == 0
