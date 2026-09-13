"""La X del primo turno assegnata all'ultimo iscritto invece che a sorteggio.

Regola in `models/matchmaking/bye_preference.py`, scelta dal direttore
all'avvio (`Gara.bye_to_last_inscribed`).

Quel che qui si difende non è solo «la X va a chi ho detto»: è che portarcela
sia una **rietichettatura**, cioè che il resto del sorteggio resti quello che
sarebbe stato. Per la strategia casuale, che pre-genera tutti i turni in un
colpo, l'errore facile è spostare la X del turno 1 e lasciare in piedi il
resto: il destinatario si ritroverebbe due X e comparirebbe un reincontro. Il
test sui cinque turni è lì per quello.
"""

import random
import uuid
from datetime import date, timedelta
from typing import List

import pytest

from models import Gara, Match, User
from models.base import db, utc_now
from models.classification.seeding_service import SeedingService
from models.competition.inscription_service import InscriptionService
from models.competition.round_service import RoundService
from models.competition.services import GaraService
from models.matchmaking import bye_preference
from models.user.role_enum import UserRole


def _players(db_session, count: int) -> List[User]:
    batch = str(uuid.uuid4())[:8]
    users = []
    for i in range(count):
        user = User(
            username=f"x{i}_{batch}",
            email=f"x{i}_{batch}@test.com",
            role=UserRole.PLAYER.value,
        )
        user.set_password("test123")
        users.append(user)
    db_session.add_all(users)
    db_session.commit()
    return users


def _login(client, user, password="test123"):
    return client.post(
        "/auth/login",
        data={"username": user.username, "password": password},
        follow_redirects=True,
    )


def _director(db_session) -> User:
    uid = str(uuid.uuid4())[:8]
    director = User(
        username=f"dir_{uid}", email=f"dir_{uid}@test.com", role=UserRole.DIRECTOR.value
    )
    director.set_password("test123")
    db_session.add(director)
    db_session.commit()
    return director


def _gara(director_id: int, players: List[User], **overrides) -> Gara:
    """Gara dispari con la X, iscritti nell'ordine in cui arrivano nella lista.

    L'ultimo della lista è l'ultimo iscritto: `inscribe_user` viene chiamata in
    ordine, e a parità di `created_at` decide l'id crescente.
    """
    defaults = dict(
        campionato_id=None,
        number=1,
        name="Gara X",
        date=date.today() + timedelta(days=7),
        location="Test",
        description="",
        rounds_count=3,
        min_participants=3,
        max_participants=len(players) + 2,
        entry_fee=0.0,
        discipline="9_ball",
        distance=5,
        is_race_to=True,
        director_id=director_id,
        matchmaking_strategy="amalfi",
        first_round_policy="random",
        odd_number_policy="bye",
        anti_rematch_enabled=True,
    )
    defaults.update(overrides)
    gara = GaraService.create_gara(**defaults)

    InscriptionService.open_inscriptions(
        gara.id, utc_now() - timedelta(hours=1), utc_now() + timedelta(days=5)
    )
    for player in players:
        InscriptionService.inscribe_user(player.id, gara.id)
    return gara


def _bye_player_id(gara_id: int, round_number: int = 1):
    match = Match.query.filter_by(
        gara_id=gara_id, round_number=round_number, is_bye=True
    ).first()
    return match.player1_id if match else None


def _pairs(gara_id: int, round_number: int):
    """Gli abbinamenti del turno come insieme di coppie ordinate."""
    matches = Match.query.filter_by(gara_id=gara_id, round_number=round_number).all()
    return {
        tuple(sorted((m.player1_id, m.player2_id)))
        for m in matches
        if not m.is_bye and m.player2_id is not None
    }


# ── Amalfi ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("strategy", ["amalfi", "random"])
def test_x_va_all_ultimo_iscritto(db_session, strategy):
    """Il direttore sceglie: la X è dell'ultimo arrivato, non di chi capita."""
    director = _director(db_session)
    players = _players(db_session, 5)
    gara = _gara(director.id, players, matchmaking_strategy=strategy)

    RoundService.start_first_round(gara.id, bye_to_last_inscribed=True)

    assert _bye_player_id(gara.id) == players[-1].id


