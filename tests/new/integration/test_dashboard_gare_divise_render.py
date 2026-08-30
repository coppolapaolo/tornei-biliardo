"""La dashboard del giocatore, renderizzata davvero.

`test_dashboard_gare_divise.py` presidia la regola — chi finisce in quale
elenco; qui si controlla che la pagina esca, e che ci sia sopra quello che la
regola ha deciso. Sono due domande diverse: la prima ha continuato a passare
per tutto il tempo in cui la sezione «I tuoi match» esisteva nel view model e
nessun template la disegnava.

Il caso della lista d'attesa per **parità** è quello che serviva di più: il
motivo è in colonna da sempre e finora nessuna schermata lo leggeva, quindi
«Lista d'attesa #1» su una gara mezza vuota si leggeva come un errore del sito.
"""

import uuid
from datetime import date, timedelta

import pytest

from models import db
from models.competition.models import Gara, Inscription, WaitlistReason
from models.match.models import Match
from models.status_enum import GaraStatus, MatchStatus
from models.user.models import User


def _uid() -> str:
    return str(uuid.uuid4())[:8]


def _login(client, user) -> None:
    client.post(
        "/auth/login",
        data={"username": user.username, "password": "test1234"},
        follow_redirects=True,
    )


@pytest.fixture
def giocatore(db_session):
    user = User(username=f"gio_{_uid()}", email=f"gio_{_uid()}@t.com", role="player")
    user.set_password("test1234")
    db_session.add(user)
    db_session.flush()
    return user


def _gara(db_session, **kwargs) -> Gara:
    valori = {
        "name": f"Gara {_uid()}",
        # NOT NULL anche per una gara singola: la numerazione serve
        # all'ordine cronologico delle prove (ADR-016).
        "number": 1,
        "date": date.today() + timedelta(days=7),
        "discipline": "nine_ball",
        "status": GaraStatus.INSCRIPTION.value,
        "distance": 5,
        "is_race_to": True,
        "max_participants": 24,
    }
    valori.update(kwargs)
    gara = Gara(**valori)
    db_session.add(gara)
    db_session.flush()
    return gara


@pytest.mark.integration
def test_la_gara_a_cui_sono_iscritto_sta_sotto_le_tue_gare(
    client, db_session, giocatore
):
    gara = _gara(db_session, name="Torneo del Giovedi")
    db_session.add(Inscription(user_id=giocatore.id, gara_id=gara.id))
    db_session.commit()

    _login(client, giocatore)
    html = client.get("/dashboard").get_data(as_text=True)

    assert "Le tue gare" in html
    assert "Torneo del Giovedi" in html
    assert "Iscritto" in html


@pytest.mark.integration
def test_la_gara_aperta_a_cui_non_sono_iscritto_sta_sotto_le_aperte(
    client, db_session, giocatore
):
    _gara(db_session, name="Coppa del Venerdi")
    db_session.commit()

    _login(client, giocatore)
    html = client.get("/dashboard").get_data(as_text=True)

    assert "Aperte, puoi iscriverti" in html
    assert "Coppa del Venerdi" in html
    assert "Iscriviti" in html


@pytest.mark.integration
def test_la_lista_d_attesa_per_parita_spiega_perche(client, db_session, giocatore):
    """Regressione: il motivo esisteva in colonna e non lo leggeva nessuno.

    Su una gara con 24 posti e pochi iscritti, «Lista d'attesa #1» senza
    spiegazione si legge come un guasto. La differenza fra i due motivi è
    esattamente questa frase.
    """
    gara = _gara(db_session, name="Gara Pari")
    db_session.add(
        Inscription(
            user_id=giocatore.id,
            gara_id=gara.id,
            is_waitlist=True,
            waitlist_position=1,
            waitlist_reason=WaitlistReason.PARITY.value,
        )
    )
    db_session.commit()

    _login(client, giocatore)
    html = client.get("/dashboard").get_data(as_text=True)

    assert "Serve un numero pari" in html
    assert "La gara &egrave; al completo" not in html
    assert "La gara è al completo" not in html


@pytest.mark.integration
def test_la_lista_d_attesa_per_capienza_dice_l_altra_cosa(
    client, db_session, giocatore
):
    gara = _gara(db_session, name="Gara Piena", max_participants=2)
    db_session.add(
        Inscription(
            user_id=giocatore.id,
            gara_id=gara.id,
            is_waitlist=True,
            waitlist_position=3,
            waitlist_reason=WaitlistReason.CAPACITY.value,
        )
    )
    db_session.commit()

    _login(client, giocatore)
    html = client.get("/dashboard").get_data(as_text=True)

    assert "Serve un numero pari" not in html
    assert "completo" in html


