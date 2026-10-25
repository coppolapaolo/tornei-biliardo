"""L'admin elimina un utente dalla sua scheda, e la conferma dice chi.

Segnalazione dell'admin del 25/10/2026: nell'elenco utenti il cestino stava
in fondo a destra, dopo quindici colonne, dove il nome non si vedeva più; il
dialogo diceva «Eliminare definitivamente questo utente?» senza dire quale, e
il messaggio dopo non nominava nessuno. Cliccare la riga sbagliata era facile
e nessuno dei tre passi lo avrebbe fatto notare.

Ora:

* l'elenco non ha comandi che cambiano un account: si apre la scheda;
* la scheda ha il foglio «Eliminare <username>?», con nome, ruolo, quante
  iscrizioni e partite ha e cosa succede, e il pulsante «Elimina <username>»;
* il messaggio dopo l'eliminazione nomina l'utente.
"""

from __future__ import annotations

import uuid

import pytest

from models.base import db
from models.user.models import User
from models.user.role_enum import UserRole

PASSWORD = "prova123"


def _make_user(role: str = UserRole.PLAYER.value, **kwargs) -> User:
    suffix = uuid.uuid4().hex[:8]
    user = User(
        username=kwargs.pop("username", f"u_{suffix}"),
        email=f"{suffix}@example.com",
        role=role,
        is_verified=kwargs.pop("is_verified", True),
        onboarding_completed=True,
        gamification_override=True,
        **kwargs,
    )
    user.set_password(PASSWORD)
    db.session.add(user)
    db.session.flush()
    return user


@pytest.fixture
def admin_client(app, db_session):
    admin = _make_user(UserRole.ADMIN.value)
    db_session.commit()
    client = app.test_client()
    client.post(
        "/auth/login",
        data={"username": admin.username, "password": PASSWORD},
        follow_redirects=True,
    )
    return client


def _foglio(pagina: str) -> str:
    """Il solo foglio di eliminazione, ritagliato dalla pagina."""
    inizio = pagina.index('id="eliminaUtenteModal"')
    return pagina[inizio : pagina.index("</form>", inizio)]


def test_il_foglio_dice_chi_si_elimina(app, db_session, admin_client):
    vittima = _make_user(first_name="Mario", last_name="Rossi")
    _make_user()
    db_session.commit()

    pagina = admin_client.get(f"/admin/user/{vittima.id}").get_data(as_text=True)
    foglio = _foglio(pagina)

    assert vittima.username in foglio
    assert "Mario Rossi" in foglio
    assert "Giocatore" in foglio
    assert "0 iscrizioni" in foglio
    assert "0 partite" in foglio
    assert "non si annulla" in foglio.lower()
    assert f"/admin/user/{vittima.id}/anonymize" in foglio
    # Il pulsante porta il nome dentro (ADR-074): «Elimina mario», non
    # «Conferma» né un cestino muto.
    assert f"Elimina {vittima.username}" in foglio


def test_l_elenco_non_ha_comandi_lontani_dal_nome(app, db_session, admin_client):
    """Nessuna azione che cambia un account in fondo a una riga larga."""
    direttore = _make_user(UserRole.DIRECTOR.value)
    giocatore = _make_user(is_verified=False)
    db_session.commit()

    pagina = admin_client.get("/admin/users").get_data(as_text=True)
    tabella = pagina[pagina.index('id="usersTable"') :]

    for utente in (direttore, giocatore):
        assert f"/admin/user/{utente.id}/anonymize" not in tabella
        assert f"/admin/user/{utente.id}/demote_director" not in tabella
        assert f"/admin/user/{utente.id}/verify-email" not in tabella
        # La riga porta alla scheda, che è dove si agisce.
        assert f'href="/admin/user/{utente.id}"' in tabella
    assert "Azioni" not in tabella[: tabella.index("</thead>")]

    # I ruoli concedibili restano nell'elenco (nominarne tre di fila, ADR-041)
    # ma nella **prima cella**, quella del nome, e non in fondo alla riga.
    for riga in tabella.split("<tr")[2:]:
        prima_cella, resto = riga.split("</td>", 1)
        assert "/roles/" not in resto
    assert "/roles/grant/" in tabella


