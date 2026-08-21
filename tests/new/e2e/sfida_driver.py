"""Driver HTTP per i test end-to-end delle sfide individuali.

Stessa disciplina del ``GaraDriver``: **solo route**, mai un service. Se una
cosa non si può fare passando dalle stesse richieste che farebbe un browser,
il test non la fa — e il fatto che non si possa è già un'informazione.

Le sfide individuali hanno due strade per cominciare, e sono diverse per
natura:

* la **proposta**, per accordarsi su una partita futura: si compila, l'altro
  accetta, qualcuno avvia;
* l'**avvio rapido** (ADR-051), per due che sono già in sala: la partita nasce
  in corso, e l'accettazione si sposta alla doppia conferma finale.

Il driver le offre tutt'e due, perché è proprio nel confronto fra le due che
si vedono le differenze che contano.

Le osservazioni guardano **prima l'HTML** e poi il DB: la pagina dice quello
che il giocatore vede davvero, il DB dice se il fatto è stato registrato. Una
sola delle due lascia scoperta metà della domanda — è esattamente così che è
passato inosservato il «Termina la sfida» che non dava alcun segno di aver
funzionato.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from models import db
from models.base import utc_now
from models.individual_match.models import IndividualMatch
from models.status_enum import Discipline, MatchStatus
from models.user.models import User
from models.user.role_enum import UserRole

PASSWORD = "e2e-secret-123"


@dataclass(frozen=True)
class Giocatore:
    """Le sole tre cose che al driver servono di un giocatore."""

    id: int
    username: str
    ruolo: str


class SfidaDriver:
    """Guida una sfida individuale attraverso le route, come chi gioca."""

    def __init__(self, client: Any) -> None:
        self.client = client
        self.attuale: Giocatore | None = None

    # ── Allestimento ────────────────────────────────────────────────

    def crea_giocatore(self, sbloccato: bool = True) -> Giocatore:
        """Un giocatore che ha già sbloccato le sfide individuali.

        `gamification_override` e non un livello finto: il gate
        (`can_access("create_match_direct")`) è quello vero, e qui non è la
        cosa in prova. Ha i suoi test.
        """
        sigla = uuid.uuid4().hex[:8]
        user = User(
            username=f"sfidante_{sigla}",
            email=f"sfidante_{sigla}@example.test",
            role=UserRole.PLAYER.value,
            gamification_override=sbloccato,
        )
        user.set_password(PASSWORD)
        db.session.add(user)
        db.session.commit()
        return Giocatore(id=user.id, username=user.username, ruolo=user.role)

    def crea_giocatori(self, quanti: int) -> list[Giocatore]:
        return [self.crea_giocatore() for _ in range(quanti)]

    # ── Sessione ────────────────────────────────────────────────────

    def entra(self, giocatore: Giocatore) -> None:
        """Login vero, col form vero. Fallisce forte se non ha funzionato."""
        risposta = self.client.post(
            "/auth/login",
            data={"username": giocatore.username, "password": PASSWORD},
            follow_redirects=True,
        )
        assert risposta.status_code == 200, "login non riuscito"
        self.attuale = giocatore

    def esci(self) -> None:
        self.client.get("/auth/logout", follow_redirects=True)
        self.attuale = None

    # ── Cominciare a giocare ────────────────────────────────────────

    def avvio_rapido(self, avversario: Giocatore, **opzioni: Any) -> Any:
        """La partita che comincia adesso (ADR-051). Restituisce la risposta.

        Le opzioni sono quelle del modulo: `match_format`, `distance`,
        `discipline`, `location`… Quelle non passate le sceglie il servizio
        dalle abitudini del giocatore.
        """
        dati: dict[str, Any] = {"opponent_id": avversario.id}
        dati.update(opzioni)
        return self.client.post("/match/quick", json=dati)

    def apri_partita(self, avversario: Giocatore, **opzioni: Any) -> int:
        """Avvio rapido riuscito: restituisce l'id della partita."""
        risposta = self.avvio_rapido(avversario, **opzioni)
        assert risposta.status_code == 200, risposta.get_data(as_text=True)[:400]
        return risposta.get_json()["match_id"]

    def proponi(self, invitati: list[Giocatore], **opzioni: Any) -> int:
        """Una proposta diretta, dal modulo vero. Restituisce l'id."""
        # Il campo `datetime-local` arriva nell'**ora di chi scrive** e viene
        # convertito in UTC (ADR-043): un orario a tre ore da adesso, scritto
        # come se fosse locale, in agosto torna indietro di due e la proposta
        # nasce già scaduta (`expires_at` = orario meno un'ora). Un giorno
        # avanti toglie di mezzo la questione, che qui non è in prova.
        quando = utc_now() + timedelta(days=1)
        modulo: dict[str, Any] = {
            "proposal_type": "direct",
            "invited_user_ids": [str(g.id) for g in invitati],
            "scheduled_at": quando.strftime("%Y-%m-%dT%H:%M"),
            "expires_hours": "1",
            "location": "Sala di prova",
            "discipline": Discipline.NINE_BALL.value,
            "match_format": "single",
            "distance": "5",
            "is_race_to": "true",
            "break_rule": "alternate",
        }
        modulo.update(opzioni)
        risposta = self.client.post("/match/proposals/create", data=modulo)
        assert risposta.status_code in (200, 302), risposta.status_code
        from models.individual_match.models import MatchProposal

        proposta = MatchProposal.query.order_by(MatchProposal.id.desc()).first()
        assert proposta is not None, "la proposta non è stata creata"
        return proposta.id

    def rifiuta_proposta(self, proposta_id: int) -> Any:
        return self.client.post(f"/match/proposals/{proposta_id}/decline", json={})

    def annulla_proposta(self, proposta_id: int) -> Any:
        return self.client.post(f"/match/proposals/{proposta_id}/cancel", json={})

    def accetta_proposta(self, proposta_id: int) -> int:
        risposta = self.client.post(f"/match/proposals/{proposta_id}/accept", json={})
        assert risposta.status_code == 200, risposta.get_data(as_text=True)[:400]
        return risposta.get_json()["match_id"]

    def avvia(self, match_id: int) -> Any:
        return self.client.post(f"/match/matches/{match_id}/start", json={})

    # ── Segnare ─────────────────────────────────────────────────────

    def segna(self, match_id: int, vincitore: Giocatore) -> Any:
        return self.client.post(
            f"/match/matches/{match_id}/racks/add", json={"winner_id": vincitore.id}
        )

    def segna_piu_volte(self, match_id: int, vincitore: Giocatore, quanti: int) -> None:
        for _ in range(quanti):
            risposta = self.segna(match_id, vincitore)
            assert risposta.status_code == 200, risposta.get_data(as_text=True)[:200]

    def inizia_set_successivo(self, match_id: int) -> Any:
        """Il set dopo, in una sfida al meglio dei set."""
        return self.client.post(f"/match/matches/{match_id}/sets/next", json={})

    def togli_ultimo(self, match_id: int, giocatore: Giocatore) -> Any:
        return self.client.post(
            f"/match/matches/{match_id}/racks/remove", json={"player_id": giocatore.id}
        )

    # ── Chiudere ────────────────────────────────────────────────────

    def conferma(self, match_id: int) -> Any:
        """La firma sul risultato. Ne servono due: è l'accettazione (ADR-051)."""
        return self.client.post(f"/match/matches/{match_id}/confirm", json={})

    def rifiuta(self, match_id: int) -> Any:
        return self.client.post(f"/match/matches/{match_id}/reject", json={})

    def forfait(self, match_id: int) -> Any:
        return self.client.post(f"/match/matches/{match_id}/forfeit", json={})

    def annulla(self, match_id: int) -> Any:
        return self.client.post(f"/match/matches/{match_id}/cancel", json={})

    # ── Osservazioni: prima la pagina ───────────────────────────────

    def pagina(self, match_id: int) -> str:
        """L'HTML della partita, come lo vede chi è entrato adesso."""
        risposta = self.client.get(f"/match/matches/{match_id}")
        assert risposta.status_code == 200, risposta.status_code
        return risposta.get_data(as_text=True)

    def pagina_elenco(self) -> str:
        risposta = self.client.get("/match/matches")
        assert risposta.status_code == 200
        return risposta.get_data(as_text=True)

    def pagina_avvio_rapido(self, **query: Any) -> str:
        risposta = self.client.get("/match/quick", query_string=query)
        assert risposta.status_code == 200
        return risposta.get_data(as_text=True)

    # ── Osservazioni: poi il dato ───────────────────────────────────

    def partita(self, match_id: int) -> IndividualMatch:
        db.session.expire_all()
        partita = db.session.get(IndividualMatch, match_id)
        assert partita is not None, f"partita {match_id} inesistente"
        return partita

    def stato(self, match_id: int) -> MatchStatus:
        return self.partita(match_id).status

    def punteggio(self, match_id: int) -> tuple[int, int]:
        partita = self.partita(match_id)
        return (partita.player1_score or 0, partita.player2_score or 0)

    def quante_partite(self) -> int:
        return IndividualMatch.query.count()

    def set_giocati(self, match_id: int) -> int:
        return len(self.partita(match_id).sets or [])

    def rating_globale(self, giocatore: Giocatore) -> float | None:
        """L'Elo globale, se il giocatore ne ha uno.

        Serve a verificare il patto di ADR-051: la partita aperta senza
        accettazione non muove niente finché non la riconoscono in due.
        """
        from models.rating.models import PlayerRating, RatingSystem

        riga = PlayerRating.query.filter_by(
            user_id=giocatore.id, rating_system=RatingSystem.ELO_GLOBAL
        ).first()
        return riga.rating_value if riga else None
