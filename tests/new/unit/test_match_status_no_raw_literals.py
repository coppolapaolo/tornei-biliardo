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

from models.status_enum import MatchStatus

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
