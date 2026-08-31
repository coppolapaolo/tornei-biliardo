# tests/new/integration/test_iscritti_ricerca_per_nome.py
"""Cercare chi iscrivere per username, nome o cognome.

Il direttore che aggiunge un iscritto sceglieva da una tendina di username, in
ordine alfabetico: con un centinaio di giocatori è scorrimento cieco, e lo
username non è il nome della persona. La stringa cercata deve pescare in tutti
e tre i campi.

La ricerca **non può essere SQL**: `first_name` e `last_name` sono
`EncryptedString` con cifratura non deterministica (come l'email, che per la
lookup esatta ha dovuto darsi `email_hash`). Il testo in chiaro esiste solo a
valle della decifratura, cioè nella pagina già resa — dove la lista completa
degli iscrivibili è già presente. Questi test presidiano il dato che il server
deve mettere nel markup perché il filtro possa lavorarci.
"""

from datetime import date, time, timedelta
import re
import uuid

import pytest

from models.base import utc_now
from models.competition.models import Gara
from models.status_enum import GaraStatus
from models.user.models import User
from models.user.role_enum import UserRole


@pytest.fixture
def direttore(db_session):
    user = User(
        username=f"director_{uuid.uuid4().hex[:8]}",
        email=f"director_{uuid.uuid4().hex[:8]}@test.com",
        role=UserRole.DIRECTOR.value,
    )
    user.set_password("password123")
    db_session.add(user)
    db_session.commit()
    return db_session.get(User, user.id)


@pytest.fixture
def giocatore_con_anagrafica(db_session):
    user = User(
        username=f"mb_{uuid.uuid4().hex[:8]}",
        email=f"mb_{uuid.uuid4().hex[:8]}@test.com",
        role=UserRole.PLAYER.value,
        first_name="Marco",
        last_name="Bianchi",
    )
    user.set_password("password123")
    db_session.add(user)
    db_session.commit()
    return db_session.get(User, user.id)


@pytest.fixture
def gara_in_iscrizione(db_session, direttore):
    gara = Gara(
        name=f"Gara {uuid.uuid4().hex[:8]}",
        number=1,
        date=date.today() + timedelta(days=7),
        time=time(18, 0),
        discipline="8_ball",
        distance=5,
        rounds_count=3,
        min_participants=2,
        max_participants=10,
        director_id=direttore.id,
        status=GaraStatus.INSCRIPTION.value,
        inscription_start=utc_now() - timedelta(hours=1),
        inscription_end=utc_now() + timedelta(days=1),
    )
    db_session.add(gara)
    db_session.commit()
    return db_session.get(Gara, gara.id)


def _pagina_da_direttore(client, direttore, gara):
    client.post(
        "/auth/login",
        data={"username": direttore.username, "password": "password123"},
        follow_redirects=True,
    )
    risposta = client.get(f"/admin/gara/{gara.id}", follow_redirects=True)
    assert risposta.status_code == 200
    return risposta.get_data(as_text=True)


def _chiavi_di_ricerca(html, user_id):
    """I `data-cerca` delle option di quell'utente (una per copia del componente)."""
    return re.findall(
        rf'<option value="{user_id}"[^>]*data-cerca="([^"]*)"',
        html,
    )


def test_la_chiave_di_ricerca_contiene_username_nome_e_cognome(
    client, direttore, giocatore_con_anagrafica, gara_in_iscrizione
):
    html = _pagina_da_direttore(client, direttore, gara_in_iscrizione)

    chiavi = _chiavi_di_ricerca(html, giocatore_con_anagrafica.id)
    assert chiavi, "l'option del giocatore non porta la chiave di ricerca"
    for chiave in chiavi:
        assert giocatore_con_anagrafica.username in chiave
        assert "marco" in chiave.lower()
        assert "bianchi" in chiave.lower()


def test_senza_anagrafica_resta_il_solo_username(
    client, db_session, direttore, gara_in_iscrizione
):
    """Nome e cognome sono facoltativi: chi non li ha si cerca come prima."""
    anonimo = User(
        username=f"solo_{uuid.uuid4().hex[:8]}",
        email=f"solo_{uuid.uuid4().hex[:8]}@test.com",
        role=UserRole.PLAYER.value,
    )
    anonimo.set_password("password123")
    db_session.add(anonimo)
    db_session.commit()

    html = _pagina_da_direttore(client, direttore, gara_in_iscrizione)

    chiavi = _chiavi_di_ricerca(html, anonimo.id)
    assert chiavi
    for chiave in chiavi:
        assert chiave.strip() == anonimo.username.lower()


def test_la_tendina_mostra_il_nome_accanto_allo_username(
    client, direttore, giocatore_con_anagrafica, gara_in_iscrizione
):
    """Chi non conosce lo username deve poter riconoscere la persona.

    Cercare non basta: un elenco di soli username non dice al direttore quale
    dei tre `marco` sia quello che ha davanti.
    """
    html = _pagina_da_direttore(client, direttore, gara_in_iscrizione)

    etichette = re.findall(
        rf'<option value="{giocatore_con_anagrafica.id}"[^>]*>([^<]*)</option>',
        html,
    )
    assert etichette
    for etichetta in etichette:
        assert "Marco Bianchi" in etichetta
        assert giocatore_con_anagrafica.username in etichetta


def test_il_campo_di_ricerca_e_lo_script_ci_sono(
    client, direttore, giocatore_con_anagrafica, gara_in_iscrizione
):
    html = _pagina_da_direttore(client, direttore, gara_in_iscrizione)

    assert "js-iscritti-cerca" in html
    assert "js/iscritti_ricerca.js" in html


def test_lo_script_e_caricato_una_volta_sola(
    client, direttore, giocatore_con_anagrafica, gara_in_iscrizione
):
    """Il componente iscritti è incluso due volte (mobile e desktop).

    Uno `<script>` dentro al componente girerebbe due volte: la pagina lo carica
    una volta sola, fuori dal componente.
    """
    html = _pagina_da_direttore(client, direttore, gara_in_iscrizione)

    assert html.count("js/iscritti_ricerca.js") == 1


def test_il_nome_del_giocatore_non_arriva_a_chi_non_dirige(
    client, db_session, giocatore_con_anagrafica, gara_in_iscrizione
):
    """L'anagrafica la vede chi dirige la gara, non chi la guarda da fuori."""
    spettatore = User(
        username=f"spett_{uuid.uuid4().hex[:8]}",
        email=f"spett_{uuid.uuid4().hex[:8]}@test.com",
        role=UserRole.PLAYER.value,
    )
    spettatore.set_password("password123")
    db_session.add(spettatore)
    db_session.commit()

    client.post(
        "/auth/login",
        data={"username": spettatore.username, "password": "password123"},
        follow_redirects=True,
    )
    html = client.get(
        f"/admin/gara/{gara_in_iscrizione.id}", follow_redirects=True
    ).get_data(as_text=True)

    assert "Bianchi" not in html
