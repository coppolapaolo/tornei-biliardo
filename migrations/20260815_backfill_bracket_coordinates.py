"""Backfill conservativo delle coordinate di tabellone sul primo turno.

Le gare a eliminazione diretta o doppio KO create **prima** di
``20260809_bracket_and_squadre`` hanno ``bracket_type`` NULL su tutti i match:
il tabellone non esisteva come dato. Le strategie sanno gia' conviverci — c'e'
un ramo legacy che accoppia come si faceva prima — ma una gara appena
sorteggiata e non ancora giocata puo' ricevere le coordinate senza che nulla
di quel che i giocatori hanno visto cambi, e da li' in poi avanzare secondo il
tabellone invece che secondo l'ordine di ritorno della query.

**Perche' solo il primo turno, e solo se non e' ancora arrivato il secondo.**
Ricostruire un tabellone e applicarlo a turni gia' giocati con altri
accoppiamenti produrrebbe un tabellone *falso*: direbbe che il vincitore dello
slot 2 ha incontrato quello dello slot 3 quando in realta' ha incontrato un
altro. Meglio nessun dato che un dato inventato — quelle gare restano NULL e
continuano sul ramo legacy fino alla fine.

Condizioni perche' una gara venga toccata (tutte, non alcune):

- strategia a tabellone (``direct_elimination`` o ``double_knockout``);
- ``current_round <= 1`` e **nessun match** di turno >= 2;
- nessun match del turno 1 ha gia' delle coordinate (idempotenza);
- nessun trio nel turno 1: nei tabelloni i trio non esistono, e trovarne uno
  significa che quella gara non e' il tabellone che sembra;
- il numero di nodi del turno 1 e' una **potenza di 2**. E' l'invariante di un
  albero completo: se non torna, il turno 1 non era un tabellone pieno (tipico
  del vecchio codice, che per i bye non materializzava un nodo) e assegnare
  slot sarebbe inventare una struttura che non c'e'.

Gli slot vengono assegnati per ``id`` crescente, che e' l'ordine in cui i
match sono stati creati. Non e' il sorteggio originale — quello non e' piu'
ricostruibile, non essendo mai stato scritto — ma e' *un* tabellone coerente,
ed e' tutto cio' che serve: nessuno di quei nodi ha ancora prodotto un
avanzamento.
"""

import os
import sqlite3
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

migration_name = "20260815_backfill_bracket_coordinates"

BRACKET_STRATEGIES = ("direct_elimination", "double_knockout")


def _is_power_of_two(value: int) -> bool:
    return value > 0 and value & (value - 1) == 0


def _candidate_gare(cursor: sqlite3.Cursor):
    """Gare a tabellone ferme al primo turno, in ordine di id."""
    placeholders = ",".join("?" for _ in BRACKET_STRATEGIES)
    cursor.execute(
        f"""
        SELECT id FROM gara
         WHERE matchmaking_strategy IN ({placeholders})
           AND COALESCE(current_round, 0) <= 1
         ORDER BY id
        """,
        BRACKET_STRATEGIES,
    )
    return [row[0] for row in cursor.fetchall()]


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # La migration dello schema deve essere gia' passata: senza le colonne non
    # c'e' nulla da riempire, e fallire qui sarebbe piu' chiaro che scrivere a
    # meta'.
    cursor.execute("PRAGMA table_info(match)")
    colonne = {row[1] for row in cursor.fetchall()}
    if not {"bracket_type", "bracket_round", "bracket_slot"} <= colonne:
        print(
            "  ⏭️  colonne di tabellone assenti: esegui prima la migration dello schema"
        )
        conn.close()
        return

    aggiornate, saltate = 0, 0

    for gara_id in _candidate_gare(cursor):
        cursor.execute(
            """
            SELECT id, round_number, bracket_type, is_trio
              FROM match
             WHERE gara_id = ?
             ORDER BY id
            """,
            (gara_id,),
        )
        righe = cursor.fetchall()
        if not righe:
            continue

        primo_turno = [r for r in righe if (r[1] or 1) == 1]
        oltre = [r for r in righe if (r[1] or 1) >= 2]

        motivo = None
        if oltre:
            motivo = "ha già turni successivi"
        elif any(r[2] for r in primo_turno):
            motivo = "coordinate già presenti"
        elif any(r[3] for r in primo_turno):
            motivo = "contiene un trio"
        elif not _is_power_of_two(len(primo_turno)):
            motivo = f"{len(primo_turno)} nodi al turno 1 (non è un albero pieno)"

        if motivo:
            saltate += 1
            print(f"  ⏭️  gara {gara_id}: {motivo}")
            continue

        for slot, riga in enumerate(primo_turno):
            cursor.execute(
                """
                UPDATE match
                   SET bracket_type = 'W', bracket_round = 1, bracket_slot = ?
                 WHERE id = ?
                """,
                (slot, riga[0]),
            )
        aggiornate += 1
        print(f"  ✓ gara {gara_id}: {len(primo_turno)} nodi con coordinate")

    conn.commit()
    conn.close()
    print(
        f"  ✓ Backfill completato: {aggiornate} gare aggiornate, "
        f"{saltate} lasciate com'erano"
    )


if __name__ == "__main__":
    upgrade_sqlite()
