"""Il tabellone dopo i gironi dal modulo della gara singola alla classifica.

Il passaggio interfaccia↔server (ADR-081): il modulo porta fase finale,
qualificati per girone, finalina e limite della fase finale; il foglio di
avvio conta i turni del tabellone e dice quando non si gioca; avviare,
giocare i gironi e il tabellone porta alla classifica finale. Le regole
hanno i loro unit test (`test_gironi_tabellone_finale.py`,
`test_fase_finale_moduli.py`).
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Dict

import pytest
from werkzeug.datastructures import MultiDict

from models import Gara, User
from models.base import db, utc_now
from models.classification.models import GaraClassification
from models.competition.inscription_service import InscriptionService
from models.competition.round_service import RoundService
from models.competition.state_service import StateService
from models.match.models import Match
from models.match.services import RackService
from models.matchmaking.bracket import BRACKET_THIRD_PLACE
from models.status_enum import MatchStatus
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


def _crea(client, direttore, **campi) -> Gara:
    _login(client, direttore)
    nome = f"Natale al 74 {uuid.uuid4().hex[:6]}"
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
        ("max_groups", "2"),
        ("group_seeding", "elo"),
        ("final_phase_mode", "tabellone"),
        ("qualifiers_per_group", "2"),
        ("third_place_match", "on"),
        ("final_phase_time_limit", "nessuno"),
    ]
    sostituiti = {k: v for k, v in campi.items()}
    dati = [(k, sostituiti.pop(k, v)) for k, v in dati] + list(sostituiti.items())
    client.post(
        "/admin/gara/create_standalone",
        data=MultiDict(dati),
        follow_redirects=True,
    )
    return Gara.query.filter_by(name=nome).one()


def _iscrivi(db_session, gara: Gara, n: int) -> Dict[int, int]:
    InscriptionService.open_inscriptions(
        gara.id, utc_now() - timedelta(hours=1), utc_now() + timedelta(hours=1)
    )
    elo = {}
    for i in range(n):
        uid = uuid.uuid4().hex[:8]
        player = User(
            username=f"ff_{uid}",
            email=f"ff_{uid}@test.com",
            role=UserRole.PLAYER.value,
        )
        player.set_password("x")
        player.elo_rating = 2000 - 10 * i
        db_session.add(player)
        db_session.commit()
        InscriptionService.inscribe_user(player.id, gara.id)
        elo[player.id] = player.elo_rating
    return elo


def _gioca(gara_id: int, r: int, elo: Dict[int, int]) -> None:
    """Vince sempre il più forte: l'ordine finale si legge dall'ELO."""
    for match in Match.query.filter_by(gara_id=gara_id, round_number=r).all():
        if match.is_bye or MatchStatus.is_finished(match.status):
            continue
        if not match.player2_id:
            continue
        vince = max((match.player1_id, match.player2_id), key=lambda p: elo[p])
        for _ in range(match.match_distance):
            RackService.add_rack_with_score_update(
                match_id=match.id,
                winner_id=vince,
                reported_by_id=vince,
                validated_by_admin=True,
            )
    db.session.commit()
    RoundService.update_round_progression(gara_id)
    db.session.commit()


def _gioca_fino_in_fondo(client, gara: Gara, elo: Dict[int, int]) -> Gara:
    gara = db.session.get(Gara, gara.id)
    for r in range(1, gara.rounds_count + 1):
        if r > 1:
            RoundService.start_next_round(gara.id, r)
            db.session.commit()
            # Le pagine reggono ogni turno, gironi e tabellone.
            assert client.get(f"/admin/gara/{gara.id}").status_code == 200
            ospite = client.application.test_client()
            assert ospite.get(f"/admin/gara/{gara.id}").status_code == 200
        _gioca(gara.id, r, elo)
    gara = db.session.get(Gara, gara.id)
    StateService.complete(gara)
    db.session.commit()
    return db.session.get(Gara, gara.id)


def _posizioni(gara: Gara) -> Dict[int, int]:
    return {
        gc.user_id: gc.position
        for gc in GaraClassification.query.filter_by(gara_id=gara.id).all()
    }


def test_il_modulo_porta_la_fase_finale(client, direttore):
    _login(client, direttore)
    pagina = client.get("/admin/gara/create_standalone").get_data(as_text=True)
    assert 'name="final_phase_mode"' in pagina
    assert 'name="qualifiers_per_group"' in pagina
    assert 'name="final_phase_time_limit"' in pagina
    assert "Fase finale" in pagina
    # Le finali per piazzamento si scelgono (con «Gironi: fino a 2»).
    assert 'value="piazzamento"' in pagina


def test_due_gironi_k2_con_finalina_fino_alla_classifica(client, db_session, direttore):
    gara = _crea(client, direttore)
    assert gara.final_phase_mode == "tabellone"
    assert gara.qualifiers_per_group == 2
    assert gara.third_place_match is True
    assert gara.final_phase_time_limit_minutes == 0

    elo = _iscrivi(db_session, gara, 8)
    pagina = client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)
    # Due gironi da 4: tre turni di girone più semifinali e finale.
    assert "2 gironi · 5 turni" in pagina
    assert "il tabellone non si gioca: la gara finisce col girone" in pagina
    assert "Poi il tabellone fra i primi 2 di ogni girone" in pagina

    client.post(
        f"/admin/gara/{gara.id}/start_first_round",
        data={"groups_count": "2"},
        follow_redirects=True,
    )
    db_session.expire_all()
    gara = db_session.get(Gara, gara.id)
    assert gara.rounds_count == 5

    gara = _gioca_fino_in_fondo(client, gara, elo)
    finalina = Match.query.filter_by(
        gara_id=gara.id, round_number=5, bracket_type=BRACKET_THIRD_PLACE
    ).one()
    assert finalina.time_limit_minutes in (None, 0)
    pos = _posizioni(gara)
    assert sorted(pos.values())[:4] == [1, 2, 3, 4]
    # Vince sempre il più forte: il più forte di tutti è primo.
    assert pos[max(elo, key=lambda p: elo[p])] == 1
    assert len(pos) == 8


def test_tre_gironi_e_due_qualificati_con_i_bye(client, db_session, direttore):
    gara = _crea(client, direttore, max_groups="3")
    elo = _iscrivi(db_session, gara, 9)
    pagina = client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)
    # Tre gironi da 3 (tre turni col riposo), poi un tabellone da 8.
    assert "3 gironi · 6 turni" in pagina

    client.post(
        f"/admin/gara/{gara.id}/start_first_round",
        data={"groups_count": "3"},
        follow_redirects=True,
    )
    db_session.expire_all()
    gara = db_session.get(Gara, gara.id)
    assert gara.rounds_count == 6
    gara = _gioca_fino_in_fondo(client, gara, elo)
    primo_turno_del_tabellone = Match.query.filter_by(
        gara_id=gara.id, round_number=4
    ).all()
    # Sei qualificati in un tabellone da otto: due passano senza giocare.
    assert sum(1 for m in primo_turno_del_tabellone if m.is_bye) == 2
    pos = _posizioni(gara)
    assert pos[max(elo, key=lambda p: elo[p])] == 1
    assert len(pos) == 9


def test_un_girone_solo_finisce_col_girone(client, db_session, direttore):
    gara = _crea(client, direttore)
    elo = _iscrivi(db_session, gara, 5)
    pagina = client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)
    # Con 5 iscritti non stanno due gironi da 3: si gioca un girone solo.
    assert "il tabellone non si gioca: la gara finisce col girone" in pagina

    client.post(
        f"/admin/gara/{gara.id}/start_first_round",
        data={"groups_count": "1"},
        follow_redirects=True,
    )
    db_session.expire_all()
    gara = db_session.get(Gara, gara.id)
    assert gara.current_round == 1
    assert gara.rounds_count == 5
    gara = _gioca_fino_in_fondo(client, gara, elo)
    assert not Match.query.filter(
        Match.gara_id == gara.id, Match.round_number > 5
    ).count()
    pos = _posizioni(gara)
    assert pos[max(elo, key=lambda p: elo[p])] == 1


def test_esattamente_n_col_tabellone_si_spiega(client, db_session, direttore):
    _login(client, direttore)
    nome = f"Natale esatto {uuid.uuid4().hex[:6]}"
    risposta = client.post(
        "/admin/gara/create_standalone",
        data=MultiDict(
            [
                ("name", nome),
                ("date", (date.today() + timedelta(days=10)).isoformat()),
                ("time", "20:00"),
                ("discipline", "9_ball"),
                ("distance", "3"),
                ("exact_number", "on"),
                ("rounds_count", "3"),
                ("min_participants", "4"),
                ("max_participants", "16"),
                ("entry_fee", "0"),
                ("matchmaking_strategy", "round_robin"),
                ("first_round_policy", "random"),
                ("odd_number_policy", "bye"),
                ("withdraw_policy", "Forfeit"),
                ("classification_system", "POINTS"),
                ("max_groups", "2"),
                ("final_phase_mode", "tabellone"),
                ("qualifiers_per_group", "2"),
                ("final_phase_time_limit", "gironi"),
            ]
        ),
        follow_redirects=True,
    )
    assert Gara.query.filter_by(name=nome).count() == 0
    assert "il pareggio non esiste" in risposta.get_data(as_text=True)


def test_la_modifica_della_gara_cambia_la_fase_finale(client, db_session, direttore):
    gara = _crea(client, direttore)
    pagina = client.get(f"/admin/gara/{gara.id}/edit").get_data(as_text=True)
    assert 'name="final_phase_mode"' in pagina
    assert 'name="qualifiers_per_group"' in pagina


def test_il_regolamento_dice_il_tabellone(client, db_session, direttore):
    gara = _crea(client, direttore)
    pagina = client.get(f"/gara/{gara.id}/regolamento").get_data(as_text=True)
    assert "vanno al tabellone" in pagina
    assert "finalina" in pagina
    assert "nel tabellone senza limite di tempo" in pagina


def _campionato(db_session, direttore, **campi):
    from models import Campionato
    from models.user.models import DirectorAssignment

    camp = Campionato(
        name=f"Lunedì al 74 {uuid.uuid4().hex[:6]}",
        campionato_type="round_robin",
        is_active=True,
        default_classification_system="POSITION",
        default_gara_classification_system="POINTS",
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


def test_la_modifica_del_campionato_propone_la_fase_finale(
    client, db_session, direttore
):
    from models import Campionato

    camp = _campionato(db_session, direttore)
    _login(client, direttore)
    pagina = client.get(f"/admin/campionato/{camp.id}/edit").get_data(as_text=True)
    assert 'name="default_final_phase_mode"' in pagina
    client.post(
        f"/admin/campionato/{camp.id}/edit",
        data={
            "name": camp.name,
            "campionato_type": "round_robin",
            "planned_gare_count": "10",
            "default_classification_system": "POSITION",
            "default_gara_classification_system": "POINTS",
            "default_odd_policy": "bye",
            "default_max_groups": "2",
            "default_group_seeding": "elo",
            "default_final_phase_mode": "tabellone",
            "default_qualifiers_per_group": "1",
            "default_third_place_match": "on",
            "default_final_phase_time_limit": "minuti",
            "default_final_phase_time_limit_minutes": "45",
        },
        follow_redirects=True,
    )
    db_session.expire_all()
    camp = db_session.get(Campionato, camp.id)
    assert camp.default_final_phase_mode == "tabellone"
    assert camp.default_qualifiers_per_group == 1
    assert camp.default_third_place_match is True
    assert camp.default_final_phase_time_limit_minutes == 45


def test_la_nuova_gara_del_campionato_mostra_la_proposta(client, db_session, direttore):
    camp = _campionato(
        db_session,
        direttore,
        default_max_groups=2,
        default_final_phase_mode="tabellone",
    )
    _login(client, direttore)
    pagina = client.get(f"/admin/campionato/{camp.id}").get_data(as_text=True)
    assert 'id="create_qualifiers_per_group"' in pagina
