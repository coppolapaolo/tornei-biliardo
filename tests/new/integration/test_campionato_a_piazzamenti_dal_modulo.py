"""Il campionato a piazzamenti dal modulo alla classifica generale (ADR-080).

Il passaggio interfaccia↔server: il wizard crea un campionato a piazzamenti
con le serate a punti; le gare nascono dal modale del campionato con formati
diversi — una a gironi, una Amalfi, un tabellone dalla modifica della gara —
e la classifica generale somma i punti del posto in ogni gara. Un campionato a
vittorie, invece, rifiuta i gironi da ogni modulo. Le regole hanno i loro unit
test (`tests/new/unit/test_campionato_a_piazzamenti.py`).
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest

from models import Gara, User
from models.campionato.models import Campionato
from models.campionato.tournament_service import TournamentService
from models.classification.models import GaraClassification
from models.match.models import Match
from models.status_enum import GaraStatus, MatchStatus
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


def _wizard(client, nome, sistema, tipo, **passo2):
    client.post(
        "/admin/campionato/wizard/step2",
        data={
            "name": nome,
            "planned_gare_count": "3",
            "campionato_type": tipo,
            "default_classification_system": sistema,
            "default_gara_classification_system": "POINTS",
        },
    )
    client.post(
        "/admin/campionato/wizard/create",
        data={"default_odd_policy": "bye", "default_rounds_count": "3", **passo2},
        follow_redirects=True,
    )
    return Campionato.query.filter_by(name=nome).first()


def _nuova_gara(client, camp, numero, **campi):
    dati = {
        "campionato_id": str(camp.id),
        "number": str(numero),
        "name": f"Serata {numero}",
        "date": (date.today() + timedelta(days=7 * numero)).isoformat(),
        "time": "20:00",
        "discipline": "8_ball",
        "distance": "3",
        "rounds_count": "3",
        "min_participants": "4",
        "max_participants": "16",
        "entry_fee": "0",
        "first_round_policy": "random",
        "odd_number_policy": "bye",
        "withdraw_policy": "Forfeit",
    }
    dati.update(campi)
    return client.post("/admin/gara/create", data=dati, follow_redirects=True)


def _giocatore(db_session, nome):
    s = uuid.uuid4().hex[:6]
    u = User(username=f"{nome}_{s}", email=f"{nome}_{s}@t.com", role="player")
    u.set_password("x")
    db_session.add(u)
    db_session.flush()
    return u


def _chiudi(db_session, gara, vince, perde, piazzamenti):
    """La gara conclusa: una partita e la classifica finale scritte a mano.

    Giocare tre serate intere dal segnapunti non aggiunge niente a questo
    passaggio: qui si guarda come il campionato legge il piazzamento.
    """
    from models.classification.gara_classification import RoundClassificationService

    gara.status = GaraStatus.COMPLETED.value
    gara.current_round = 1
    db_session.add(
        Match(
            gara_id=gara.id,
            round_number=1,
            player1_id=vince.id,
            player2_id=perde.id,
            player1_score=3,
            player2_score=1,
            status=MatchStatus.CLOSED_UNILATERALLY.value,
            winner_id=vince.id,
        )
    )
    db_session.flush()
    RoundClassificationService.calculate_and_save_round_classification(gara.id, 1)
    for giocatore, posto in piazzamenti:
        riga = GaraClassification.query.filter_by(
            gara_id=gara.id, user_id=giocatore.id
        ).first()
        if riga is None:
            riga = GaraClassification(gara_id=gara.id, user_id=giocatore.id)
            db_session.add(riga)
        riga.position = posto
    db_session.commit()


def test_dal_wizard_alla_classifica_con_formati_diversi(client, db_session, direttore):
    _login(client, direttore)
    nome = f"Lunedì al 74 {uuid.uuid4().hex[:6]}"
    camp = _wizard(client, nome, "POSITION", "round_robin", default_max_groups="2")
    assert camp.default_classification_system == "POSITION"
    assert camp.default_gara_classification_system == "POINTS"
    assert camp.default_max_groups == 2

    # Il modale del campionato propone i gironi e i punti delle serate.
    pagina = client.get(f"/admin/campionato/{camp.id}").get_data(as_text=True)
    assert 'id="create_max_groups"' in pagina

    # Serata 1 a due gironi, serata 2 Amalfi, serata 3 nata girone e
    # diventata tabellone dalla modifica della gara.
    _nuova_gara(client, camp, 1, max_groups="2")
    _nuova_gara(
        client, camp, 2, matchmaking_strategy="amalfi", anti_rematch_enabled="on"
    )
    _nuova_gara(client, camp, 3)
    gare = {g.number: g for g in Gara.query.filter_by(campionato_id=camp.id)}
    assert gare[1].matchmaking_strategy == "round_robin"
    assert gare[1].max_groups == 2
    assert gare[1].classification_system == "POINTS"
    assert gare[2].matchmaking_strategy == "amalfi"
    assert gare[2].classification_system == "POINTS"

    # A piazzamenti la modifica della gara sceglie sistema e formato.
    modulo = client.get(f"/admin/gara/{gare[3].id}/edit").get_data(as_text=True)
    assert '<select class="form-select" id="classification_system"' in modulo
    assert 'id="matchmaking_strategy"' in modulo

    risposta = client.post(
        f"/admin/gara/{gare[3].id}/edit",
        data={
            "name": gare[3].name,
            "date": gare[3].date.isoformat(),
            "time": "20:00",
            "discipline": "8_ball",
            "distance": "3",
            "is_race_to": "on",
            "rounds_count": "3",
            "min_participants": "4",
            "max_participants": "16",
            "entry_fee": "0",
            "matchmaking_strategy": "direct_elimination",
            "first_round_policy": "random",
            "odd_number_policy": "bye",
            "withdraw_policy": "Forfeit",
        },
        follow_redirects=True,
    )
    assert risposta.status_code == 200
    db_session.expire_all()
    tabellone = db_session.get(Gara, gare[3].id)
    assert tabellone.matchmaking_strategy == "direct_elimination"
    assert tabellone.classification_system == "POSITION"

    a, b, c = (_giocatore(db_session, n) for n in "abc")
    _chiudi(db_session, db_session.get(Gara, gare[1].id), a, b, [(a, 1), (b, 2)])
    _chiudi(db_session, db_session.get(Gara, gare[2].id), b, a, [(b, 1), (a, 2)])
    _chiudi(db_session, tabellone, a, c, [(a, 1), (c, 2)])

    classifica = {
        d["user_id"]: (pos, d["total_points"])
        for pos, d in TournamentService().calculate_general_classification(camp.id)
    }
    # 25 + 18 + 25; 18 + 25 + assente; assente, assente, 18.
    assert classifica[a.id] == (1, 68)
    assert classifica[b.id] == (2, 43)
    assert classifica[c.id] == (3, 18)


def test_un_campionato_a_vittorie_rifiuta_i_gironi(client, db_session, direttore):
    _login(client, direttore)
    nome = f"Campionato a vittorie {uuid.uuid4().hex[:6]}"
    # I gironi chiesti a mano al wizard: il campionato non nasce.
    _wizard(client, nome, "WINS", "round_robin", default_max_groups="2")
    assert Campionato.query.filter_by(name=nome).count() == 0

    camp = _wizard(client, nome, "WINS", "round_robin")
    assert camp.default_classification_system == "WINS"
    assert camp.default_gara_classification_system is None
    assert camp.default_max_groups == 1

    # Il modale della nuova gara non mostra i gironi: blocco nascosto, campo
    # spento, quindi non arriva al server.
    pagina = client.get(f"/admin/campionato/{camp.id}").get_data(as_text=True)
    inizio = pagina.index("data-gironi")
    blocco = pagina[inizio : pagina.index('id="create_max_groups"')]
    assert "hidden" in blocco
    campo = pagina[pagina.index('id="create_max_groups"') :]
    assert "disabled" in campo[: campo.index(">")]

    # La nuova gara con i gironi chiesti a mano non nasce.
    _nuova_gara(client, camp, 1, max_groups="2")
    assert Gara.query.filter_by(campionato_id=camp.id).count() == 0
    # A girone unico sì.
    _nuova_gara(client, camp, 1)
    assert Gara.query.filter_by(campionato_id=camp.id).count() == 1

    # La modifica del campionato con i gironi si rifiuta.
    pagina = client.post(
        f"/admin/campionato/{camp.id}/edit",
        data={
            "name": camp.name,
            "campionato_type": "round_robin",
            "planned_gare_count": "3",
            "default_classification_system": "WINS",
            "default_odd_policy": "bye",
            "default_max_groups": "2",
        },
        follow_redirects=True,
    ).get_data(as_text=True)
    assert "girone unico" in pagina
    db_session.expire_all()
    assert db_session.get(Campionato, camp.id).default_max_groups == 1


def test_la_catena_della_classifica_generale_a_piazzamenti(
    client, db_session, direttore
):
    """A pari punti decide la catena scelta nel wizard (2026-10-11).

    Le vittorie non sono ammesse: il server le toglie. La modifica del
    campionato mostra l'editor, e il regolamento dice la frase.
    """
    _login(client, direttore)
    nome = f"Piazzamenti {uuid.uuid4().hex[:6]}"
    camp = _wizard(
        client,
        nome,
        "POSITION",
        "amalfi",
        catena_generale="scontri_diretti,vittorie,piazzamenti",
    )
    assert camp.catena_generale == '["scontri_diretti", "piazzamenti", "sorteggio"]'

    modifica = client.get(f"/admin/campionato/{camp.id}/edit").get_data(as_text=True)
    assert 'name="catena_generale"' in modifica

    regolamento = client.get(f"/campionato/{camp.id}/regolamento").get_data(
        as_text=True
    )
    assert "A pari punti conta lo scontro diretto, poi chi ha più primi posti" in (
        regolamento.replace("&#39;", "'")
    )


def test_anche_un_campionato_a_tabellone_sceglie_la_catena(
    client, db_session, direttore
):
    _login(client, direttore)
    nome = f"Tabelloni {uuid.uuid4().hex[:6]}"
    pagina = client.post(
        "/admin/campionato/wizard/step2",
        data={
            "name": nome,
            "planned_gare_count": "3",
            "campionato_type": "direct_elimination",
            "default_classification_system": "WINS",
        },
    ).get_data(as_text=True)
    assert 'name="catena_generale"' in pagina
    assert 'name="default_catena_turno"' not in pagina
    client.post(
        "/admin/campionato/wizard/create",
        data={"default_rounds_count": "3", "catena_generale": "piazzamenti"},
        follow_redirects=True,
    )
    camp = Campionato.query.filter_by(name=nome).first()
    assert camp.default_classification_system == "POSITION"
    assert camp.catena_generale == '["piazzamenti", "sorteggio"]'