def test_amalfi_senza_scelta_la_x_resta_quella_del_sorteggio(db_session):
    """Nessuna risposta = comportamento storico, la X la decide l'algoritmo.

    Non basta constatare che la X finisca a *qualcuno*: si fissa il seme e si
    confronta con lo stesso sorteggio fatto scegliendo l'ultimo iscritto. Le
    due gare devono differire **solo** per lo scambio dei due giocatori: è la
    definizione di "il resto degli abbinamenti resta casuale".

    Solo Amalfi: lì il sorteggio passa dal `random` globale, quindi il seme lo
    rende ripetibile. La strategia casuale ha un RNG suo per istanza, e la
    stessa prova la fa `test_random_*` per invarianti invece che per confronto.
    """
    director = _director(db_session)
    players = _players(db_session, 5)

    random.seed(20260826)
    gara_sorteggio = _gara(director.id, players)
    RoundService.start_first_round(gara_sorteggio.id)
    sorteggiato = _bye_player_id(gara_sorteggio.id)
    pairs_sorteggio = _pairs(gara_sorteggio.id, 1)

    assert gara_sorteggio.bye_to_last_inscribed is False
    assert sorteggiato is not None

    random.seed(20260826)
    gara_scelta = _gara(director.id, players, number=2)
    RoundService.start_first_round(gara_scelta.id, bye_to_last_inscribed=True)

    assert _bye_player_id(gara_scelta.id) == players[-1].id

    # Stesso sorteggio, due nomi scambiati: nient'altro si muove.
    scambio = {sorteggiato: players[-1].id, players[-1].id: sorteggiato}
    atteso = {
        tuple(sorted(scambio.get(p, p) for p in coppia)) for coppia in pairs_sorteggio
    }
    assert _pairs(gara_scelta.id, 1) == atteso


def test_amalfi_allinea_la_classifica_di_partenza(db_session):
    """Il seeding pubblicato deve continuare a spiegare gli abbinamenti.

    Amalfi deriva il primo turno dalla classifica di partenza: scambiare due
    giocatori negli abbinamenti senza scambiarli anche lì lascerebbe in pagina
    un "ordine sorteggio" che non corrisponde più a nulla.
    """
    director = _director(db_session)
    players = _players(db_session, 5)

    random.seed(7)
    gara_sorteggio = _gara(director.id, players)
    RoundService.start_first_round(gara_sorteggio.id)
    sorteggiato = _bye_player_id(gara_sorteggio.id)
    posizioni = SeedingService.get_seeding_positions(gara_sorteggio.id)

    random.seed(7)
    gara_scelta = _gara(director.id, players, number=2)
    RoundService.start_first_round(gara_scelta.id, bye_to_last_inscribed=True)
    posizioni_scelta = SeedingService.get_seeding_positions(gara_scelta.id)

    if sorteggiato == players[-1].id:
        pytest.skip("il sorteggio aveva già dato la X all'ultimo iscritto")

    # I due si sono scambiati di posto; gli altri sono rimasti dov'erano.
    assert posizioni_scelta[players[-1].id] == posizioni[sorteggiato]
    assert posizioni_scelta[sorteggiato] == posizioni[players[-1].id]
    for user_id, posizione in posizioni.items():
        if user_id not in (sorteggiato, players[-1].id):
            assert posizioni_scelta[user_id] == posizione

    # `initial_order` è la proiezione del seeding mostrata al giocatore.
    from models.competition.models import Inscription

    for inscription in Inscription.active_for_gara(gara_scelta.id):
        assert inscription.initial_order == posizioni_scelta[inscription.user_id]


# ── Random: lo scambio non deve rompere lo schedule già generato ──────────


def test_random_conserva_una_sola_x_e_zero_reincontri(db_session):
    """Cinque giocatori, cinque turni: una X a testa e mai lo stesso incontro.

    È la trappola del caso casuale: lì i turni nascono tutti insieme, e
    spostare la X del solo primo turno darebbe due X al destinatario e un
    reincontro a qualcun altro.
    """
    director = _director(db_session)
    players = _players(db_session, 5)
    gara = _gara(director.id, players, matchmaking_strategy="random", rounds_count=5)

    RoundService.start_first_round(gara.id, bye_to_last_inscribed=True)

    assert _bye_player_id(gara.id) == players[-1].id

    x_per_giocatore = {p.id: 0 for p in players}
    incontri = []
    for turno in range(1, 6):
        bye = _bye_player_id(gara.id, turno)
        assert bye is not None, f"turno {turno} senza X"
        x_per_giocatore[bye] += 1
        incontri.extend(_pairs(gara.id, turno))

    assert set(x_per_giocatore.values()) == {1}
    assert len(incontri) == len(set(incontri)), "reincontro introdotto dallo scambio"


def test_random_senza_scelta_conserva_le_stesse_garanzie(db_session):
    """Il controllo: senza la scelta lo schedule resta quello di sempre.

    Serve a distinguere «lo scambio conserva le garanzie» da «le garanzie non
    c'erano»: le stesse asserzioni, con la preferenza spenta.
    """
    director = _director(db_session)
    players = _players(db_session, 5)
    gara = _gara(director.id, players, matchmaking_strategy="random", rounds_count=5)

    RoundService.start_first_round(gara.id)

    assert gara.bye_to_last_inscribed is False

    x_per_giocatore = {p.id: 0 for p in players}
    incontri = []
    for turno in range(1, 6):
        bye = _bye_player_id(gara.id, turno)
        assert bye is not None, f"turno {turno} senza X"
        x_per_giocatore[bye] += 1
        incontri.extend(_pairs(gara.id, turno))

    assert set(x_per_giocatore.values()) == {1}
    assert len(incontri) == len(set(incontri))


