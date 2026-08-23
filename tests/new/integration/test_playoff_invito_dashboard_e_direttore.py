"""L'invito ai playoff visto dalle due parti: la dashboard e la direzione.

Due percorsi che prima non esistevano:

* il giocatore qualificato trova la scheda «Sei qualificato» in dashboard, con
  accetta e rifiuta, invece di doverla cercare dietro una notifica;
* il direttore registra la risposta ricevuta a voce, e resta scritto che e'
  stato lui a registrarla.
"""

import uuid
from datetime import date

import pytest

from models import Campionato, db
from models.base import utc_now
from models.classification.models import Classification
from models.competition.models import Gara, Inscription
from models.playoff.models import (
    PlayoffConfiguration,
    PlayoffQualification,
    PlayoffType,
    QualificationStatus,
)
from models.status_enum import GaraStatus
from models.user.models import DirectorAssignment, User


def _uid():
    return str(uuid.uuid4())[:8]


def _login(client, user):
    client.post(
        "/auth/login",
        data={"username": user.username, "password": "test1234"},
        follow_redirects=True,
    )


@pytest.fixture
def campionato_con_inviti(db_session):
    """Campionato terminato, playoff avviato, tre inviti ancora in attesa."""
    direttore = User(
        username=f"dir_{_uid()}", email=f"dir_{_uid()}@t.com", role="director"
    )
    direttore.set_password("test1234")
    db_session.add(direttore)
    db_session.flush()

    camp = Campionato(name=f"Camp {_uid()}", campionato_type="amalfi", is_active=True)
    db_session.add(camp)
    db_session.flush()
    db_session.add(
        DirectorAssignment(
            entity_type="campionato",
            entity_id=camp.id,
            user_id=direttore.id,
            assigned_by_id=direttore.id,
        )
    )
    db_session.flush()

    gara = Gara(
        campionato_id=camp.id,
        number=1,
        name="Gara 1",
        date=date(2026, 1, 15),
        discipline="nine_ball",
        status=GaraStatus.COMPLETED.value,
        rounds_count=1,
        current_round=1,
        distance=5,
    )
    db_session.add(gara)
    db_session.flush()

    cfg = PlayoffConfiguration(
        campionato_id=camp.id,
        name="Finale",
        playoff_type=PlayoffType.TOP_N,
        max_participants=2,
        positions_from=1,
        positions_to=2,
        is_active=True,
        location="Sala Centrale",
    )
    db_session.add(cfg)
    db_session.flush()

    giocatori = []
    for i in range(3):
        p = User(username=f"p{_uid()}", email=f"p{_uid()}@t.com", role="player")
        p.set_password("test1234")
        db_session.add(p)
        db_session.flush()
        db_session.add(
            Classification(
                campionato_id=camp.id,
                user_id=p.id,
                position=i + 1,
                total_matches_won=10 - i,
                total_point_difference=20 - i,
                gare_played=5,
            )
        )
        db_session.add(Inscription(user_id=p.id, gara_id=gara.id))
        giocatori.append(p)

    inviti = []
    for i, p in enumerate(giocatori[:2]):
        q = PlayoffQualification(
            configuration_id=cfg.id,
            user_id=p.id,
            qualifying_position=i + 1,
            qualification_reason=f"Posizione {i + 1}",
            status=QualificationStatus.PENDING,
            invited_at=utc_now(),
        )
        db_session.add(q)
        inviti.append(q)

    camp.terminated_at = utc_now()
    db_session.commit()
    return {
        "campionato": camp,
        "config": cfg,
        "direttore": direttore,
        "giocatori": giocatori,
        "inviti": inviti,
    }


