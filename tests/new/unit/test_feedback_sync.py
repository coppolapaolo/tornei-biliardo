"""Il giro giornaliero delle segnalazioni: cosa succede quando GitHub non aiuta.

Il valore di questi test non sta nel percorso felice — sta nei tre modi in cui
un job notturno diventa un guasto che nessuno vede:

* **il segnaposto che avanza dopo un errore.** Se `ultimo_controllo` si
  spostasse anche quando il polling fallisce, le issue cambiate in quella
  finestra non verrebbero rilette mai più, e l'utente non saprebbe mai come è
  andata a finire. È il difetto peggiore perché non lascia tracce;
* **il giro che muore a metà.** Una notifica che solleva farebbe perdere gli
  aggiornamenti di tutte le altre segnalazioni dello stesso giro;
* **il token assente che tace.** Senza il token le segnalazioni si accumulano
  in attesa: un job che stampa «tutto bene» le nasconde.
"""

from __future__ import annotations

import pytest

from models.base import db, utc_now
from models.feedback.github_client import GitHubClient, Risposta
from models.feedback.models import FeedbackReport, FeedbackStatus, FeedbackSyncState
from models.feedback.service import FeedbackService
from models.feedback.sync import FeedbackSync


class ClienteFinto:
    """Un GitHub che risponde quello che gli si dice, e conta le chiamate."""

    def __init__(self, issue=None, commenti=None, polling_ok=True, etag="W/nuovo"):
        self.configurato = True
        self._issue = issue if issue is not None else []
        self._commenti = commenti or {}
        self._polling_ok = polling_ok
        self._etag = etag
        self.chiamate_polling = []
        self.issue_create = 0

    def crea_issue(self, titolo, corpo, etichette):
        self.issue_create += 1
        return Risposta(ok=True, corpo={"number": 100 + self.issue_create})

    def issue_toccate(self, etichetta, da_quando=None, etag=None):
        self.chiamate_polling.append({"since": da_quando, "etag": etag})
        if not self._polling_ok:
            return Risposta(ok=False, errore="HTTP 502: bad gateway")
        return Risposta(ok=True, corpo=self._issue, etag=self._etag)

    def commenti(self, numero_issue):
        return Risposta(ok=True, corpo=self._commenti.get(numero_issue, []))


def _issue_json(numero, **campi):
    base = {
        "number": numero,
        "state": "open",
        "state_reason": None,
        "labels": [{"name": "segnalazione"}, {"name": "bug"}],
        "assignees": [],
        "milestone": None,
    }
    base.update(campi)
    return base


@pytest.fixture
def utente(isolated_players):
    return isolated_players[0]


@pytest.fixture
def segnalazione_spedita(db_session, utente):
    """Una segnalazione già diventata la issue numero 55."""
    segnalazione = FeedbackService.registra(
        user_id=utente.id, tipo="bug", titolo="Non si segna", corpo="Racconto."
    )
    db.session.flush()
    segnalazione.issue_number = 55
    db.session.flush()
    return segnalazione


def _usa(monkeypatch, cliente):
    monkeypatch.setattr(
        GitHubClient, "dalla_configurazione", classmethod(lambda cls: cliente)
    )


# ══ Il segnaposto ═══════════════════════════════════════════════════════════


@pytest.mark.unit
class TestIlSegnaposto:
    def test_un_polling_fallito_non_lo_sposta(
        self, db_session, segnalazione_spedita, monkeypatch
    ):
        """Il difetto che non lascia tracce: spostarlo dopo un errore
        significa non rileggere mai più quella finestra."""
        cliente = ClienteFinto(polling_ok=False)
        _usa(monkeypatch, cliente)

        aggiornate, notificate, nota = FeedbackSync.rileggi_da_github(cliente)

        assert (aggiornate, notificate) == (0, 0)
        assert "502" in nota
        assert FeedbackSyncState.corrente().ultimo_controllo is None

    def test_un_giro_riuscito_lo_sposta_e_ricorda_l_etag(self, db_session, monkeypatch):
        cliente = ClienteFinto(issue=[], etag='W/"abc"')
        _usa(monkeypatch, cliente)

        FeedbackSync.rileggi_da_github(cliente)

        stato = FeedbackSyncState.corrente()
        assert stato.ultimo_controllo is not None
        assert stato.etag == 'W/"abc"'

    def test_il_giro_dopo_passa_since_ed_etag(self, db_session, monkeypatch):
        """È ciò che rende il caso normale una risposta da poche centinaia di
        byte invece di cento issue."""
        cliente = ClienteFinto(issue=[], etag='W/"abc"')
        _usa(monkeypatch, cliente)
        FeedbackSync.rileggi_da_github(cliente)

        FeedbackSync.rileggi_da_github(cliente)

        secondo = cliente.chiamate_polling[1]
        assert secondo["etag"] == 'W/"abc"'
        assert secondo["since"] is not None and secondo["since"].endswith("Z")

    def test_un_304_e_un_giro_riuscito_non_un_errore(self, db_session, monkeypatch):
        """«Non è cambiato niente» è la risposta giusta, non un guasto: se
        fermasse il segnaposto, `since` non avanzerebbe mai."""
        cliente = ClienteFinto()
        cliente.issue_toccate = lambda **kw: Risposta(
            ok=True, non_modificato=True, etag='W/"uguale"'
        )
        _usa(monkeypatch, cliente)

        aggiornate, notificate, nota = FeedbackSync.rileggi_da_github(cliente)

        assert (aggiornate, notificate, nota) == (0, 0, None)
        assert FeedbackSyncState.corrente().ultimo_controllo is not None


