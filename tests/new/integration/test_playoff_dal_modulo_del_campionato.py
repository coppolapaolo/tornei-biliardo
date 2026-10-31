"""I playoff si cambiano dal modulo di modifica del campionato (issue #732).

Il modulo di creazione propone i playoff, quello di modifica non li mostrava:
a stagione in corso il direttore non poteva allargare l'elite in base alla
partecipazione, né togliere i playoff per chiudere il campionato sulle sole
gare. I servizi lo permettevano già fino agli inviti (ADR-075): mancava
l'interfaccia. Dopo la terminazione i playoff si gestiscono dalla linguetta
Playoff della pagina del campionato, e il modulo ci rimanda.
"""

import uuid

import pytest

from models import Campionato
from models.base import db, utc_now
from models.playoff.models import PlayoffConfiguration, PlayoffType
from models.status_enum import TournamentStatus
from models.user.models import DirectorAssignment, User
from models.user.role_enum import UserRole

pytestmark = pytest.mark.integration


@pytest.fixture
def campionato_con_playoff(client, db_session):
    uid = uuid.uuid4().hex[:8]
    director = User(
        username=f"dir_{uid}", email=f"dir_{uid}@test.com", role=UserRole.DIRECTOR.value
    )
    director.set_password("testpass123")
    db_session.add(director)
    c = Campionato(name=f"Camp {uid}", campionato_type="amalfi", is_active=True)
    db_session.add(c)
    db_session.flush()
    db_session.add(
        DirectorAssignment(
            entity_type="campionato",
            entity_id=c.id,
            user_id=director.id,
            assigned_by_id=director.id,
        )
    )
    cfg = PlayoffConfiguration(
        campionato_id=c.id,
        name="Elite",
        playoff_type=PlayoffType.TOP_N,
        max_participants=8,
        positions_from=1,
        positions_to=8,
        is_active=True,
    )
    db_session.add(cfg)
    db_session.commit()
    client.post(
        "/auth/login", data={"username": director.username, "password": "testpass123"}
    )
    return c.id, cfg.id


def _modulo(campionato_id):
    return f"/admin/campionato/{campionato_id}/edit"


def test_il_modulo_mostra_i_playoff_del_campionato_in_corso(
    client, campionato_con_playoff
):
    cid, cfg_id = campionato_con_playoff
    testo = client.get(_modulo(cid)).get_data(as_text=True)

    assert "Playoff finali" in testo
    assert f"/admin/campionato/{cid}/playoff/config/{cfg_id}/edit" in testo
    assert f"/admin/campionato/{cid}/playoff/config/{cfg_id}/deactivate" in testo
    assert f"/admin/campionato/{cid}/playoff/config/add" in testo


def test_allargare_l_elite_dal_modulo_torna_al_modulo(client, campionato_con_playoff):
    cid, cfg_id = campionato_con_playoff
    risposta = client.post(
        f"/admin/campionato/{cid}/playoff/config/{cfg_id}/edit",
        data={
            "name": "Elite",
            "positions_from": "1",
            "positions_to": "20",
            "max_participants": "20",
            "next": _modulo(cid),
        },
    )

    assert risposta.status_code == 302
    assert risposta.headers["Location"].endswith(_modulo(cid))
    cfg = db.session.get(PlayoffConfiguration, cfg_id)
    assert (cfg.positions_to, cfg.max_participants) == (20, 20)


def test_togliere_i_playoff_a_stagione_in_corso(client, campionato_con_playoff):
    cid, cfg_id = campionato_con_playoff
    risposta = client.post(
        f"/admin/campionato/{cid}/playoff/config/{cfg_id}/deactivate",
        data={"next": _modulo(cid)},
    )

    assert risposta.headers["Location"].endswith(_modulo(cid))
    campionato = db.session.get(Campionato, cid)
    assert campionato.has_playoff_configurations() is False
    assert "Nessun playoff" in client.get(_modulo(cid)).get_data(as_text=True)

    # Terminato, il campionato si chiude sulle sole gare.
    campionato.terminated_at = utc_now()
    db.session.commit()
    assert campionato.get_status() == TournamentStatus.COMPLETED.value


def test_aggiungere_i_playoff_dal_modulo(client, campionato_con_playoff):
    cid, cfg_id = campionato_con_playoff
    client.post(f"/admin/campionato/{cid}/playoff/config/{cfg_id}/deactivate")
    risposta = client.post(
        f"/admin/campionato/{cid}/playoff/config/add",
        data={
            "name": "Tutti",
            "positions_from": "1",
            "positions_to": "30",
            "max_participants": "30",
            "next": _modulo(cid),
        },
    )

    assert risposta.headers["Location"].endswith(_modulo(cid))
    attive = PlayoffConfiguration.query.filter_by(
        campionato_id=cid, is_active=True
    ).all()
    assert [c.name for c in attive] == ["Tutti"]


def test_un_indirizzo_esterno_non_porta_fuori(client, campionato_con_playoff):
    cid, cfg_id = campionato_con_playoff
    risposta = client.post(
        f"/admin/campionato/{cid}/playoff/config/{cfg_id}/deactivate",
        data={"next": "https://esempio.com/"},
    )

    assert risposta.headers["Location"].endswith(f"/admin/campionato/{cid}")


def test_a_campionato_terminato_il_modulo_rimanda_alla_pagina(
    client, campionato_con_playoff
):
    cid, cfg_id = campionato_con_playoff
    campionato = db.session.get(Campionato, cid)
    campionato.terminated_at = utc_now()
    db.session.commit()

    testo = client.get(_modulo(cid)).get_data(as_text=True)

    assert "Playoff finali" in testo
    assert f"/admin/campionato/{cid}/playoff/config/{cfg_id}/edit" not in testo
    assert "linguetta Playoff" in testo