def test_il_messaggio_dopo_nomina_l_utente(app, db_session, admin_client):
    vittima = _make_user()
    db_session.commit()
    nome = vittima.username

    risposta = admin_client.post(
        f"/admin/user/{vittima.id}/anonymize", follow_redirects=True
    )

    testo = risposta.get_data(as_text=True)
    assert f"{nome} eliminato" in testo
    ricaricato = db.session.execute(
        db.select(User)
        .where(User.id == vittima.id)
        .execution_options(include_deleted=True)
    ).scalar_one()
    assert ricaricato.username != nome


def test_un_giocatore_fittizio_non_offre_l_eliminazione(app, db_session, admin_client):
    """Il servizio lo rifiuta: il comando non deve esserci."""
    fittizio = _make_user(is_fittizio=True)
    db_session.commit()

    pagina = admin_client.get(f"/admin/user/{fittizio.id}").get_data(as_text=True)

    assert 'id="eliminaUtenteModal"' not in pagina
    assert f"/admin/user/{fittizio.id}/anonymize" not in pagina


def test_l_unione_nomina_i_due_account(app, db_session, admin_client):
    sorgente = _make_user()
    destinazione = _make_user()
    db_session.commit()
    nome_sorgente, nome_destinazione = sorgente.username, destinazione.username

    risposta = admin_client.post(
        "/admin/users/merge",
        data={"source_id": sorgente.id, "target_id": destinazione.id},
        follow_redirects=True,
    )

    testo = risposta.get_data(as_text=True)
    assert f"{nome_sorgente} unito in {nome_destinazione}" in testo


def test_il_cambio_di_ruolo_nomina_l_utente(app, db_session, admin_client):
    giocatore = _make_user()
    db_session.commit()

    pagina = admin_client.get(f"/admin/user/{giocatore.id}").get_data(as_text=True)
    assert f"Promuovi {giocatore.username}" in pagina

    risposta = admin_client.post(
        f"/admin/user/{giocatore.id}/promote_director", follow_redirects=True
    )
    assert f"{giocatore.username} è ora direttore di gara" in risposta.get_data(
        as_text=True
    )


def test_il_foglio_conta_anche_le_partite_chiuse_dai_giocatori(
    app, db_session, admin_client
):
    """«N partite» conta entrambe le chiusure, non solo quella del direttore.

    `UserStatsService` filtrava il solo `CLOSED_UNILATERALLY`: una partita
    confermata dai due giocatori (`CONFIRMED_BY_BOTH`) non contava, ed è
    giocata quanto l'altra (CLAUDE.md, «Match.status == CLOSED_UNILATERALLY
    per partita giocata»). Nel foglio il numero serve a riconoscere l'account:
    sbagliato, dice «0 partite» di chi ha giocato una stagione.
    """
    from datetime import date, time, timedelta

    from models.base import utc_now
    from models.competition.models import Gara
    from models.match.models import Match
    from models.matchmaking.configuration import MatchmakingStrategy
    from models.status_enum import Discipline, GaraStatus, MatchStatus

    vittima = _make_user()
    avversario = _make_user()
    direttore = _make_user(UserRole.DIRECTOR.value)
    gara = Gara(
        name=f"Gara {uuid.uuid4().hex[:8]}",
        number=1,
        date=date.today() + timedelta(days=7),
        time=time(18, 0),
        discipline=Discipline.EIGHT_BALL.value,
        distance=5,
        rounds_count=3,
        min_participants=2,
        max_participants=10,
        matchmaking_strategy=MatchmakingStrategy.RANDOM.value,
        director_id=direttore.id,
        status=GaraStatus.PLAYING.value,
    )
    db.session.add(gara)
    db.session.flush()
    for stato in (
        MatchStatus.CONFIRMED_BY_BOTH.value,
        MatchStatus.CLOSED_UNILATERALLY.value,
    ):
        db.session.add(
            Match(
                gara_id=gara.id,
                round_number=1,
                player1_id=vittima.id,
                player2_id=avversario.id,
                winner_id=vittima.id,
                status=stato,
                ended_at=utc_now(),
            )
        )
    db_session.commit()

    pagina = admin_client.get(f"/admin/user/{vittima.id}").get_data(as_text=True)

    assert "2 partite" in _foglio(pagina)
