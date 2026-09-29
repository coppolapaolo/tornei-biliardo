"""Come la storia si legge: nomi dei campi e valori, nella lingua di chi legge.

La storia salva valori grezzi (`lag`, `true`, `2026-10-10`); qui si
trasformano in parole. Tutto passa da `lazy_gettext`/`gettext` al momento della
lettura (ADR-062): chi legge in inglese vede l'inglese, anche se il direttore
che ha modificato parlava italiano.
"""

from __future__ import annotations

from datetime import date
from typing import Dict

from flask_babel import gettext as _
from flask_babel import lazy_gettext as _l

#: Il nome di ogni campo come lo vede chi legge. Un campo senza etichetta si
#: mostra col suo nome tecnico: meglio un nome brutto che una riga sparita.
ETICHETTE: Dict[str, object] = {
    "name": _l("Nome"),
    "location": _l("Sala"),
    "billiard_hall_id": _l("Sala"),
    "date": _l("Data"),
    "time": _l("Ora"),
    "available_tables": _l("Tavoli"),
    "description": _l("Descrizione"),
    "rounds_count": _l("Numero di turni"),
    "min_participants": _l("Minimo iscritti"),
    "max_participants": _l("Capienza"),
    "entry_fee": _l("Quota d'iscrizione"),
    "discipline": _l("Disciplina"),
    "distance": _l("Distanza"),
    "is_race_to": _l("Si vince al numero di triangoli"),
    "withdraw_policy": _l("Chi si ritira"),
    "is_multi_set": _l("Partita a set"),
    "match_distance": _l("Set per vincere"),
    "is_race_to_sets": _l("Si vince al numero di set"),
    "has_handicap": _l("Handicap"),
    "start_rule": _l("Chi apre"),
    "break_rule": _l("Chi spacca"),
    "matchmaking_strategy": _l("Strategia di abbinamento"),
    "anti_rematch_enabled": _l("Anti-reincontro"),
    "odd_number_policy": _l("Numero dispari di giocatori"),
    "first_round_policy": _l("Primo turno"),
    "classification_system": _l("Sistema di classifica"),
    "separate_teammates": _l("Separare i compagni di squadra"),
    "third_place_match": _l("Finalina"),
    "seeding_rating": _l("Criterio del sorteggio"),
    "double_ko_rounds": _l("Turni della fase a gironi"),
    "weight": _l("Peso nel campionato"),
    "x_challenge_id": _l("Esercizio al posto della X"),
    "tiebreaker_enabled": _l("Spareggio"),
    "tiebreaker_until_position": _l("Spareggio fino al posto"),
}


def etichetta(campo: str) -> str:
    return str(ETICHETTE.get(campo, campo))


def _valori_noti() -> Dict[str, Dict[str, object]]:
    return {
        "matchmaking_strategy": {
            "amalfi": _l("Amalfi"),
            "random": _l("Casuale"),
            "round_robin": _l("Girone all'italiana"),
            "direct_elimination": _l("Eliminazione diretta"),
            "double_knockout": _l("Doppio KO"),
        },
        "odd_number_policy": {
            "no": _l("Lista d'attesa"),
            "bye": _l("X"),
            "bye_with_challenge": _l("X con esercizio"),
            "trio": _l("Trio"),
        },
        "classification_system": {
            "WINS": _l("Vittorie"),
            "RACK": _l("Triangoli"),
            "RACKS": _l("Triangoli"),
            "POSITION": _l("Punti per posizione"),
        },
        "withdraw_policy": {
            "Forfeit": _l("Perde a tavolino le partite restanti"),
            "Exclude": _l("Esce dalla gara"),
        },
    }


def valore(campo: str, grezzo: str | None) -> str:
    """Il valore salvato, in parole."""
    if grezzo is None or grezzo == "":
        if campo in ("start_rule", "break_rule", "has_handicap"):
            return _("come il campionato")
        return "—"
    if grezzo in ("true", "false"):
        return _("sì") if grezzo == "true" else _("no")
    if campo == "discipline":
        from models.status_enum import Discipline

        membro = Discipline.normalize(grezzo)
        return membro.display_name if membro else grezzo
    if campo in ("start_rule", "break_rule"):
        from models.match.break_rules import BreakRule, StartRule

        enum_cls = StartRule if campo == "start_rule" else BreakRule
        membro = enum_cls.normalize(grezzo)
        return membro.display_name if membro else grezzo
    if campo == "date":
        try:
            giorno = date.fromisoformat(grezzo)
        except ValueError:
            return grezzo
        return giorno.strftime("%d/%m/%Y")
    noti = _valori_noti().get(campo, {})
    if grezzo in noti:
        return str(noti[grezzo])
    if campo == "entry_fee":
        return f"{grezzo} €"
    return grezzo
