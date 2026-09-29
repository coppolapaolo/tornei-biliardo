"""A gara finita si corregge quanto conta, e la classifica lo dice (ADR-075).

Il caso: due gare concluse, quattro giocatori, due posti ai playoff. Con i
pesi a 1 la classifica dice D, A, C, B e gli inviti vanno a D e A. Il
direttore corregge il peso della gara 2 a ×2: C e D, che l'hanno vinta,
passano davanti. La classifica si ricalcola, l'elenco gare mostra «×1»
barrato, sopra la classifica compare la riga del ricalcolo, e per i playoff
arriva la proposta «ritirare l'invito ad A, invitare C» — che il direttore
accetta o rifiuta.
"""

from __future__ import annotations

import uuid
from datetime import date, time, timedelta

import pytest

from models.base import db, utc_now
from models.campionato.models import Campionato
from models.competition.models import Gara
from models.competition.services import GaraService
from models.exceptions import ConflictError
from models.match.models import Match
from models.playoff import proposta_inviti
from models.playoff.models import (
    PlayoffConfiguration,
    PlayoffQualification,
    PlayoffType,
    QualificationStatus,
)
from models.status_enum import Discipline, GaraStatus, MatchStatus
from models.storia.ricalcolo import pesi_corretti, voci_di_ricalcolo
from models.storia.service import StoriaModificheService
from models.user.models import User

pytestmark = pytest.mark.integration


def _utente(db_session, prefisso, role="player"):
    s = uuid.uuid4().hex[:8]
    u = User(username=f"{prefisso}_{s}", email=f"{prefisso}_{s}@test.com", role=role)
    u.set_password("test1234")
    db_session.add(u)
    db_session.flush()
    return u


@pytest.fixture
def stagione(db_session):
    from models.classification.gara_classification import RoundClassificationService

    camp = Campionato(
        name=f"Camp {uuid.uuid4().hex[:6]}",
        campionato_type="amalfi",
        is_active=True,
        planned_gare_count=2,
        default_rounds_count=1,
    )
    db_session.add(camp)
    db_session.flush()
    a, b, c, d = (_utente(db_session, n) for n in "abcd")
    admin = _utente(db_session, "admin", role="admin")
    gare = []
    for numero, giorno, partite in (
        (1, 10, ((a, c, 5, 0), (b, d, 5, 4))),
        (2, 15, ((c, a, 5, 3), (d, b, 5, 0))),
    ):
        gara = Gara(
            campionato_id=camp.id,
            number=numero,
            name=f"Gara {numero}",
            date=date(2026, 1, giorno),
            time=time(18, 0),
            discipline=Discipline.NINE_BALL.value,
            distance=5,
            rounds_count=1,
            current_round=1,
            status=GaraStatus.COMPLETED.value,
        )
        db_session.add(gara)
        db_session.flush()
        for vince, perde, p1, p2 in partite:
            db_session.add(
                Match(
                    gara_id=gara.id,
                    round_number=1,
                    player1_id=vince.id,
                    player2_id=perde.id,
                    player1_score=p1,
                    player2_score=p2,
                    status=MatchStatus.CLOSED_UNILATERALLY.value,
                    winner_id=vince.id,
                )
            )
        db_session.flush()
        RoundClassificationService.calculate_and_save_round_classification(gara.id, 1)
        gare.append(gara)

    scadenza = utc_now() + timedelta(days=7)
    cfg = PlayoffConfiguration(
        campionato_id=camp.id,
        name="Finale",
        playoff_type=PlayoffType.TOP_N,
        is_active=True,
        max_participants=2,
        positions_from=1,
        positions_to=2,
        min_garas_played=0,
        response_deadline=scadenza,
    )
    db_session.add(cfg)
    db_session.flush()
    for utente, posizione in ((d, 1), (a, 2)):
        db_session.add(
            PlayoffQualification(
                configuration_id=cfg.id,
                user_id=utente.id,
                qualifying_position=posizione,
                qualification_reason=f"Posizione {posizione} in classifica",
                invited_at=utc_now(),
                expires_at=scadenza,
            )
        )
    camp.terminated_at = utc_now()
    db_session.commit()
    return {
        "camp": camp,
        "gare": gare,
        "cfg": cfg,
        "abcd": (a, b, c, d),
        "admin": admin,
    }


