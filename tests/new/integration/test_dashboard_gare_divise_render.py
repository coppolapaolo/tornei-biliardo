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
from models.base import utc_now
from models.classification.models import RoundClassification
from models.competition.models import Gara, Inscription, WaitlistReason
from models.match.models import Match
from models.status_enum import Discipline, GaraStatus, MatchStatus
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
        "discipline": Discipline.NINE_BALL.value,
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
    # Il riquadro della partita è il bersaglio (10/09): niente pulsante a
    # parte, e il riquadro porta alla partita.
    assert "Gioca la tua partita" not in html
    riquadro = html.split("La tua partita", 1)[0].rsplit("<a ", 1)[1]
    assert "c7-inset--go" in riquadro
    assert "/match/" in riquadro
    # La sezione gemella non c'è più: la partita vive dentro la sua gara.
    assert "I tuoi match" not in html
    # La gara in corso è scura per chiunque la guardi.
    assert "c7-card--accent" in html.split("Gara Viva", 1)[0].rsplit("<article", 1)[1]


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
def test_la_gara_in_corso_di_altri_sta_in_diretta_ora_come_per_l_ospite(
    client, db_session, giocatore
):
    """Regola 1 del 2026-09-10: senza un fatto mio la tessera è quella
    dell'ospite, e l'ospite la diretta la vede. Prima spariva del tutto."""
    _gara(
        db_session,
        name="Gara Di Altri",
        status=GaraStatus.PLAYING.value,
        date=date.today(),
    )
    db_session.commit()

    _login(client, giocatore)
    html = client.get("/dashboard").get_data(as_text=True)

    assert "In diretta ora" in html
    sezione = html.split("In diretta ora", 1)[1]
    assert "Gara Di Altri" in sezione
    tessera = sezione.split("Gara Di Altri", 1)[1].split("</article>", 1)[0]
    assert "Segui la diretta" in tessera
    assert "Iscritto" not in tessera and "Dirigi" not in tessera
    # Non è mia: «Le tue gare» non c'è.
    assert "Le tue gare" not in html


@pytest.mark.integration
def test_le_concluse_sono_di_tutti_e_dicono_se_hai_giocato(
    client, db_session, giocatore
):
    """Regola 2: l'ultima più l'ultimo mese, di tutti, riconoscibili."""
    mia = _gara(
        db_session,
        name="Gara Giocata",
        status=GaraStatus.COMPLETED.value,
        date=date.today() - timedelta(days=3),
    )
    db_session.add(Inscription(user_id=giocatore.id, gara_id=mia.id))
    _gara(
        db_session,
        name="Gara Altrui Finita",
        status=GaraStatus.COMPLETED.value,
        date=date.today() - timedelta(days=5),
    )
    _gara(
        db_session,
        name="Gara Vecchissima",
        status=GaraStatus.COMPLETED.value,
        date=date.today() - timedelta(days=400),
    )
    db_session.commit()

    _login(client, giocatore)
    html = client.get("/dashboard").get_data(as_text=True)

    assert "Concluse" in html
    concluse = html.split("Concluse", 1)[1]
    assert "Gara Giocata" in concluse and "Gara Altrui Finita" in concluse
    # Fuori dalla finestra e non è l'ultima: nello storico.
    assert "Gara Vecchissima" not in concluse
    assert "nello storico" in concluse
    tessera_mia = concluse.split("Gara Giocata", 1)[1].split("</article>", 1)[0]
    assert "Hai giocato" in tessera_mia
    tessera_altrui = concluse.split("Gara Altrui Finita", 1)[1].split("</article>", 1)[
        0
    ]
    assert "Hai giocato" not in tessera_altrui
    # A gara finita «Iscritto» non dice più niente.
    assert "Iscritto" not in tessera_mia


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


# --------------------------------------------------------------------------
# «Come sta andando»: la posizione e le altre partite del turno
# --------------------------------------------------------------------------


def _gara_in_corso_con_avversari(db_session, giocatore, quanti=6, turno=2):
    """Una gara che sta giocando il turno indicato, con N iscritti."""
    gara = _gara(
        db_session,
        name="Gara Con Classifica",
        status=GaraStatus.PLAYING.value,
        date=date.today(),
        current_round=turno,
        rounds_count=5,
    )
    altri = []
    for _ in range(quanti - 1):
        u = User(username=f"alt_{_uid()}", email=f"alt_{_uid()}@t.com", role="player")
        u.set_password("test1234")
        db_session.add(u)
        altri.append(u)
    db_session.flush()

    for u in [giocatore] + altri:
        db_session.add(Inscription(user_id=u.id, gara_id=gara.id))
    db_session.flush()
    return gara, altri


@pytest.mark.integration
def test_la_gara_in_corso_dice_dove_sei_in_classifica(client, db_session, giocatore):
    gara, altri = _gara_in_corso_con_avversari(db_session, giocatore, quanti=4)
    ordine = [altri[0], giocatore, altri[1], altri[2]]
    for posizione, u in enumerate(ordine, start=1):
        db_session.add(
            RoundClassification(
                gara_id=gara.id, round_number=1, user_id=u.id, position=posizione
            )
        )
    db_session.commit()

    _login(client, giocatore)
    html = client.get("/dashboard").get_data(as_text=True)

    assert "Classifica provvisoria" in html
    assert "dopo il turno" in html
    assert "2°" in html and "4" in html


