"""L'allenamento sul catalogo: una prova, una richiesta.

Il flusso precedente costava due pagine e quattro richieste per **una sola**
prova: pagina di conferma, POST che apriva il tentativo, redirect alla pagina
del punteggio, POST che lo chiudeva, redirect al dettaglio. Per farne una
seconda si ricominciava da capo — e chi si allena ne fa dieci di fila.

Qui si verifica il flusso nuovo: si sceglie il drill, si registra una prova
dopo l'altra sulla stessa schermata, si chiude quando si vuole. La sessione
**non** e' un'entita': quello che resta a DB sono i singoli tentativi, gia'
completi. Il test presidia soprattutto che non resti indietro un tentativo
aperto — era la conseguenza silenziosa piu' probabile di sbagliare il taglio.
"""

import pytest

from models import db, User, Challenge
from models.challenge.models import ChallengeAttempt
from models.user.role_enum import UserRole


@pytest.fixture
def author(app):
    """Chi crea i drill: serve solo come `created_by_id`."""
    with app.app_context():
        user = User(
            username="drill_author",
            email="drill_author@example.com",
            password_hash="x",
            role=UserRole.DIRECTOR.value,
        )
        db.session.add(user)
        db.session.commit()
        yield user


@pytest.fixture
def player(app):
    with app.app_context():
        user = User(
            username="drill_player",
            email="drill_player@example.com",
            password_hash="x",
            role=UserRole.PLAYER.value,
        )
        db.session.add(user)
        db.session.commit()
        yield user


@pytest.fixture
def numeric_drill(app, author):
    with app.app_context():
        challenge = Challenge(
            description="Dieci bilie in fila dalla testa del tavolo",
            image_path="/static/uploads/challenges/numeric.jpg",
            created_by_id=author.id,
            is_active=True,
            pass_fail_only=False,
        )
        db.session.add(challenge)
        db.session.commit()
        yield challenge


@pytest.fixture
def pass_fail_drill(app, author):
    with app.app_context():
        challenge = Challenge(
            description="Chiudi il tavolo senza sbagliare un colpo",
            image_path="/static/uploads/challenges/passfail.jpg",
            created_by_id=author.id,
            is_active=True,
            pass_fail_only=True,
        )
        db.session.add(challenge)
        db.session.commit()
        yield challenge


def login(client, user):
    with client.session_transaction() as sess:
        sess["_user_id"] = user.get_id()


def attempts_of(user, challenge):
    return ChallengeAttempt.query.filter_by(
        user_id=user.id, challenge_id=challenge.id
    ).all()


class TestSchermataDiAllenamento:
    def test_la_schermata_si_apre_sul_drill(self, client, player, numeric_drill):
        login(client, player)

        response = client.get(f"/challenges/{numeric_drill.id}/train")

        assert response.status_code == 200
        assert numeric_drill.description.encode() in response.data

    def test_si_apre_anche_sui_drill_riuscita_o_no(
        self, client, player, pass_fail_drill
    ):
        """I due tipi di drill hanno due rami di pagina diversi.

        Senza questo, un errore Jinja nel ramo pass/fail non lo vedrebbe
        nessuno: gli altri test di questa classe passano tutti dal numerico.
        """
        login(client, player)

        response = client.get(f"/challenges/{pass_fail_drill.id}/train")

        assert response.status_code == 200
        assert b"Superata" in response.data

    def test_il_catalogo_porta_qui(self, client, player, numeric_drill):
        """Il pulsante «Provala» del catalogo apre l'allenamento, non piu' la
        vecchia pagina di conferma."""
        login(client, player)

        response = client.get("/challenges/")

        assert response.status_code == 200
        assert f"/challenges/{numeric_drill.id}/train".encode() in response.data

    def test_admin_non_si_allena(self, app, client, numeric_drill):
        """Gli amministratori non provano i drill: era gia' cosi' e resta."""
        drill_id = numeric_drill.id
        with app.app_context():
            admin = User(
                username="drill_admin",
                email="drill_admin@example.com",
                password_hash="x",
                role=UserRole.ADMIN.value,
            )
            db.session.add(admin)
            db.session.commit()
            admin_id = admin.id

        with client.session_transaction() as sess:
            sess["_user_id"] = db.session.get(User, admin_id).get_id()
        response = client.get(f"/challenges/{drill_id}/train")

        assert response.status_code == 302

    def test_drill_ritirato_non_si_allena(self, client, player, numeric_drill):
        drill_id = numeric_drill.id
        login(client, player)

        numeric_drill.is_active = False
        db.session.commit()

        response = client.get(f"/challenges/{drill_id}/train")

        assert response.status_code == 302


