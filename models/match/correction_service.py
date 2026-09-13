"""Correzione di un risultato già chiuso, con la sua traccia.

Il direttore inserisce un punteggio sbagliato e se ne accorge dopo. Finché la
partita è aperta non è un problema; una volta chiusa, l'unica strada era
annullarla e reinserire — che funziona, ma non lascia detto a nessuno che il
risultato di ieri era un altro (issue #90).

**Cosa può essere corretto, e cosa no.** Il perimetro non lo decide questo
modulo: è quello che `AdvancedRoundManager.can_modify_match` già codifica, e
che coincide con la regola voluta — si corregge solo dentro una gara **in
corso**, e solo dove la correzione non ricade sui turni successivi. In
pratica: con la formula casuale, dove i turni nascono tutti insieme e nessuno
discende dalla classifica, anche un turno passato; con Amalfi, dove il turno
seguente si costruisce sulla classifica, solo finché quel turno non è partito;
mai con uno spareggio in corso, che sulla classifica si è già basato
(ADR-026).

Quando il lucchetto scatta la via d'uscita esiste ed è esplicita — annullare
il turno successivo e rifarlo — ma va detta a chi la deve percorrere, ed è per
questo che il rifiuto porta con sé il motivo.

**I triangoli si cancellano.** Un punteggio corretto a mano e un elenco di
triangoli che dice un'altra cosa sono due segnapunti che si contraddicono, ed
è la contraddizione che l'ADR-044 evita per il referto TPA. Vale la pena
dirlo chiaro a chi corregge: il dettaglio triangolo per triangolo — con i
runout e i break and run che ne discendono — non è ricostruibile da un
punteggio finale, e va perso.

**L'Elo si annulla e si riapplica** senza logica nuova: la correzione passa
per `to_playing` (che emette `MatchReopenedEvent`, cioè il revert dei delta) e
poi per `to_completed` (che riemette `MatchCompletedEvent`). Gli stessi due
mattoni che usa il reset.

**Il trio si corregge allo stesso modo** dal 2026-09-13, con tre numeri. Lì
però il punteggio non esiste fuori dai triangoli — classifica ed Elo li
leggono uno per uno — quindi i triangoli non si cancellano soltanto: si
riscrivono nell'ordine del girone, come fa la card del direttore
(`trio_punteggio.assegna_vincitori`). Il vincitore segue `SPECIFICHE.md` riga
164: il totale più alto, se è uno solo.

**E la partita a set, set per set.** Su `match` i suoi punteggi sono i set
vinti: correggerli a mano lascerebbe i set com'erano. Si riscrivono i set,
con i loro triangoli, e set vinti e vincitore discendono da quelli. La traccia
tiene anche il dettaglio dei set, prima e dopo, perché i set vinti possono
restare uguali mentre cambia un set.
"""

from __future__ import annotations

from typing import Iterable, Optional, Sequence, Tuple

from flask_babel import lazy_gettext as _

from models.base import db
from models.status_enum import MatchStatus

from .models import Match, MatchCorrection, Rack


