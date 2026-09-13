"""Le schede dei playoff nella dashboard vera, per chi ha risposto e per chi è fuori.

Il costruttore è presidiato da `tests/new/unit/test_schede_playoff_dashboard.py`;
qui si guarda cosa legge il giocatore: la sezione giusta, la pastiglia giusta,
e nessun pulsante per iscriversi a un playoff (si entra solo dall'invito).
"""

import uuid

import pytest

from models import Campionato
from models.base import utc_now
from models.classification.models import Classification
from models.matchmaking.configuration import MatchmakingStrategy
from models.playoff.models import (
    PlayoffConfiguration,
    PlayoffQualification,
    PlayoffType,
    QualificationStatus,
)
from models.user.models import User
from models.user.role_enum import UserRole


def _login(client, user):
    client.post(
        "/auth/login",
        data={"username": user.username, "password": "test1234"},
        follow_redirects=True,
    )


@pytest.fixture
def playoff(db_session):
    """Due posti: p1 accetta, p2 rifiuta, p3 chiamato al suo posto, p4 fuori."""
    sigla = uuid.uuid4().hex[:6]
    camp = Campionato(
        name=f"Sociale {sigla}",
        campionato_type=MatchmakingStrategy.AMALFI.value,
        is_active=True,
    )
    db_session.add(camp)
    db_session.flush()
    cfg = PlayoffConfiguration(
        campionato_id=camp.id,
        name=f"Finale {sigla}",
        playoff_type=PlayoffType.TOP_N,
        max_participants=2,
        positions_from=1,
        positions_to=2,
        is_active=True,
        location="Sala Centrale",
    )
    db_session.add(cfg)
    db_session.flush()

    giocatori = {}
    for pos in range(1, 5):
        nome = f"p{pos}_{uuid.uuid4().hex[:6]}"
        utente = User(username=nome, email=f"{nome}@t.com", role=UserRole.PLAYER.value)
        utente.set_password("test1234")
        db_session.add(utente)
        db_session.flush()
        db_session.add(
            Classification(
                campionato_id=camp.id,
                user_id=utente.id,
                position=pos,
                total_matches_won=10 - pos,
                total_point_difference=20 - pos,
                gare_played=5,
            )
        )
        giocatori[f"p{pos}"] = utente

    for chi, pos, stato in (
        ("p1", 1, QualificationStatus.CONFIRMED),
        ("p2", 2, QualificationStatus.DECLINED),
        ("p3", 3, QualificationStatus.PENDING),
    ):
        db_session.add(
            PlayoffQualification(
                configuration_id=cfg.id,
                user_id=giocatori[chi].id,
                qualifying_position=pos,
                qualification_reason=f"Posizione {pos}",
                status=stato,
                invited_at=utc_now(),
            )
        )
    camp.terminated_at = utc_now()
    db_session.commit()
    return {"config": cfg, **giocatori}


def _dashboard(client, utente) -> str:
    _login(client, utente)
    risposta = client.get("/dashboard")
    assert risposta.status_code == 200
    return risposta.get_data(as_text=True)


def _sezione(html: str, titolo: str) -> str:
    """Il pezzo di pagina dal titolo di una sezione alla successiva."""
    inizio = html.index(titolo)
    fine = html.find("<section", inizio)
    return html[inizio : fine if fine != -1 else len(html)]


def test_chi_ha_accettato_ha_la_scheda_da_iscritto_fra_le_sue(client, playoff):
    html = _dashboard(client, playoff["p1"])
    mie = _sezione(html, "Le tue gare")
    assert playoff["config"].name in mie
    assert ">Iscritto<" in mie


def test_chi_e_fuori_zona_e_in_lista_d_attesa(client, playoff):
    html = _dashboard(client, playoff["p4"])
    mie = _sezione(html, "Le tue gare")
    assert playoff["config"].name in mie
    assert "Lista d'attesa #1" in mie


def test_chi_ha_rifiutato_la_vede_in_arrivo_con_le_iscrizioni_chiuse(client, playoff):
    html = _dashboard(client, playoff["p2"])
    assert "Le tue gare" not in html
    in_arrivo = _sezione(html, "In arrivo")
    assert playoff["config"].name in in_arrivo
    assert "Iscrizioni chiuse" in in_arrivo


def test_l_invito_in_attesa_resta_solo_in_cima(client, playoff):
    html = _dashboard(client, playoff["p3"])
    assert "Sei qualificato" in html
    assert "Le tue gare" not in html and "In arrivo" not in html
