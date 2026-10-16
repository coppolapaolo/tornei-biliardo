# routes/admin/campionato_form_parser.py
"""Shared form-parsing logic for campionato creation / update routes.

The "default gare settings" block (default venue / entry fee / rounds count /
odd-number policy / anti-rematch) was duplicated, with slightly different
validation, between ``wizard_create`` and ``edit_campionato``. This parser is
the single source of truth for that block so the two paths cannot drift.

It intentionally covers only the fields both routes read from ``request.form``
with the same meaning. Step-1 wizard fields (name, type, classification system,
playoff config) live in the session for the wizard and in the form for edit, so
they stay in their respective handlers.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from werkzeug.datastructures import MultiDict

from models.classification.position_points import (
    DEFAULT_POSITION_POINTS,
    serialize_points_table,
)
from models.match.break_rules import (
    DEFAULT_BREAK_RULE,
    DEFAULT_START_RULE,
    BreakRule,
    StartRule,
)
from models.matchmaking.configuration import (
    FirstRoundPolicy,
    MatchmakingStrategy,
    OddNumberPolicy,
)

_VALID_ODD_POLICIES = {
    OddNumberPolicy.NO.value,
    OddNumberPolicy.BYE.value,
    OddNumberPolicy.BYE_WITH_CHALLENGE.value,
    OddNumberPolicy.TRIO.value,
}

DEFAULT_ROUNDS_COUNT = 3


def parse_position_points(form: MultiDict) -> Optional[str]:
    """Tabella punti per posizione (US-17), o ``None`` per "usa il default".

    Il form espone una casella per ciascuna **soglia** del default — 1°, 2°,
    3°, 4°, 5°-8°, 9°-16° — e non una per posizione: è la stessa forma in cui
    la tabella è scritta nella spec, e ``points_for_position`` risolve già una
    posizione scoperta con la prima soglia che la contiene.

    Se i valori coincidono col default si salva ``None`` invece della tabella:
    un campionato che non ha configurato nulla deve continuare a **seguire** il
    default, non a portarsene dietro una copia congelata.
    """
    table: Dict[int, int] = {}
    for threshold, fallback in DEFAULT_POSITION_POINTS:
        raw = form.get(f"position_points_{threshold}")
        if raw is None or raw == "":
            table[threshold] = fallback
            continue
        try:
            value = int(raw)
        except (TypeError, ValueError):
            value = fallback
        table[threshold] = max(value, 0)

    if table == {threshold: pts for threshold, pts in DEFAULT_POSITION_POINTS}:
        return None
    return serialize_points_table(table)


class CampionatoFormParser:
    """Extract and normalise the shared 'default gare settings' form block."""

    #: Le colonne del campionato che i suoi moduli scrivono (wizard e
    #: modifica), nell'ordine in cui il modulo le presenta: prima tipo e
    #: sistema, poi i valori proposti alle gare. È la base della whitelist dei
    #: preset di campionato (`models.preset.payload`), accanto a quella della
    #: gara: un campo nuovo letto da `parse_configurazione` va aggiunto qui, e
    #: il presidio `test_preset_campionato_e_condivisione` lo pretende.
    CAMPI_DEL_MODULO = (
        "name",
        "campionato_type",
        "planned_gare_count",
        "challenge_mode",
        "default_classification_system",
        "default_gara_classification_system",
        "default_venue_id",
        "default_entry_fee",
        "default_rounds_count",
        "default_odd_policy",
        "default_first_round_policy",
        "default_anti_rematch",
        "default_start_rule",
        "default_break_rule",
        "has_handicap",
        "default_time_limit_minutes",
        "position_points",
        "default_points_win",
        "default_points_draw",
        "default_points_loss",
        "default_max_groups",
        "default_group_seeding",
        "default_final_phase_mode",
        "default_qualifiers_per_group",
        "default_third_place_match",
        "default_final_phase_time_limit_minutes",
        "default_final_phase_distance",
        "default_final_time_limit_minutes",
        "default_final_distance",
        "default_catena_turno",
        "default_catena_gara",
        "catena_generale",
    )

    @staticmethod
    def parse_configurazione(form: MultiDict, tipo_di_ripiego: str) -> Dict[str, Any]:
        """Tutto ciò che il modulo di modifica del campionato configura.

        Tipo, numero di gare, esercizi, i due sistemi e i valori proposti alle
        gare (catene e punti compresi), letti come li legge la modifica del
        campionato. Il nome resta fuori: è della route. ``tipo_di_ripiego`` è
        il tipo da tenere se il modulo ne manda uno sconosciuto.

        Lo usano la modifica del campionato e «Salva come preset» (ADR-082):
        un modo solo di leggere il modulo.
        """
        from routes.admin.campionato import CAMPIONATO_TYPE_VALUES

        campionato_type = form.get("campionato_type", MatchmakingStrategy.AMALFI.value)
        if campionato_type not in CAMPIONATO_TYPE_VALUES:
            campionato_type = tipo_di_ripiego
        planned_gare_count = form.get("planned_gare_count")

        settings = CampionatoFormParser.parse_default_settings(form)
        settings.update(CampionatoFormParser.parse_gironi(form))
        # Sommando i totali o a piazzamenti, e il sistema delle serate
        # (ADR-080): catene e punti proposti seguono quello delle gare.
        sistemi = CampionatoFormParser.parse_sistemi(form, campionato_type)
        sistema_gare = CampionatoFormParser.sistema_delle_serate(sistemi)
        # La catena della classifica generale segue il sistema del
        # campionato: a piazzamenti ha criteri suoi (ADR-080).
        settings.update(
            CampionatoFormParser.parse_catene(
                form, sistema_gare, sistemi["default_classification_system"]
            )
        )
        settings.update(CampionatoFormParser.parse_punti(form, sistema_gare))
        return {
            "campionato_type": campionato_type,
            "planned_gare_count": (
                int(planned_gare_count) if planned_gare_count else None
            ),
            "challenge_mode": "challenge_mode" in form,
            **sistemi,
            **settings,
        }

    @staticmethod
    def parse_prova(form: MultiDict) -> bool:
        """La spunta «Competizione di prova» del passo 1 (ADR-058).

        Sta qui e non nella route perché è la stessa domanda del modulo della
        gara singola (`request.form.get("is_prova") == "on"`), e la risposta
        deve avere una forma sola.
        """
        return form.get("is_prova") == "on"

    @staticmethod
    def parse_time_limit(form: MultiDict) -> int:
        """I minuti proposti alle gare; vuoto o zero = nessun limite (ADR-077).

        Stessi confini del modulo della gara (`GaraFormParser`): un valore fuori
        si rifiuta, non si corregge in silenzio.
        """
        from flask_babel import gettext as _

        from routes.admin.competition.form_parser import LIMITE_DI_TEMPO_MASSIMO

        grezzo = (form.get("default_time_limit_minutes") or "").strip()
        if not grezzo:
            return 0
        try:
            minuti = int(grezzo)
        except ValueError:
            minuti = -1
        if minuti < 0 or minuti > LIMITE_DI_TEMPO_MASSIMO:
            raise ValueError(
                _(
                    "Il limite di tempo si scrive in minuti, da 1 a %(max)s; "
                    "lascia vuoto per non mettere limiti.",
                    max=LIMITE_DI_TEMPO_MASSIMO,
                )
            )
        return minuti

    @staticmethod
    def parse_catene(
        form: MultiDict, sistema: Any, sistema_generale: Any = None
    ) -> Dict[str, str]:
        """Le tre catene degli spareggi del campionato, se il modulo le manda.

        Le due proposte alle gare (turno e gara), lette col sistema delle
        gare ``sistema``, e quella della classifica generale (ADR-078), letta
        col sistema del campionato ``sistema_generale`` — a piazzamenti
        POSITION, che ha criteri suoi (ADR-080). Un campo assente non si tocca.
        """
        from models.classification.catene import testo_dal_modulo
        from models.classification.ordinamento import Livello
        from models.status_enum import ClassificationSystem

        risolto = ClassificationSystem.resolve(sistema)
        generale = ClassificationSystem.resolve(sistema_generale or sistema)
        campi = (
            ("default_catena_turno", Livello.TURNO),
            ("default_catena_gara", Livello.GARA),
            ("catena_generale", Livello.CAMPIONATO),
        )
        return {
            campo: testo_dal_modulo(
                form.get(campo, ""),
                livello,
                generale if livello is Livello.CAMPIONATO else risolto,
            )
            for campo, livello in campi
            if campo in form
        }

    @staticmethod
    def parse_punti(form: MultiDict, sistema: Any) -> Dict[str, int]:
        """I punti di vittoria, pareggio e sconfitta proposti alle gare.

        Solo per un campionato a punti, e solo se il modulo li manda: con un
        altro sistema i campi sono nascosti e non si leggono (stessa regola
        del modulo della gara, `GaraFormParser._parse_punti`).
        """
        from models.classification.punti import (
            COLONNE_PROPOSTE,
            PUNTI_DEFAULT,
            valida_punti,
        )
        from models.status_enum import ClassificationSystem

        if ClassificationSystem.resolve(sistema) is not ClassificationSystem.POINTS:
            return {}
        if not any(colonna in form for colonna in COLONNE_PROPOSTE):
            return {}
        grezzi = [
            (form.get(colonna) or "").strip() or str(default)
            for colonna, default in zip(COLONNE_PROPOSTE, PUNTI_DEFAULT.come_tupla())
        ]
        return dict(zip(COLONNE_PROPOSTE, valida_punti(*grezzi).come_tupla()))

    @staticmethod
    def parse_sistemi(form: MultiDict, tipo: Any) -> Dict[str, Any]:
        """Come si classifica il campionato, e le sue serate (ADR-080).

        ``default_classification_system``: sommando i totali (vittorie,
        triangoli, punti) o a piazzamenti (POSITION); chi propone il
        tabellone è a piazzamenti. ``default_gara_classification_system``:
        a piazzamenti, il sistema proposto alle serate che non sono un
        tabellone; sommando i totali non c'è (NULL), perché le gare hanno il
        sistema del campionato.
        """
        from models.campionato.piazzamenti import (
            sistema_del_campionato,
            sistema_della_serata,
        )
        from models.status_enum import ClassificationSystem

        sistema = sistema_del_campionato(
            tipo, form.get("default_classification_system")
        )
        serate = (
            sistema_della_serata(form.get("default_gara_classification_system"))
            if sistema == ClassificationSystem.POSITION.value
            else None
        )
        return {
            "default_classification_system": sistema,
            "default_gara_classification_system": serate,
        }

    @staticmethod
    def sistema_delle_serate(sistemi: Dict[str, Any]) -> str:
        """Il sistema con cui si ordinano le gare, dati i due di `parse_sistemi`."""
        return (
            sistemi.get("default_gara_classification_system")
            or sistemi["default_classification_system"]
        )

    @staticmethod
    def parse_gironi(form: MultiDict) -> Dict[str, Any]:
        """Tetto, composizione e fase finale proposti alle gare (ADR-076, 081).

        Solo se il modulo li manda: col girone all'italiana si vedono, con le
        altre strategie sono nascosti e non arrivano. Stessi confini del modulo
        della gara (`leggi_tetto_dei_gironi`, `leggi_composizione`).
        """
        from routes.admin.competition.form_parser import (
            leggi_composizione,
            leggi_la_fase_finale,
            leggi_tetto_dei_gironi,
        )

        valori: Dict[str, Any] = {}
        if "default_max_groups" in form:
            valori["default_max_groups"] = leggi_tetto_dei_gironi(
                form.get("default_max_groups")
            )
        if "default_group_seeding" in form:
            valori["default_group_seeding"] = leggi_composizione(
                form.get("default_group_seeding")
            )
        # La fase finale proposta (ADR-081): solo col tetto, e solo con più
        # gironi; col girone unico torna «nessuna».
        if "default_max_groups" in valori:
            valori.update(
                leggi_la_fase_finale(form, "default_", valori["default_max_groups"])
            )
        return valori

    @staticmethod
    def parse_default_settings(form: MultiDict) -> Dict[str, Any]:
        """Parse the default-settings block shared by create-wizard and edit.

        Returns kwargs ready for ``TournamentService.update_campionato`` /
        ``create_campionato_with_director``:
        ``default_venue_id``, ``default_entry_fee``, ``default_rounds_count``,
        ``default_odd_policy``, ``default_first_round_policy``,
        ``default_anti_rematch``.

        Invalid/empty numeric inputs fall back to safe defaults rather than
        raising, so neither path can 500 on a malformed field.
        """
        raw_venue = form.get("default_venue_id")
        try:
            default_venue_id = int(raw_venue) if raw_venue else None
        except (TypeError, ValueError):
            default_venue_id = None

        raw_fee = form.get("default_entry_fee")
        try:
            default_entry_fee = float(raw_fee) if raw_fee else None
        except (TypeError, ValueError):
            default_entry_fee = None

        try:
            default_rounds_count = int(
                form.get("default_rounds_count", DEFAULT_ROUNDS_COUNT)
            )
            if default_rounds_count < 1:
                default_rounds_count = DEFAULT_ROUNDS_COUNT
        except (TypeError, ValueError):
            default_rounds_count = DEFAULT_ROUNDS_COUNT

        default_odd_policy = form.get("default_odd_policy", OddNumberPolicy.BYE.value)
        if default_odd_policy not in _VALID_ODD_POLICIES:
            default_odd_policy = OddNumberPolicy.BYE.value

        # Il primo abbinamento proposto: un valore ignoto vale il sorteggio,
        # com'è sempre stato per le gare.
        default_first_round_policy = form.get(
            "default_first_round_policy", FirstRoundPolicy.RANDOM.value
        )
        if default_first_round_policy not in {p.value for p in FirstRoundPolicy}:
            default_first_round_policy = FirstRoundPolicy.RANDOM.value

        return {
            "default_venue_id": default_venue_id,
            "default_entry_fee": default_entry_fee,
            "default_rounds_count": default_rounds_count,
            "default_odd_policy": default_odd_policy,
            "default_first_round_policy": default_first_round_policy,
            "default_anti_rematch": "default_anti_rematch" in form,
            # Come si comincia e chi apre poi (ADR-056). Radice della catena:
            # un valore ignoto ricade sul default del progetto — che è il
            # comportamento storico, non una scelta nuova imposta a nessuno.
            "default_start_rule": (
                StartRule.normalize(form.get("default_start_rule"))
                or DEFAULT_START_RULE
            ).value,
            "default_break_rule": (
                BreakRule.normalize(form.get("default_break_rule"))
                or DEFAULT_BREAK_RULE
            ).value,
            # Handicap mode del campionato (ereditato da gare/match). Checkbox.
            "has_handicap": "has_handicap" in form,
            # Limite di tempo per partita proposto alle gare (ADR-077).
            "default_time_limit_minutes": CampionatoFormParser.parse_time_limit(form),
            # Punti per posizione delle gare a tabellone (US-17). Il campo
            # esiste solo sui campionati a tabellone; altrove resta None e la
            # colonna non viene mai letta.
            "position_points": parse_position_points(form),
        }
