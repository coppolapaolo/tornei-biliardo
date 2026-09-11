"""La simulazione dei risultati (ADR-058, tappa 2).

Tre azioni — **una partita**, **il turno**, **tutta la gara** — con cui il
direttore di una prova fa andare avanti la gara senza giocatori veri. Nascono
dal trasloco delle azioni di debug di `routes/main.py` (`/debug/complete_*`),
che oggi chiamano questo servizio: una sola implementazione.

Due scelte di progetto, dalla specifica
(`docs/usecases/competizione-di-prova.md`):

* **La simulazione è sottile.** Ogni rack passa da
  `ScoringService.add_rack_for_player` con l'id del fittizio che lo segna —
  lo stesso servizio della route del giocatore — e ogni conferma da
  `MatchService.confirm_match_result`. Non si scrive `player1_score` a mano:
  i rack esistono davvero sul tabellino, con chi apre e chi ha segnato, e
  il segnapunti vero resta usabile dopo. Se quei servizi cambiano firma, la
  simulazione fallisce forte invece di divergere in silenzio.
* **Le partite si chiudono in entrambi i modi.** Il direttore deve imparare
  sia la chiusura dai giocatori sia la propria: le partite con **id pari**
  finiscono con la doppia conferma (`CONFIRMED_BY_BOTH`), quelle con **id
  dispari** restano a distanza raggiunta con la firma del solo vincitore, in
  attesa che lui le validi dal segnapunti. «Simula tutta la gara» chiude
  tutto, validando le dispari come farebbe lui
  (`MatchValidationService.validate_and_complete`). La parità è
  deterministica come in `seed_demo.py`, così due direttori vedono la stessa
  cosa.

I punteggi rispettano la distanza **effettiva** del turno (ADR-027:
`match.distance_config`), e in «esattamente N» con N pari il pareggio esiste,
come nella realtà.

Il servizio lavora dentro `prova_visibili()`: lo chiamano route già
autorizzate (chi dirige la prova, o il footer di debug su una gara vera).
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Protocol

from models.base import db
from models.exceptions import ConflictError

from .visibility import prova_visibili

logger = logging.getLogger(__name__)

#: Le tre azioni della route (`simula_<azione>`): una partita, il turno, la gara.
AZIONI_SIMULAZIONE = ("partita", "turno", "gara")


class Sorteggio(Protocol):
    """Quel che serve del generatore casuale: iniettabile nei test."""

    def randint(self, a: int, b: int) -> int: ...

    def choice(self, seq: Any) -> Any: ...


@dataclass(frozen=True)
class EsitoSimulazione:
    """Cosa ha fatto una simulazione, per il messaggio all'utente."""

    #: Partite portate a un risultato, in uno dei due modi.
    partite_chiuse: int = 0
    #: Il turno su cui si è lavorato (None: niente da fare).
    turno: Optional[int] = None
    #: Tavoli passati alle partite in attesa dopo la simulazione.
    tavoli_riassegnati: int = 0
    #: Turni avviati da «simula tutta la gara» (strategie a turni on-demand).
    turni_avviati: int = 0
    #: La partita simulata da «simula una partita».
    partita_id: Optional[int] = None
    #: Perché «simula tutta la gara» si è fermata prima della fine, se lo ha fatto.
    fermata: Optional[str] = None


