"""Il tetto di punteggio dell'esercizio, e l'annulla della prova sbagliata.

Due funzioni distinte che si incontrano nella stessa schermata:

- **il massimo punteggio** (facoltativo) esiste perché fuori da un esame non
  c'era nessun posto dove dire quanto vale al massimo una prova. Non sostituisce
  ``ExamChallenge.max_score``, che risponde a un'altra domanda (ADR-042);
- **l'annulla** esiste perché ora una prova si registra con **un** tocco: il
  tasto sbagliato si preme, e senza via d'uscita l'unico rimedio sarebbe
  compensare a mano.

Quello che questi test difendono soprattutto è la parte invisibile: che il
punteggio impossibile venga rifiutato dal **server** e non solo dal tastierino,
e che annullare restituisca l'XP — altrimenti registra-e-annulla sarebbe un
modo banale di salire di livello.
"""

import pytest

from models import db, User, Challenge
from models.challenge.models import ChallengeAttempt
from models.challenge.services import ChallengeService
from models.exceptions import PermissionDeniedError, ValidationError
from models.user.role_enum import UserRole


@pytest.fixture
def autore(app):
    with app.app_context():
        user = User(
            username="max_autore",
            email="max_autore@example.com",
            password_hash="x",
            role=UserRole.DIRECTOR.value,
        )
        db.session.add(user)
        db.session.commit()
        yield user


@pytest.fixture
def giocatore(app):
    with app.app_context():
        user = User(
            username="max_giocatore",
            email="max_giocatore@example.com",
            password_hash="x",
            role=UserRole.PLAYER.value,
        )
        db.session.add(user)
        db.session.commit()
        yield user


@pytest.fixture
def drill_con_tetto(app, autore):
    with app.app_context():
        challenge = Challenge(
            description="Quindici bilie, una dopo l'altra",
            image_path="/static/uploads/challenges/tetto.jpg",
            created_by_id=autore.id,
            is_active=True,
            pass_fail_only=False,
            max_score=15,
        )
        db.session.add(challenge)
        db.session.commit()
        yield challenge


@pytest.fixture
def drill_riuscita_o_no(app, autore):
    with app.app_context():
        challenge = Challenge(
            description="Chiudi il tavolo senza sbagliare",
            image_path="/static/uploads/challenges/pf.jpg",
            created_by_id=autore.id,
            is_active=True,
            pass_fail_only=True,
        )
        db.session.add(challenge)
        db.session.commit()
        yield challenge


def login(client, user):
    with client.session_transaction() as sess:
        sess["_user_id"] = user.get_id()


