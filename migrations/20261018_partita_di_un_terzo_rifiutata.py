"""La partita di altri due con un rifiuto è rifiutata per tutti e due.

Regola del 2026-10-18, decisa dall'utente (ADR-084, emendamento): un rifiuto
basta, e la partita passa a ``individual_match.status = 'rejected'``. Fino a
quella data il rifiuto valeva solo per chi lo faceva, e la partita restava
``in_progress`` per sempre: con una conferma e un rifiuto non c'era nessuno
stato a cui arrivare.

Qui le righe scritte con la regola vecchia rientrano nella nuova: una partita
di un terzo ancora ``in_progress`` con almeno un ``player*_rejected_at`` diventa
``rejected``. Le conferme restano scritte com'erano; chi l'ha segnata la vede
fra le sue partite, marcata «rifiutata», e la corregge o la cancella. Le
altre righe non si toccano: le annullate restano annullate, le sfide normali
non hanno mai un rifiuto scritto lì.

L'ELO non cambia: con la regola vecchia una partita con un rifiuto era già
fuori dall'ELO di tutti e due.

Nessun cambio di schema: la colonna è un ``VARCHAR`` senza vincolo sui valori
(`20260202_individual_match_nullable_distance`). Una tabella o una colonna
assente è un no-op dichiarato, non un errore: una migration che solleva non
viene marcata applicata e `auto_deploy` la ritenta ogni notte per niente.
Rilanciata, non trova più niente da cambiare.
"""

import sqlite3

migration_name = "20261018_partita_di_un_terzo_rifiutata"

#: Il valore di ``MatchStatus.REJECTED``: la colonna salva i valori
#: (``values_callable``), quindi è questo che l'ORM rilegge.
RIFIUTATA = "rejected"
IN_CORSO = "in_progress"

COLONNE_NECESSARIE = {
    "scorer_id",
    "status",
    "player1_rejected_at",
    "player2_rejected_at",
}


def _colonne(cursor, tabella):
    return {riga[1] for riga in cursor.execute(f'PRAGMA table_info("{tabella}")')}


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db") -> None:
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        presenti = _colonne(cursor, "individual_match")
        if not presenti:
            print("  ⏭️  tabella individual_match assente")
            return
        mancanti = COLONNE_NECESSARIE - presenti
        if mancanti:
            print(f"  ⏭️  colonne assenti: {', '.join(sorted(mancanti))}")
            return
        cursor.execute(
            "UPDATE individual_match SET status = ? "
            "WHERE scorer_id IS NOT NULL AND status = ? "
            "AND (player1_rejected_at IS NOT NULL "
            "OR player2_rejected_at IS NOT NULL)",
            (RIFIUTATA, IN_CORSO),
        )
        print(f"  ✓ Partite di un terzo portate a «rifiutata»: {cursor.rowcount}")
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    upgrade_sqlite()