class TestSchedaInDashboard:
    def test_il_qualificato_vede_la_scheda_con_accetta_e_rifiuta(
        self, client, db_session, campionato_con_inviti
    ):
        giocatore = campionato_con_inviti["giocatori"][0]
        invito = campionato_con_inviti["inviti"][0]
        _login(client, giocatore)

        resp = client.get("/dashboard")
        html = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert "Sei qualificato" in html
        assert f"/player/playoff/confirm/{invito.id}" in html
        assert f"/player/playoff/decline/{invito.id}" in html

    def test_chi_ha_gia_risposto_non_vede_piu_la_scheda(
        self, client, db_session, campionato_con_inviti
    ):
        """La scheda e' una cosa da fare: fatta la cosa, sparisce."""
        giocatore = campionato_con_inviti["giocatori"][0]
        invito = campionato_con_inviti["inviti"][0]
        _login(client, giocatore)
        client.post(f"/player/playoff/confirm/{invito.id}", follow_redirects=True)

        html = client.get("/dashboard").get_data(as_text=True)
        assert f"/player/playoff/confirm/{invito.id}" not in html

    def test_chi_non_e_qualificato_non_vede_niente(
        self, client, db_session, campionato_con_inviti
    ):
        escluso = campionato_con_inviti["giocatori"][2]
        _login(client, escluso)

        html = client.get("/dashboard").get_data(as_text=True)
        assert "Sei qualificato" not in html

    def test_un_campionato_eliminato_non_lascia_inviti_in_giro(
        self, client, db_session, campionato_con_inviti
    ):
        """Il soft-delete del campionato non e' automatico sulle query.

        Trovato sul DB di sviluppo: sette qualificazioni `PENDING` su un
        campionato eliminato. Senza questo filtro la scheda comparirebbe
        comunque, con due pulsanti che scrivono su dati orfani.
        """
        camp = campionato_con_inviti["campionato"]
        giocatore = campionato_con_inviti["giocatori"][0]
        camp.deleted_at = utc_now()
        db_session.commit()

        _login(client, giocatore)
        html = client.get("/dashboard").get_data(as_text=True)
        assert "Sei qualificato" not in html

    def test_una_configurazione_disattivata_non_e_piu_un_invito(
        self, client, db_session, campionato_con_inviti
    ):
        cfg = campionato_con_inviti["config"]
        giocatore = campionato_con_inviti["giocatori"][0]
        cfg.is_active = False
        db_session.commit()

        _login(client, giocatore)
        html = client.get("/dashboard").get_data(as_text=True)
        assert "Sei qualificato" not in html


class TestRispostaDelDirettore:
    def test_il_direttore_conferma_per_conto_del_giocatore(
        self, client, db_session, campionato_con_inviti
    ):
        camp = campionato_con_inviti["campionato"]
        cfg = campionato_con_inviti["config"]
        direttore = campionato_con_inviti["direttore"]
        invito = campionato_con_inviti["inviti"][0]
        _login(client, direttore)

        resp = client.post(
            f"/admin/campionato/{camp.id}/playoff/{cfg.id}/respond",
            data={"qualification_id": invito.id, "answer": "accept"},
            follow_redirects=True,
        )

        assert resp.status_code == 200
        aggiornato = db.session.get(PlayoffQualification, invito.id)
        assert aggiornato.status == QualificationStatus.CONFIRMED
        assert aggiornato.responded_by_id == direttore.id

    def test_il_rifiuto_registrato_invita_il_primo_degli_esclusi(
        self, client, db_session, campionato_con_inviti
    ):
        camp = campionato_con_inviti["campionato"]
        cfg = campionato_con_inviti["config"]
        direttore = campionato_con_inviti["direttore"]
        invito = campionato_con_inviti["inviti"][0]
        terzo = campionato_con_inviti["giocatori"][2]
        _login(client, direttore)

        client.post(
            f"/admin/campionato/{camp.id}/playoff/{cfg.id}/respond",
            data={"qualification_id": invito.id, "answer": "decline"},
            follow_redirects=True,
        )

        inviti = PlayoffQualification.query.filter_by(configuration_id=cfg.id).all()
        assert {q.user_id for q in inviti} >= {terzo.id}

    def test_una_risposta_senza_verso_non_cambia_niente(
        self, client, db_session, campionato_con_inviti
    ):
        camp = campionato_con_inviti["campionato"]
        cfg = campionato_con_inviti["config"]
        direttore = campionato_con_inviti["direttore"]
        invito = campionato_con_inviti["inviti"][0]
        _login(client, direttore)

        resp = client.post(
            f"/admin/campionato/{camp.id}/playoff/{cfg.id}/respond",
            data={"qualification_id": invito.id, "answer": "forse"},
            follow_redirects=True,
        )

        assert resp.status_code == 200
        assert db.session.get(PlayoffQualification, invito.id).status == (
            QualificationStatus.PENDING
        )


class TestRegoleClassificaFinaleDallaPagina:
    def test_il_direttore_cambia_modalita_e_peso(
        self, client, db_session, campionato_con_inviti
    ):
        camp = campionato_con_inviti["campionato"]
        cfg = campionato_con_inviti["config"]
        direttore = campionato_con_inviti["direttore"]
        _login(client, direttore)

        resp = client.post(
            f"/admin/campionato/{camp.id}/playoff/{cfg.id}/scoring",
            data={"final_ranking_mode": "playoff_only", "playoff_weight": "3"},
            follow_redirects=True,
        )

        assert resp.status_code == 200
        aggiornata = db.session.get(PlayoffConfiguration, cfg.id)
        assert aggiornata.decides_final_ranking is True
        assert aggiornata.playoff_weight == 3
