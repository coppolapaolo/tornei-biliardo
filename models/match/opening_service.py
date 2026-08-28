"""L'acchito e il runout, per tutte e due le famiglie di partite (ADR-056).

`Match` e `IndividualMatch` sono due classi diverse con due tabelle di
triangoli diverse, ma le due domande sono identiche: *chi apre il primo
triangolo?* e *questo triangolo è stato chiuso in una visita?* Le regole
stanno qui una volta sola; i due servizi di dominio ci passano attraverso
portandosi dietro la propria transazione.

Sono funzioni normali, senza `@transactional`: il decoratore va sul metodo più
interno **uno solo**, e annidarlo fa rollback (vedi
`models/transaction/CLAUDE.md`). Qui il più interno è il chiamante.
"""

from __future__ import annotations

from typing import Any, Optional

from flask_babel import gettext as _

from models.exceptions import ConflictError, NotFoundError, ValidationError
from models.match.break_rules import StartRule
from models.status_enum import MatchStatus

__all__ = ["register_lag", "toggle_run_out"]


def register_lag(
    match: Any,
    lag_winner_id: Optional[int],
    first_break_player_id: Optional[int],
) -> None:
    """Registra l'esito dell'acchito: chi ha vinto, e chi esegue l'apertura.

    Due domande, non una. «Regole generali pool» 1.2: chi vince l'acchito
    **sceglie chi** eseguirà il tiro di apertura, e può scegliere l'avversario
    — quindi i due argomenti sono indipendenti, e il secondo non si deduce dal
    primo.

    Raises:
        ValidationError: uno dei due non gioca questa partita, oppure la
            partita non prevede l'acchito.
        ConflictError: c'è già un triangolo giocato. Cambiare chi ha aperto il
            primo riscriverebbe l'apertura di tutti quelli venuti dopo — e con
            essa quali sono stati break and run.
    """
    if match.effective_start_rule is not StartRule.LAG:
        raise ValidationError(
            _("Questa partita non si decide con l'acchito: apre il primo giocatore.")
        )

    if not match.is_player(lag_winner_id) or not match.is_player(first_break_player_id):
        raise ValidationError(_("Scegli uno dei due giocatori."))

    if match.active_racks():
        raise ConflictError(_("L'acchito si registra prima del primo triangolo."))

    match.lag_winner_id = lag_winner_id
    match.first_break_player_id = first_break_player_id


def toggle_run_out(match: Any, rack_id: int) -> dict:
    """Marca (o smarca) un triangolo come chiuso in una visita.

    È un interruttore, non un comando a senso unico: il trattino si preme una
    seconda volta e torna com'era. Non c'è una conferma perché non c'è niente
    da perdere — a differenza dell'annullo, che toglie un punto.

    Non si chiede *quale* runout: se ad aprire quel triangolo era chi l'ha
    vinto è un break and run, altrimenti no, e lo dice
    `rack.is_break_and_run`. Chi segna preme e basta.

    Returns:
        Lo stato **dopo** il tocco — marcato o no, e se è un break and run —
        così il chiamante può rispondere senza rileggere. La sigla la decide
        il server e non il tabellone: dedurla nel JavaScript sarebbe la terza
        copia della regola, dopo il modello e il motore TPA.
    """
    stato = _stato_partita(match)
    if not (stato["in_corso"] or stato["chiusa_dai_giocatori"]):
        raise ConflictError(
            _("Il risultato è stato registrato dal direttore: non si modifica.")
        )

    rack = next((r for r in match.active_racks() if r.id == rack_id), None)
    if rack is None:
        raise NotFoundError(_("Triangolo non trovato."))

    rack.is_run_out = not bool(rack.is_run_out)
    return {
        "is_run_out": bool(rack.is_run_out),
        "is_break_and_run": bool(rack.is_break_and_run),
    }


def _stato_partita(match: Any) -> dict:
    """Le due condizioni che aprono la finestra in cui si può ancora correggere.

    Le stesse dell'annulla sul tabellone (`puo_annullare`): finché si gioca, o
    finché la chiusura è quella **dei due giocatori** — che è reversibile. Su
    una chiusura d'ufficio no: quel risultato non è più dei giocatori.
    """
    status = getattr(match.status, "value", match.status)
    return {
        "in_corso": status
        in (MatchStatus.PLAYING.value, MatchStatus.IN_PROGRESS.value),
        "chiusa_dai_giocatori": status == MatchStatus.CONFIRMED_BY_BOTH.value,
    }