# ────────────────────────────────────────────────────────────────────────────
# Il tetto di punteggio
# ────────────────────────────────────────────────────────────────────────────
class TestPunteggioMassimo:
    def test_e_facoltativo(self, app, autore):
        """Senza tetto l'esercizio funziona: NULL è una scelta, non un buco.

        Ci sono prove che si ripetono finché non si sbaglia, dove un massimo
        non esiste. Obbligare a dichiararlo vorrebbe dire far inventare un
        numero a chi crea l'esercizio.
        """
        with app.app_context():
            challenge = ChallengeService.create_challenge(
                description="Finché non sbagli",
                image_path="/static/uploads/challenges/x.jpg",
                created_by_id=autore.id,
            )
            db.session.flush()
            assert challenge.max_score is None

    def test_vietato_sugli_esercizi_riuscita_o_no(self, app, autore):
        """Lì il punteggio è la rappresentazione 1/0 dell'esito, non una misura."""
        with app.app_context():
            with pytest.raises(ValidationError):
                ChallengeService.create_challenge(
                    description="Riuscita o no",
                    image_path="/static/uploads/challenges/x.jpg",
                    created_by_id=autore.id,
                    pass_fail_only=True,
                    max_score=10,
                )

    def test_zero_non_e_un_tetto(self, app, autore):
        """Un massimo a zero renderebbe lo zero l'unico punteggio ammesso."""
        with app.app_context():
            with pytest.raises(ValidationError):
                ChallengeService.create_challenge(
                    description="Tetto assurdo",
                    image_path="/static/uploads/challenges/x.jpg",
                    created_by_id=autore.id,
                    max_score=0,
                )

    def test_il_server_rifiuta_il_punteggio_impossibile(
        self, app, giocatore, drill_con_tetto
    ):
        """Il tastierino si ferma a 15, ma la POST la può fare chiunque.

        Un 40 su una prova che arriva a 15 falserebbe per sempre il record
        personale e la classifica dell'esercizio, senza che niente segnali
        l'anomalia: è il tipo di dato sbagliato che non dà errore da nessuna
        parte.
        """
        with app.app_context():
            with pytest.raises(ValidationError):
                ChallengeService.record_attempt(
                    user_id=giocatore.id,
                    challenge_id=drill_con_tetto.id,
                    score=40,
                )
            assert ChallengeAttempt.query.filter_by(user_id=giocatore.id).count() == 0

    def test_il_punteggio_al_tetto_si_registra(self, app, giocatore, drill_con_tetto):
        """Il massimo è ottenibile: il confronto è `>`, non `>=`."""
        with app.app_context():
            attempt = ChallengeService.record_attempt(
                user_id=giocatore.id,
                challenge_id=drill_con_tetto.id,
                score=15,
            )
            assert attempt.score == 15

    def test_cambiare_tipo_toglie_il_tetto(self, app, autore, drill_con_tetto):
        """Un esercizio che diventa riuscita-o-no non si tiene un massimo.

        Resterebbe scritto senza più nessuno che lo legge, pronto a ricomparire
        se un domani tornasse a punteggio con un valore che nessuno ha scelto.
        """
        with app.app_context():
            aggiornato = ChallengeService.update_challenge(
                challenge_id=drill_con_tetto.id, pass_fail_only=True
            )
            db.session.flush()
            assert aggiornato.max_score is None

    def test_una_modifica_parziale_non_cancella_il_tetto(self, app, drill_con_tetto):
        """Cambiare il solo titolo non deve azzerare il massimo.

        `max_score=None` vuol dire «campo non inviato». Senza la distinzione
        fra questo e `clear_max_score`, ogni salvataggio dal builder avrebbe
        cancellato il tetto in silenzio.
        """
        with app.app_context():
            aggiornato = ChallengeService.update_challenge(
                challenge_id=drill_con_tetto.id, title="Nuovo nome"
            )
            db.session.flush()
            assert aggiornato.max_score == 15

    def test_il_tetto_si_puo_togliere_apposta(self, app, drill_con_tetto):
        with app.app_context():
            aggiornato = ChallengeService.update_challenge(
                challenge_id=drill_con_tetto.id, clear_max_score=True
            )
            db.session.flush()
            assert aggiornato.max_score is None

    def test_la_schermata_mostra_il_tetto(self, client, giocatore, drill_con_tetto):
        login(client, giocatore)
        response = client.get(f"/challenges/{drill_con_tetto.id}/train")
        assert response.status_code == 200
        assert b"15" in response.data


