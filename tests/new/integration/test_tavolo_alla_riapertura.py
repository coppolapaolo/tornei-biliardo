"""«Annulla ultimo triangolo» su una partita già chiusa: il tavolo torna.

Rilievo del 2026-10-29, in gara: chi perde segna il triangolo decisivo, la
partita si chiude con la doppia conferma e il tavolo passa alla partita in
attesa. Il giocatore annulla l'ultimo triangolo — era un errore — e la partita
si riapre **senza tavolo**: il segnapunti spegneva il +1 e lasciava solo
«Annulla». Il direttore la vedeva senza tavolo.

Decisione dell'utente: la riaperta riprende il suo tavolo se è libero, se no
un altro libero; senza tavoli liberi resta senza ma **non si blocca**, e i
direttori ricevono un avviso, anche per chi aspettava quel tavolo e potrebbe
trovarlo occupato (`models/match/riapertura.py`).
"""

from datetime import date

import pytest
from flask import g

from models.competition.models import Gara
from models.match.models import Match
from models.notification.models import Notification, NotificationType
from models.status_enum import Discipline, GaraStatus, MatchStatus
from models.user.role_enum import UserRole

pytestmark = pytest.mark.integration


@pytest.fixture
def gara_due_tavoli(db_session):
    """Due tavoli, A–B al 1, C–D al 2; con `attesa` anche E–F senza tavolo."""
    from models.user.models import DirectorAssignment
    from models.user.services import UserService

    def costruisci(attesa: bool):
        direttore = UserService.create_user("ria_dir", "ria_dir@test.local", "pw12345")
        direttore.role = UserRole.DIRECTOR.value
        g_ = {
            n: UserService.create_user(f"ria_{n}", f"ria_{n}@test.local", "pw12345")
            for n in "abcdef"
        }
        gara = Gara(
            number=1,
            name="Gara della riapertura",
            date=date.today(),
            discipline=Discipline.EIGHT_BALL.value,
            distance=3,
            is_race_to=True,
            matchmaking_strategy="amalfi",
            status=GaraStatus.PLAYING.value,
            current_round=1,
            rounds_count=3,
            min_participants=4,
            director_id=direttore.id,
        )
        gara.available_tables = '["1", "2"]'
        db_session.add(gara)
        db_session.commit()
        db_session.add(
            DirectorAssignment(
                user_id=direttore.id,
                entity_type="gara",
                entity_id=gara.id,
                assigned_by_id=direttore.id,
            )
        )

        def partita(p1, p2, tavolo):
            m = Match(
                gara_id=gara.id,
                round_number=1,
                player1_id=p1.id,
                player2_id=p2.id,
                table_assignment=tavolo,
                status=(
                    MatchStatus.PLAYING.value if tavolo else MatchStatus.PENDING.value
                ),
                player1_score=0,
                player2_score=0,
            )
            db_session.add(m)
            return m

        ab = partita(g_["a"], g_["b"], "1")
        cd = partita(g_["c"], g_["d"], "2")
        ef = partita(g_["e"], g_["f"], None) if attesa else None
        db_session.commit()
        return direttore, g_, ab.id, cd.id, (ef.id if ef else None)

    return costruisci


def _entra(client, username):
    g.pop("_login_user", None)
    client.get("/auth/logout")
    r = client.post("/auth/login", data={"username": username, "password": "pw12345"})
    assert r.status_code in (200, 302)


def _chiudi_segnando_da_perdente(client, match_id, vincitore_id):
    """Chi perde segna i tre triangoli: alla distanza le due firme ci sono."""
    for _ in range(3):
        g.pop("_login_user", None)
        r = client.post(
            f"/player/match/{match_id}/racks/add", data={"winner_id": vincitore_id}
        )
        assert r.status_code == 200, r.get_json()


def _annulla(client, match_id, player_id):
    g.pop("_login_user", None)
    r = client.post(
        f"/player/match/{match_id}/racks/remove", data={"player_id": player_id}
    )
    assert r.status_code == 200, r.get_json()


def _avvisi(direttore_id):
    return Notification.query.filter_by(
        user_id=direttore_id, notification_type=NotificationType.TAVOLO_DA_SISTEMARE
    ).all()


def test_senza_nessuno_in_attesa_il_tavolo_torna_suo(
    client, db_session, gara_due_tavoli
):
    direttore, g_, ab, _cd, _ = gara_due_tavoli(attesa=False)
    _entra(client, "ria_b")
    _chiudi_segnando_da_perdente(client, ab, g_["a"].id)
    db_session.expire_all()
    assert db_session.get(Match, ab).status == MatchStatus.CONFIRMED_BY_BOTH.value

    _annulla(client, ab, g_["a"].id)

    db_session.expire_all()
    riaperta = db_session.get(Match, ab)
    assert riaperta.status == MatchStatus.PLAYING.value
    assert riaperta.table_assignment == "1"
    assert _avvisi(direttore.id) == []