@pytest.mark.integration
def test_la_partita_in_corso_e_dentro_la_card_della_sua_gara(
    client, db_session, giocatore
):
    """Il cuore della forma scelta: niente più sezione «I tuoi match»."""
    avversario = User(
        username=f"avv_{_uid()}", email=f"avv_{_uid()}@t.com", role="player"
    )
    avversario.set_password("test1234")
    db_session.add(avversario)
    db_session.flush()

    gara = _gara(
        db_session,
        name="Gara Viva",
        status=GaraStatus.PLAYING.value,
        date=date.today(),
    )
    db_session.add(Inscription(user_id=giocatore.id, gara_id=gara.id))
    db_session.add(Inscription(user_id=avversario.id, gara_id=gara.id))
    db_session.add(
        Match(
            gara_id=gara.id,
            round_number=2,
            player1_id=giocatore.id,
            player2_id=avversario.id,
            status=MatchStatus.PLAYING.value,
            table_assignment=4,
        )
    )
    db_session.commit()

    _login(client, giocatore)
    html = client.get("/dashboard").get_data(as_text=True)

    assert "La tua partita" in html
    assert avversario.username in html
    assert "Gioca la tua partita" in html
    # La sezione gemella non c'è più: la partita vive dentro la sua gara.
    assert "I tuoi match" not in html


@pytest.mark.integration
def test_una_partita_senza_tavolo_lo_dice_invece_di_tacere(
    client, db_session, giocatore
):
    avversario = User(
        username=f"avv_{_uid()}", email=f"avv_{_uid()}@t.com", role="player"
    )
    avversario.set_password("test1234")
    db_session.add(avversario)
    db_session.flush()

    gara = _gara(
        db_session,
        name="Gara Senza Tavoli",
        status=GaraStatus.PLAYING.value,
        date=date.today(),
    )
    db_session.add(Inscription(user_id=giocatore.id, gara_id=gara.id))
    db_session.add(
        Match(
            gara_id=gara.id,
            round_number=1,
            player1_id=giocatore.id,
            player2_id=avversario.id,
            status=MatchStatus.PENDING.value,
            table_assignment=None,
        )
    )
    db_session.commit()

    _login(client, giocatore)
    html = client.get("/dashboard").get_data(as_text=True)

    assert "tavolo non" in html


@pytest.mark.integration
def test_la_gara_in_corso_di_altri_non_finisce_in_dashboard(
    client, db_session, giocatore
):
    """Regressione: «Gare» conteneva ogni gara viva del sistema."""
    _gara(
        db_session,
        name="Gara Di Altri",
        status=GaraStatus.PLAYING.value,
        date=date.today(),
    )
    db_session.commit()

    _login(client, giocatore)
    html = client.get("/dashboard").get_data(as_text=True)

    assert "Gara Di Altri" not in html


@pytest.mark.integration
def test_senza_niente_da_fare_un_vuoto_solo_non_due(client, db_session, giocatore):
    db.session.commit()

    _login(client, giocatore)
    html = client.get("/dashboard").get_data(as_text=True)

    assert "Nessuna gara per te, per ora" in html
    assert html.count("Nessuna gara per te, per ora") == 1


@pytest.mark.integration
def test_il_saluto_compare_una_volta_sola_e_sta_nella_testata(
    client, db_session, giocatore
):
    """Prima la stessa cosa era scritta due volte a tre centimetri.

    In cima «Dashboard Giocatore», e subito sotto un blocco «GIOCATORE / Ciao
    nome» dentro il contenuto. Il titolo diceva anche meno: chi è arrivato
    sulla propria home lo sa che è la sua home; quello che non sa è con quale
    ruolo il sito lo sta trattando — ed è il sottotitolo.
    """
    db.session.commit()

    _login(client, giocatore)
    html = client.get("/dashboard").get_data(as_text=True)

    assert html.count(f"Ciao {giocatore.username}") == 1
    # Resta nel titolo del browser, dove nella linguetta serve; ma non più
    # come intestazione visibile della pagina.
    assert "<title>Dashboard Giocatore</title>" in html
    assert html.count("Dashboard Giocatore") == 1
