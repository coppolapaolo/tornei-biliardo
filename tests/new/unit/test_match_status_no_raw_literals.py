"""Lo stato di una partita non si confronta con una stringa scritta a mano.

`MatchStatus` esiste per una ragione precisa, scritta in `CLAUDE.md`: i suoi
valori persistiti (`"completed"`, `"validated"`) **non coincidono** con i nomi
dei membri (`CLOSED_UNILATERALLY`, `CONFIRMED_BY_BOTH`), e quel divario è
deliberato. Chi scrive la stringa a mano perde l'unico appiglio che collega le
due cose, e il giorno in cui un valore cambia non se ne accorge nessuno: un
refuso in `selectattr("status", "equalto", "complated")` non solleva, restituisce
zero — per sempre, in silenzio.

Perché serve un presidio *statico*: i template non hanno test. La suite non
renderizza Jinja, quindi un contatore che vale zero perché confronta la stringa
sbagliata passa tutti i 3700 test e si vede solo guardando la pagina. È la
stessa ragione per cui il progetto presidia staticamente il token CSRF
(`test_drill_exam_manual_findings.py`) e le colonne enum
(`test_enum_columns_store_values.py`).

Cosa ha motivato questo file: al 2026-08-17 `templates/gara_detail.html`
includeva a quattro righe di distanza `_match_cards_mobile.html` (migrato
all'enum) e `_gara_matches.html` (letterali) — le stesse quattro righe di
conteggio, una corretta e una no. La migrazione era stata fatta sul gemello
mobile e non su quello desktop, e nulla lo segnalava.

Il presidio è volutamente **mirato**: guarda solo i soggetti che sono
inequivocabilmente partite (`match.status`, `set.status`, e i `selectattr` su
collezioni di partite). Uno stato di gara (`GaraStatus`) o di richiesta ha un
vocabolario suo e non riguarda questo file.
"""

from __future__ import annotations

import re
from pathlib import Path

from models.competition.validators import (
    MatchmakingStrategy as MatchmakingStrategyValidators,
)
from models.matchmaking.configuration import MatchmakingStrategy
from models.status_enum import GaraStatus, MatchStatus, ProvaDerivedStatus

PROJECT_ROOT = Path(__file__).resolve().parents[3]

# I valori che MatchStatus persiste. Sono questi, e non i nomi dei membri, a
# finire sul disco e nei confronti.
MATCH_STATUS_VALUES = tuple(membro.value for membro in MatchStatus)

_VALORI = "|".join(re.escape(v) for v in MATCH_STATUS_VALUES)
_Q = "[\"']"

# Soggetti che sono senza ambiguita' una partita (o un set di partita).
# `item.entity.status` non c'e': li' l'entita' puo' essere una gara.
#
# Il `.value` finale e' opzionale e non decorativo: su `IndividualMatch` la
# colonna e' `db.Enum(MatchStatus)`, quindi lo stato *e'* un membro dell'enum e
# si legge `match.status.value`. Chi poi lo confronta con `'in_progress'` ha
# fatto meta' del lavoro — ed e' proprio il caso che senza questo pezzo di
# pattern sfuggiva (templates/individual_match/dashboard.html:85).
_SOGGETTI_DIRETTI = r"(?:match|m|set|current_set|bye_match)\.status(?:\.value)?"

# Confronto diretto:  match.status == 'playing'   /   set.status in ['completed']
_CONFRONTO_DIRETTO = re.compile(
    rf"{_SOGGETTI_DIRETTI}\s*(?:==|!=|\bin\b)\s*[\[(]?\s*{_Q}(?:{_VALORI}){_Q}"
)

# Assegnazione (solo Python):  self.status = "playing"
_ASSEGNAZIONE = re.compile(rf"\.status\s*=\s*{_Q}(?:{_VALORI}){_Q}")

# Filtro Jinja su una collezione di partite:
#   round_matches | selectattr("status", "equalto", "completed")
_SELECTATTR_PARTITE = re.compile(
    rf"(?:matches|round_matches|sets)\s*\|\s*(?:select|reject)attr\(\s*"
    rf"{_Q}status{_Q}\s*,\s*{_Q}equalto{_Q}\s*,\s*{_Q}(?:{_VALORI}){_Q}"
)