@pytest.mark.integration
def test_la_classifica_di_partenza_non_si_spaccia_per_provvisoria(
    client, db_session, giocatore
):
    """Il turno 0 è l'ordine del sorteggio, non una classifica.

    Dire a qualcuno che è quarto prima che si sia giocato un solo triangolo
    è un'informazione inventata: quella riga la scrive il seeding.
    """
    gara, altri = _gara_in_corso_con_avversari(db_session, giocatore, quanti=4, turno=1)
    for posizione, u in enumerate([giocatore] + altri, start=1):
        db_session.add(
            RoundClassification(
                gara_id=gara.id, round_number=0, user_id=u.id, position=posizione
            )
        )
    db_session.commit()

    _login(client, giocatore)
    html = client.get("/dashboard").get_data(as_text=True)

    assert "Classifica provvisoria" not in html


@pytest.mark.integration
def test_si_vedono_le_altre_partite_del_turno_e_quante_ne_restano(
    client, db_session, giocatore
):
    gara, altri = _gara_in_corso_con_avversari(
        db_session, giocatore, quanti=11, turno=2
    )

    # La mia, che sta gia' in cima alla card.
    db_session.add(
        Match(
            gara_id=gara.id,
            round_number=2,
            player1_id=giocatore.id,
            player2_id=altri[0].id,
            status=MatchStatus.PLAYING.value,
            table_assignment=1,
        )
    )
    # Cinque degli altri, tutte con un punteggio: tre si mostrano, due no.
    for i in range(1, 10, 2):
        db_session.add(
            Match(
                gara_id=gara.id,
                round_number=2,
                player1_id=altri[i].id,
                player2_id=altri[i + 1].id if i + 1 < len(altri) else None,
                status=MatchStatus.PLAYING.value,
                player1_score=3,
                player2_score=1,
                table_assignment=i + 1,
            )
        )
    db_session.commit()

    _login(client, giocatore)
    html = client.get("/dashboard").get_data(as_text=True)

    assert "Altre partite del turno" in html
    assert "e altre 2 partite" in html

    # La propria partita non e' ripetuta fra le altre. Si guarda **dentro la
    # sezione**, non su tutta la pagina: in modalita' debug il pannello Quick
    # Login elenca ogni utente per nome, quindi un `html.count(username)`
    # conterebbe quello e non direbbe niente sulla dashboard.
    sezione = html.split("Altre partite del turno", 1)[1].split("</article>", 1)[0]
    assert altri[0].username not in sezione
    assert any(u.username in sezione for u in altri[1:])


# --------------------------------------------------------------------------
# La sfida a due
# --------------------------------------------------------------------------


def _sfida(db_session, giocatore, avversario, *, stato, punteggio=(0, 0)):
    from models.individual_match.match_models import IndividualMatch

    sfida = IndividualMatch(
        player1_id=giocatore.id,
        player2_id=avversario.id,
        location="Sala Da Vinci",
        scheduled_at=utc_now() + timedelta(hours=3),
        discipline=Discipline.NINE_BALL.value,
        distance=7,
        is_race_to=True,
        status=stato,
        player1_score=punteggio[0],
        player2_score=punteggio[1],
    )
    db_session.add(sfida)
    db_session.flush()
    return sfida


@pytest.mark.integration
def test_la_sfida_a_due_in_corso_compare_in_dashboard(client, db_session, giocatore):
    """Regressione: non compariva in nessuna dashboard.

    `DashboardSectionBuilder` la calcolava e nessun template la disegnava, con
    il risultato che si vedevano solo le proposte aperte **degli altri** — gli
    inviti — e non le sfide già accettate.
    """
    avversario = User(
        username=f"avv_{_uid()}", email=f"avv_{_uid()}@t.com", role="player"
    )
    avversario.set_password("test1234")
    db_session.add(avversario)
    db_session.flush()

    _sfida(
        db_session,
        giocatore,
        avversario,
        stato=MatchStatus.IN_PROGRESS,
        punteggio=(3, 4),
    )
    db_session.commit()

    _login(client, giocatore)
    html = client.get("/dashboard").get_data(as_text=True)

    assert "Sfide a due" in html
    sezione = html.split("Sfide a due", 1)[1].split("</section>", 1)[0]
    assert avversario.username in sezione
    assert "3" in sezione and "4" in sezione
    assert "Gioca" in sezione


@pytest.mark.integration
def test_una_sfida_gia_conclusa_non_e_una_cosa_da_fare(client, db_session, giocatore):
    avversario = User(
        username=f"avv_{_uid()}", email=f"avv_{_uid()}@t.com", role="player"
    )
    avversario.set_password("test1234")
    db_session.add(avversario)
    db_session.flush()

    _sfida(
        db_session,
        giocatore,
        avversario,
        stato=MatchStatus.CONFIRMED_BY_BOTH,
        punteggio=(7, 5),
    )
    db_session.commit()

    _login(client, giocatore)
    html = client.get("/dashboard").get_data(as_text=True)

    assert "Sfide a due" not in html