# ══ L'aggiornamento ═════════════════════════════════════════════════════════


@pytest.mark.unit
class TestLAggiornamento:
    def test_una_issue_presa_in_carico_aggiorna_e_notifica(
        self, db_session, segnalazione_spedita, monkeypatch
    ):
        cliente = ClienteFinto(issue=[_issue_json(55, assignees=[{"login": "tizio"}])])
        _usa(monkeypatch, cliente)

        aggiornate, notificate, _nota = FeedbackSync.rileggi_da_github(cliente)

        assert (aggiornate, notificate) == (1, 1)
        riletta = db.session.get(FeedbackReport, segnalazione_spedita.id)
        assert riletta.stato == FeedbackStatus.PRESA_IN_CARICO.value

    def test_la_nota_marcata_arriva_all_utente(
        self, db_session, segnalazione_spedita, monkeypatch
    ):
        cliente = ClienteFinto(
            issue=[_issue_json(55, state="closed", state_reason="completed")],
            commenti={
                55: [
                    {"body": "nota interna, non pubblicare"},
                    {"body": "@utente: corretto nella versione di stasera"},
                ]
            },
        )
        _usa(monkeypatch, cliente)

        FeedbackSync.rileggi_da_github(cliente)

        riletta = db.session.get(FeedbackReport, segnalazione_spedita.id)
        assert riletta.stato == FeedbackStatus.RISOLTA.value
        assert riletta.nota_pubblica == "corretto nella versione di stasera"

    def test_una_issue_senza_segnalazione_dietro_si_ignora(
        self, db_session, monkeypatch
    ):
        """Una issue con l'etichetta scritta a mano da un umano non è roba
        nostra: non deve far saltare il giro né inventare aggiornamenti."""
        cliente = ClienteFinto(issue=[_issue_json(999)])
        _usa(monkeypatch, cliente)

        aggiornate, notificate, nota = FeedbackSync.rileggi_da_github(cliente)

        assert (aggiornate, notificate, nota) == (0, 0, None)

    def test_le_pull_request_non_sono_segnalazioni(
        self, db_session, segnalazione_spedita, monkeypatch
    ):
        """GitHub restituisce le PR nella stessa lista delle issue. Una PR
        numerata come una segnalazione ne cambierebbe lo stato per sbaglio."""
        cliente = ClienteFinto(
            issue=[
                dict(
                    _issue_json(55, state="closed", state_reason="completed"),
                    pull_request={"url": "..."},
                )
            ]
        )
        _usa(monkeypatch, cliente)

        aggiornate, _n, _nota = FeedbackSync.rileggi_da_github(cliente)

        assert aggiornate == 0
        riletta = db.session.get(FeedbackReport, segnalazione_spedita.id)
        assert riletta.stato == FeedbackStatus.RICEVUTA.value

    def test_un_secondo_giro_senza_cambiamenti_non_rinotifica(
        self, db_session, segnalazione_spedita, monkeypatch
    ):
        """Il job ripassa ogni notte sulle stesse issue: senza il confronto,
        l'utente riceverebbe la stessa notifica per sempre."""
        cliente = ClienteFinto(issue=[_issue_json(55, assignees=[{"login": "tizio"}])])
        _usa(monkeypatch, cliente)
        FeedbackSync.rileggi_da_github(cliente)

        aggiornate, notificate, _nota = FeedbackSync.rileggi_da_github(cliente)

        assert (aggiornate, notificate) == (0, 0)

    def test_una_notifica_che_fallisce_non_perde_l_aggiornamento(
        self, db_session, segnalazione_spedita, monkeypatch
    ):
        """La segnalazione è già aggiornata: far saltare il giro per una
        notifica perderebbe anche il lavoro fatto sulle altre."""
        from models.notification.services import NotificationService

        def esplode(**kwargs):
            raise RuntimeError("notifiche giù")

        monkeypatch.setattr(NotificationService, "create_notification", esplode)
        cliente = ClienteFinto(
            issue=[_issue_json(55, state="closed", state_reason="not_planned")]
        )
        _usa(monkeypatch, cliente)

        aggiornate, notificate, _nota = FeedbackSync.rileggi_da_github(cliente)

        assert (aggiornate, notificate) == (1, 0)
        riletta = db.session.get(FeedbackReport, segnalazione_spedita.id)
        assert riletta.stato == FeedbackStatus.NON_PREVISTA.value