# I file Python del dominio partita. Fuori da qui `.status = "pending"` puo'
# legittimamente riguardare un'altra entita'.
#
# gamification/ e kpi/ ci sono perche' *interrogano* lo stato delle partite per
# contare: una metrica che filtra sulla stringa sbagliata non solleva, conta
# zero — e l'achievement non si sblocca mai (era il caso di
# `_PLAYED_MATCH_STATUSES` in achievement_metrics.py).
_MODULI_PARTITA = (
    "models/match/",
    "models/individual_match/",
    "models/matchmaking/",
    "models/gamification/",
    "models/kpi/",
    "routes/admin/match/",
    "routes/individual_match/",
)

# Righe che documentano il problema invece di commetterlo: commenti e docstring
# che *citano* la forma sbagliata per spiegare perche' e' sbagliata.
_RIGA_DI_COMMENTO = re.compile(r"^\s*(?:#|\*|\{#|--)|^\s*[\"']{3}")


def _sorgenti_template() -> list[Path]:
    return sorted((PROJECT_ROOT / "templates").rglob("*.html"))


def _sorgenti_python() -> list[Path]:
    fonti: list[Path] = []
    for modulo in _MODULI_PARTITA:
        fonti.extend(sorted((PROJECT_ROOT / modulo).rglob("*.py")))
    return fonti


def _violazioni(percorsi: list[Path], pattern_attivi: tuple[re.Pattern, ...]):
    trovate = []
    for percorso in percorsi:
        testo = percorso.read_text(encoding="utf-8")
        for numero, riga in enumerate(testo.splitlines(), start=1):
            if _RIGA_DI_COMMENTO.match(riga):
                continue
            for pattern in pattern_attivi:
                if pattern.search(riga):
                    relativo = percorso.relative_to(PROJECT_ROOT)
                    trovate.append(f"{relativo}:{numero}: {riga.strip()}")
                    break
    return trovate


def test_i_template_non_confrontano_lo_stato_partita_con_letterali():
    """Nessun template deve leggere lo stato di una partita come stringa."""
    violazioni = _violazioni(
        _sorgenti_template(),
        (_CONFRONTO_DIRETTO, _SELECTATTR_PARTITE),
    )
    assert not violazioni, (
        "Stato di partita confrontato con una stringa scritta a mano.\n"
        "Usa MatchStatus.<MEMBRO>.value (o MatchStatus.is_finished/is_active),\n"
        "che e' gia' disponibile in ogni template via context processor "
        "(app.py).\n\n" + "\n".join(violazioni)
    )


def test_il_dominio_partita_non_assegna_lo_stato_con_letterali():
    """Nel dominio partita, scrivere lo stato passa dall'enum come leggerlo."""
    violazioni = _violazioni(
        _sorgenti_python(),
        (_CONFRONTO_DIRETTO, _ASSEGNAZIONE),
    )
    assert not violazioni, (
        "Stato di partita assegnato o confrontato con una stringa a mano.\n"
        "Usa MatchStatus.<MEMBRO>.value: leggere con l'enum e scrivere col\n"
        "letterale e' il modo in cui i due lati divergono senza accorgersene."
        "\n\n" + "\n".join(violazioni)
    )


# ══ Stato di gara ════════════════════════════════════════════════════════════
#
# Stesso difetto, vocabolario diverso. `Gara.get_real_status()` complica il
# quadro: restituisce sia valori di GaraStatus (persistiti) sia di
# ProvaDerivedStatus (calcolati, mai su disco), e i template li confrontavano
# tutti come stringhe.

_VALORI_GARA = "|".join(
    re.escape(v)
    for v in (
        tuple(m.value for m in GaraStatus) + tuple(m.value for m in ProvaDerivedStatus)
    )
)

_SOGGETTI_GARA = r"(?:gara|g|p|prova|insc\.gara|item\.entity)\.status"

_CONFRONTO_GARA = re.compile(
    rf"{_SOGGETTI_GARA}\s*(?:==|!=|\bin\b)\s*[\[(]?\s*{_Q}(?:{_VALORI_GARA}){_Q}"
)

_REAL_STATUS = re.compile(
    rf"get_real_status\(\)\s*(?:==|!=)\s*{_Q}(?:{_VALORI_GARA}){_Q}"
)