class SimulationService:
    """Simula i risultati di una gara chiamando i servizi veri."""

    # ------------------------------------------------------------- regola

    @staticmethod
    def chiusa_dai_giocatori(match: Any) -> bool:
        """Chi chiude questa partita: i due giocatori (id pari) o il direttore.

        Deterministico sull'id, come `seed_demo.py`: il direttore che ripete
        la prova ritrova le stesse partite da validare.
        """
        return match.id % 2 == 0

    # ------------------------------------------------------------ azioni

    @staticmethod
    def simula_partita(
        gara_id: int, rng: Optional[Sorteggio] = None, *, chiudi_tutto: bool = False
    ) -> EsitoSimulazione:
        """Chiude **una** partita, scelta fra quelle al tavolo.

        Le partite già a distanza raggiunta — in attesa del direttore — non
        vengono ripescate: validarle è il suo compito. `chiudi_tutto` chiude
        anche le dispari: è quel che vuole il footer di debug, che serve a far
        avanzare una gara e non a insegnare niente.
        """
        rng = rng or random
        with prova_visibili():
            gara = SimulationService._gara_avviata(gara_id)
            candidate = SimulationService.partite_simulabili(gara.id)
            if not candidate:
                return EsitoSimulazione()
            scelta = rng.choice(candidate)
            chiusa = SimulationService._simula(
                scelta, chiudi_tutto=chiudi_tutto, rng=rng
            )
            SimulationService._avanza(gara.id)
            tavoli = SimulationService._rilascia_tavoli_e_riassegna([scelta], gara.id)
            return EsitoSimulazione(
                partite_chiuse=int(chiusa),
                turno=scelta.round_number,
                tavoli_riassegnati=tavoli,
                partita_id=scelta.id,
            )

    @staticmethod
    def simula_turno(
        gara_id: int, rng: Optional[Sorteggio] = None, *, chiudi_tutto: bool = False
    ) -> EsitoSimulazione:
        """Chiude tutte le partite del primo turno con partite ancora aperte.

        Le dispari restano da validare: finché il direttore non lo fa, il
        turno non risulta concluso — è la stessa cosa che gli succederebbe
        con giocatori veri che non passano dal suo tavolo.
        """
        rng = rng or random
        with prova_visibili():
            gara = SimulationService._gara_avviata(gara_id)
            turno = SimulationService.primo_turno_attivo(gara.id)
            if turno is None:
                return EsitoSimulazione()
            partite = SimulationService.partite_incomplete_del_turno(gara.id, turno)
            chiuse = sum(
                1
                for m in partite
                if SimulationService._simula(m, chiudi_tutto=chiudi_tutto, rng=rng)
            )
            SimulationService._avanza(gara.id)
            tavoli = SimulationService._rilascia_tavoli_e_riassegna(partite, gara.id)
            return EsitoSimulazione(
                partite_chiuse=chiuse, turno=turno, tavoli_riassegnati=tavoli
            )

    @staticmethod
    def simula_gara(gara_id: int, rng: Optional[Sorteggio] = None) -> EsitoSimulazione:
        """Porta la gara in fondo: chiude tutto, avvia i turni che mancano.

        Per ogni giro: chiude le partite del primo turno attivo (le dispari
        validate come dal direttore), aggiorna la progressione, riassegna i
        tavoli; senza partite attive avvia il turno successivo, per le
        strategie che lo generano a richiesta (Amalfi). Le azioni di chiusura
        della gara — spareggi, «termina» — restano al direttore: sono le
        schermate che deve imparare.
        """
        rng = rng or random
        with prova_visibili():
            gara = SimulationService._gara_avviata(gara_id)
            from models.competition.round_service import RoundService
            from models.status_enum import GaraStatus

            chiuse = 0
            turni_avviati = 0
            fermata: Optional[str] = None
            ultimo_turno: Optional[int] = None
            # Un limite di sicurezza contro un turno che non si chiude mai.
            for _ in range((gara.rounds_count or 1) + 5):
                db.session.refresh(gara)
                if gara.status == GaraStatus.COMPLETED.value:
                    break

                turno = SimulationService.primo_turno_attivo(gara.id)
                if turno is not None:
                    ultimo_turno = turno
                    partite = SimulationService.partite_incomplete_del_turno(
                        gara.id, turno
                    )
                    chiuse += sum(
                        1
                        for m in partite
                        if SimulationService._simula(m, chiudi_tutto=True, rng=rng)
                    )
                    SimulationService._avanza(gara.id)
                    SimulationService._rilascia_tavoli_e_riassegna(partite, gara.id)
                    continue

                # Nessuna partita attiva: o la gara è finita, o la strategia
                # genera i turni a richiesta e va avviato il prossimo.
                if gara.current_round >= (gara.rounds_count or 0):
                    break
                prossimo = gara.current_round + 1
                try:
                    RoundService.start_next_round(gara.id, prossimo)
                    turni_avviati += 1
                except Exception as errore:  # noqa: BLE001 — l'errore va in pagina
                    fermata = (
                        f"al turno {gara.current_round}: impossibile avviare "
                        f"il turno {prossimo} ({errore})"
                    )
                    logger.warning(
                        "Simulazione della gara %s fermata %s", gara.id, fermata
                    )
                    break

            return EsitoSimulazione(
                partite_chiuse=chiuse,
                turno=ultimo_turno,
                turni_avviati=turni_avviati,
                fermata=fermata,
            )

    # ------------------------------------------------------------ playoff

    @staticmethod
    def rispondi_invito(qualification_id: int, *, accetta: bool) -> Optional[Any]:
        """Il fittizio accetta o rifiuta l'invito ai playoff.

        Passa dai servizi della route del giocatore — `confirm_qualification`
        e `decline_qualification` — con l'id del fittizio, e senza
        `responded_by_id`: è lui che risponde, non il direttore per suo
        conto. Sul rifiuto torna il sostituto trovato (SPECIFICHE.md, «primo
        degli esclusi»), come farebbe la route.
        """
        from models.exceptions import NotFoundError, ValidationError
        from models.playoff.models import PlayoffQualification, QualificationStatus
        from models.playoff.services import PlayoffService

        with prova_visibili():
            invito = db.session.get(PlayoffQualification, qualification_id)
            if invito is None:
                raise NotFoundError("Invito non trovato")
            if invito.user is None or not invito.user.is_fittizio:
                raise ValidationError(
                    "Qui si risponde solo per i giocatori fittizi: gli altri "
                    "rispondono da soli"
                )
            if invito.status != QualificationStatus.PENDING:
                raise ConflictError("Questo invito ha già una risposta")
            if accetta:
                PlayoffService.confirm_qualification(invito.id, invito.user_id)
                return None
            return PlayoffService.decline_qualification(invito.id, invito.user_id)

    @staticmethod
    def accetta_tutti_gli_inviti(campionato_id: int) -> int:
        """Accetta ogni invito ancora in attesa dei fittizi. Restituisce quanti.

        Uno alla volta, con `rispondi_invito`: ogni accettazione è la stessa
        transazione che farebbe il giocatore.
        """
        from models.playoff.models import (
            PlayoffConfiguration,
            PlayoffQualification,
            QualificationStatus,
        )
        from models.user.models import User

        with prova_visibili():
            in_attesa = (
                db.session.query(PlayoffQualification.id)
                .join(
                    PlayoffConfiguration,
                    PlayoffConfiguration.id == PlayoffQualification.configuration_id,
                )
                .join(User, User.id == PlayoffQualification.user_id)
                .filter(
                    PlayoffConfiguration.campionato_id == campionato_id,
                    PlayoffConfiguration.is_active.is_(True),
                    PlayoffQualification.status == QualificationStatus.PENDING,
                    User.is_fittizio.is_(True),
                )
                .order_by(PlayoffQualification.id)
                .all()
            )
            for (invito_id,) in in_attesa:
                SimulationService.rispondi_invito(invito_id, accetta=True)
            return len(in_attesa)

    # ------------------------------------------------------------ letture

    @staticmethod
    def _gara_avviata(gara_id: int) -> Any:
        from models.competition.models import Gara

        gara = db.session.get(Gara, gara_id)
        if gara is None:
            from models.exceptions import NotFoundError

            raise NotFoundError("Gara non trovata")
        if not gara.current_round:
            raise ConflictError("La gara non è ancora iniziata")
        return gara

    @staticmethod
    def partite_al_tavolo(gara_id: int) -> List[Any]:
        """Le partite «al tavolo»: in corso e con un tavolo assegnato.

        Una partita senza tavolo è in attesa che uno si liberi e non è ancora
        al tavolo: chiuderla salterebbe la fase di gioco. In questo dominio
        tavolo e stato PLAYING sono accoppiati (`assign_available_tables`),
        ma si filtra su entrambi per dire l'intento.
        """
        from models.match.models import Match
        from models.status_enum import MatchStatus

        return (
            Match.query.filter_by(gara_id=gara_id, status=MatchStatus.PLAYING.value)
            .filter(Match.is_bye == False)  # noqa: E712
            .filter(Match.table_assignment.isnot(None))
            .order_by(Match.round_number, Match.id)
            .all()
        )

    @staticmethod
    def partite_simulabili(gara_id: int) -> List[Any]:
        """Le partite fra cui «simula una partita» sceglie.

        Quelle al tavolo, se la gara ha tavoli: una partita senza tavolo sta
        aspettando il suo turno, e chiuderla salterebbe la fase di gioco.
        Senza tavoli configurati non esiste un «al tavolo» — le partite
        restano PENDING per sempre — e si pesca dal primo turno con partite
        aperte. In entrambi i casi restano fuori le partite già a distanza
        raggiunta: sono in attesa del direttore.
        """
        from models.competition.models import Gara

        candidate = [
            m
            for m in SimulationService.partite_al_tavolo(gara_id)
            if not m.is_at_distance
        ]
        if candidate:
            return candidate
        gara = db.session.get(Gara, gara_id)
        if gara is None or gara.get_available_tables():
            # Con i tavoli configurati, chi non ne ha uno sta aspettando.
            return []
        turno = SimulationService.primo_turno_attivo(gara_id)
        if turno is None:
            return []
        return [
            m
            for m in SimulationService.partite_incomplete_del_turno(gara_id, turno)
            if not m.is_bye and not m.is_at_distance
        ]

    @staticmethod
    def partite_incomplete(gara_id: int) -> List[Any]:
        """Tutte le partite ancora aperte, per turno e poi per id."""
        from models.match.models import Match
        from models.status_enum import MatchStatus

        return (
            Match.query.filter_by(gara_id=gara_id)
            .filter(
                Match.status.in_([MatchStatus.PENDING.value, MatchStatus.PLAYING.value])
            )
            .order_by(Match.round_number, Match.id)
            .all()
        )

    @staticmethod
    def partite_incomplete_del_turno(gara_id: int, turno: int) -> List[Any]:
        return [
            m
            for m in SimulationService.partite_incomplete(gara_id)
            if m.round_number == turno
        ]

    @staticmethod
    def primo_turno_attivo(gara_id: int) -> Optional[int]:
        """Il primo turno con almeno una partita aperta.

        Non `gara.current_round`: per le strategie che generano tutti i turni
        all'avvio (casuale, girone) quel numero resta indietro finché il turno
        precedente non è chiuso del tutto, mentre i turni successivi hanno già
        partite in corso.
        """
        partite = SimulationService.partite_incomplete(gara_id)
        return partite[0].round_number if partite else None

    # ------------------------------------------------------ una partita

    @staticmethod
    def _simula(match: Any, *, chiudi_tutto: bool, rng: Sorteggio) -> bool:
        """Porta `match` a un risultato. True se ha fatto qualcosa.

        `chiudi_tutto`: anche le dispari vengono chiuse, validate come dal
        direttore. Altrimenti restano a distanza raggiunta, in attesa.
        """
        if match.is_bye:
            return False
        if match.is_trio:
            return SimulationService._simula_trio(match, rng)
        if match.is_multi_set:
            return SimulationService._chiudi_multi_set(match, rng)
        return SimulationService._gioca_a_rack(
            match, chiudi_tutto=chiudi_tutto, rng=rng
        )

    @staticmethod
    def _gioca_a_rack(match: Any, *, chiudi_tutto: bool, rng: Sorteggio) -> bool:
        """Segna i rack uno a uno dal servizio del giocatore, poi chiude.

        Chi segna ogni rack è chi lo ha vinto: al rack decisivo il servizio
        firma da solo il vincitore, e la partita resta con **una** firma —
        quella che il direttore vede sul segnapunti come «in attesa». Per le
        pari si aggiunge la seconda firma con `confirm_match_result`, come
        farebbe l'altro giocatore.

        Una partita già aperta a mano prosegue da dov'era: il ciclo si ferma
        appena la distanza è raggiunta, quindi il punteggio simulato non può
        sforare quello che il segnapunti accetterebbe.
        """
        from models.match.match_service import MatchService
        from models.match.models import Match
        from models.match.scoring_service import ScoringService
        from models.match.validation_service import MatchValidationService
        from models.status_enum import MatchStatus

        if MatchStatus.is_finished(match.status):
            return False

        # «Chiusa» solo se qui è successo qualcosa: una dispari già a distanza
        # e in attesa del direttore, ripescata da «simula il turno», non va
        # contata di nuovo — altrimenti il messaggio dice partite simulate
        # che non lo sono state.
        fatto = False
        match_id = match.id
        for chi in SimulationService._sequenza_rack(match, rng):
            corrente = db.session.get(Match, match_id)
            if corrente is None or corrente.is_at_distance:
                break
            ScoringService.add_rack_for_player(match_id, user_id=chi, winner_id=chi)
            fatto = True

        corrente = db.session.get(Match, match_id)
        if corrente is None or not corrente.is_at_distance:
            return False

        if SimulationService.chiusa_dai_giocatori(corrente):
            for giocatore in (corrente.player1_id, corrente.player2_id):
                corrente = db.session.get(Match, match_id)
                if corrente is None or MatchStatus.is_finished(corrente.status):
                    break
                firmato = (
                    corrente.player1_confirmed
                    if giocatore == corrente.player1_id
                    else corrente.player2_confirmed
                )
                if not firmato:
                    MatchService.confirm_match_result(match_id, giocatore)
                    fatto = True
        elif chiudi_tutto:
            MatchValidationService.validate_and_complete(match_id)
            fatto = True
        return fatto

    @staticmethod
    def _sequenza_rack(match: Any, rng: Sorteggio) -> List[int]:
        """A chi va ciascun rack, nell'ordine in cui si segnano.

        Il punteggio rispetta la distanza effettiva del turno (ADR-027): nella
        corsa a N il vincitore arriva a N e l'altro sotto; in «esattamente N»
        si giocano tutti gli N rack, e con N pari la metà esatta è un
        pareggio. Si alterna partendo da chi ne vince di più, così il rack
        decisivo cade per ultimo e la partita non si chiude a metà sequenza.
        """
        distanza = match.distance_config
        p1, p2 = match.player1_id, match.player2_id
        if distanza.is_race_to_racks:
            traguardo = distanza.get_winning_racks()
            al_vincitore = traguardo
            al_perdente = rng.randint(0, traguardo - 1)
            vincitore = rng.choice([p1, p2])
            perdente = p2 if vincitore == p1 else p1
        else:
            totali = distanza.racks
            a_p1 = rng.randint(0, totali)
            a_p2 = totali - a_p1
            if a_p1 >= a_p2:
                vincitore, perdente = p1, p2
                al_vincitore, al_perdente = a_p1, a_p2
            else:
                vincitore, perdente = p2, p1
                al_vincitore, al_perdente = a_p2, a_p1

        sequenza: List[int] = []
        restano = [al_vincitore, al_perdente]
        while sum(restano) > 0:
            for indice, giocatore in enumerate((vincitore, perdente)):
                if restano[indice] > 0:
                    sequenza.append(giocatore)
                    restano[indice] -= 1
        return sequenza

    @staticmethod
    def _simula_trio(match: Any, rng: Sorteggio) -> bool:
        """Un risultato per il trio: passa da `TrioScoringService`.

        Distribuisce `total_played_racks` vittorie fra i tre rispettando
        `max_per_player = 2 * num_rounds`, con un vincitore **netto**: un
        pareggio in testa lascerebbe `winner_id=None` e il trio incompleto
        per classifica e playoff. I pareggi sono circa un quarto dei casi,
        rigenerare converge subito.
        """
        from models.match.trio_scoring_service import TrioScoringService

        trio = match.trio_match
        if trio is None:
            return False

        config = trio.trio_config
        totale = config.total_played_racks
        massimo = 2 * config.num_rounds
        giocatori = [trio.player1_id, trio.player2_id, trio.player3_id]

        def _distribuisci() -> Optional[Dict[int, int]]:
            conteggi = {pid: 0 for pid in giocatori}
            for _ in range(totale):
                ammessi = [pid for pid, c in conteggi.items() if c < massimo]
                if not ammessi:
                    return None
                conteggi[rng.choice(ammessi)] += 1
            return conteggi

        conteggi = None
        for _ in range(100):
            candidato = _distribuisci()
            if candidato is None:
                return False
            vetta = max(candidato.values())
            if list(candidato.values()).count(vetta) == 1:
                conteggi = candidato
                break
        if conteggi is None:
            return False

        TrioScoringService.set_result_direct(
            trio.id,
            conteggi[trio.player1_id],
            conteggi[trio.player2_id],
            conteggi[trio.player3_id],
        )
        return True

    @staticmethod
    def _chiudi_multi_set(match: Any, rng: Sorteggio) -> bool:
        """Una partita a set si chiude d'ufficio, col punteggio in set.

        Il segnapunti a set ha un percorso suo (`start_next_set`,
        `add_rack_to_current_set`) che la simulazione non ripercorre: il
        risultato si scrive in set vinti e la partita si chiude come farebbe
        il direttore. È il comportamento che le azioni di debug hanno sempre
        avuto per questo formato.
        """
        from models.match.match_service import MatchService
        from models.status_enum import MatchStatus

        if MatchStatus.is_finished(match.status):
            return False
        distanza = match.distance_config
        sets = max(1, int(distanza.sets or 1))
        if distanza.is_race_to_sets:
            # Corsa a N set: il vincitore arriva a N, l'altro sotto.
            al_vincitore = sets
            al_perdente = rng.randint(0, sets - 1)
        else:
            # Esattamente N set: si giocano tutti, vince chi ne ha di più.
            al_vincitore = sets // 2 + 1 + rng.randint(0, sets - (sets // 2 + 1))
            al_perdente = sets - al_vincitore
        if rng.choice([True, False]):
            match.player1_score, match.player2_score = al_vincitore, al_perdente
            match.winner_id = match.player1_id
        else:
            match.player1_score, match.player2_score = al_perdente, al_vincitore
            match.winner_id = match.player2_id
        db.session.add(match)
        MatchService.to_completed(match.id, closed_by_director=True)
        return True

    # ------------------------------------------------------- dopo la chiusura

    @staticmethod
    def _avanza(gara_id: int) -> None:
        from models.competition.round_service import RoundService

        RoundService.update_round_progression(gara_id)

    @staticmethod
    def _rilascia_tavoli_e_riassegna(partite: Iterable[Any], gara_id: int) -> int:
        """Libera i tavoli delle partite chiuse e li passa a chi aspetta.

        Anche ai turni successivi, grazie all'ordine `(round_number, id)` di
        `assign_available_tables`. Le partite lasciate in attesa del direttore
        tengono il loro tavolo: sono ancora «al tavolo».
        """
        from models.match.table_assignment_service import TableAssignmentService
        from models.status_enum import MatchStatus

        for m in partite:
            if MatchStatus.is_finished(m.status) and m.table_assignment:
                m.table_assignment = None
                db.session.add(m)
        return TableAssignmentService.assign_available_tables(gara_id)


__all__ = ["AZIONI_SIMULAZIONE", "EsitoSimulazione", "SimulationService", "Sorteggio"]
