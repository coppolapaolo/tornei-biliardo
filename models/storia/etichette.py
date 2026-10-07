"""Come la storia si legge: nomi dei campi e valori, nella lingua di chi legge.

La storia salva valori grezzi (`lag`, `true`, `2026-10-10`); qui si
trasformano in parole. Tutto passa da `lazy_gettext`/`gettext` al momento della
lettura (ADR-062): chi legge in inglese vede l'inglese, anche se il direttore
che ha modificato parlava italiano.
"""

from __future__ import annotations

from datetime import date, datetime
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
    "listino": _l("Listino quote"),
    "discipline": _l("Disciplina"),
    "distance": _l("Distanza"),
    "is_race_to": _l("Si vince al numero di triangoli"),
    "withdraw_policy": _l("Chi si ritira"),
    "is_multi_set": _l("Partita a set"),
    "match_distance": _l("Set per vincere"),
    "is_race_to_sets": _l("Si vince al numero di set"),
    "has_handicap": _l("Handicap"),
    "time_limit_minutes": _l("Limite di tempo per partita"),
    "start_rule": _l("Chi apre"),
    "break_rule": _l("Chi spacca"),
    "matchmaking_strategy": _l("Strategia di abbinamento"),
    "anti_rematch_enabled": _l("Anti-reincontro"),
    "odd_number_policy": _l("Numero dispari di giocatori"),
    "first_round_policy": _l("Primo turno"),
    "classification_system": _l("Sistema di classifica"),
    # La classifica a punti (ADR-078, emendamento).
    "punti_in_classifica": _l("Punti in classifica"),
    "points_win": _l("Punti per la vittoria"),
    "points_draw": _l("Punti per il pareggio"),
    "points_loss": _l("Punti per la sconfitta"),
    "default_points_win": _l("Punti per la vittoria, proposti"),
    "default_points_draw": _l("Punti per il pareggio, proposti"),
    "default_points_loss": _l("Punti per la sconfitta, proposti"),
    "separate_teammates": _l("Separare i compagni di squadra"),
    "third_place_match": _l("Finalina"),
    "seeding_rating": _l("Criterio del sorteggio"),
    "double_ko_rounds": _l("Turni della fase a gironi"),
    "weight": _l("Peso nel campionato"),
    "x_challenge_id": _l("Esercizio al posto della X"),
    # Le catene degli spareggi (ADR-078).
    "catena_turno": _l("Pari merito nella classifica di turno"),
    "catena_gara": _l("Pari merito nella classifica di gara"),
    "default_catena_turno": _l("Pari merito di turno, proposti"),
    "default_catena_gara": _l("Pari merito di gara, proposti"),
    "catena_generale": _l("Pari merito nella classifica generale"),
    # Le colonne dello spareggio di prima: restano nelle voci già scritte.
    "tiebreaker_enabled": _l("Spareggio"),
    "tiebreaker_until_position": _l("Spareggio fino al posto"),
    # I valori del campionato (quelli proposti alle gare).
    "campionato_type": _l("Tipo di campionato"),
    "planned_gare_count": _l("Gare previste"),
    "challenge_mode": _l("Modalità esercizi"),
    "default_classification_system": _l("Sistema di classifica"),
    "default_venue_id": _l("Sala proposta"),
    "default_entry_fee": _l("Quota proposta"),
    "default_rounds_count": _l("Turni proposti"),
    "default_odd_policy": _l("Dispari proposti"),
    "default_anti_rematch": _l("Anti-reincontro proposto"),
    "default_start_rule": _l("Chi apre, proposto"),
    "default_break_rule": _l("Chi spacca, proposto"),
    "default_time_limit_minutes": _l("Limite di tempo proposto"),
    "position_points": _l("Punti per posizione"),
    # La configurazione dei playoff.
    "positions_from": _l("Dalla posizione"),
    "positions_to": _l("Alla posizione"),
    "min_garas_played": _l("Gare giocate, almeno"),
    "strategy_type": _l("Strategia di abbinamento"),
    "scheduled_date": _l("Data dei playoff"),
    "response_deadline": _l("Scadenza degli inviti"),
    "final_ranking_mode": _l("Classifica finale"),
    "playoff_weight": _l("Peso della finale"),
    "is_active": _l("Attiva"),
    # Gli strumenti a mano dei playoff.
    "giocatore": _l("Giocatore"),
    "risposta": _l("Risposta"),
    # La proposta di inviti dopo una correzione della classifica.
    "inviti_ritirati": _l("Inviti ritirati"),
    "inviti_nuovi": _l("Inviti nuovi"),
}

