# routes/admin/competition/form_parser.py
"""Shared form-parsing logic for gara creation / update routes."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from flask import request

from models.competition.models import Gara
from models.competition.constants import (
    DEFAULT_MIN_PARTICIPANTS,
    DEFAULT_ROUNDS_COUNT,
    DEFAULT_ENTRY_FEE,
    DEFAULT_WITHDRAW_POLICY,
)
from models.matchmaking.configuration import (
    BRACKET_STRATEGIES,
    StrategyConfiguration,
    MatchmakingStrategy,
    FirstRoundPolicy,
    OddNumberPolicy,
    calculate_rounds_for_strategy,
    minimum_players_for,
    resolve_classification_system,
)
from models.matchmaking.bracket import group_format_total_rounds
from models.match.break_rules import BreakRule, StartRule
from models.status_enum import WithdrawPolicy

# Ri-esportato: `BRACKET_STRATEGIES` vive nel dominio
# (`models/matchmaking/configuration.py`) perché la domanda "questa gara ha un
# tabellone?" se la pongono anche modelli e template. Qui resta importabile
# dove lo era prima.
__all__ = ["BRACKET_STRATEGIES", "GaraFormParser"]

# La regola vive nel dominio, dove la usano anche il playoff e il cambio di
# sistema sul campionato; qui resta il nome storico.
_resolve_classification_system = resolve_classification_system


def _third_place_applies(strategy: str, double_ko_rounds: Optional[int]) -> bool:
    """La finalina ha senso solo dove il terzo posto è un pari merito.

    A eliminazione diretta i due semifinalisti sconfitti escono allo stesso
    turno e restano terzi a pari merito: è lì che la finalina serve.

    Nel doppio KO **pieno** no: il terzo è chi perde la finale del losers
    bracket, un risultato sul campo e non un'ambiguità: far rigiocare quel
    posto aggiungerebbe un match che il formato non prevede. Ma con la fase a
    gironi (formula FISBB) il tabellone finale è a eliminazione diretta pura,
    quindi il pari merito ricompare e la finalina torna ad avere senso.
    """
    if strategy == MatchmakingStrategy.DIRECT_ELIMINATION.value:
        return True
    if strategy == MatchmakingStrategy.DOUBLE_KNOCKOUT.value:
        return bool(double_ko_rounds)
    return False


def _bracket_derived_fields(data: Dict[str, Any]) -> Dict[str, Any]:
    """Campi che sul tabellone non sono una scelta, ma una conseguenza.

    Sei impostazioni del form non hanno alcun effetto su una gara a
    tabellone, e chiederle significava solo far credere che decidessero
    qualcosa:

    * **gestione forfait** — nessuna delle due strategie legge
      ``withdraw_policy``. Dopo il sorteggio il tabellone non si tocca più:
      chi si ritira lascia avanzare l'avversario a tavolino, e "escludi dal
      turno" lascerebbe un nodo senza giocatori.
    * **giocatori dispari** — nemmeno ``odd_number_policy`` viene letto. I bye
      sono strutturali (``S - n`` buchi ai primi seed), non una politica: un
      trio o una lista d'attesa non hanno un posto nell'albero.
    * **spareggio SSR** — le strategie POSITION dichiarano
      ``requires_tiebreaker=False``, perché i pari merito per banda sono
      l'esito voluto. Il flag acceso non produceva alcuno spareggio.
    * **numero di turni** — lo riscrive il sorteggio sugli iscritti effettivi
      (ADR-038). Qui vale la stima da ``max_participants``, che è anche il
      tetto massimo: il valore digitato dal director veniva buttato comunque.
    * **numero esatto di rack (e di set)** — sul tabellone conta solo chi passa
      il turno. Il vincitore è deciso appena uno arriva a ``(N+1)/2``, e i rack
      dopo quel punto non cambiano né il tabellone né la classifica, che è per
      posizione e non guarda i rack: sono solo partite più lunghe a parità di
      risultato. Con un numero pari è anche peggio, perché la partita può finire
      in parità e il nodo resterebbe senza vincitore.
    * **anti-reincontro** — nemmeno ``anti_rematch_enabled`` viene letto, e non
      avrebbe cosa fare: nel tabellone due giocatori non possono reincontrarsi,
      perché chi perde esce. Nel doppio KO il reincontro fra un ripescato e chi
      lo aveva battuto è previsto dal formato, e l'incrocio del losers bracket
      lo allontana già per costruzione.

    Il minimo iscritti viene alzato al pavimento del formato: il default del
    form è 6, che per il doppio KO (che ne vuole 8) avrebbe dato una gara
    impossibile da avviare.
    """
    strategy = data["matchmaking_strategy"]
    if strategy not in BRACKET_STRATEGIES:
        return {}

    derived: Dict[str, Any] = {
        "withdraw_policy": WithdrawPolicy.FORFEIT.value,
        "odd_number_policy": OddNumberPolicy.BYE.value,
        "tiebreaker_enabled": False,
        # Sempre "a chi arriva prima", sui rack e sui set.
        "is_race_to": True,
        "is_race_to_sets": True,
        "anti_rematch_enabled": False,
    }

    floor = minimum_players_for(strategy)
    derived["min_participants"] = max(data.get("min_participants") or floor, floor)

    capienza = data.get("max_participants")
    if capienza:
        # Con una fase a gironi i turni sono `2w - 1` di girone piu' quelli del
        # tabellone finale fra i qualificati: molti meno del doppio KO pieno
        # sulla stessa capienza (6 invece di 8 con 16 iscritti, 8 invece di 12
        # con 48). Il sorteggio lo sa gia' — `DoubleKnockoutStrategy` fissa
        # `rounds_count` sugli iscritti effettivi con la stessa funzione — ma
        # fino a quel momento il direttore leggeva la stima del formato
        # sbagliato, in creazione e sulla pagina della gara.
        gruppi = data.get("double_ko_rounds")
        if gruppi:
            derived["rounds_count"] = group_format_total_rounds(
                int(capienza), int(gruppi)
            )
        else:
            derived["rounds_count"] = calculate_rounds_for_strategy(
                MatchmakingStrategy(strategy), int(capienza)
            )

    return derived


class GaraFormParser:
    """Extract and validate gara form fields from a Flask request.

    Usage::

        parser = GaraFormParser(campionato=campionato)  # or campionato=None
        data = parser.parse()
        # data contains all kwargs ready for GaraService.create_gara()
    """

    def __init__(self, campionato: Optional[Any] = None) -> None:
        self.campionato = campionato

    def parse(self) -> Dict[str, Any]:
        """Parse the current Flask request form and return a dict of gara fields.

        Raises ValueError if strategy validation fails.
        """
        data: Dict[str, Any] = {}

        # ── Date / time ──────────────────────────────────────────
        date_str = request.form["date"]
        time_str = request.form.get("time", "20:00")
        if "T" in date_str:
            parsed_dt = datetime.strptime(date_str, "%Y-%m-%dT%H:%M")
            data["date"] = parsed_dt.date()
            data["time"] = parsed_dt.time()
        else:
            data["date"] = datetime.strptime(date_str, "%Y-%m-%d").date()
            data["time"] = datetime.strptime(time_str, "%H:%M").time()

        # ── Tables ───────────────────────────────────────────────
        tables_input = request.form.get("available_tables", "").strip()
        data["available_tables"] = (
            Gara.parse_tables_input(tables_input) if tables_input else []
        )

        # ── Basic fields ─────────────────────────────────────────
        camp = self.campionato
        default_rounds = (
            camp.default_rounds_count
            if camp and camp.default_rounds_count
            else DEFAULT_ROUNDS_COUNT
        )
        default_fee = (
            camp.default_entry_fee
            if camp and camp.default_entry_fee is not None
            else DEFAULT_ENTRY_FEE
        )

        data["description"] = request.form.get("description", "").strip()
        data["rounds_count"] = int(request.form.get("rounds_count", default_rounds))
        data["min_participants"] = int(
            request.form.get("min_participants", DEFAULT_MIN_PARTICIPANTS)
        )
        max_p = request.form.get("max_participants")
        data["max_participants"] = int(max_p) if max_p else None
        data["entry_fee"] = float(request.form.get("entry_fee", default_fee))

        # ── Game settings ────────────────────────────────────────
        data["discipline"] = request.form["discipline"]
        data["distance"] = int(request.form["distance"])
        data["is_race_to"] = "exact_number" not in request.form
        data["withdraw_policy"] = request.form.get(
            "withdraw_policy", DEFAULT_WITHDRAW_POLICY
        )

        # ── Multi-set ────────────────────────────────────────────
        data["is_multi_set"] = "is_multi_set" in request.form
        md = request.form.get("match_distance")
        data["match_distance"] = int(md) if md else None
        data["is_race_to_sets"] = "is_race_to_sets" in request.form

        # ── Handicap mode (tri-state: eredita/sì/no) ─────────────
        # Select con valori "" (eredita dal campionato) / "true" / "false".
        # Per gare standalone "" equivale a NULL → False.
        raw_handicap = request.form.get("has_handicap", "")
        if raw_handicap == "true":
            data["has_handicap"] = True
        elif raw_handicap == "false":
            data["has_handicap"] = False
        else:
            data["has_handicap"] = None  # eredita dal campionato

        # ── Regola di inizio e di apertura (ADR-056) ─────────────
        # Tri-stato come l'handicap: "" = eredita dal campionato (NULL), un
        # valore = scelta esplicita per questa gara.
        #
        # **Assenti dal form = non toccare.** Non è la stessa cosa di "":
        # a gara cominciata i due campi si affossano, e un campo affossato non
        # viene inviato. Se qui li leggessimo comunque, un salvataggio
        # innocuo — cambiare la descrizione — riscriverebbe le due regole a
        # "eredita", cioè cambierebbe chi ha aperto i triangoli già giocati,
        # senza che nessuno l'abbia chiesto e senza dirlo.
        for campo, enum_cls in (("start_rule", StartRule), ("break_rule", BreakRule)):
            if campo in request.form:
                scelta = enum_cls.normalize(request.form.get(campo, ""))
                data[campo] = scelta.value if scelta is not None else None

        # ── Strategy ─────────────────────────────────────────────
        if camp:
            data["matchmaking_strategy"] = camp.campionato_type
            default_anti = (
                camp.default_anti_rematch
                if camp.default_anti_rematch is not None
                else True
            )
            default_odd = camp.default_odd_policy or "bye"
            data["anti_rematch_enabled"] = (
                request.form.get("anti_rematch_enabled") == "on"
                if "anti_rematch_enabled" in request.form
                else default_anti
            )
            data["odd_number_policy"] = request.form.get(
                "odd_number_policy", default_odd
            )
            data["first_round_policy"] = request.form.get(
                "first_round_policy", "random"
            )
            data["classification_system"] = camp.default_classification_system or "WINS"
        else:
            data["matchmaking_strategy"] = request.form.get(
                "matchmaking_strategy", "amalfi"
            )
            data["first_round_policy"] = request.form.get(
                "first_round_policy", "random"
            )
            data["odd_number_policy"] = request.form.get("odd_number_policy", "bye")
            data["anti_rematch_enabled"] = (
                request.form.get("anti_rematch_enabled") == "on"
            )
            data["classification_system"] = request.form.get(
                "classification_system", "WINS"
            )

        # I formati a tabellone ammettono un solo sistema di classifica, quindi
        # non lo si chiede: lo si impone. Prima il parser forzava WINS/RACK, il
        # che rendeva la combinazione valida irraggiungibile e faceva fallire il
        # salvataggio di ogni gara a eliminazione diretta o doppio KO.
        data["classification_system"] = _resolve_classification_system(
            data["matchmaking_strategy"], data["classification_system"]
        )

        data.update(GaraFormParser._parse_bracket_options(data["matchmaking_strategy"]))

        # ── Peso nella classifica del campionato (issue #64) ─────
        data["weight"] = GaraFormParser._parse_weight(camp)

        # ── Esercizio giocato al posto della X (issue #267) ───────
        data["x_challenge_id"] = GaraFormParser._parse_x_challenge(
            data["odd_number_policy"]
        )

        # ── SSR tiebreaker ───────────────────────────────────────
        data["tiebreaker_enabled"] = request.form.get("tiebreaker_enabled") == "on"
        data["tiebreaker_until_position"] = int(
            request.form.get("tiebreaker_until_position", 3)
        )

        # Ultimo passaggio: sul tabellone alcune di queste impostazioni sono
        # conseguenze, non scelte. Le si impone qui — dopo che tutto il resto
        # è stato letto — così una gara resta coerente anche se il form arriva
        # da una schermata vecchia o con il JavaScript spento.
        data.update(_bracket_derived_fields(data))

        return data

    @staticmethod
    def _parse_x_challenge(odd_number_policy: str) -> Optional[int]:
        """Quale esercizio si gioca al posto della X, se il direttore lo sceglie.

        Si legge **solo** con `bye_with_challenge`: con qualunque altra politica
        e' una domanda senza oggetto, e una scelta rimasta da prima resterebbe
        in colonna senza che nessuna schermata la mostri piu'. Si azzera invece
        di ignorarla, come `_parse_bracket_options` fa con le opzioni del
        tabellone fuori dal tabellone.

        Con `bye_with_challenge` la scelta e' **obbligatoria**: non esiste un
        «decide l'applicazione» (issue #267). Il rifiuto sta qui e non a valle
        perche' questo e' il momento in cui il direttore sta guardando il
        modulo: accettare e scoprirlo al primo turno dispari vorrebbe dire
        dirglielo a gara cominciata, quando cambiare costa.
        """
        from models.matchmaking.configuration import OddNumberPolicy

        if odd_number_policy != OddNumberPolicy.BYE_WITH_CHALLENGE.value:
            return None

        raw = (request.form.get("x_challenge_id") or "").strip()
        try:
            scelto = int(raw)
        except ValueError:
            scelto = 0
        if scelto < 1:
            raise ValueError(
                "Scegli l'esercizio che si gioca al posto della X. "
                "Se non ne trovi uno adatto puoi crearlo dal modulo."
            )
        return scelto

    @staticmethod
    def _parse_weight(campionato: Optional[Any]) -> int:
        """Quanto pesa questa gara nella classifica generale del campionato.

        Su una gara **standalone** il campo non viene mostrato — non c'e'
        nessuna classifica generale in cui pesare — e quindi non viene nemmeno
        letto: restituire sempre 1 evita che un POST costruito a mano scriva un
        valore che poi nessuna schermata potra' rivedere. E' la stessa regola
        di `_parse_bracket_options` per le opzioni del tabellone fuori dal
        tabellone.

        Un valore assente o vuoto vale 1, che e' il comportamento storico. Un
        valore **non positivo o non intero** invece si rifiuta invece di
        ripiegare sul default: lo zero ha gia' un significato riservato
        (`Gara.classification_weight` vale 0 per il playoff che decide da solo
        la classifica finale), e correggerlo in silenzio scriverebbe in
        classifica un peso che il direttore non ha scelto. Stesso messaggio di
        `PlayoffService.update_scoring`, che sulla stessa colonna decide gia'
        cosi'.
        """
        if campionato is None:
            return 1

        raw = (request.form.get("weight") or "").strip()
        if not raw:
            return 1

        try:
            weight = int(raw)
        except ValueError:
            raise ValueError("Il peso deve essere un intero maggiore di zero")
        if weight < 1:
            raise ValueError("Il peso deve essere un intero maggiore di zero")
        return weight

    @staticmethod
    def _parse_bracket_options(strategy: str) -> Dict[str, Any]:
        """Opzioni che esistono solo per i formati a tabellone.

        Fuori dal tabellone vengono **azzerate** invece che ignorate: se il
        director cambia formato dopo aver spuntato la finalina, lasciare il
        flag acceso su una gara a girone significherebbe portarsi dietro una
        configurazione che nessuna schermata mostra più.
        """
        if strategy not in BRACKET_STRATEGIES:
            return {
                "separate_teammates": False,
                "third_place_match": False,
                "double_ko_rounds": None,
            }

        double_ko_rounds: Optional[int] = None
        if strategy == MatchmakingStrategy.DOUBLE_KNOCKOUT.value:
            raw = (request.form.get("double_ko_rounds") or "").strip()
            if raw:
                try:
                    parsed = int(raw)
                except ValueError:
                    parsed = 0
                # 0 e valori non numerici valgono "nessuna fase a gironi",
                # cioè doppio KO pieno: è il default e non va segnalato come
                # errore, il formato a gironi è una scelta esplicita.
                double_ko_rounds = parsed if parsed > 0 else None

        return {
            "separate_teammates": request.form.get("separate_teammates") == "on",
            "third_place_match": (
                request.form.get("third_place_match") == "on"
                and _third_place_applies(strategy, double_ko_rounds)
            ),
            "seeding_rating": request.form.get("seeding_rating", "elo"),
            "double_ko_rounds": double_ko_rounds,
        }

    @staticmethod
    def validate_strategy(data: Dict[str, Any]) -> List[str]:
        """Validate strategy config. Returns error strings (empty = OK)."""
        try:
            cfg = StrategyConfiguration(
                strategy=MatchmakingStrategy(data["matchmaking_strategy"]),
                first_round_policy=FirstRoundPolicy(data["first_round_policy"]),
                odd_number_policy=OddNumberPolicy(data["odd_number_policy"]),
                anti_rematch_enabled=data.get("anti_rematch_enabled", False),
                rounds_count=data["rounds_count"],
            )
            return cfg.validate(
                distance=data["distance"], is_race_to=data["is_race_to"]
            )
        except ValueError as e:
            return [str(e)]