# ────────────────────────────────────────────────────────────────────────────
# L'annulla
# ────────────────────────────────────────────────────────────────────────────
class TestAnnullaLaProva:
    def test_annulla_l_ultima(self, app, client, giocatore, drill_con_tetto):
        with app.app_context():
            for punteggio in (3, 7, 11):
                ChallengeService.record_attempt(
                    user_id=giocatore.id,
                    challenge_id=drill_con_tetto.id,
                    score=punteggio,
                )
            db.session.commit()

        login(client, giocatore)
        response = client.post(
            f"/challenges/{drill_con_tetto.id}/train/undo",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )

        assert response.status_code == 200
        assert response.get_json()["success"] is True
        with app.app_context():
            rimaste = (
                ChallengeAttempt.query.filter_by(
                    user_id=giocatore.id, challenge_id=drill_con_tetto.id
                )
                .order_by(ChallengeAttempt.id)
                .all()
            )
            # Sparisce l'ultima, non una a caso.
            assert [a.score for a in rimaste] == [3, 7]

    def test_registrare_aggiorna_anche_le_riuscite(
        self, client, giocatore, drill_riuscita_o_no
    ):
        """Sui superato/non superato il secondo contatore conta le riuscite.

        Regressione trovata provando la schermata a mano: la risposta della
        registrazione portava `attempts_count` e `best_score` ma non
        `passed_count`, quindi il contatore delle riuscite restava fermo al
        valore renderizzato dal server. Chi registrava dieci prove di fila
        vedeva salire solo il totale — e nessun test lo notava, perche' il dato
        a DB era giusto: sbagliata era solo la risposta.
        """
        login(client, giocatore)
        url = f"/challenges/{drill_riuscita_o_no.id}/train"

        prima = client.post(
            url, json={"passed": True}, headers={"X-Requested-With": "XMLHttpRequest"}
        ).get_json()
        assert prima["passed_count"] == 1

        # Una non riuscita alza il totale ma non le riuscite.
        dopo = client.post(
            url, json={"passed": False}, headers={"X-Requested-With": "XMLHttpRequest"}
        ).get_json()
        assert dopo["attempts_count"] == 2
        assert dopo["passed_count"] == 1

    def test_senza_prove_non_c_e_niente_da_annullare(
        self, client, giocatore, drill_con_tetto
    ):
        login(client, giocatore)
        response = client.post(
            f"/challenges/{drill_con_tetto.id}/train/undo",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert response.status_code == 404
        assert response.get_json()["success"] is False

    def test_non_si_annulla_la_prova_di_un_altro(self, app, autore, giocatore):
        """L'annulla passa dall'id della prova: senza il controllo, chiunque
        potrebbe cancellare lo storico altrui indovinando un numero."""
        with app.app_context():
            challenge = Challenge(
                description="Prova altrui",
                image_path="/static/uploads/challenges/y.jpg",
                created_by_id=autore.id,
                pass_fail_only=True,
            )
            db.session.add(challenge)
            db.session.flush()
            attempt = ChallengeService.record_attempt(
                user_id=giocatore.id, challenge_id=challenge.id, passed=True
            )
            db.session.commit()

            with pytest.raises(PermissionDeniedError):
                ChallengeService.delete_attempt(
                    attempt_id=attempt.id, actor_id=autore.id
                )

    def test_annullare_restituisce_l_xp(self, app, giocatore, drill_riuscita_o_no):
        """Senza restituzione, registra-e-annulla sarebbe un modo banale di
        salire di livello.

        La restituzione è una **transazione compensativa**: un movimento
        negativo, non la cancellazione di quello originale. Il registro deve
        raccontare cos'è successo, non far finta di niente — per questo si
        contano due movimenti e non zero.
        """
        from models.gamification.models import XPTransaction, XPTransactionType

        with app.app_context():
            attempt = ChallengeService.record_attempt(
                user_id=giocatore.id,
                challenge_id=drill_riuscita_o_no.id,
                passed=True,
            )
            db.session.commit()
            attempt_id = attempt.id

            movimenti = XPTransaction.query.filter_by(
                user_id=giocatore.id,
                transaction_type=XPTransactionType.CHALLENGE_COMPLETION,
            ).all()
            if not movimenti:
                pytest.skip("La gamification non ha pagato XP in questo ambiente")
            pagato = sum(m.xp_amount for m in movimenti)
            assert pagato > 0

            ChallengeService.delete_attempt(
                attempt_id=attempt_id, actor_id=giocatore.id
            )
            db.session.commit()

            dopo = XPTransaction.query.filter_by(
                user_id=giocatore.id,
                transaction_type=XPTransactionType.CHALLENGE_COMPLETION,
            ).all()
            assert sum(m.xp_amount for m in dopo) == 0
            assert len(dopo) > len(movimenti)  # compensato, non cancellato