# ── Quando la domanda non si pone ─────────────────────────────────────────


def test_niente_scelta_con_giocatori_pari(db_session):
    director = _director(db_session)
    players = _players(db_session, 6)
    gara = _gara(director.id, players)

    assert bye_preference.choice_applies(gara) is False
    assert bye_preference.preferred_bye_player(gara) is None


def test_niente_scelta_col_trio(db_session):
    director = _director(db_session)
    players = _players(db_session, 5)
    gara = _gara(director.id, players, odd_number_policy="trio")

    assert bye_preference.choice_applies(gara) is False


def test_niente_scelta_se_il_primo_turno_non_e_a_sorteggio(db_session):
    director = _director(db_session)
    players = _players(db_session, 5)
    gara = _gara(director.id, players, first_round_policy="rating")

    assert bye_preference.choice_applies(gara) is False


def test_la_scelta_vale_anche_per_la_x_con_esercizio(db_session):
    director = _director(db_session)
    players = _players(db_session, 5)
    gara = _gara(director.id, players, odd_number_policy="bye_with_challenge")

    assert bye_preference.choice_applies(gara) is True

    RoundService.start_first_round(gara.id, bye_to_last_inscribed=True)
    assert _bye_player_id(gara.id) == players[-1].id


def test_preferenza_ignorata_se_la_gara_torna_pari(db_session):
    """Un'iscrizione fra la scelta e l'avvio spegne la preferenza, non rompe.

    `choice_applies` viene richiesta anche al momento di applicare la
    preferenza, non solo di mostrarla: qui non c'è più una X da assegnare.
    """
    director = _director(db_session)
    players = _players(db_session, 6)
    gara = _gara(director.id, players)
    gara.bye_to_last_inscribed = True
    db.session.flush()

    assert bye_preference.preferred_bye_player(gara) is None

    RoundService.start_first_round(gara.id)
    assert _bye_player_id(gara.id) is None


def test_ultimo_iscritto_ignora_ritirati_e_lista_attesa(db_session):
    """Chi non gioca non può ricevere la X, anche se è arrivato per ultimo."""
    director = _director(db_session)
    players = _players(db_session, 6)
    gara = _gara(director.id, players)

    from models.competition.models import Inscription

    ultimo = Inscription.query.filter_by(gara_id=gara.id, user_id=players[-1].id).one()
    ultimo.is_withdrawn = True
    db.session.flush()

    assert bye_preference.last_inscribed_user_id(gara) == players[-2].id


# ── La route trasporta la risposta del direttore ──────────────────────────


def test_la_route_registra_la_scelta(db_session, client):
    director = _director(db_session)
    players = _players(db_session, 5)
    gara = _gara(director.id, players)
    gara_id = gara.id
    _login(client, director)

    response = client.post(
        f"/admin/gara/{gara_id}/start_first_round",
        data={"bye_to_last_inscribed": "1"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    gara = db.session.get(Gara, gara_id)
    assert gara.bye_to_last_inscribed is True
    assert _bye_player_id(gara_id) == players[-1].id


def test_la_route_senza_campo_lascia_il_sorteggio(db_session, client):
    director = _director(db_session)
    players = _players(db_session, 5)
    gara = _gara(director.id, players)
    gara_id = gara.id
    _login(client, director)

    response = client.post(
        f"/admin/gara/{gara_id}/start_first_round", follow_redirects=False
    )

    assert response.status_code == 302
    assert db.session.get(Gara, gara_id).bye_to_last_inscribed is False


# ── La pagina propone la domanda solo dove serve ──────────────────────────


def test_la_pagina_mostra_il_modale_quando_c_e_una_x(db_session, client):
    director = _director(db_session)
    players = _players(db_session, 5)
    gara = _gara(director.id, players)
    _login(client, director)

    body = client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)

    # Il foglio «Avvia la gara» (canvas 2.5) porta la scelta della X.
    assert 'id="avviaGaraModal"' in body
    assert 'name="bye_to_last_inscribed"' in body
    assert players[-1].username in body


def test_la_pagina_non_mostra_il_modale_con_giocatori_pari(db_session, client):
    director = _director(db_session)
    players = _players(db_session, 6)
    gara = _gara(director.id, players)
    _login(client, director)

    body = client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)

    assert 'id="avviaGaraModal"' in body
    assert 'name="bye_to_last_inscribed"' not in body
