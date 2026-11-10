"""«La nostra risposta» è solo di chi mantiene il progetto (2026-11-10).

Il giro giornaliero consegna al segnalante, come «La nostra risposta», l'ultimo
commento della issue che comincia col marcatore pubblico. Non guardava chi lo
avesse scritto: il repository è pubblico e chiunque può commentare, quindi un
estraneo poteva far arrivare all'utente — in notifica e nella sua pagina — un
testo a nome nostro. Ora contano solo i commenti il cui `author_association`,
che GitHub mette su ogni commento, è OWNER, MEMBER o COLLABORATOR.

Nessuna chiamata di rete: GitHub è un cliente finto.
"""

from models.base import db
from models.feedback.github_client import GitHubClient, Risposta
from models.feedback.models import FeedbackReport
from models.feedback.service import FeedbackService
from models.feedback.sync import FeedbackSync


class _GitHubFinto:
    configurato = True

    def __init__(self, commenti):
        self._commenti = commenti

    def issue_toccate(self, etichetta, da_quando=None, etag=None):
        issue = {
            "number": 55,
            "state": "open",
            "state_reason": None,
            "labels": [{"name": "segnalazione"}],
            "assignees": [{"login": "chi-mantiene"}],
            "milestone": None,
        }
        return Risposta(ok=True, corpo=[issue], etag="W/x")

    def commenti(self, numero_issue):
        return Risposta(ok=True, corpo=self._commenti)


def _segnalazione(db_session, utente):
    segnalazione = FeedbackService.registra(
        user_id=utente.id, tipo="bug", titolo="Non si segna", corpo="Racconto."
    )
    db.session.flush()
    segnalazione.issue_number = 55
    db_session.commit()
    return segnalazione.id


def _giro(monkeypatch, commenti):
    cliente = _GitHubFinto(commenti)
    monkeypatch.setattr(
        GitHubClient, "dalla_configurazione", classmethod(lambda cls: cliente)
    )
    FeedbackSync.rileggi_da_github(cliente)
    db.session.commit()


def test_il_commento_di_un_estraneo_non_diventa_la_nostra_risposta(
    db_session, logged_in_client, monkeypatch
):
    client, utente = logged_in_client(role="player", username_prefix="segn")
    segnalazione_id = _segnalazione(db_session, utente)

    _giro(
        monkeypatch,
        [
            {"body": "@utente: testo di un passante", "author_association": "NONE"},
            {
                "body": "@utente: testo di chi ha solo contribuito",
                "author_association": "CONTRIBUTOR",
            },
            {"body": "@utente: testo senza provenienza"},
        ],
    )

    db_session.expire_all()
    assert db_session.get(FeedbackReport, segnalazione_id).nota_pubblica is None
    pagina = client.get("/segnalazioni/").get_data(as_text=True)
    assert "testo di un passante" not in pagina
    assert "testo di chi ha solo contribuito" not in pagina
    assert "testo senza provenienza" not in pagina


def test_la_risposta_di_chi_mantiene_arriva_anche_se_dopo_scrive_un_estraneo(
    db_session, logged_in_client, monkeypatch
):
    client, utente = logged_in_client(role="player", username_prefix="segn")
    segnalazione_id = _segnalazione(db_session, utente)

    _giro(
        monkeypatch,
        [
            {"body": "@utente: corretto stasera", "author_association": "OWNER"},
            {"body": "@utente: testo di un passante", "author_association": "NONE"},
        ],
    )

    db_session.expire_all()
    nota = db_session.get(FeedbackReport, segnalazione_id).nota_pubblica
    assert nota == "corretto stasera"
    pagina = client.get("/segnalazioni/").get_data(as_text=True)
    assert "corretto stasera" in pagina
    assert "testo di un passante" not in pagina


def test_membri_e_collaboratori_rispondono_a_nome_nostro():
    for associazione in ("OWNER", "MEMBER", "COLLABORATOR"):
        nota = FeedbackService.nota_pubblica(
            [{"body": "@utente: fatto", "author_association": associazione}]
        )
        assert nota == "fatto", associazione