# ══ Il giro completo ════════════════════════════════════════════════════════


@pytest.mark.unit
class TestIlGiroCompleto:
    def test_senza_token_lo_dice_forte(self, db_session, utente, monkeypatch):
        """Un giro che tace quando il token manca nasconde una coda che
        cresce: il riepilogo del task deve nominarla."""
        FeedbackService.registra(user_id=utente.id, tipo="bug", titolo="T", corpo="C")
        db.session.flush()
        monkeypatch.setattr(
            GitHubClient, "dalla_configurazione", classmethod(lambda cls: cls(None, ""))
        )

        esito = FeedbackSync.giro_completo()

        assert esito["spedite"] == 0
        assert "GITHUB_FEEDBACK_TOKEN" in esito["nota"]
        assert "1 segnalazioni" in esito["nota"]

    def test_rispedisce_prima_di_rileggere(self, db_session, utente, monkeypatch):
        """L'ordine conta: una segnalazione nata stamattina diventa issue e
        riceve il suo stato nello stesso giro."""
        FeedbackService.registra(
            user_id=utente.id, tipo="bug", titolo="Rimasta indietro", corpo="C"
        )
        db.session.flush()
        cliente = ClienteFinto(issue=[])
        _usa(monkeypatch, cliente)

        esito = FeedbackSync.giro_completo()

        assert esito["spedite"] == 1
        assert cliente.issue_create == 1
        assert cliente.chiamate_polling, "il polling deve girare dopo l'invio"

    def test_un_polling_fallito_non_annulla_le_rispedizioni(
        self, db_session, utente, monkeypatch
    ):
        """Le due fasi sono indipendenti: quello che è riuscito resta."""
        FeedbackService.registra(user_id=utente.id, tipo="bug", titolo="T", corpo="C")
        db.session.flush()
        cliente = ClienteFinto(polling_ok=False)
        _usa(monkeypatch, cliente)

        esito = FeedbackSync.giro_completo()

        assert esito["spedite"] == 1
        assert "polling fallito" in esito["nota"]
        assert FeedbackService.in_attesa_di_invio() == []

    def test_la_rispedizione_ha_un_tetto_per_giro(
        self, db_session, utente, monkeypatch
    ):
        """Dopo un guasto prolungato la coda può essere lunga: svuotarla tutta
        in una raffica è il modo migliore per farsi limitare da GitHub."""
        from models.feedback.sync import MAX_RISPEDIZIONI_PER_GIRO

        for n in range(MAX_RISPEDIZIONI_PER_GIRO + 3):
            FeedbackService.registra(
                user_id=utente.id, tipo="bug", titolo=f"T{n}", corpo="C"
            )
        db.session.flush()
        cliente = ClienteFinto(issue=[])
        _usa(monkeypatch, cliente)

        spedite = FeedbackSync.rispedisci_le_rimaste()

        assert spedite == MAX_RISPEDIZIONI_PER_GIRO
        assert len(FeedbackService.in_attesa_di_invio()) == 3


@pytest.mark.unit
def test_lo_stato_di_sincronia_e_una_riga_sola(db_session):
    """`corrente()` la crea al primo giro e poi la ritrova: due righe
    vorrebbero dire due segnaposti, e uno dei due sbagliato."""
    primo = FeedbackSyncState.corrente()
    primo.ultimo_controllo = utc_now()
    db.session.flush()

    secondo = FeedbackSyncState.corrente()

    assert secondo.id == primo.id == 1
    assert db.session.query(FeedbackSyncState).count() == 1
