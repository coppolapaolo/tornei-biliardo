"""Driver HTTP per i test end-to-end delle gare.

I test che usano questo driver **non chiamano mai un service**: fanno le stesse
richieste che farebbe un browser, sulle stesse route che l'interfaccia espone.
Serve a coprire la classe di guasti che il livello servizio non vede — un
permesso applicato al ruolo globale invece che ai permessi sulla gara, un
pulsante che punta all'endpoint sbagliato, una sequenza rifiutata dal dominio
che la route trasforma in 500 invece che in un messaggio.

Divisione netta, e voluta:

* **Azioni** — solo HTTP. Se una cosa non si può fare via route, il test non la
  fa: significa che l'interfaccia non la offre, ed è un'informazione.
* **Osservazioni** — prima l'HTML (`partite_nella_pagina` legge gli id delle
  partite dai link della pagina gara, come farebbe un occhio umano), poi il DB
  come controprova sulla sostanza. Le due cose insieme dicono sia "l'interfaccia
  lo mostra" sia "il dato è giusto"; una sola delle due lascia scoperta metà
  della domanda.
* **Allestimento** — creare gli utenti passa dal modello. La registrazione ha i
  suoi test (`test_onboarding.py`); qui è rumore.

Il sorteggio è casuale e persistito (`draw_seed`), quindi le asserzioni non
possono nominare i giocatori: si asserisce sulla *forma* del turno (quante
partite, chi compare quante volte), mai su chi incontra chi.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Iterable, Sequence

from models import db
from models.competition.models import Gara
from models.match.models import Match
from models.status_enum import Discipline, MatchStatus, WithdrawPolicy
from models.user.models import User
from models.user.role_enum import UserRole

PASSWORD = "e2e-secret-123"

#: Campi che la schermata di creazione manda sempre. I test sovrascrivono solo
#: ciò che stanno effettivamente mettendo alla prova: un form scritto per intero
#: in ogni test nasconde qual è la variabile dell'esperimento.
FORM_GARA_DEFAULT: dict[str, str] = {
    "time": "20:00",
    "discipline": Discipline.NINE_BALL.value,
    "distance": "5",
    "matchmaking_strategy": "amalfi",
    "first_round_policy": "random",
    "odd_number_policy": "bye",
    # Amalfi *richiede* l'anti-reincontro (`anti_rematch_required` in
    # STRATEGY_CONSTRAINTS): senza, la creazione viene rifiutata.
    "anti_rematch_enabled": "on",
    "classification_system": "WINS",
    "rounds_count": "3",
    "min_participants": "4",
    "entry_fee": "0",
    "location": "Sala di prova",
    # Un intero significa "quanti tavoli", non "quale tavolo" (parse_tables_input).
    # Senza tavoli le partite restano PENDING e non si possono segnare.
    "available_tables": "8",
    "withdraw_policy": WithdrawPolicy.FORFEIT.value,
}


@dataclass(frozen=True)
class Utente:
    """Le sole tre cose che al driver servono di un utente."""

    id: int
    username: str
    ruolo: str


class GaraDriver:
    """Guida una gara attraverso le route, come farebbe un direttore col mouse."""

    def __init__(self, client: Any) -> None:
        self.client = client
        self.attuale: Utente | None = None

    # ── Allestimento ────────────────────────────────────────────────

    def crea_utente(self, ruolo: str = UserRole.PLAYER.value) -> Utente:
        sigla = uuid.uuid4().hex[:8]
        user = User(
            username=f"{ruolo}_{sigla}",
            email=f"{ruolo}_{sigla}@example.test",
            role=ruolo,
        )
        user.set_password(PASSWORD)
        db.session.add(user)
        db.session.commit()
        return Utente(id=user.id, username=user.username, ruolo=ruolo)

    def crea_giocatori(self, quanti: int) -> list[Utente]:
        return [self.crea_utente(UserRole.PLAYER.value) for _ in range(quanti)]

    # ── Sessione ────────────────────────────────────────────────────

    def entra(self, utente: Utente) -> None:
        """Login vero, col form vero. Fallisce forte se non ha funzionato."""
        risposta = self.client.post(
            "/auth/login",
            data={"username": utente.username, "password": PASSWORD},
            follow_redirects=True,
        )
        assert risposta.status_code == 200, "login non riuscito"
        self.attuale = utente

    def esci(self) -> None:
        self.client.get("/auth/logout", follow_redirects=True)
        self.attuale = None

    # ── Azioni del direttore ────────────────────────────────────────

    def crea_gara(self, **opzioni: Any) -> int:
        """Compila e manda il form di creazione. Restituisce l'id della gara.

        La route risponde con un redirect alla pagina della gara appena creata:
        è da lì che si ricava l'id, esattamente come lo saprebbe il browser.
        Un fallimento di validazione redirige invece al form, e allora l'id non
        c'è — il driver lo dice subito invece di far esplodere il test dieci
        righe più in là.
        """
        dati = dict(FORM_GARA_DEFAULT)
        dati.setdefault("name", f"Gara e2e {uuid.uuid4().hex[:6]}")
        dati.setdefault("date", (date.today() + timedelta(days=7)).isoformat())
        dati.update({chiave: str(valore) for chiave, valore in opzioni.items()})

        risposta = self.client.post("/admin/gara/create_standalone", data=dati)
        assert risposta.status_code == 302, "creazione gara: atteso un redirect"

        trovato = re.search(r"/admin/gara/(\d+)$", risposta.headers["Location"])
        assert trovato, (
            "la creazione è stata rifiutata: la route rimanda al form invece "
            f"che alla gara ({risposta.headers['Location']})"
        )
        return int(trovato.group(1))

    def crea_gara_rifiutata(self, **opzioni: Any) -> str:
        """Come `crea_gara`, ma per i casi in cui il rifiuto è il risultato atteso.

        Restituisce il testo del messaggio mostrato all'utente.
        """
        dati = dict(FORM_GARA_DEFAULT)
        dati.setdefault("name", f"Gara e2e {uuid.uuid4().hex[:6]}")
        dati.setdefault("date", (date.today() + timedelta(days=7)).isoformat())
        dati.update({chiave: str(valore) for chiave, valore in opzioni.items()})

        risposta = self.client.post(
            "/admin/gara/create_standalone", data=dati, follow_redirects=True
        )
        assert risposta.status_code == 200
        return risposta.get_data(as_text=True)

    def apri_iscrizioni(self, gara_id: int, chiusura: date | None = None) -> Any:
        """Apre la finestra di iscrizione.

        Le date arrivano da due `datetime-local`, cioè nell'ora di chi scrive
        (ADR-043): il formato è quello del browser, non l'ISO del DB.

        Di default si chiude il giorno prima della gara. Una `chiusura` oltre
        la data della gara viene accorciata dal service, che lo segnala in
        pagina senza rifiutare l'apertura — comportamento coperto da
        `test_la_finestra_troppo_lunga_viene_accorciata_e_lo_dice`.
        """
        inizio = date.today() - timedelta(days=1)
        fine = chiusura or (self.gara(gara_id).date - timedelta(days=1))
        return self.client.post(
            f"/admin/gara/{gara_id}/open_inscriptions",
            data={
                "inscription_start": f"{inizio.isoformat()}T00:00",
                "inscription_end": f"{fine.isoformat()}T23:59",
            },
            follow_redirects=True,
        )

    def avvia_primo_turno(self, gara_id: int) -> Any:
        return self.client.post(
            f"/admin/gara/{gara_id}/start_first_round", follow_redirects=True
        )

    def avvia_turno(self, gara_id: int, numero: int) -> dict[str, Any]:
        """Avvia un turno successivo al primo.

        Questa route risponde **sempre 200 con un JSON**, anche quando rifiuta:
        l'esito sta in `success`, non nel codice HTTP. Chi asserisce sullo
        status code qui non verifica nulla.
        """
        risposta = self.client.post(f"/admin/gara/{gara_id}/start_round/{numero}")
        assert risposta.status_code == 200
        return risposta.get_json()

    def annulla_primo_turno(self, gara_id: int) -> Any:
        return self.client.post(
            f"/admin/gara/{gara_id}/cancel_first_round", follow_redirects=True
        )

    def termina(self, gara_id: int) -> Any:
        return self.client.post(
            f"/admin/gara/{gara_id}/terminate", follow_redirects=True
        )

    # ── Azioni del giocatore ────────────────────────────────────────

    def iscrivi(self, gara_id: int, utente: Utente) -> Any:
        """Fa il login del giocatore e lo iscrive dal suo pulsante."""
        self.entra(utente)
        return self.client.post(
            f"/player/gara/{gara_id}/inscribe", follow_redirects=True
        )

    def iscrivi_tutti(self, gara_id: int, utenti: Iterable[Utente]) -> None:
        for utente in utenti:
            self.iscrivi(gara_id, utente)

    # ── Punteggio ───────────────────────────────────────────────────

    def aggiungi_rack(self, match_id: int, vincitore_id: int) -> Any:
        """Un rack dal percorso del direttore. Risponde JSON (lo chiama il JS)."""
        return self.client.post(
            f"/admin/match/{match_id}/add_rack", data={"winner_id": str(vincitore_id)}
        )

    def aggiungi_rack_da_giocatore(self, match_id: int, vincitore_id: int) -> Any:
        """Lo stesso rack dal percorso del giocatore: altro endpoint, stesso gesto."""
        return self.client.post(
            f"/player/match/{match_id}/racks/add",
            data={"winner_id": str(vincitore_id)},
        )

    def conferma(self, match_id: int) -> Any:
        """Conferma il risultato da giocatore. Servono entrambe le firme."""
        return self.client.post(f"/player/match/{match_id}/confirm")

    def valida(self, match_id: int) -> Any:
        """Il pulsante «valida» del direttore: chiude la partita d'ufficio.

        Risponde JSON, come tutte le azioni che il JS della pagina gara chiama
        senza ricaricare.
        """
        return self.client.post(f"/admin/match/{match_id}/validate")

    def annulla_ultimo_rack(self, match_id: int, giocatore_id: int) -> Any:
        """Il ripensamento del giocatore sull'ultimo rack segnato.

        È il gesto che separa i due stati finali: dopo la doppia conferma dei
        giocatori si può ancora tornare indietro, dopo la chiusura del
        direttore no.
        """
        return self.client.post(
            f"/player/match/{match_id}/racks/remove",
            data={"player_id": str(giocatore_id)},
        )

    def ritirati(self, match_id: int) -> Any:
        """Forfait del giocatore autenticato: perde, e la partita si chiude."""
        return self.client.post(f"/player/match/{match_id}/forfeit")

    def imposta_risultato(self, match_id: int, punti1: int, punti2: int) -> Any:
        """Risultato secco dal percorso del direttore, senza passare dai rack."""
        return self.client.post(
            f"/admin/match/{match_id}/set_result",
            data={"player1_score": str(punti1), "player2_score": str(punti2)},
            follow_redirects=True,
        )

    def gioca_match(self, match_id: int, vincitore_id: int | None = None) -> int:
        """Segna rack finché la partita non è finita. Restituisce il vincitore.

        Senza `vincitore_id` vince il primo giocatore: a un test che sta
        verificando il *percorso* non interessa chi vince, gli interessa che la
        partita si chiuda e il turno avanzi.

        I due formati chiudono in modi diversi e la sequenza di rack non può
        essere la stessa. Nel race-to basta portare uno dei due al traguardo.
        Nel formato **esattamente N rack** il traguardo non esiste: la partita
        finisce quando i rack giocati sono N, e vince chi ne ha di più — quindi
        si segnano tutti gli N, dando al vincitore la maggioranza. Segnarne N
        di fila allo stesso giocatore chiuderebbe lo stesso, ma su un punteggio
        (N-0) che non distinguerebbe i due formati.
        """
        partita = db.session.get(Match, match_id)
        assert partita is not None, f"partita {match_id} inesistente"
        assert not partita.is_bye, "una partita vs X è già decisa"
        assert not partita.is_trio, "il trio ha route sue (/admin/gara/trio/...)"

        vincitore_id = vincitore_id or partita.player1_id
        assert vincitore_id in (partita.player1_id, partita.player2_id)
        perdente_id = (
            partita.player2_id
            if vincitore_id == partita.player1_id
            else partita.player1_id
        )

        # La sequenza è calcolata su una partita da zero, e resta sufficiente
        # anche se qualche rack è già segnato: in entrambi i formati serve al
        # più un rack per ciascuno di quelli previsti, mai di più. Il `break`
        # sullo stato la interrompe appena la partita è chiusa.
        for segnare_a in self._sequenza_rack(partita, vincitore_id, perdente_id):
            partita = db.session.get(Match, match_id)
            assert partita is not None
            if MatchStatus.is_finished(partita.status):
                break
            risposta = self.aggiungi_rack(match_id, segnare_a)
            assert risposta.status_code == 200, risposta.get_data(as_text=True)

        partita = db.session.get(Match, match_id)
        assert partita is not None
        assert MatchStatus.is_finished(
            partita.status
        ), f"partita {match_id} non si chiude ({partita.status})"

        return vincitore_id

    @staticmethod
    def _sequenza_rack(
        partita: Match, vincitore_id: int, perdente_id: int
    ) -> list[int]:
        """A chi va ciascun rack, nell'ordine in cui si segnano.

        I rack si alternano invece di andare tutti al vincitore: un punteggio
        3-2 su «esattamente 5» è chiuso, mentre su «al 5» non lo è, ed è la
        differenza che rende il test capace di accorgersi se il formato
        configurato non è quello che la partita sta usando davvero.
        """
        distanza = partita.distance_config
        if distanza.is_race_to_racks:
            return [vincitore_id] * distanza.get_winning_racks()

        totali = distanza.racks
        al_vincitore = totali // 2 + 1
        sequenza: list[int] = []
        restano = [al_vincitore, totali - al_vincitore]
        while sum(restano) > 0:
            for indice, giocatore in enumerate((vincitore_id, perdente_id)):
                if restano[indice] > 0:
                    sequenza.append(giocatore)
                    restano[indice] -= 1
        return sequenza

    def gioca_turno(self, gara_id: int, numero: int) -> None:
        """Porta a termine tutte le partite giocabili di un turno."""
        for partita in self.partite(gara_id, turno=numero):
            if partita.is_bye or partita.is_trio:
                continue  # già decise, o con un percorso di segnatura tutto suo
            if MatchStatus.is_finished(partita.status):
                continue
            self.gioca_match(partita.id)

    # ── Osservazioni ────────────────────────────────────────────────

    def pagina_gara(self, gara_id: int) -> str:
        """L'HTML della pagina gara, come lo riceverebbe il browser."""
        risposta = self.client.get(f"/admin/gara/{gara_id}")
        assert risposta.status_code == 200, f"pagina gara: {risposta.status_code}"
        return risposta.get_data(as_text=True)

    def partite_nella_pagina(self, gara_id: int) -> set[int]:
        """Gli id delle partite *visibili* nella pagina, letti dai suoi link.

        È la controparte dell'occhio umano: se una partita esiste sul DB ma la
        pagina non la mostra, questo insieme non la contiene — ed è quasi sempre
        il bug che si stava cercando.
        """
        html = self.pagina_gara(gara_id)
        return {int(x) for x in re.findall(r"/admin/match/(\d+)", html)}

    def gara(self, gara_id: int) -> Gara:
        gara = db.session.get(Gara, gara_id)
        assert gara is not None, f"gara {gara_id} inesistente"
        db.session.refresh(gara)
        return gara

    def partite(self, gara_id: int, turno: int | None = None) -> list[Match]:
        query = Match.query.filter_by(gara_id=gara_id)
        if turno is not None:
            query = query.filter_by(round_number=turno)
        return query.order_by(Match.round_number, Match.id).all()

    def turni_creati(self, gara_id: int) -> set[int]:
        return {partita.round_number for partita in self.partite(gara_id)}


def partecipanti(partite: Sequence[Match]) -> list[int]:
    """Tutti gli id che scendono in campo in queste partite, con le ripetizioni.

    Le ripetizioni sono il punto: se un giocatore compare due volte nello stesso
    turno il sorteggio è rotto, e contare le occorrenze è il solo modo per
    accorgersene senza sapere in anticipo chi incontra chi.
    """
    ids: list[int] = []
    for partita in partite:
        for giocatore in (partita.player1_id, partita.player2_id):
            if giocatore:
                ids.append(giocatore)
    return ids