def test_tavolo_gia_dato_via_si_continua_e_il_direttore_lo_sa(
    client, db_session, gara_due_tavoli
):
    direttore, g_, ab, _cd, ef = gara_due_tavoli(attesa=True)
    _entra(client, "ria_b")
    _chiudi_segnando_da_perdente(client, ab, g_["a"].id)
    db_session.expire_all()
    assert db_session.get(Match, ef).table_assignment == "1"

    _annulla(client, ab, g_["a"].id)

    db_session.expire_all()
    riaperta = db_session.get(Match, ab)
    assert riaperta.status == MatchStatus.PLAYING.value
    assert riaperta.table_assignment is None
    assert riaperta.aspetta_un_tavolo is False
    # Per il direttore si sta giocando, non è «da giocare» coi trattini.
    from models.competition.direttore_view import StatoPartita, stato_partita

    assert stato_partita(riaperta) == StatoPartita.IN_CORSO
    # Il segnapunti non chiede il tavolo: era lui a spegnere il +1.
    g.pop("_login_user", None)
    pagina = client.get(f"/admin/match/{ab}").get_data(as_text=True)
    assert "Serve un tavolo assegnato" not in pagina
    assert "c7-rackpad__btn" in pagina
    # Si va avanti: il triangolo giusto si segna anche senza tavolo.
    g.pop("_login_user", None)
    r = client.post(f"/player/match/{ab}/racks/add", data={"winner_id": g_["b"].id})
    assert r.status_code == 200, r.get_json()

    avvisi = _avvisi(direttore.id)
    assert len(avvisi) == 1
    assert "ria_e – ria_f" in avvisi[0].message and "1" in avvisi[0].message


def test_tavolo_gia_dato_via_ne_prende_un_altro_libero(
    client, db_session, gara_due_tavoli
):
    direttore, g_, ab, cd, ef = gara_due_tavoli(attesa=True)
    _entra(client, "ria_b")
    _chiudi_segnando_da_perdente(client, ab, g_["a"].id)
    _entra(client, "ria_d")
    _chiudi_segnando_da_perdente(client, cd, g_["c"].id)  # il 2 resta libero
    _entra(client, "ria_b")

    _annulla(client, ab, g_["a"].id)

    db_session.expire_all()
    assert db_session.get(Match, ab).table_assignment == "2"
    assert db_session.get(Match, ef).table_assignment == "1"
    avvisi = _avvisi(direttore.id)
    assert len(avvisi) == 1
    assert "ria_e – ria_f" in avvisi[0].message and "2" in avvisi[0].message


def test_il_segnapunti_non_spegne_il_piu_a_partita_cominciata(db_session):
    """Il tavolo serve per cominciare: senza triangoli lo chiede, con no."""
    partita = Match(gara_id=None, round_number=1, player1_score=0, player2_score=0)
    assert partita.aspetta_un_tavolo is True
    partita.player1_score = 2
    assert partita.aspetta_un_tavolo is False
    partita.table_assignment = "3"
    partita.player1_score = 0
    assert partita.aspetta_un_tavolo is False


def test_anche_il_trio_riaperto_si_continua_e_il_direttore_lo_sa(
    client, db_session, gara_due_tavoli
):
    """Il trio chiude e riapre per un'altra strada (`TrioScoringService`)."""
    from models.match.models import TrioMatch
    from models.match.trio_scoring_service import TrioScoringService

    direttore, g_, ab, _cd, ef = gara_due_tavoli(attesa=True)
    partita = db_session.get(Match, ab)
    partita.is_trio = True
    trio = TrioMatch(
        match_id=ab,
        player1_id=g_["a"].id,
        player2_id=g_["b"].id,
        player3_id=g_["e"].id,
    )
    db_session.add(trio)
    # E gioca nel trio: in attesa resta C–F, che aspetta il tavolo 1.
    db_session.get(Match, ef).player1_id = g_["c"].id
    db_session.get(Match, _cd).player1_id = g_["d"].id
    db_session.get(Match, _cd).player2_id = g_["b"].id
    db_session.commit()
    trio_id = trio.id

    # Al 3 il trio si gioca in tre triangoli; il direttore li firma tutti.
    for vincitore in ("a", "a", "b"):
        TrioScoringService.add_rack_win(
            trio_id, g_[vincitore].id, added_by_id=direttore.id, authoritative=True
        )
        db_session.commit()
    db_session.expire_all()
    assert db_session.get(Match, ab).status == MatchStatus.CONFIRMED_BY_BOTH.value
    assert db_session.get(Match, ef).table_assignment == "1"

    TrioScoringService.remove_last_rack(trio_id, g_["a"].id)
    db_session.commit()

    db_session.expire_all()
    riaperta = db_session.get(Match, ab)
    assert riaperta.status == MatchStatus.PLAYING.value
    assert riaperta.table_assignment is None
    assert riaperta.aspetta_un_tavolo is False
    _entra(client, "ria_a")
    pagina = client.get(f"/admin/match/{ab}").get_data(as_text=True)
    assert "Assegna un tavolo per abilitare i controlli" not in pagina
    assert "addTrioRackWin(" in pagina
    avvisi = _avvisi(direttore.id)
    assert len(avvisi) == 1
    assert "ria_a – ria_b – ria_e" in avvisi[0].message
