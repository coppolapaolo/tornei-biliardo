"""I gironi dal modulo della gara singola fino all'avvio (ADR-076).

Il passaggio interfaccia↔server: il modulo porta «Gironi: fino a N» e
«Composizione dei gironi», salvarli li scrive sulla gara, il foglio di avvio
propone il numero e mostra le taglie, e avviare con 2 gironi compone i
gironi sugli iscritti. Le regole hanno i loro unit test
(`tests/new/unit/test_gironi_*.py`).
"""

from __future__ import annotations

import uuid
from collections import Counter
from datetime import date, timedelta

import pytest
from werkzeug.datastructures import MultiDict

from models import Gara, User
from models.base import utc_now
from models.competition.inscription_service import InscriptionService
from models.competition.models import Inscription
from models.user.role_enum import UserRole

pytestmark = pytest.mark.integration


@pytest.fixture
def direttore(db_session):
    user = User(
        username=f"dir_{uuid.uuid4().hex[:8]}",
        email=f"dir_{uuid.uuid4().hex[:8]}@test.com",
        role=UserRole.DIRECTOR.value,
        onboarding_completed=True,
    )
    user.set_password("director123")
    db_session.add(user)
    db_session.commit()
    return user


def _login(client, user):
    client.post(
        "/auth/login",
        data={"username": user.username, "password": "director123"},
        follow_redirects=True,
    )


def _modulo(nome, **campi):
    dati = [
        ("name", nome),
        ("date", (date.today() + timedelta(days=10)).isoformat()),
        ("time", "20:00"),
        ("discipline", "9_ball"),
        ("distance", "3"),
        ("rounds_count", "3"),
        ("min_participants", "4"),
        ("max_participants", "16"),
        ("entry_fee", "0"),
        ("matchmaking_strategy", "round_robin"),
        ("first_round_policy", "random"),
        ("odd_number_policy", "bye"),
        ("withdraw_policy", "Forfeit"),
        ("classification_system", "POINTS"),
    ]
    return MultiDict(dati + list(campi.items()))


def _crea(client, direttore, **campi) -> Gara:
    _login(client, direttore)
    nome = f"Natale al 74 {uuid.uuid4().hex[:6]}"
    client.post(
        "/admin/gara/create_standalone",
        data=_modulo(nome, **campi),
        follow_redirects=True,
    )
    return Gara.query.filter_by(name=nome).one()


def _iscrivi(db_session, gara: Gara, n: int) -> None:
    InscriptionService.open_inscriptions(
        gara.id, utc_now() - timedelta(hours=1), utc_now() + timedelta(hours=1)
    )
    for i in range(n):
        uid = uuid.uuid4().hex[:8]
        player = User(
            username=f"gi_{uid}",
            email=f"gi_{uid}@test.com",
            role=UserRole.PLAYER.value,
        )
        player.set_password("x")
        player.elo_rating = 2000 - i
        db_session.add(player)
        db_session.commit()
        InscriptionService.inscribe_user(player.id, gara.id)


def test_il_modulo_porta_i_gironi(client, direttore):
    _login(client, direttore)
    pagina = client.get("/admin/gara/create_standalone").get_data(as_text=True)
    assert 'name="max_groups"' in pagina
    assert 'name="group_seeding"' in pagina
    assert "js/campo_gironi.js" in pagina
    # Il nome dell'opzione è vincolante (ADR-076).
    assert "Composizione dei gironi" in pagina
    assert "serpentina" not in pagina.lower()


def test_dal_modulo_all_avvio_con_due_gironi(client, db_session, direttore):
    gara = _crea(client, direttore, max_groups="2", group_seeding="elo")
    assert gara.max_groups == 2
    assert gara.group_seeding == "elo"

    _iscrivi(db_session, gara, 11)
    pagina = client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)
    assert 'name="groups_count"' in pagina
    assert "Girone A: 6 · Girone B: 5" in pagina

    client.post(
        f"/admin/gara/{gara.id}/start_first_round",
        data={"groups_count": "2"},
        follow_redirects=True,
    )
    db_session.expire_all()
    gara = db_session.get(Gara, gara.id)
    assert gara.current_round == 1
    taglie = Counter(
        i.group_index for i in Inscription.query.filter_by(gara_id=gara.id).all()
    )
    assert sorted(taglie.values(), reverse=True) == [6, 5]
    assert gara.rounds_count == 5


def test_troppi_gironi_si_rifiutano(client, db_session, direttore):
    gara = _crea(client, direttore, max_groups="2")
    _iscrivi(db_session, gara, 5)
    risposta = client.post(
        f"/admin/gara/{gara.id}/start_first_round",
        data={"groups_count": "2"},
        follow_redirects=True,
    )
    db_session.expire_all()
    assert db_session.get(Gara, gara.id).current_round == 0
    assert "almeno 3 per girone" in risposta.get_data(as_text=True)


def test_la_composizione_scelta_al_foglio_si_scrive(client, db_session, direttore):
    gara = _crea(client, direttore, max_groups="2", group_seeding="sorteggio")
    _iscrivi(db_session, gara, 8)
    client.post(
        f"/admin/gara/{gara.id}/start_first_round",
        data={"groups_count": "2", "group_seeding": "elo"},
        follow_redirects=True,
    )
    db_session.expire_all()
    gara = db_session.get(Gara, gara.id)
    assert gara.group_seeding == "elo"
    assert gara.current_round == 1


def test_il_regolamento_dice_i_gironi(client, db_session, direttore):
    gara = _crea(client, direttore, max_groups="2", group_seeding="elo")
    pagina = client.get(f"/gara/{gara.id}/regolamento").get_data(as_text=True)
    assert "Fino a 2 gironi all&#39;italiana, composti per ELO" in pagina


def _campionato(db_session, direttore, **campi):
    from models import Campionato
    from models.user.models import DirectorAssignment

    camp = Campionato(
        name=f"Lunedì al 74 {uuid.uuid4().hex[:6]}",
        campionato_type="round_robin",
        is_active=True,
        default_classification_system="POINTS",
        default_rounds_count=3,
        **campi,
    )
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
    db_session.commit()
    return camp


def test_la_nuova_gara_del_campionato_mostra_la_proposta(client, db_session, direttore):
    camp = _campionato(db_session, direttore, default_max_groups=2)
    _login(client, direttore)
    pagina = client.get(f"/admin/campionato/{camp.id}").get_data(as_text=True)
    assert 'id="create_max_groups"' in pagina
    assert '<option value="2" selected>' in pagina


def test_la_modifica_del_campionato_salva_i_gironi(client, db_session, direttore):
    from models import Campionato

    camp = _campionato(db_session, direttore)
    _login(client, direttore)
    client.post(
        f"/admin/campionato/{camp.id}/edit",
        data={
            "name": camp.name,
            "campionato_type": "round_robin",
            "planned_gare_count": "10",
            "default_classification_system": "POINTS",
            "default_odd_policy": "bye",
            "default_max_groups": "2",
            "default_group_seeding": "categoria",
        },
        follow_redirects=True,
    )
    db_session.expire_all()
    camp = db_session.get(Campionato, camp.id)
    assert camp.default_max_groups == 2
    assert camp.default_group_seeding == "categoria"
