"""Guardia: `Discipline` è l'unico vocabolario delle discipline.

Il progetto ha convissuto a lungo con un **vocabolario fantasma** — il nome
italiano usato come valore persistito, mai dichiarato da nessuna parte, scritto
a mano nei default di colonna, nelle firme dei servizi e nelle `<option>` dei
form. Non era un secondo enum visibile: erano letterali sparsi che nessun
controllo validava, perché le colonne sono `db.String(50)`.

Il danno era silenzioso per costruzione: costruire `Discipline` su un valore
fuori vocabolario solleva `ValueError`, che il filtro `discipline_display`
cattura ripiegando su `raw.replace("_", " ").title()` → **"Palla 8"**, che a
schermo sembra giusto. Un fallback difensivo che mascherava esattamente il caso
da segnalare. Nel frattempo `tiebreaker/services.py` confrontava la disciplina
col vocabolario vecchio contro dati scritti in quello nuovo: ramo morto, zero
errori.

Questi test presidiano l'invariante, non i singoli punti già corretti.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from models.status_enum import Discipline

REPO_ROOT = Path(__file__).resolve().parents[3]

# Il vocabolario fantasma. `palla_` seguito da una cifra: non intercetta
# parole italiane legittime ("palla" in un commento) né i nomi tradotti.
LEGACY_PATTERN = re.compile(r"palla_\d")

# Il codice vivo. `migrations/` è escluso di proposito: le migration storiche
# sono immutabili (riscriverle cambierebbe ciò che è già girato in produzione) e
# quella di normalizzazione deve poter nominare i valori vecchi per convertirli.
LIVE_CODE_DIRS = ("models", "routes", "utils", "templates", "static/js")
LIVE_CODE_FILES = ("app.py",)

# L'unico file autorizzato a nominare il vocabolario storico: è quello che
# dichiara il ponte (`_DISCIPLINE_LEGACY_ALIASES`). Ovunque altro il divieto
# vale anche nei commenti — un esempio in un docstring è il modo in cui un
# valore sbagliato si ripropaga per copia.
ALLOWED_TO_MENTION_LEGACY = ("models/status_enum.py",)


def _live_code_paths() -> list[Path]:
    paths: list[Path] = []
    for directory in LIVE_CODE_DIRS:
        base = REPO_ROOT / directory
        if not base.exists():
            continue
        for suffix in ("*.py", "*.html", "*.js"):
            paths.extend(base.rglob(suffix))
    paths.extend(REPO_ROOT / name for name in LIVE_CODE_FILES)
    return [p for p in paths if p.exists()]


def test_no_legacy_discipline_literals_in_live_code() -> None:
    """Nessun `palla_<cifra>` sopravvive fuori dalle migration storiche."""
    offenders: list[str] = []
    for path in _live_code_paths():
        rel = path.relative_to(REPO_ROOT)
        if rel.as_posix() in ALLOWED_TO_MENTION_LEGACY:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if LEGACY_PATTERN.search(line):
                offenders.append(f"{rel}:{lineno}: {line.strip()}")

    assert not offenders, (
        "Vocabolario fantasma tornato nel codice vivo. Usa Discipline.*.value:\n"
        + "\n".join(offenders)
    )


def test_every_discipline_column_default_is_a_valid_enum_value() -> None:
    """I default delle colonne `discipline` sono membri di `Discipline`.

    È il punto in cui il vocabolario fantasma entrava nei dati: bastava creare
    una riga senza passare la disciplina.
    """
    from models import db  # noqa: F401  (registra i modelli)
    import models.individual_match.match_models  # noqa: F401
    import models.individual_match.proposal_models  # noqa: F401
    import models.tiebreaker.models  # noqa: F401
    import models.playoff.models  # noqa: F401
    import models.match.set_models  # noqa: F401
    import models.competition.models  # noqa: F401

    valid = {d.value for d in Discipline}
    offenders: list[str] = []

    for mapper in db.Model.registry.mappers:
        table = mapper.local_table
        if table is None:
            continue
        for column in table.columns:
            if "discipline" not in column.name:
                continue
            default = getattr(column.default, "arg", None)
            if default is None or callable(default):
                continue
            if isinstance(default, str) and default not in valid:
                offenders.append(f"{table.name}.{column.name} = {default!r}")

    assert (
        not offenders
    ), "Default di colonna fuori dall'enum Discipline:\n" + "\n".join(offenders)


# I valori storici sono composti a runtime: scritti come letterali, la
# normalizzazione automatica dei test li convertirebbe insieme agli altri e il
# caso di prova perderebbe senso (è già successo una volta).
_LEGACY_EIGHT = "palla" + "_8"
_LEGACY_NINE = "palla" + "_9"
_LEGACY_TEN = "palla" + "_10"


@pytest.mark.parametrize(
    "legacy,expected",
    [
        (_LEGACY_EIGHT, Discipline.EIGHT_BALL),
        (_LEGACY_NINE, Discipline.NINE_BALL),
        (_LEGACY_TEN, Discipline.TEN_BALL),
        # I valori già canonici passano indenni.
        ("8_ball", Discipline.EIGHT_BALL),
        ("one_pocket", Discipline.ONE_POCKET),
        # Anche il membro dell'enum, per rendere `normalize` idempotente.
        (Discipline.NINE_BALL, Discipline.NINE_BALL),
    ],
)
def test_normalize_maps_legacy_vocabulary(legacy, expected) -> None:
    """`Discipline.normalize` è il ponte per i dati storici."""
    assert Discipline.normalize(legacy) is expected


def test_normalize_returns_none_for_unknown_values() -> None:
    """Su un valore ignoto non inventa una disciplina: restituisce `None`.

    Il chiamante decide se ripiegare su un default o segnalare — la scelta non
    va nascosta dentro la conversione, che era il difetto originale.
    """
    assert Discipline.normalize("scopone") is None
    assert Discipline.normalize(None) is None
    assert Discipline.normalize("") is None


def test_available_disciplines_derives_from_the_enum() -> None:
    """L'elenco per i form non è una seconda tabella scritta a mano.

    `MultiDisciplineService.get_available_disciplines` conteneva la propria
    mappa valore→etichetta, coi valori del vocabolario fantasma: era il secondo
    enum non dichiarato.
    """
    from models.match.multi_discipline_service import MultiDisciplineService

    values = [
        entry["value"] for entry in MultiDisciplineService.get_available_disciplines()
    ]
    assert values == [d.value for d in Discipline]


def test_discipline_rules_cover_every_enum_member() -> None:
    """Le regole per disciplina sono indicizzate sui valori dell'enum.

    Erano indicizzate sul vocabolario fantasma, quindi non venivano mai trovate
    per i dati reali e ogni chiamata cadeva nel ramo di default.
    """
    from models.match.multi_discipline_service import MultiDisciplineService

    for discipline in Discipline:
        rules = MultiDisciplineService.get_discipline_rules(discipline.value)
        assert rules, f"nessuna regola per {discipline.value}"
        assert rules.get("name"), f"regole senza nome per {discipline.value}"


def test_display_name_goes_through_gettext(monkeypatch) -> None:
    """Il nome mostrato è una stringa tradotta, non un letterale.

    Verifica il collegamento, non il contenuto del catalogo: se qualcuno
    reintroduce una mappa di etichette costanti, questo test se ne accorge.
    """
    import models.status_enum as status_enum

    monkeypatch.setattr(status_enum, "_", lambda s: f"[tradotto]{s}")
    assert Discipline.EIGHT_BALL.display_name.startswith("[tradotto]")
    assert Discipline.ONE_POCKET.display_name.startswith("[tradotto]")


def test_get_choices_labels_are_translated(monkeypatch) -> None:
    """Anche le scelte dei form passano dalla traduzione."""
    import models.status_enum as status_enum

    monkeypatch.setattr(status_enum, "_", lambda s: f"[tradotto]{s}")
    for value, label in Discipline.get_choices():
        assert value in {d.value for d in Discipline}
        assert label.startswith("[tradotto]")


# ── Palla 7 (2026-08-26) ────────────────────────────────────────────────────
#
# Aggiunta per la «Garetta Esordienti Palla 7 "Sudden Death"»: la specialità
# esisteva già nelle note della gara, ma non nel vocabolario, quindi la gara
# risultava giocata a Palla 9.


def test_palla_7_e_nel_vocabolario() -> None:
    """`7_ball` è un valore canonico, non un letterale scritto a mano."""
    assert Discipline.SEVEN_BALL.value == "7_ball"
    assert Discipline.normalize("7_ball") is Discipline.SEVEN_BALL
    assert ("7_ball", Discipline.SEVEN_BALL.display_name) in Discipline.get_choices()


def test_palla_7_resta_fuori_dal_referto_tpa() -> None:
    """Il referto TPA non copre Palla 7, ed è una scelta, non una dimenticanza.

    `TpaRefertoService._match_blocking_reason` dice all'utente che il referto
    «vale per palla 8, palla 9 e palla 10»: finché quella frase resta, la mappa
    deve dire la stessa cosa. Se un giorno si decide di includerla, questo test
    va cambiato *insieme* al messaggio, non prima.
    """
    from models.tpa.services import TpaRefertoService

    assert TpaRefertoService.game_type_for(Discipline.SEVEN_BALL.value) is None


# La regex prende un `<select>…</select>` intero, corpo compreso.
SELECT_BLOCK = re.compile(r"<select\b[^>]*>(.*?)</select>", re.DOTALL | re.IGNORECASE)

# Le due forme con cui un template cicla le discipline.
ITERATES_DISCIPLINES = re.compile(r"discipline_choices|Discipline\.get_choices")


def test_ogni_tendina_di_discipline_fissa_la_propria_scelta() -> None:
    """Nessun `<select>` di discipline lascia decidere al browser.

    L'ordine di dichiarazione di `Discipline` **è** l'ordine delle opzioni. Un
    `<select>` che non marca `selected` e non mette davanti un'opzione propria
    fa preselezionare al browser la prima voce dell'enum: aggiungere una
    disciplina in testa cambierebbe in silenzio il valore predefinito di quel
    form. È il genere di regressione che nessuno collega alla riga aggiunta
    dentro un enum, e che si vede solo mesi dopo nei dati.

    Due forme sono accettate: `selected` sull'opzione giusta, oppure
    un'opzione scritta a mano **prima** del ciclo (il segnaposto vuoto
    «Seleziona disciplina…», o il default della gara in cima).
    """
    offenders: list[str] = []
    for path in _live_code_paths():
        if path.suffix != ".html":
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for match in SELECT_BLOCK.finditer(text):
            body = match.group(1)
            if not ITERATES_DISCIPLINES.search(body):
                continue
            if "selected" in body:
                continue
            before_loop = body.split("{%", 1)[0]
            if "<option" in before_loop:
                continue
            rel = path.relative_to(REPO_ROOT)
            line = text[: match.start()].count("\n") + 1
            offenders.append(f"{rel}:{line}")

    assert not offenders, (
        "Tendine di discipline senza scelta esplicita: la prima voce dell'enum "
        "diventerebbe il default di fatto.\n" + "\n".join(offenders)
    )