#: I valori del campionato si leggono come il campo della gara che propongono.
_COME_CAMPO_DELLA_GARA = {
    "default_classification_system": "classification_system",
    "default_entry_fee": "entry_fee",
    "default_odd_policy": "odd_number_policy",
    "default_anti_rematch": "anti_rematch_enabled",
    "default_start_rule": "start_rule",
    "default_break_rule": "break_rule",
    "default_time_limit_minutes": "time_limit_minutes",
    "default_catena_turno": "catena_turno",
    "default_catena_gara": "catena_gara",
    "default_points_win": "points_win",
    "default_points_draw": "points_draw",
    "default_points_loss": "points_loss",
    "campionato_type": "matchmaking_strategy",
    "strategy_type": "matchmaking_strategy",
}


def etichetta(campo: str) -> str:
    # Le regole di un singolo turno arrivano come `turno_3.distance`.
    if campo.startswith("turno_") and "." in campo:
        turno, interno = campo.split(".", 1)
        numero = turno.split("_", 1)[1]
        return _("Turno %(n)s", n=numero) + " · " + etichetta(interno)
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
            "POINTS": _l("Punti"),
        },
        "final_ranking_mode": {
            "campionato_plus_playoff": _l("Campionato + gara di playoff"),
            "playoff_only": _l("Solo i playoff"),
        },
        "risposta": {
            "accettato": _l("ha accettato"),
            "rifiutato": _l("ha rifiutato"),
        },
        "withdraw_policy": {
            "Forfeit": _l("Perde a tavolino le partite restanti"),
            "Exclude": _l("Esce dalla gara"),
        },
    }


def valore(campo: str, grezzo: str | None) -> str:
    """Il valore salvato, in parole."""
    if campo.startswith("turno_") and "." in campo:
        interno = campo.split(".", 1)[1]
        if grezzo is None or grezzo == "":
            return _("come la gara")
        return valore(interno, grezzo)
    if campo in ("default_catena_turno", "default_catena_gara") and not grezzo:
        # Il campionato non eredita da nessuno: senza catena vale quella
        # dell'app.
        return _("come l'app")
    campo = _COME_CAMPO_DELLA_GARA.get(campo, campo)
    if campo in ("default_venue_id", "billiard_hall_id") and grezzo:
        from models.base import db
        from models.location.models import BilliardHall

        sala = db.session.get(BilliardHall, int(grezzo))
        return sala.name if sala else grezzo
    if campo == "giocatore" and grezzo:
        from models.base import db
        from models.user.models import User

        utente = db.session.get(User, int(grezzo))
        return utente.username if utente else grezzo
    if grezzo is None or grezzo == "":
        if campo in (
            "start_rule",
            "break_rule",
            "has_handicap",
            "time_limit_minutes",
            "catena_turno",
            "catena_gara",
            "points_win",
            "points_draw",
            "points_loss",
        ):
            return _("come il campionato")
        if campo == "catena_generale":
            return _("come l'app")
        return "—"
    if campo in ("catena_turno", "catena_gara", "catena_generale"):
        from models.classification.ordinamento import catena_dal_testo, elenca_catena

        catena = catena_dal_testo(grezzo)
        return elenca_catena(catena) if catena is not None else grezzo
    if campo == "listino":
        from models.categoria.listino import in_parole

        return in_parole(grezzo)
    if campo == "time_limit_minutes":
        try:
            minuti = int(grezzo)
        except ValueError:
            return grezzo
        if minuti <= 0:
            return _("senza limite")
        return _("%(n)s minuti", n=minuti)
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
    if campo in ("scheduled_date", "response_deadline"):
        from utils.local_time import resolve_timezone, to_local_naive

        try:
            momento = datetime.fromisoformat(grezzo)
        except ValueError:
            return grezzo
        # Salvato in UTC come ogni orario: si legge nel fuso di chi legge.
        return to_local_naive(momento, resolve_timezone()).strftime("%d/%m/%Y %H:%M")
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
    if campo in ("weight", "playoff_weight"):
        return f"×{grezzo}"
    return grezzo