_SELECTATTR_GARE = re.compile(
    rf"(?:provas|garas|gare)\s*\|\s*(?:select|reject)attr\(\s*"
    rf"{_Q}status{_Q}\s*,\s*{_Q}equalto{_Q}\s*,\s*{_Q}(?:{_VALORI_GARA}){_Q}"
)

_MODULI_GARA = (
    "routes/",
    "models/competition/",
    "models/campionato/",
)


def _sorgenti_python_gara() -> list[Path]:
    fonti: list[Path] = []
    for modulo in _MODULI_GARA:
        fonti.extend(sorted((PROJECT_ROOT / modulo).rglob("*.py")))
    return fonti


def test_i_template_non_confrontano_lo_stato_gara_con_letterali():
    violazioni = _violazioni(
        _sorgenti_template(),
        (_CONFRONTO_GARA, _REAL_STATUS, _SELECTATTR_GARE),
    )
    assert not violazioni, (
        "Stato di gara confrontato con una stringa scritta a mano.\n"
        "Usa GaraStatus.<MEMBRO>.value per gli stati persistiti e\n"
        "ProvaDerivedStatus.<MEMBRO>.value per quelli derivati da\n"
        "get_real_status(); entrambi sono iniettati nei template da app.py.\n\n"
        + "\n".join(violazioni)
    )


def test_le_route_non_confrontano_lo_stato_gara_con_letterali():
    violazioni = _violazioni(
        _sorgenti_python_gara(),
        (_CONFRONTO_GARA, _REAL_STATUS),
    )
    assert (
        not violazioni
    ), "Stato di gara confrontato con una stringa scritta a mano.\n\n" + "\n".join(
        violazioni
    )


# ══ Formula di gara ══════════════════════════════════════════════════════════
#
# Terzo vocabolario, stesso difetto — con un'aggravante che gli altri due non
# hanno: `MatchmakingStrategy` esiste **due volte**, con lo stesso nome di
# classe e valori diversi. `models/matchmaking/configuration.py` (canonico, e'
# quello che finisce in `Gara.matchmaking_strategy` e in
# `Campionato.campionato_type`) dice `direct_elimination` e `double_knockout`;
# `models/competition/validators.py` dice `elimination` e `double_ko`, e serve
# solo alla validazione, raggiunto attraverso `_MATCHMAKING_MAP`.
#
# Chi scrive il letterale a mano non ha modo di sapere quale dei due sta
# citando, e sbagliare non costa niente: `gara.matchmaking_strategy ==
# "elimination"` e' semplicemente sempre falso — era il caso di
# `models/match/trio_config.py`, dove il guard che doveva escludere le gare a
# tabellone non ha mai escluso niente.
#
# Per questo il presidio guarda **entrambi** i vocabolari: un confronto col
# valore giusto scritto a mano e' fragile, uno col valore dell'enum sbagliato
# e' gia' rotto, e nessuno dei due deve passare.

_VALORI_FORMULA = "|".join(
    sorted(
        {
            re.escape(v)
            for v in (
                tuple(m.value for m in MatchmakingStrategy)
                + tuple(m.value for m in MatchmakingStrategyValidators)
            )
        },
        key=len,
        reverse=True,  # 'direct_elimination' prima di 'elimination'
    )
)

# Il soggetto e' il campo, non la variabile che lo porta: `gara.`,
# `item.entity.`, `match.gara.`, `self.` o niente affatto. `strategy` e
# `strategy_key` ci sono perche' e' cosi' che il valore si chiama una volta
# estratto dalla colonna — in un `{% set %}`, in una variabile di ciclo o nel
# JavaScript di pagina.
_SOGGETTI_FORMULA = (
    r"(?:[\w.]+\.)?" r"(?:matchmaking_strategy|campionato_type|strategy_key|strategy)"
)

# I filtri Jinja fra il campo e il confronto non sono una scappatoia:
# `campionato_type|lower == 'amalfi'` e' esattamente la stessa cosa, e senza
# questo pezzo il presidio ne lasciava passare otto
# (`_campionato_general_classification.html`, `_index_campionato_cards.html`).
_FILTRI = r"(?:\s*\|\s*\w+)*"

_CONFRONTO_FORMULA = re.compile(
    rf"{_SOGGETTI_FORMULA}{_FILTRI}\s*(?:===|==|!==|!=|\bin\b)\s*"
    rf"[\[(]?\s*{_Q}(?:{_VALORI_FORMULA}){_Q}"
)