class MatchCorrectionService:
    """Corregge il risultato di una partita di gara, lasciandone traccia."""

    @staticmethod
    def can_correct(match_id: int) -> Tuple[bool, str]:
        """Se la partita è correggibile, e altrimenti perché no.

        Il motivo è testo per l'utente: chi si vede rifiutare la correzione
        deve sapere cosa fare, non solo che non si può.
        """
        from models.competition.round_manager import AdvancedRoundManager

        match = db.session.get(Match, match_id)
        if not match:
            return False, str(_("Partita non trovata"))

        if match.is_bye:
            return False, str(_("La X a tavolino non ha un risultato da correggere"))

        if not match.gara_id:
            return False, str(_("Questa partita non appartiene a una gara"))

        consentito, motivo = AdvancedRoundManager.can_modify_match(match_id)
        if not consentito:
            return False, motivo

        return True, ""

    @staticmethod
    def correct_result(
        match_id: int,
        player1_score: int,
        player2_score: int,
        corrected_by_id: int,
        note: Optional[str] = None,
        player3_score: Optional[int] = None,
        sets: Optional[Sequence[Tuple[int, int]]] = None,
    ) -> MatchCorrection:
        """Sostituisce il risultato di una partita e ne registra la traccia.

        `player3_score` serve solo al trio, e lì è obbligatorio. `sets` serve
        solo alla partita a set, e lì è obbligatorio: i triangoli di ogni set
        giocato, in ordine. I set vinti e il vincitore discendono da quelli.

        Raises:
            ValueError: se la partita non è correggibile o il punteggio non è
                un risultato possibile per la distanza di quel turno.
        """
        from models.competition.round_manager import AdvancedRoundManager
        from models.match.state_service import MatchStateService

        consentito, motivo = MatchCorrectionService.can_correct(match_id)
        if not consentito:
            raise ValueError(motivo)

        match = db.session.get(Match, match_id)
        assert match is not None  # can_correct l'ha già cercata

        if match.is_trio:
            return MatchCorrectionService._correct_trio(
                match,
                (player1_score, player2_score, player3_score),
                corrected_by_id,
                note,
            )
        if match.is_multi_set:
            return MatchCorrectionService._correct_sets(
                match, sets, corrected_by_id, note
            )

        MatchCorrectionService._validate_score(match, player1_score, player2_score)

        traccia = MatchCorrection(
            match_id=match.id,
            corrected_by_id=corrected_by_id,
            previous_player1_score=match.player1_score,
            previous_player2_score=match.player2_score,
            previous_status=match.status,
            new_player1_score=player1_score,
            new_player2_score=player2_score,
            note=(note or "").strip() or None,
        )
        db.session.add(traccia)

        # Riapertura: annulla i delta Elo già applicati. Una partita mai
        # chiusa (PENDING) non ha nulla da annullare e resta dov'è.
        if MatchStatus.is_finished(match.status):
            MatchStateService.to_playing(match.id)

        # I triangoli non sopravvivono a un punteggio scritto a mano.
        Rack.query.filter_by(match_id=match.id).delete()

        match.player1_score = player1_score
        match.player2_score = player2_score
        match.winner_id = MatchCorrectionService._winner_of(
            match, player1_score, player2_score
        )
        match.reset_confirmations()
        db.session.add(match)

        # `closed_by_director=True`: la partita può essere ferma a PENDING —
        # è il caso della issue, il risultato annullato che nessuno ha più
        # potuto reinserire — e senza questo non si potrebbe chiudere.
        MatchStateService.to_completed(match.id, closed_by_director=True)

        AdvancedRoundManager._recalculate_affected_classifications(
            match.gara_id, match.round_number
        )

        return traccia

    # ------------------------------------------------------------------
    # Interno
    # ------------------------------------------------------------------

    @staticmethod
    def _correct_trio(
        match: Match,
        punti: Tuple[int, int, Optional[int]],
        corrected_by_id: int,
        note: Optional[str],
    ) -> MatchCorrection:
        """La correzione del trio: tre numeri, e i triangoli riscritti.

        Stessi passi della partita a due — traccia, riapertura, chiusura del
        direttore, classifica ricalcolata — con una differenza: il punteggio
        del trio sono i suoi triangoli, quindi si riscrivono nell'ordine del
        girone invece di sparire.
        """
        from models.competition.round_manager import AdvancedRoundManager
        from models.match.state_service import MatchStateService

        from .models import TrioRack
        from .trio_punteggio import vincitore_del_trio

        trio = match.trio_match
        terzo = punti[2]
        if trio is None or terzo is None:
            raise ValueError(
                str(_("Nel trio servono i triangoli di tutti e tre i giocatori"))
            )
        terna = (punti[0], punti[1], terzo)
        config = trio.trio_config
        attivi = sorted(trio.active_racks, key=lambda r: r.rack_number)
        vincitori = MatchCorrectionService._validate_trio_score(
            config, terna, [trio.get_player_index(r.winner_id) for r in attivi]
        )

        prima = trio.player_racks_list
        traccia = MatchCorrection(
            match_id=match.id,
            corrected_by_id=corrected_by_id,
            previous_player1_score=prima[0],
            previous_player2_score=prima[1],
            previous_player3_score=prima[2],
            previous_status=match.status,
            new_player1_score=terna[0],
            new_player2_score=terna[1],
            new_player3_score=terna[2],
            note=(note or "").strip() or None,
        )
        db.session.add(traccia)

        if MatchStatus.is_finished(match.status):
            MatchStateService.to_playing(match.id)

        # Come il risultato secco: i triangoli di prima si tolgono, quelli
        # nuovi seguono l'ordine fisso del girone, e il vincitore di ognuno e'
        # uno dei due al tavolo.
        for rack in trio.racks.all():
            db.session.delete(rack)
        db.session.flush()
        for numero, vincitore in enumerate(vincitori, start=1):
            incontro = config.get_matchup_for_rack(numero)
            assert incontro is not None  # `assegna_vincitori` l'ha gia' trovato
            primo, secondo, attende = incontro
            db.session.add(
                TrioRack(
                    trio_match_id=trio.id,
                    rack_number=numero,
                    winner_id=trio.player_ids[vincitore],
                    player1_id=trio.player_ids[primo],
                    player2_id=trio.player_ids[secondo],
                    waiting_player_id=trio.player_ids[attende],
                    added_by_id=corrected_by_id,
                )
            )
        db.session.flush()

        trio.bonus_applied = config.bonus_racks > 0
        trio.awaiting_confirmation = False
        trio.player1_confirmed = False
        trio.player2_confirmed = False
        trio.player3_confirmed = False
        trio.is_completed = True
        trio.winner_id = vincitore_del_trio(
            dict(zip(trio.player_ids, terna)), escluso=trio.forfeit_player_id
        )
        match.player1_score = terna[0]
        match.player2_score = terna[1]
        match.winner_id = trio.winner_id
        db.session.add(trio)
        db.session.add(match)

        MatchStateService.to_completed(match.id, closed_by_director=True)

        AdvancedRoundManager._recalculate_affected_classifications(
            match.gara_id, match.round_number
        )

        return traccia

    @staticmethod
    def _correct_sets(
        match: Match,
        sets: Optional[Sequence[Tuple[int, int]]],
        corrected_by_id: int,
        note: Optional[str],
    ) -> MatchCorrection:
        """La correzione della partita a set: set per set.

        Su `match` i punteggi sono i set vinti, quindi scrivere due numeri non
        basta: i set si riscrivono tutti, con i loro triangoli, e set vinti e
        vincitore si ricalcolano da quelli. Un set in più o in meno è una
        correzione come un'altra. I triangoli segnati uno per uno si perdono,
        come nella partita a due.
        """
        from models.base import utc_now
        from models.competition.round_manager import AdvancedRoundManager
        from models.match.state_service import MatchStateService

        from .set_models import Set

        if sets is None:
            raise ValueError(str(_("Nella partita a set servono i punteggi dei set")))
        nuovi = [(int(a), int(b)) for a, b in sets]
        esistenti = sorted(match.sets, key=lambda s: s.set_number)
        riferimento = esistenti[0] if esistenti else None
        # La distanza del set e' quella con cui i set sono nati; senza set,
        # quella che darebbe il prossimo.
        distanza = riferimento.distance if riferimento else match.distance_config.racks
        al_traguardo = (
            bool(riferimento.is_race_to)
            if riferimento
            else bool(match.effective_is_race_to)
        )
        vinti1, vinti2 = MatchCorrectionService._validate_sets(
            match, nuovi, distanza, al_traguardo
        )

        traccia = MatchCorrection(
            match_id=match.id,
            corrected_by_id=corrected_by_id,
            previous_player1_score=match.player1_score,
            previous_player2_score=match.player2_score,
            previous_status=match.status,
            previous_detail=_dettaglio_set(
                (s.player1_racks, s.player2_racks) for s in esistenti
            ),
            new_player1_score=vinti1,
            new_player2_score=vinti2,
            new_detail=_dettaglio_set(nuovi),
            note=(note or "").strip() or None,
        )
        db.session.add(traccia)

        if MatchStatus.is_finished(match.status):
            MatchStateService.to_playing(match.id)

        # I set di prima escono dalla partita (e con loro i triangoli, per la
        # cascata), quelli nuovi entrano chiusi. Disciplina e inizio si tengono
        # dove il set con quel numero c'era gia'.
        prima = {s.set_number: (s.discipline, s.started_at) for s in esistenti}
        for vecchio in esistenti:
            match.sets.remove(vecchio)
        db.session.flush()
        adesso = utc_now()
        for numero, (a, b) in enumerate(nuovi, start=1):
            disciplina, inizio = prima.get(numero, (None, None))
            match.sets.append(
                Set(
                    set_number=numero,
                    distance=distanza,
                    is_race_to=al_traguardo,
                    player1_racks=a,
                    player2_racks=b,
                    status=MatchStatus.CLOSED_UNILATERALLY.value,
                    winner_id=match.player1_id if a > b else match.player2_id,
                    discipline=disciplina,
                    started_at=inizio or adesso,
                    completed_at=adesso,
                )
            )
        db.session.flush()

        match.player1_score = vinti1
        match.player2_score = vinti2
        if vinti1 > vinti2:
            match.winner_id = match.player1_id
        elif vinti2 > vinti1:
            match.winner_id = match.player2_id
        else:
            match.winner_id = None
        match.current_set_number = len(nuovi)
        match.reset_confirmations()
        db.session.add(match)

        MatchStateService.to_completed(match.id, closed_by_director=True)

        AdvancedRoundManager._recalculate_affected_classifications(
            match.gara_id, match.round_number
        )

        return traccia

    @staticmethod
    def _validate_sets(
        match: Match, sets: list, distanza: int, al_traguardo: bool
    ) -> Tuple[int, int]:
        """Una partita a set corretta è una partita finita, e possibile.

        Ogni set è chiuso secondo la sua regola — al traguardo, o esattamente
        N triangoli con un vincitore — e la partita finisce all'ultimo set:
        con «al N set» nessuno ci era arrivato prima, con «esattamente N set»
        se ne giocano N. Restituisce i set vinti dai due giocatori.
        """
        if not sets:
            raise ValueError(str(_("Serve almeno un set")))
        config = match.distance_config
        da_vincere = config.get_winning_sets()
        vinti1 = vinti2 = 0
        for numero, (a, b) in enumerate(sets, start=1):
            if a < 0 or b < 0:
                raise ValueError(str(_("I triangoli non possono essere negativi")))
            if config.is_race_to_sets and max(vinti1, vinti2) >= da_vincere:
                raise ValueError(
                    str(
                        _(
                            "La partita è decisa al set %(num)s: i set dopo non "
                            "si giocano",
                            num=numero - 1,
                        )
                    )
                )
            if al_traguardo:
                if max(a, b) != distanza or min(a, b) >= distanza:
                    raise ValueError(
                        str(
                            _(
                                "Il set %(num)s non è finito: si gioca al %(n)s",
                                num=numero,
                                n=distanza,
                            )
                        )
                    )
            elif a + b != distanza or a == b:
                raise ValueError(
                    str(
                        _(
                            "Il set %(num)s non è finito: si giocano esattamente "
                            "%(n)s triangoli, e uno deve vincerne di più",
                            num=numero,
                            n=distanza,
                        )
                    )
                )
            if a > b:
                vinti1 += 1
            else:
                vinti2 += 1
        if config.is_race_to_sets:
            if max(vinti1, vinti2) < da_vincere:
                raise ValueError(
                    str(
                        _(
                            "Nessuno arriva a %(n)s set: la partita non è finita",
                            n=da_vincere,
                        )
                    )
                )
        elif len(sets) != da_vincere:
            raise ValueError(str(_("Si giocano esattamente %(n)s set", n=da_vincere)))
        return vinti1, vinti2

    @staticmethod
    def _validate_trio_score(config, punti: Tuple[int, int, int], esistenti) -> list:
        """Il trio corretto e' un trio giocato per intero, e possibile.

        La somma e' quella dei triangoli del trio, nessuno vince piu' dei
        triangoli che gioca, e l'ordine del girone deve ammettere quei totali.
        Restituisce la sequenza dei vincitori, che cambia il meno possibile
        quella registrata.
        """
        from .trio_punteggio import assegna_vincitori, massimo_per_giocatore

        if any(p < 0 for p in punti):
            raise ValueError(str(_("I triangoli non possono essere negativi")))
        totale = config.total_played_racks
        if sum(punti) != totale:
            raise ValueError(
                str(
                    _(
                        "Nel trio si giocano %(n)s triangoli: la somma dei tre "
                        "punteggi deve fare %(n)s",
                        n=totale,
                    )
                )
            )
        massimo = massimo_per_giocatore(config)
        if max(punti) > massimo:
            raise ValueError(
                str(
                    _(
                        "Nel trio ognuno gioca %(n)s triangoli: non se ne "
                        "vincono di più.",
                        n=massimo,
                    )
                )
            )
        vincitori = assegna_vincitori(config, punti, esistenti)
        if vincitori is None:
            raise ValueError(
                str(_("Questo punteggio non torna con l'ordine del girone."))
            )
        return vincitori

    @staticmethod
    def _validate_score(match: Match, p1: int, p2: int) -> None:
        """Il punteggio deve essere un risultato che in quel turno si può ottenere.

        La distanza si legge da `match.distance_config` e non dalla gara: in
        un turno «al 3» dentro una gara «al 5» il massimo è 3, e la gara
        accetterebbe un punteggio che nessuno può fare giocando (ADR-027).
        """
        if p1 < 0 or p2 < 0:
            raise ValueError(str(_("I triangoli non possono essere negativi")))

        distanza = match.distance_config

        if distanza.is_race_to_racks:
            traguardo = distanza.get_winning_racks()
            if max(p1, p2) != traguardo:
                raise ValueError(
                    str(
                        _(
                            "In una partita al %(n)s la vince chi arriva a "
                            "%(n)s triangoli",
                            n=traguardo,
                        )
                    )
                )
            if min(p1, p2) >= traguardo:
                raise ValueError(
                    str(_("Non possono arrivarci tutti e due: uno solo vince"))
                )
            return

        # Esattamente N triangoli: si giocano tutti, e il pareggio esiste
        # quando N è pari.
        if p1 + p2 != distanza.racks:
            raise ValueError(
                str(
                    _(
                        "Si giocano esattamente %(n)s triangoli: la somma dei "
                        "due punteggi deve fare %(n)s",
                        n=distanza.racks,
                    )
                )
            )

    @staticmethod
    def _winner_of(match: Match, p1: int, p2: int) -> Optional[int]:
        """Chi ha vinto, o `None` — che con N pari è un pareggio, non un errore."""
        if p1 > p2:
            return match.player1_id
        if p2 > p1:
            return match.player2_id
        return None


def _dettaglio_set(coppie: Iterable[Tuple[int, int]]) -> Optional[str]:
    """I set come si leggono: «4–1 · 2–4 · 1–4». Nessun set, nessun dettaglio."""
    testo = " · ".join(f"{a}–{b}" for a, b in coppie)
    return testo or None


__all__ = ["MatchCorrectionService"]
