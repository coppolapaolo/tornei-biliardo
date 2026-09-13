"""La prova giocata al posto della X arriva in classifica (issue #221).

`SPECIFICHE.md` riga 65: chi resta senza avversario, con
`odd_number_policy = "bye_with_challenge"`, gioca una prova di abilità invece di
stare fermo e ottiene «il match vinto e una differenza rack **pari al punteggio
nella challenge**».

La macchina per farlo c'era tutta e funzionava — `create_x_replacement_attempt`
verifica che il bye sia davvero suo, `complete_x_replacement_attempt` valida il
punteggio contro la distanza del turno e lo scrive sul match — ma **nessuno la
raggiungeva**. Il collegamento che il giocatore vedeva partiva da
`challenge.start_attempt`, e la chiusura passava da `complete_attempt`, che
registra il tentativo e non tocca il `Match`. Chi giocava la prova prendeva
zero, esattamente come chi era rimasto fermo.

Perché nessun test lo vedeva, ed è il motivo per cui questo file esiste: tutti i
test della X con prova chiamavano i servizi **direttamente**
(`_create_x_replacement_match_result`, `update_bye_match_from_challenge`);
nessuno percorreva la strada di un giocatore. È il caso che `tests/CLAUDE.md`
assegna al livello e2e — «può rompersi nel passaggio interfaccia↔server» — e per
questa funzione un e2e non esisteva.

Qui si percorre tutta la catena via HTTP: la scheda in dashboard, la partenza
della prova, la registrazione del punteggio, e il punteggio che si ritrova sul
match e quindi in classifica.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest

from models.base import db, utc_now
from models.challenge.models import Challenge, ChallengeAttempt
from models.competition.gara_bye_challenge import GaraByeChallenge
from models.competition.inscription_service import InscriptionService
from models.competition.round_service import RoundService
from models.competition.services import GaraService
from models.match.models import Match
from models.user.models import User
from models.user.role_enum import UserRole

pytestmark = pytest.mark.integration


def _utente(db_session, prefisso, ruolo=UserRole.PLAYER.value):
    s = uuid.uuid4().hex[:8]
    u = User(
        username=f"{prefisso}_{s}",
        email=f"{prefisso}_{s}@test.com",
        role=ruolo,
        onboarding_completed=True,
    )
    u.set_password("test1234")
    db_session.add(u)
    db_session.commit()
    return u


def _login(client, utente):
    client.post(
        "/auth/login",
        data={"username": utente.username, "password": "test1234"},
        follow_redirects=True,
    )


@pytest.fixture
def gara_con_x(db_session):
    """Gara Amalfi a 5 giocatori con la X sostituita da una prova.

    Cinque iscritti: uno per turno resta senza avversario, e con
    `bye_with_challenge` quello è chi deve giocare l'esercizio.
    """
    direttore = _utente(db_session, "dir", UserRole.DIRECTOR.value)
    giocatori = [_utente(db_session, f"p{i}") for i in range(5)]

    esercizio = Challenge(
        description="Spot Shot Rally",
        image_path="test.jpg",
        pass_fail_only=False,
        created_by_id=direttore.id,
        is_active=True,
    )
    db_session.add(esercizio)
    db_session.commit()

    gara = GaraService.create_gara(
        campionato_id=None,
        number=1,
        name=f"Gara X {uuid.uuid4().hex[:6]}",
        date=date.today() + timedelta(days=7),
        location="Test",
        description="",
        rounds_count=3,
        min_participants=3,
        max_participants=8,
        entry_fee=0.0,
        discipline="9_ball",
        distance=5,
        is_race_to=True,
        director_id=direttore.id,
        matchmaking_strategy="amalfi",
        first_round_policy="random",
        odd_number_policy="bye_with_challenge",
        anti_rematch_enabled=True,
        # L'esercizio lo sceglie il direttore, sempre (issue #267): una gara
        # con la X senza esercizio scelto non è più una configurazione valida.
        x_challenge_id=esercizio.id,
    )
    InscriptionService.open_inscriptions(
        gara.id, utc_now() - timedelta(hours=1), utc_now() + timedelta(days=5)
    )
    for g in giocatori:
        InscriptionService.inscribe_user(g.id, gara.id)
    db_session.commit()

    RoundService.start_first_round(gara.id)
    db_session.commit()

    match_x = Match.query.filter_by(gara_id=gara.id, round_number=1, is_bye=True).one()
    di_turno = db.session.get(User, match_x.player1_id)

    return {
        "gara": gara,
        "direttore": direttore,
        "esercizio": esercizio,
        "match_x": match_x,
        "giocatore": di_turno,
        "altri": [g for g in giocatori if g.id != di_turno.id],
    }


class TestLaSchedaInDashboard:
    """Chi ha la X deve vedere che ha qualcosa da fare.

    Il match con la X nasce già concluso (`round_creation.py`: nasce `pending` e
    viene subito portato a concluso), quindi non compare fra «I tuoi match», che
    mostra solo le partite `pending`/`playing`. Senza una scheda sua, la prova
    da giocare non è annunciata da nessuna parte.
    """

    def test_chi_ha_la_x_vede_la_scheda(self, client, db_session, gara_con_x):
        _login(client, gara_con_x["giocatore"])

        pagina = client.get("/dashboard").get_data(as_text=True)

        assert "x-replacement" in pagina

    def test_chi_gioca_normalmente_non_la_vede(self, client, db_session, gara_con_x):
        _login(client, gara_con_x["altri"][0])

        pagina = client.get("/dashboard").get_data(as_text=True)

        assert "x-replacement" not in pagina

    def test_la_scheda_sparisce_quando_la_prova_e_giocata(
        self, client, db_session, gara_con_x
    ):
        giocatore = gara_con_x["giocatore"]
        _login(client, giocatore)

        risposta = client.post(
            f"/challenges/x-replacement/{gara_con_x['gara'].id}/1",
            follow_redirects=True,
        )
        assert risposta.status_code == 200
        tentativo = ChallengeAttempt.query.filter_by(user_id=giocatore.id).one()
        client.post(
            f"/challenges/x-replacement/{tentativo.id}/complete",
            data={"score": "3"},
            follow_redirects=True,
        )

        pagina = client.get("/dashboard").get_data(as_text=True)

        assert "x-replacement" not in pagina


class TestIlPunteggioArrivaAlMatch:
    """Il cuore della issue: la prova deve contare."""

    def test_il_giocatore_registra_ma_da_solo_non_conta(
        self, client, db_session, gara_con_x
    ):
        """Registrare non è ancora contare: manca la validazione del direttore.

        Il punteggio lo dichiara il giocatore stesso, e a differenza di una
        partita non c'è un avversario che possa smentirlo — la doppia conferma
        qui non esiste per costruzione. Finché il direttore non valida, la prova
        è giocata e vale zero, come una X non sostituita.
        """
        gara, giocatore = gara_con_x["gara"], gara_con_x["giocatore"]
        match_x = gara_con_x["match_x"]
        assert match_x.player1_score == 0, "la X secca nasce a zero (SPECIFICHE 64)"

        _login(client, giocatore)
        client.post(f"/challenges/x-replacement/{gara.id}/1", follow_redirects=True)
        tentativo = ChallengeAttempt.query.filter_by(user_id=giocatore.id).one()

        client.post(
            f"/challenges/x-replacement/{tentativo.id}/complete",
            data={"score": "3"},
            follow_redirects=True,
        )

        assert db_session.get(ChallengeAttempt, tentativo.id).score == 3
        assert db_session.get(Match, match_x.id).player1_score == 0

    def test_con_la_validazione_il_punteggio_arriva_in_classifica(
        self, client, db_session, gara_con_x
    ):
        gara, giocatore = gara_con_x["gara"], gara_con_x["giocatore"]
        direttore = gara_con_x["direttore"]

        _login(client, giocatore)
        client.post(f"/challenges/x-replacement/{gara.id}/1", follow_redirects=True)
        tentativo = ChallengeAttempt.query.filter_by(user_id=giocatore.id).one()
        client.post(
            f"/challenges/x-replacement/{tentativo.id}/complete",
            data={"score": "3"},
            follow_redirects=True,
        )

        _login(client, direttore)
        client.post(
            f"/admin/gara/{gara.id}/round/1/prova-x/{giocatore.id}/valida",
            data={"score": ""},  # conferma quello dichiarato
            follow_redirects=True,
        )

        aggiornato = db_session.get(Match, gara_con_x["match_x"].id)
        assert aggiornato.player1_score == 3
        assert aggiornato.player2_score == 0
        assert aggiornato.winner_id == giocatore.id

    def test_la_chiusura_dalla_schermata_dell_esercizio_conta_lo_stesso(
        self, client, db_session, gara_con_x
    ):
        """Il modulo della schermata deve puntare alla chiusura giusta.

        È la seconda rottura, che l'issue non nominava: anche partendo dalla
        strada corretta, `challenge_attempt_detail.html` inviava **sempre** a
        `complete_attempt`, che non tocca il match. Qui si segue esattamente il
        modulo che la pagina mostra, invece di indovinare l'indirizzo.
        """
        import re

        gara, giocatore = gara_con_x["gara"], gara_con_x["giocatore"]
        _login(client, giocatore)

        client.post(f"/challenges/x-replacement/{gara.id}/1", follow_redirects=True)
        tentativo = ChallengeAttempt.query.filter_by(user_id=giocatore.id).one()

        pagina = client.get(f"/challenges/attempt/{tentativo.id}").get_data(
            as_text=True
        )
        azione = re.search(
            r'<form[^>]*id="completeAttemptForm"[^>]*' r'action="([^"]+)"', pagina
        )
        assert azione, "il modulo di chiusura non è nella pagina"

        client.post(azione.group(1), data={"score": "4"}, follow_redirects=True)

        # Il punteggio è registrato sul tentativo — che è ciò che questa via
        # deve fare. In classifica ci arriva con la validazione del direttore,
        # verificata sopra.
        assert db_session.get(ChallengeAttempt, tentativo.id).score == 4
        ponte = GaraByeChallenge.query.filter_by(
            challenge_attempt_id=tentativo.id
        ).one()
        assert ponte.is_completed is True

    def test_un_punteggio_oltre_la_distanza_del_turno_viene_rifiutato(
        self, client, db_session, gara_con_x
    ):
        """La scala la impone chi registra il dato (#220, SPECIFICHE riga 65).

        Il limite vale su **entrambe** le strade: quella del giocatore e quella
        del direttore. Verificarlo solo sulla prima lascerebbe passare dalla
        seconda un 12 su una gara «al 5», cioè una differenza triangoli che
        giocando nessuno può ottenere in quel turno.
        """
        gara, giocatore = gara_con_x["gara"], gara_con_x["giocatore"]
        direttore = gara_con_x["direttore"]
        _login(client, giocatore)

        client.post(f"/challenges/x-replacement/{gara.id}/1", follow_redirects=True)
        tentativo = ChallengeAttempt.query.filter_by(user_id=giocatore.id).one()

        client.post(
            f"/challenges/x-replacement/{tentativo.id}/complete",
            data={"score": "12"},  # la gara è «al 5»
            follow_redirects=True,
        )
        assert db_session.get(ChallengeAttempt, tentativo.id).score != 12

        _login(client, direttore)
        client.post(
            f"/admin/gara/{gara.id}/round/1/prova-x/{giocatore.id}/valida",
            data={"score": "12"},
            follow_redirects=True,
        )

        aggiornato = db_session.get(Match, gara_con_x["match_x"].id)
        assert aggiornato.player1_score == 0, "un punteggio fuori scala non si scrive"


class TestIlDirettoreRegistraEAzzera:
    """Come per i match, il direttore può inserire il risultato e disfarlo.

    Non è una comodità: molti giocatori non usano l'applicazione, ed è il
    direttore a inserire per loro. Senza questa strada la prova resterebbe
    giocabile solo da chi ha l'app in mano, cioè non da tutti.
    """

    def test_registra_al_posto_di_chi_non_ha_usato_l_app(
        self, client, db_session, gara_con_x
    ):
        """Nessun tentativo esistente: lo apre e lo chiude il direttore."""
        gara, giocatore = gara_con_x["gara"], gara_con_x["giocatore"]
        assert ChallengeAttempt.query.filter_by(user_id=giocatore.id).first() is None

        _login(client, gara_con_x["direttore"])
        client.post(
            f"/admin/gara/{gara.id}/round/1/prova-x/{giocatore.id}/valida",
            data={"score": "4"},
            follow_redirects=True,
        )

        assert db_session.get(Match, gara_con_x["match_x"].id).player1_score == 4
        assert ChallengeAttempt.query.filter_by(user_id=giocatore.id).one().score == 4

    def test_corregge_un_punteggio_gia_dichiarato(self, client, db_session, gara_con_x):
        gara, giocatore = gara_con_x["gara"], gara_con_x["giocatore"]
        _login(client, giocatore)
        client.post(f"/challenges/x-replacement/{gara.id}/1", follow_redirects=True)
        tentativo = ChallengeAttempt.query.filter_by(user_id=giocatore.id).one()
        client.post(
            f"/challenges/x-replacement/{tentativo.id}/complete",
            data={"score": "5"},
            follow_redirects=True,
        )

        _login(client, gara_con_x["direttore"])
        client.post(
            f"/admin/gara/{gara.id}/round/1/prova-x/{giocatore.id}/valida",
            data={"score": "2"},
            follow_redirects=True,
        )

        assert db_session.get(Match, gara_con_x["match_x"].id).player1_score == 2

    def test_azzera_riporta_il_turno_a_zero(self, client, db_session, gara_con_x):
        gara, giocatore = gara_con_x["gara"], gara_con_x["giocatore"]
        _login(client, gara_con_x["direttore"])
        client.post(
            f"/admin/gara/{gara.id}/round/1/prova-x/{giocatore.id}/valida",
            data={"score": "4"},
            follow_redirects=True,
        )
        assert db_session.get(Match, gara_con_x["match_x"].id).player1_score == 4

        client.post(
            f"/admin/gara/{gara.id}/round/1/prova-x/{giocatore.id}/azzera",
            follow_redirects=True,
        )

        assert db_session.get(Match, gara_con_x["match_x"].id).player1_score == 0
        ponte = GaraByeChallenge.query.filter_by(
            gara_id=gara.id, user_id=giocatore.id, round_number=1
        ).one()
        assert ponte.is_validated is False

    def test_un_giocatore_non_puo_validarsi_da_solo(
        self, client, db_session, gara_con_x
    ):
        """È il punto della validazione: deve venire da qualcun altro."""
        gara, giocatore = gara_con_x["gara"], gara_con_x["giocatore"]
        _login(client, giocatore)

        client.post(
            f"/admin/gara/{gara.id}/round/1/prova-x/{giocatore.id}/valida",
            data={"score": "5"},
            follow_redirects=True,
        )

        assert db_session.get(Match, gara_con_x["match_x"].id).player1_score == 0

    def test_il_ponte_gara_esercizio_risulta_completato(
        self, client, db_session, gara_con_x
    ):
        gara, giocatore = gara_con_x["gara"], gara_con_x["giocatore"]
        _login(client, giocatore)

        client.post(f"/challenges/x-replacement/{gara.id}/1", follow_redirects=True)
        tentativo = ChallengeAttempt.query.filter_by(user_id=giocatore.id).one()
        client.post(
            f"/challenges/x-replacement/{tentativo.id}/complete",
            data={"score": "2"},
            follow_redirects=True,
        )

        ponte = GaraByeChallenge.query.filter_by(
            challenge_attempt_id=tentativo.id
        ).one()
        assert ponte.is_completed is True


class TestNessunoPuoFabbricarsiUnaX:
    def test_chi_non_ha_la_x_non_puo_avviare_la_prova(
        self, client, db_session, gara_con_x
    ):
        """`create_x_replacement_attempt` verifica che il bye sia davvero suo."""
        gara = gara_con_x["gara"]
        _login(client, gara_con_x["altri"][0])

        client.post(f"/challenges/x-replacement/{gara.id}/1", follow_redirects=True)

        assert (
            ChallengeAttempt.query.filter_by(user_id=gara_con_x["altri"][0].id).first()
            is None
        )


class TestIComandiSonoNellaPaginaDellaGara:
    """I due comandi devono esistere in una schermata, non solo come route.

    È la distinzione che ha creato questa issue: le route `x_replacement`
    esistevano, erano in allowlist e funzionavano — e nessun template le
    linkava, quindi la funzione non esisteva.
    """

    def test_il_direttore_vede_il_comando_di_convalida(
        self, client, db_session, gara_con_x
    ):
        _login(client, gara_con_x["direttore"])

        pagina = client.get(f"/admin/gara/{gara_con_x['gara'].id}").get_data(
            as_text=True
        )

        assert "prova-x" in pagina
        # Dal 2026-09-13 il punteggio si segna con lo stepper della card e
        # parte con «Convalida» (`test_card_trio_set_x.py`), non da un campo.
        assert "convalidaProvaX(this)" in pagina

    def test_dopo_la_convalida_compare_l_azzeramento(
        self, client, db_session, gara_con_x
    ):
        gara, giocatore = gara_con_x["gara"], gara_con_x["giocatore"]
        _login(client, gara_con_x["direttore"])
        client.post(
            f"/admin/gara/{gara.id}/round/1/prova-x/{giocatore.id}/valida",
            data={"score": "3"},
            follow_redirects=True,
        )

        pagina = client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)

        assert "azzera" in pagina

    def test_un_giocatore_non_vede_i_comandi(self, client, db_session, gara_con_x):
        _login(client, gara_con_x["giocatore"])

        pagina = client.get(f"/admin/gara/{gara_con_x['gara'].id}").get_data(
            as_text=True
        )

        assert "prova-x" not in pagina


class TestSenzaEsercizioSceltoNonSiInventa:
    """Nessun ripiego: se manca l'esercizio si dice, non si sostituisce.

    Ci si arriva solo con una gara creata prima che la scelta diventasse
    obbligatoria (#267), o con l'esercizio scelto poi disattivato dal catalogo.
    Pescarne un altro sarebbe l'applicazione che decide al posto del direttore,
    per giunta in un momento in cui nessuno sta guardando.
    """

    @pytest.fixture
    def gara_senza_esercizio(self, db_session, gara_con_x):
        gara = gara_con_x["gara"]
        gara.x_challenge_id = None
        db_session.commit()
        return gara_con_x

    def test_la_scheda_lo_dice_invece_di_offrire_il_pulsante(
        self, client, db_session, gara_senza_esercizio
    ):
        _login(client, gara_senza_esercizio["giocatore"])

        pagina = client.get("/dashboard").get_data(as_text=True)

        assert "non ha ancora scelto" in pagina
        assert "x-replacement" not in pagina

    def test_la_prova_non_si_puo_avviare(
        self, client, db_session, gara_senza_esercizio
    ):
        gara = gara_senza_esercizio["gara"]
        giocatore = gara_senza_esercizio["giocatore"]
        _login(client, giocatore)

        client.post(f"/challenges/x-replacement/{gara.id}/1", follow_redirects=True)

        assert ChallengeAttempt.query.filter_by(user_id=giocatore.id).first() is None
