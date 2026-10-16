"""Tempi di gioco di un campionato, gara per gara e turno per turno (READ-ONLY).

Serve a decidere la distanza di un campionato nuovo guardando quanto sono
durate le serate di uno vecchio: per ogni gara, playoff compreso, e per ogni
turno stampa disciplina e distanza, quante partite, la durata minima, media e
massima di una partita e l'ora in cui si è chiusa l'ultima.

Che cosa misura, perché non è ovvio:

* **inizio** = `match.started_at`, scritto quando la partita **riceve il
  tavolo** (all'avvio del turno, o quando un tavolo si libera). Non è l'ora
  dell'acchito: una partita mandata al tavolo prima che i giocatori fossero
  pronti risulta più lunga;
* **fine** = `match.ended_at`, scritto quando la partita **si chiude** (dal
  direttore o con la seconda conferma dei giocatori), quindi può arrivare dopo
  l'ultimo rack giocato. Per questo accanto all'ora di chiusura del turno c'è
  quella dell'**ultimo rack inserito** (`rack.added_at`): se è molto prima,
  il turno è finito lì;
* restano fuori dalle durate le X e i riposi, che non hanno durata, e le
  partite senza rack (i tavolini). Quelle senza inizio o fine si contano a
  parte. Disciplina e distanza si leggono dalle partite, quindi valgono anche
  gli override per turno (ADR-027).

Orari in ora italiana.

Usage:
    python scripts/tempi_di_gara.py                       # elenca i campionati
    python scripts/tempi_di_gara.py "Prima R"             # per parte del nome
    python scripts/tempi_di_gara.py 12                    # per id
    python scripts/tempi_di_gara.py "Prima R" --db percorso/del.db

Apre il DB in sola lettura (`mode=ro`) e non importa l'app: su PythonAnywhere
NON serve disabilitare la web app, né caricare le env di produzione.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, TextIO
from zoneinfo import ZoneInfo

DB_DI_DEFAULT = (
    Path(__file__).resolve().parents[1] / "instance" / ("billiard_campionato.db")
)
ROMA = ZoneInfo("Europe/Rome")

#: Le colonne che lo script legge, tabella per tabella. Un presidio
#: (`test_tempi_di_gara.py`) controlla che esistano nei modelli: lo script non
#: importa l'app, quindi una colonna rinominata lo romperebbe solo in
#: produzione.
COLONNE_LETTE = {
    "campionato": ("id", "name", "campionato_type", "deleted_at"),
    "gara": (
        "id",
        "campionato_id",
        "number",
        "name",
        "date",
        "discipline",
        "distance",
        "is_race_to",
        "playoff_config_id",
        "deleted_at",
    ),
    "match": (
        "id",
        "gara_id",
        "round_number",
        "discipline",
        "match_distance",
        "is_race_to",
        "started_at",
        "ended_at",
        "is_bye",
        "is_trio",
    ),
    "rack": ("match_id", "added_at", "is_deleted"),
}


def _ts(valore) -> Optional[datetime]:
    return datetime.fromisoformat(str(valore)) if valore else None


def _ora(momento: Optional[datetime]) -> str:
    if momento is None:
        return "—"
    return momento.replace(tzinfo=timezone.utc).astimezone(ROMA).strftime("%H:%M")


def apri(percorso: Path) -> sqlite3.Connection:
    """Il DB in sola lettura: un errore di scrittura qui è impossibile."""
    if not percorso.exists():
        raise SystemExit(f"DB non trovato: {percorso}")
    con = sqlite3.connect(f"file:{percorso}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def campionati(con: sqlite3.Connection, chiave: Optional[str]) -> List[sqlite3.Row]:
    """I campionati non eliminati: tutti, per id, o per parte del nome."""
    sql = "SELECT id, name, campionato_type FROM campionato WHERE deleted_at IS NULL"
    if chiave is None:
        return con.execute(sql + " ORDER BY id").fetchall()
    if chiave.isdigit():
        return con.execute(sql + " AND id = ?", (int(chiave),)).fetchall()
    return con.execute(
        sql + " AND name LIKE ? ORDER BY id", (f"%{chiave}%",)
    ).fetchall()


def _formato(partita: sqlite3.Row, gara: sqlite3.Row) -> str:
    """Disciplina e distanza della partita, coi ripieghi della gara.

    Stessa regola di `Match.effective_distance`: `match_distance` a 1 è il
    default dello schema, non una distanza.
    """
    disciplina = partita["discipline"] or gara["discipline"]
    distanza = partita["match_distance"]
    if not distanza or distanza <= 1:
        distanza = gara["distance"]
    corsa = partita["is_race_to"]
    if corsa is None:
        corsa = gara["is_race_to"]
    return f"{disciplina}, {'al' if corsa else 'esattamente'} {distanza}"


def riga_del_turno(
    numero: int, partite: Sequence[sqlite3.Row], gara: sqlite3.Row
) -> str:
    """La riga di un turno: formato, partite, durate, ora di chiusura."""
    giocate = [p for p in partite if p["rack"] or p["is_trio"]]
    durate: List[float] = []
    senza_orari = 0
    for p in giocate:
        inizio, fine = _ts(p["started_at"]), _ts(p["ended_at"])
        if inizio and fine and fine >= inizio:
            durate.append((fine - inizio).total_seconds() / 60)
        else:
            senza_orari += 1
    chiusa = max((_ts(p["ended_at"]) for p in giocate if p["ended_at"]), default=None)
    ultimo_rack = max(
        (_ts(p["ultimo_rack"]) for p in giocate if p["ultimo_rack"]), default=None
    )

    formati = sorted({_formato(p, gara) for p in partite})
    riga = f"  Turno {numero}: {' / '.join(formati)} — {len(giocate)} partite"
    if len(partite) > len(giocate):
        riga += f" (+{len(partite) - len(giocate)} senza rack: tavolini)"
    if durate:
        riga += (
            f"; durata min {min(durate):.0f}′, media "
            f"{sum(durate) / len(durate):.0f}′, max {max(durate):.0f}′"
        )
    if senza_orari:
        riga += f"; {senza_orari} senza inizio o fine"
    riga += (
        f"; ultima chiusa alle {_ora(chiusa)} (ultimo rack alle {_ora(ultimo_rack)})"
    )
    return riga


def rapporto(con: sqlite3.Connection, campionato: sqlite3.Row) -> Iterable[str]:
    yield f"Campionato {campionato['id']}: {campionato['name']}"
    gare = con.execute(
        "SELECT id, number, name, date, discipline, distance, is_race_to, "
        "playoff_config_id FROM gara WHERE campionato_id = ? "
        "AND deleted_at IS NULL ORDER BY number",
        (campionato["id"],),
    ).fetchall()
    for gara in gare:
        yield (
            f"\n=== Gara {gara['number']} — {gara['name']} ({gara['date']})"
            + (" [PLAYOFF]" if gara["playoff_config_id"] else "")
        )
        partite = con.execute(
            "SELECT m.round_number, m.discipline, m.match_distance, m.is_race_to, "
            "m.started_at, m.ended_at, m.is_trio, "
            "(SELECT COUNT(*) FROM rack r WHERE r.match_id = m.id "
            " AND r.is_deleted = 0) AS rack, "
            "(SELECT MAX(r.added_at) FROM rack r WHERE r.match_id = m.id "
            " AND r.is_deleted = 0) AS ultimo_rack "
            "FROM match m WHERE m.gara_id = ? AND COALESCE(m.is_bye, 0) = 0 "
            "ORDER BY m.round_number, m.id",
            (gara["id"],),
        ).fetchall()
        if not partite:
            yield "  nessuna partita"
            continue
        for numero in sorted({p["round_number"] for p in partite}):
            yield riga_del_turno(
                numero, [p for p in partite if p["round_number"] == numero], gara
            )


def main(argv: Optional[Sequence[str]] = None, out: TextIO = sys.stdout) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("campionato", nargs="?", help="id o parte del nome")
    parser.add_argument("--db", type=Path, default=DB_DI_DEFAULT)
    args = parser.parse_args(argv)

    con = apri(args.db)
    try:
        trovati = campionati(con, args.campionato)
        if args.campionato is None or len(trovati) != 1:
            if args.campionato is not None:
                print(f"{len(trovati)} campionati per «{args.campionato}»:", file=out)
            for c in trovati:
                print(f"{c['id']:>4}  {c['campionato_type']:<16} {c['name']}", file=out)
            if args.campionato is None or not trovati:
                return 0 if args.campionato is None else 1
            print("Ripeti con l'id o con una parte del nome più precisa.", file=out)
            return 1
        for riga in rapporto(con, trovati[0]):
            print(riga, file=out)
        return 0
    finally:
        con.close()


if __name__ == "__main__":
    sys.exit(main())