_ASSEGNAZIONE_FORMULA = re.compile(
    rf"\.(?:matchmaking_strategy|campionato_type)\s*=\s*{_Q}(?:{_VALORI_FORMULA}){_Q}"
)

_MODULI_FORMULA = (
    "routes/",
    "models/competition/",
    "models/campionato/",
    "models/match/",
    "models/matchmaking/",
    "models/classification/",
)


def _sorgenti_python_formula() -> list[Path]:
    fonti: list[Path] = []
    for modulo in _MODULI_FORMULA:
        fonti.extend(sorted((PROJECT_ROOT / modulo).rglob("*.py")))
    return fonti


def test_i_template_non_confrontano_la_formula_con_letterali():
    violazioni = _violazioni(_sorgenti_template(), (_CONFRONTO_FORMULA,))
    assert not violazioni, (
        "Formula di gara confrontata con una stringa scritta a mano.\n"
        "Usa MatchmakingStrategy.<MEMBRO>.value, iniettato nei template da\n"
        "app.py: e' quello di models/matchmaking/configuration.py, l'unico i\n"
        "cui valori stanno davvero nella colonna.\n\n" + "\n".join(violazioni)
    )


def test_il_dominio_non_confronta_la_formula_con_letterali():
    violazioni = _violazioni(
        _sorgenti_python_formula(),
        (_CONFRONTO_FORMULA, _ASSEGNAZIONE_FORMULA),
    )
    assert not violazioni, (
        "Formula di gara confrontata o assegnata con una stringa a mano.\n"
        "Attenzione a quale dei due enum omonimi stai citando: in colonna c'e'\n"
        "sempre quello di models/matchmaking/configuration.py.\n\n"
        + "\n".join(violazioni)
    )


def test_il_presidio_formula_distingue_i_due_vocabolari(tmp_path):
    """Entrambi i vocabolari vanno riconosciuti, e per ragioni diverse.

    Il valore canonico scritto a mano e' fragile; quello di `validators.py`
    confrontato con la colonna e' gia' rotto — non corrisponde a nessuna riga.
    """
    righe = [
        "{% if gara.matchmaking_strategy == 'random' %}x{% endif %}",
        "{% if campionato.campionato_type in ['amalfi'] %}x{% endif %}",
        'if gara.matchmaking_strategy == "elimination":',
        "gara.matchmaking_strategy = 'double_knockout'",
    ]
    for riga in righe:
        assert _CONFRONTO_FORMULA.search(riga) or _ASSEGNAZIONE_FORMULA.search(
            riga
        ), f"il presidio non riconosce: {riga}"

    # Non deve mordere su cio' che non e' una formula: `random` e' anche una
    # first round policy, e li' il letterale non riguarda questo vocabolario.
    innocua = "{% if gara.first_round_policy == 'random' %}x{% endif %}"
    assert not _CONFRONTO_FORMULA.search(innocua)


def test_il_presidio_riconosce_una_violazione_introdotta(tmp_path):
    """Il presidio deve fallire davvero: verifica che i pattern mordano."""
    finto = tmp_path / "_finto.html"
    finto.write_text(
        "{% if match.status == 'playing' %}x{% endif %}\n"
        '{% set n = matches|selectattr("status","equalto","validated")'
        "|list|length %}\n",
        encoding="utf-8",
    )
    # `_violazioni` relativizza su PROJECT_ROOT: qui basta contare i match.
    trovate = [
        riga
        for riga in finto.read_text(encoding="utf-8").splitlines()
        if _CONFRONTO_DIRETTO.search(riga) or _SELECTATTR_PARTITE.search(riga)
    ]
    assert len(trovate) == 2, f"i pattern non riconoscono le violazioni: {trovate}"


# ─────────────────────────────────────────────────────────────────────────────
# Lo stato passato per una variabile locale
#
# I pattern qui sopra pretendono che il soggetto sia scritto per intero:
# `match.status`, `set.status`. Basta una riga di indirezione per uscire dal
# loro cono di luce —
#
#     {% set status_str = match.status.value|default(match.status) %}
#     {% set is_completed = status_str in ['completed', 'validated'] %}
#
# — e il letterale torna invisibile. Non e' un caso di scuola: al 2026-08-21
# `_unified_match_score.html` faceva esattamente cosi', col presidio verde,
# mentre il file gemello `_unified_rack_input.html` usava l'enum nello stesso
# identico punto e con la stessa identica indirezione.
#
# Questo controllo e' per file, non per riga: prima raccoglie i nomi legati a
# uno `.status`, poi cerca quei nomi confrontati con un valore grezzo.
# ─────────────────────────────────────────────────────────────────────────────

