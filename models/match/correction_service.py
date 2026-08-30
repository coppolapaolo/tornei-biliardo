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
"""

from __future__ import annotations

from typing import Optional, Tuple

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

        if match.is_trio:
            return False, str(
                _(
                    "Le partite a tre si correggono dal loro segnapunti, "
                    "che tiene il conto dei tre giocatori"
                )
            )

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
    ) -> MatchCorrection:
        """Sostituisce il risultato di una partita e ne registra la traccia.

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


__all__ = ["MatchCorrectionService"]