# --------------------------------------------------------------------------
# Il comando che la gara aspetta dal suo direttore
# --------------------------------------------------------------------------


@pytest.fixture
def direttore(db_session):
    user = User(username=f"dir_{_uid()}", email=f"dir_{_uid()}@t.com", role="director")
    user.set_password("test1234")
    db_session.add(user)
    db_session.flush()
    return user


@pytest.mark.integration
def test_la_gara_che_dirigo_dice_cosa_aspetta_da_me(client, db_session, direttore):
    """Prima diceva «Gestisci», uguale per ogni stato.

    Con cinque gare in mano, capire quale aspetta te e per fare cosa voleva
    aprirle una a una.
    """
    _gara(
        db_session,
        name="Gara Da Aprire",
        status=GaraStatus.SETUP.value,
        director_id=direttore.id,
    )
    db_session.commit()

    _login(client, direttore)
    html = client.get("/dashboard").get_data(as_text=True)

    assert "Gara Da Aprire" in html
    sezione = html.split("Gara Da Aprire", 1)[1].split("</article>", 1)[0]
    assert "Apri le iscrizioni" in sezione
    assert "Dirigi" in sezione


@pytest.mark.integration
def test_senza_abbastanza_iscritti_la_card_dice_quanti_ne_mancano(
    client, db_session, direttore
):
    gara = _gara(
        db_session,
        name="Gara Vuota",
        status=GaraStatus.INSCRIPTION.value,
        director_id=direttore.id,
        min_participants=6,
        inscription_start=utc_now() - timedelta(days=1),
        inscription_end=utc_now() + timedelta(days=7),
    )
    db_session.add(Inscription(user_id=direttore.id, gara_id=gara.id))
    db_session.commit()

    _login(client, direttore)
    html = client.get("/dashboard").get_data(as_text=True)

    sezione = html.split("Gara Vuota", 1)[1].split("</article>", 1)[0]
    assert "Avvia la gara" in sezione
    assert "abbastanza iscritti" in sezione
    assert "6" in sezione


@pytest.mark.integration
def test_a_chi_gioca_e_basta_non_si_annuncia_nessun_comando(
    client, db_session, giocatore, direttore
):
    """Il comando è del direttore: a un giocatore non dice niente.

    E non è solo estetica: calcolarlo costa una query di parimerito a gara.
    """
    gara = _gara(
        db_session,
        name="Gara Altrui",
        status=GaraStatus.INSCRIPTION.value,
        director_id=direttore.id,
        inscription_start=utc_now() - timedelta(days=1),
        inscription_end=utc_now() + timedelta(days=7),
    )
    db_session.add(Inscription(user_id=giocatore.id, gara_id=gara.id))
    db_session.commit()

    _login(client, giocatore)
    html = client.get("/dashboard").get_data(as_text=True)

    sezione = html.split("Gara Altrui", 1)[1].split("</article>", 1)[0]
    assert "Avvia la gara" not in sezione
    assert "Dirigi" not in sezione


@pytest.mark.integration
def test_chi_dirige_una_gara_in_corso_ha_gestisci_al_posto_di_segui_la_diretta(
    client, db_session, direttore
):
    """Sul conflitto vince il direttore: «Segui la diretta» e «Gioca» non
    hanno senso per chi dirige, la gestione sì — anche se ci gioca."""
    gara = _gara(
        db_session,
        name="Gara Che Dirigo",
        status=GaraStatus.PLAYING.value,
        director_id=direttore.id,
        date=date.today(),
    )
    db_session.add(Inscription(user_id=direttore.id, gara_id=gara.id))
    db_session.commit()

    _login(client, direttore)
    html = client.get("/dashboard").get_data(as_text=True)

    tessera = html.split("Gara Che Dirigo", 1)[1].split("</article>", 1)[0]
    assert "Gestisci" in tessera
    assert "Segui la diretta" not in tessera
    assert "Gioca la tua partita" not in tessera
    assert "Dirigi" in tessera and "Iscritto" in tessera


@pytest.mark.integration
def test_sulle_tessere_non_ci_sono_pulsanti_piccoli(client, db_session, giocatore):
    """I 40px di `btn-sm` sono difficili da tappare, e su una tessera si
    tappa: le azioni hanno l'altezza standard del tema."""
    gara = _gara(db_session, name="Gara Aperta Tap")
    db_session.add(Inscription(user_id=giocatore.id, gara_id=gara.id))
    db_session.commit()

    _login(client, giocatore)
    html = client.get("/dashboard").get_data(as_text=True)

    tessera = html.split("Gara Aperta Tap", 1)[1].split("</article>", 1)[0]
    assert "btn-sm" not in tessera
    assert "Disiscriviti" in tessera