# {% set status_str = match.status.value|default(match.status) %}
#   → cattura `status_str`.
#
# Il soggetto a destra e' ristretto a `_SOGGETTI_DIRETTI` per la stessa ragione
# per cui lo e' il confronto diretto: un `.status` qualunque puo' essere di
# un'altra entita', e i vocabolari si sovrappongono. `proposal.status` vale
# anche `'pending'`, ma e' una **proposta**, non una partita — accettare ogni
# `.status` segnalava `individual_match/proposal_detail.html` per un letterale
# che li' e' quello giusto.
_LEGAME_DA_STATUS = re.compile(
    rf"\{{%-?\s*set\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*[^%]*{_SOGGETTI_DIRETTI}"
)


def _violazioni_per_indirezione(percorsi: list[Path]) -> list[str]:
    trovate: list[str] = []
    for percorso in percorsi:
        testo = percorso.read_text(encoding="utf-8")
        nomi = set(_LEGAME_DA_STATUS.findall(testo))
        if not nomi:
            continue
        alternative = "|".join(re.escape(n) for n in sorted(nomi))
        confronto = re.compile(
            rf"\b(?:{alternative})\b\s*(?:==|!=|\bin\b)\s*"
            rf"[\[(]?\s*{_Q}(?:{_VALORI}){_Q}"
        )
        for numero, riga in enumerate(testo.splitlines(), start=1):
            if _RIGA_DI_COMMENTO.match(riga):
                continue
            if _LEGAME_DA_STATUS.search(riga):
                continue  # la riga che *lega* il nome, non quella che confronta
            if confronto.search(riga):
                trovate.append(
                    f"{percorso.relative_to(PROJECT_ROOT)}:{numero}: {riga.strip()}"
                )
    return trovate


def test_i_template_non_confrontano_lo_stato_passando_da_una_variabile():
    """Mettere lo stato in una variabile non lo affranca dall'enum."""
    violazioni = _violazioni_per_indirezione(_sorgenti_template())
    assert not violazioni, (
        "Stato di partita messo in una variabile e poi confrontato con una\n"
        "stringa scritta a mano. Vale la stessa regola del confronto diretto:\n"
        "MatchStatus.is_finished(...) / is_active(...), o "
        "MatchStatus.<MEMBRO>.value.\n\n" + "\n".join(violazioni)
    )


def test_il_presidio_riconosce_lo_stato_passato_per_una_variabile(tmp_path):
    """L'indirezione deve essere vista, e il passaggio dall'enum lasciato stare."""
    colpevole = tmp_path / "_colpevole.html"
    colpevole.write_text(
        "{% set status_str = match.status.value|default(match.status) %}\n"
        "{% set is_completed = status_str in ['completed', 'validated'] %}\n"
        "{% set is_in_progress = status_str == 'playing' %}\n",
        encoding="utf-8",
    )
    innocente = tmp_path / "_innocente.html"
    innocente.write_text(
        "{% set status_str = match.status.value|default(match.status) %}\n"
        "{% set chiusa = status_str == MatchStatus.CONFIRMED_BY_BOTH.value %}\n"
        "{% set is_completed = MatchStatus.is_finished(status_str) %}\n",
        encoding="utf-8",
    )

    def _conta(percorso):
        testo = percorso.read_text(encoding="utf-8")
        nomi = set(_LEGAME_DA_STATUS.findall(testo))
        alternative = "|".join(re.escape(n) for n in sorted(nomi))
        confronto = re.compile(
            rf"\b(?:{alternative})\b\s*(?:==|!=|\bin\b)\s*"
            rf"[\[(]?\s*{_Q}(?:{_VALORI}){_Q}"
        )
        return [
            r
            for r in testo.splitlines()
            if confronto.search(r) and not _LEGAME_DA_STATUS.search(r)
        ]

    assert len(_conta(colpevole)) == 2, "l'indirezione non viene riconosciuta"
    assert not _conta(innocente), "il passaggio dall'enum non deve essere segnalato"
