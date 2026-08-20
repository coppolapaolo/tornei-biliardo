"""Ogni tabella di un'entità deve nascere con `created_at` e `updated_at`.

`BaseModel` le aggiunge a tutti i modelli, quindi una `CREATE TABLE` che le
dimentica produce una tabella che l'ORM non riesce a scrivere: al primo
inserimento arriva ``no such column: created_at`` e la funzione che ci sta
sopra è morta in silenzio. È successo con `categoria` (GlitchTip, 2026-08-19):
la creazione delle categorie di ADR-049 rispondeva 500 in produzione mentre in
sviluppo funzionava.

**In sviluppo funzionava, ed è il punto.** I test costruiscono lo schema con
`db.create_all()`, che parte dai modelli e quindi le colonne ce le mette
sempre; le migration le esegue solo la produzione. Nessun test di
comportamento può accorgersene — per questo qui si legge il *testo* delle
migration invece di eseguirle.

Il rimedio per un DB già sbagliato non è correggere la migration che lo ha
creato: quella è marcata applicata e non gira più, e in ogni caso è
`CREATE TABLE IF NOT EXISTS`. Serve una migration nuova che aggiunga le
colonne mancanti — vedi `migrations/20260820_timestamps_basemodel.py`.
"""

from __future__ import annotations

import importlib
import pkgutil
import re
from pathlib import Path

RADICE = Path(__file__).resolve().parents[3]
MIGRAZIONI = RADICE / "migrations"

CREATE_TABLE = re.compile(
    r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[\"'`]?(\w+)[\"'`]?\s*\(", re.I
)

RICHIESTE = ("created_at", "updated_at")


def _tabelle_delle_entita() -> set[str]:
    """I `__tablename__` di tutto ciò che eredita da `BaseModel`."""
    import models
    from models.base import BaseModel

    for modulo in pkgutil.walk_packages(models.__path__, "models."):
        try:
            importlib.import_module(modulo.name)
        except Exception:  # moduli con dipendenze opzionali: non è il loro test
            continue

    def discendenti(classe):
        for figlia in classe.__subclasses__():
            yield figlia
            yield from discendenti(figlia)

    return {
        c.__tablename__
        for c in discendenti(BaseModel)
        if getattr(c, "__tablename__", None)
    }


def _corpo_della_create(testo: str, inizio: int) -> str:
    """Dal `(` che apre la CREATE TABLE alla parentesi che la chiude."""
    livello = 0
    for posizione in range(inizio, len(testo)):
        if testo[posizione] == "(":
            livello += 1
        elif testo[posizione] == ")":
            livello -= 1
            if livello == 0:
                return testo[inizio : posizione + 1]
    return testo[inizio:]


def test_le_create_table_delle_entita_hanno_i_timestamp():
    tabelle = _tabelle_delle_entita()
    assert tabelle, "nessun modello caricato: il test non starebbe controllando nulla"

    mancanze: list[str] = []
    for file_migration in sorted(MIGRAZIONI.glob("*.py")):
        testo = file_migration.read_text(encoding="utf-8")
        for trovata in CREATE_TABLE.finditer(testo):
            tabella = trovata.group(1)
            if tabella not in tabelle:
                continue  # tabella di appoggio, di servizio, o non un'entità
            corpo = _corpo_della_create(testo, trovata.end() - 1)
            assenti = [c for c in RICHIESTE if c not in corpo]
            if assenti:
                mancanze.append(
                    f"{file_migration.name}: la tabella «{tabella}» nasce senza "
                    f"{' e '.join(assenti)}"
                )

    assert not mancanze, "\n".join(
        ["Tabelle di entità create senza i timestamp di BaseModel:", *mancanze]
    )
