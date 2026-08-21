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

    # ── Il referto TPA (ADR-044) ────────────────────────────────────

    def pagina_referto(self, match_id: int) -> Any:
        """La pagina del referto. Restituisce la **risposta**, non l'HTML.

        Qui il codice di stato è parte di quello che si osserva: chi non ha
        sbloccato la funzione e non ha un referto da guardare prende 403, e
        quel 403 è un fatto della journey quanto il testo della pagina.
        """
        return self.client.get(f"/match/matches/{match_id}/tpa")

    def html_referto(self, match_id: int) -> str:
        risposta = self.pagina_referto(match_id)
        assert risposta.status_code == 200, risposta.status_code
        return risposta.get_data(as_text=True)

    def apri_referto(self, match_id: int) -> Any:
        return self.client.post(f"/match/matches/{match_id}/tpa/open")

    def prendi_referto(self, match_id: int) -> None:
        """Apertura riuscita. Fallisce forte se il referto non c'è."""
        risposta = self.apri_referto(match_id)
        assert risposta.status_code in (200, 302), risposta.status_code
        assert self.referto(match_id) is not None, "il referto non è stato aperto"

    def premi(self, match_id: int, comando: str) -> Any:
        return self.client.post(
            f"/match/matches/{match_id}/tpa/press", json={"command": comando}
        )

    def premi_tutti(self, match_id: int, *comandi: str) -> Any:
        risposta = None
        for comando in comandi:
            risposta = self.premi(match_id, comando)
            assert risposta.status_code == 200, (
                f"comando {comando!r} rifiutato: "
                f"{risposta.get_data(as_text=True)[:200]}"
            )
        return risposta

    def vinci_rack_nel_referto(self, match_id: int, posto: int) -> Any:
        """Spacca imbucando tutto: un rack chiuso in un turno solo.

        Le bilie del rack le dice il referto (`game_type`), non il test: a
        palla 8 sono otto, a palla 9 nove, e un «9» annotato su un rack da
        otto è un comando che il tastierino non proponeva — quindi rifiutato.

        Il posto si dichiara ogni volta perché a rack finito il motore mette
        in spaccata l'avversario (spaccata alternata): senza `seat:` si
        annoterebbe il rack dell'altro.
        """
        referto = self.referto(match_id)
        assert referto is not None, "nessun referto aperto su questo match"
        tutte = str(referto.game_type)
        return self.premi_tutti(match_id, f"seat:{posto}", "1", tutte, "end")

    def annulla_tocco(self, match_id: int) -> Any:
        return self.client.post(f"/match/matches/{match_id}/tpa/undo")

    def stato_referto(self, match_id: int) -> Any:
        return self.client.get(f"/match/matches/{match_id}/tpa/state")

    def chiudi_referto(self, match_id: int) -> Any:
        return self.client.post(f"/match/matches/{match_id}/tpa/close")

    def referto(self, match_id: int) -> Any:
        """Il referto di questo match dal DB, o `None` se non ce n'è uno."""
        from models.tpa.models import TpaReferto

        db.session.expire_all()
        return TpaReferto.query.filter_by(individual_match_id=match_id).first()

    # ── Quello che arriva a chi non stava guardando ─────────────────

    def pagina_notifiche(self) -> str:
        """L'elenco delle notifiche di chi è entrato adesso."""
        risposta = self.client.get("/player/notifications")
        assert risposta.status_code == 200, risposta.status_code
        return risposta.get_data(as_text=True)

    def notifiche(self, giocatore: Giocatore) -> list[Any]:
        """Le notifiche di un giocatore, dal DB.

        La pagina dice cosa legge; questa dice **quante** ne sono partite —
        che è la domanda opposta e altrettanto importante: una notifica per
        triangolo renderebbe illeggibile tutta la casella.
        """
        from models.notification.models import Notification

        db.session.expire_all()
        return Notification.query.filter_by(user_id=giocatore.id).all()

    # ── Dichiararsi disponibile, e farsi trovare ────────────────────

    def crea_sala(self, nome: str | None = None, **campi: Any) -> int:
        """Una sala biliardo. Allestimento, non azione.

        Le sale le censisce l'amministrazione, che è un altro dominio e ha i
        suoi test: qui è lo scenario, come lo sono i giocatori.
        """
        from models.location.models import BilliardHall

        sala = BilliardHall(
            name=nome or f"Sala {uuid.uuid4().hex[:6]}",
            city=campi.pop("city", "Udine"),
            is_active=campi.pop("is_active", True),
            verified=campi.pop("verified", True),
            **campi,
        )
        db.session.add(sala)
        db.session.commit()
        return sala.id

    def pagina_disponibilita(self) -> str:
        risposta = self.client.get("/match/availability")
        assert risposta.status_code == 200, risposta.status_code
        return risposta.get_data(as_text=True)

    def dichiarati_disponibile(self, sala_id: int, **campi: Any) -> Any:
        modulo: dict[str, Any] = {"venue_id": str(sala_id), "is_available": "true"}
        modulo.update(campi)
        return self.client.post("/match/availability/venue", data=modulo)

    def togli_disponibilita(self, disponibilita_id: int) -> Any:
        return self.client.post(f"/match/availability/venue/{disponibilita_id}/remove")

    def mie_disponibilita(self, giocatore: Giocatore) -> list[Any]:
        from models.location.models import UserLocationAvailability

        db.session.expire_all()
        return UserLocationAvailability.query.filter_by(user_id=giocatore.id).all()

    @staticmethod
    def trovati(pagina: str) -> list[int]:
        """Gli id dei giocatori elencati nella pagina di scoperta.

        Si leggono dall'`action` del modulo di richiesta, non dal nome: il
        nome di chi è entrato compare comunque nella barra laterale, quindi
        cercarlo nel testo risponde sempre di sì — anche a chi non è
        nell'elenco.
        """
        import re

        return [
            int(x)
            for x in re.findall(r"/match/availability/request-match/(\d+)", pagina)
        ]

    def pagina_scoperta(self, **query: Any) -> str:
        risposta = self.client.get("/match/availability/discover", query_string=query)
        assert risposta.status_code == 200, risposta.status_code
        return risposta.get_data(as_text=True)

    def chiedi_partita(self, destinatario: Giocatore, **campi: Any) -> Any:
        """La richiesta che parte dalla scoperta: diventa una proposta diretta."""
        modulo: dict[str, Any] = {"location": "Sala di prova"}
        modulo.update(campi)
        return self.client.post(
            f"/match/availability/request-match/{destinatario.id}", data=modulo
        )

    def imposta_fuso(self, nome: str) -> Any:
        """Il fuso del lettore, dedotto dal browser e salvato (ADR-043)."""
        return self.client.post("/auth/timezone", json={"timezone": nome})

    def ultima_proposta(self) -> Any:
        from models.individual_match.models import MatchProposal

        db.session.expire_all()
        return MatchProposal.query.order_by(MatchProposal.id.desc()).first()

    # ── Le tre sparse ───────────────────────────────────────────────

    def crea_admin(self) -> Giocatore:
        """Un amministratore. Serve solo per il quadro d'insieme."""
        sigla = uuid.uuid4().hex[:8]
        user = User(
            username=f"admin_{sigla}",
            email=f"admin_{sigla}@example.test",
            role=UserRole.ADMIN.value,
        )
        user.set_password(PASSWORD)
        db.session.add(user)
        db.session.commit()
        return Giocatore(id=user.id, username=user.username, ruolo=user.role)

    def pagina_statistiche(self) -> str:
        risposta = self.client.get("/match/statistics")
        assert risposta.status_code == 200, risposta.status_code
        return risposta.get_data(as_text=True)

    def statistiche(self) -> dict[str, Any]:
        """Gli stessi numeri della pagina, in forma leggibile da un test.

        Stessa route e stessa funzione: `user_statistics` risponde in JSON a
        chi lo chiede. Non è una scorciatoia sul servizio.
        """
        risposta = self.client.get(
            "/match/statistics", headers={"Content-Type": "application/json"}
        )
        assert risposta.status_code == 200, risposta.status_code
        return risposta.get_json()["statistics"]

    def chiudi_unilateralmente(self, match_id: int, vincitore: Giocatore) -> Any:
        """La chiusura d'ufficio (route storica `/complete`)."""
        return self.client.post(
            f"/match/matches/{match_id}/complete", json={"winner_id": vincitore.id}
        )

    def aggiorna_orari(self, match_id: int, **campi: Any) -> Any:
        return self.client.post(f"/match/matches/{match_id}/update-times", json=campi)

    def pagina_quadro_admin(self) -> Any:
        return self.client.get("/match/admin/overview")