def _login(client, user):
    client.post(
        "/auth/login",
        data={"username": user.username, "password": "test1234"},
        follow_redirects=True,
    )


class TestSiCorreggeSoloQuantoConta:
    def test_il_peso_si_il_resto_no(self, db_session, stagione):
        gara = stagione["gare"][1]
        with pytest.raises(ConflictError):
            GaraService.update_gara(gara.id, name="Altro nome")
        GaraService.update_gara(
            gara.id, autore=stagione["admin"], motivo="Era la gara doppia", weight=2
        )
        assert db.session.get(Gara, gara.id).weight == 2
        voce = StoriaModificheService.voci_della_gara(gara.id)[0]
        assert voce.action == "ricalcolo"
        assert voce.reason == "Era la gara doppia"

    def test_dalla_pagina_della_gara(self, client, db_session, stagione):
        gara = stagione["gare"][1]
        _login(client, stagione["admin"])
        pagina = client.get(f"/admin/gara/{gara.id}/edit").get_data(as_text=True)
        assert 'name="weight"' in pagina
        assert 'name="location"' not in pagina
        client.post(
            f"/admin/gara/{gara.id}/edit",
            data={"weight": "2", "stato_iniziale": "{}", "motivo": "Doppia"},
        )
        assert db.session.get(Gara, gara.id).weight == 2


class TestIlSegno:
    def test_peso_barrato_e_riga_sopra_la_classifica(self, client, stagione):
        camp, gara = stagione["camp"], stagione["gare"][1]
        GaraService.update_gara(gara.id, autore=stagione["admin"], weight=2)

        voci = voci_di_ricalcolo(camp)
        assert len(voci) == 1
        assert pesi_corretti(voci) == {gara.id: "1"}

        _login(client, stagione["admin"])
        pagina = client.get(f"/admin/campionato/{camp.id}").get_data(as_text=True)
        assert "Classifica ricalcolata" in pagina
        assert "&times;1</s>" in pagina

    def test_punti_per_posizione_sono_un_ricalcolo(self, db_session, stagione):
        from models.campionato.tournament_service import TournamentService

        camp = stagione["camp"]
        TournamentService().update_campionato(
            camp.id, autore=stagione["admin"], position_points="10,6,4,2"
        )
        voce = voci_di_ricalcolo(camp)[0]
        assert [r.field for r in voce.fields] == ["position_points"]


class TestLaPropostaDiInviti:
    def test_senza_correzioni_nessuna_proposta(self, stagione):
        assert proposta_inviti.proposta_inviti(stagione["cfg"].id) is None

    def test_la_correzione_propone_e_il_rifiuto_resta_scritto(self, stagione):
        a, _b, c, _d = stagione["abcd"]
        cfg = stagione["cfg"]
        GaraService.update_gara(stagione["gare"][1].id, weight=2)

        piano = proposta_inviti.proposta_inviti(cfg.id)
        assert piano is not None
        assert [r.user_id for r in piano.da_ritirare] == [a.id]
        assert [i.user_id for i in piano.da_invitare] == [c.id]

        proposta_inviti.rifiuta(cfg.id, autore=stagione["admin"], motivo="Decido io")
        assert proposta_inviti.proposta_inviti(cfg.id) is None
        voce = StoriaModificheService.voci_dei_playoff([cfg.id])[0]
        assert voce.action == "proposta_rifiutata"

    def test_accettata_aggiorna_gli_inviti(self, db_session, stagione):
        a, _b, c, _d = stagione["abcd"]
        cfg = stagione["cfg"]
        GaraService.update_gara(stagione["gare"][1].id, weight=2)

        proposta_inviti.accetta(cfg.id, autore=stagione["admin"])
        stati = {
            q.user_id: q.status
            for q in PlayoffQualification.query.filter_by(configuration_id=cfg.id)
        }
        assert stati[a.id] == QualificationStatus.REPLACED
        assert stati[c.id] == QualificationStatus.PENDING
        ritirata = PlayoffQualification.query.filter_by(
            configuration_id=cfg.id, user_id=a.id
        ).one()
        assert "corretta" in ritirata.qualification_reason