class TestUnaProvaUnaRichiesta:
    def test_una_sola_richiesta_registra_la_prova(self, client, player, numeric_drill):
        login(client, player)

        response = client.post(
            f"/challenges/{numeric_drill.id}/train",
            json={"score": 7},
        )

        assert response.status_code == 200
        payload = response.get_json()
        assert payload["success"] is True
        assert payload["attempt"]["score"] == 7

        recorded = attempts_of(player, numeric_drill)
        assert len(recorded) == 1
        assert recorded[0].completed is True
        assert recorded[0].score == 7

    def test_non_resta_indietro_un_tentativo_aperto(
        self, client, player, numeric_drill
    ):
        """Il presidio vero: aprire e chiudere sono **un** gesto solo.

        Se il taglio fosse sbagliato — POST che apre e si aspetta una seconda
        chiamata per chiudere — a DB resterebbero righe con `completed=False`
        che nessuno chiude piu', e il conteggio dei drill completati (che
        alimenta i gate di gamification) andrebbe alla deriva senza errori.
        """
        login(client, player)

        for score in (3, 5, 9):
            client.post(f"/challenges/{numeric_drill.id}/train", json={"score": score})

        recorded = attempts_of(player, numeric_drill)
        assert len(recorded) == 3
        assert all(a.completed for a in recorded)
        assert sorted(a.score for a in recorded if a.score is not None) == [3, 5, 9]

    def test_prove_di_fila_senza_ricaricare(self, client, player, numeric_drill):
        """Dieci prove di fila: dieci richieste in tutto, non quaranta."""
        login(client, player)

        for score in range(10):
            response = client.post(
                f"/challenges/{numeric_drill.id}/train", json={"score": score}
            )
            assert response.status_code == 200
            assert response.get_json()["attempts_count"] == score + 1

        assert len(attempts_of(player, numeric_drill)) == 10

    def test_il_migliore_torna_aggiornato(self, client, player, numeric_drill):
        """La schermata mostra il record mentre si gioca: deve seguirlo."""
        login(client, player)

        client.post(f"/challenges/{numeric_drill.id}/train", json={"score": 4})
        second = client.post(f"/challenges/{numeric_drill.id}/train", json={"score": 9})
        third = client.post(f"/challenges/{numeric_drill.id}/train", json={"score": 6})

        assert second.get_json()["best_score"] == 9
        assert third.get_json()["best_score"] == 9

    def test_nota_facoltativa(self, client, player, numeric_drill):
        login(client, player)

        client.post(
            f"/challenges/{numeric_drill.id}/train",
            json={"score": 5, "notes": "tavolo lento"},
        )

        assert attempts_of(player, numeric_drill)[0].notes == "tavolo lento"


class TestRiuscitaONo:
    def test_superata(self, client, player, pass_fail_drill):
        login(client, player)

        response = client.post(
            f"/challenges/{pass_fail_drill.id}/train", json={"passed": True}
        )

        assert response.status_code == 200
        assert response.get_json()["attempt"]["passed"] is True
        assert attempts_of(player, pass_fail_drill)[0].passed is True

    def test_la_stringa_false_non_diventa_superata(
        self, client, player, pass_fail_drill
    ):
        """Un form manda `"false"`, e `bool("false")` e' `True`.

        E' la trappola che il flusso precedente aveva gia' incontrato: senza
        parsing esplicito una prova **fallita** viene registrata come superata,
        e il giocatore se ne accorge solo guardando il proprio storico.
        """
        login(client, player)

        response = client.post(
            f"/challenges/{pass_fail_drill.id}/train",
            data={"passed": "false"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )

        assert response.status_code == 200
        recorded = attempts_of(player, pass_fail_drill)
        assert len(recorded) == 1
        assert recorded[0].passed is False
        assert recorded[0].score == 0

    def test_esito_mancante_non_registra_nulla(self, client, player, pass_fail_drill):
        """Meglio un errore che una prova inventata."""
        login(client, player)

        response = client.post(f"/challenges/{pass_fail_drill.id}/train", json={})

        assert response.status_code == 422
        assert attempts_of(player, pass_fail_drill) == []

    def test_punteggio_mancante_su_drill_numerico(self, client, player, numeric_drill):
        login(client, player)

        response = client.post(f"/challenges/{numeric_drill.id}/train", json={})

        assert response.status_code == 422
        assert attempts_of(player, numeric_drill) == []


class TestIlPercorsoGaraNonSiTocca:
    def test_il_drill_al_posto_del_bye_resta_sul_flusso_suo(
        self, client, player, numeric_drill
    ):
        """Il bye in gara passa da `start_attempt`, che deve restare.

        La schermata di allenamento serve al catalogo. Il drill giocato al
        posto del bye ha un contesto (gara, turno) e conseguenze in classifica:
        non e' allenamento libero e non va accorpato.
        """
        login(client, player)

        response = client.get(f"/challenges/{numeric_drill.id}/attempt")

        assert response.status_code == 200
