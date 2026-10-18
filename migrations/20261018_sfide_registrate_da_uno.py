"""La sfida contro un giocatore non registrato si chiude da sola.

Regola del 2026-10-18 sera, decisa dall'utente (ADR-085 e ADR-086,
emendamenti): «quando un match con giocatore aggiunto finisce non deve
aspettare la conferma da parte del giocatore aggiunto». La sfida si chiude con
la firma di chi l'ha giocata contro di lui ed è *registrata da uno*:

* `individual_match.recorded_by_id`: chi l'ha registrata. Con lo stato
  ``completed`` (`CLOSED_UNILATERALLY`) distingue la sfida registrata da uno
  dal forfait, che sta nello stesso stato;
* `individual_match.contested_at`: quando chi ha riscattato l'avversario l'ha
  contestata.

Poi le righe scritte con la regola di mezzogiorno (PR #712): una sfida
normale ancora ``in_progress``, firmata da uno solo e che aspetta la firma di
un giocatore non registrato, si chiude come se la regola nuova ci fosse già
stata. Il vincitore lo dice il punteggio, la data di fine è quella della
firma. L'ELO non cambia: quella sfida contava già fra «Tutte», e ci resta.

Le sfide di quella mezza giornata già riscattate non si riconoscono più — il
riscatto ha spostato la partita sull'account vero — e restano da firmare come
una sfida qualunque.

Una tabella o una colonna assente è un no-op dichiarato, non un errore: una
migration che solleva non viene marcata applicata e `auto_deploy` la ritenta
ogni notte per niente. Rilanciata, non trova più niente da cambiare.
"""

import sqlite3

migration_name = "20261018_sfide_registrate_da_uno"

COLONNE = (
    ("individual_match", "recorded_by_id", 'INTEGER REFERENCES "user"(id)'),
    ("individual_match", "contested_at", "DATETIME"),
)

#: I valori persistiti di `MatchStatus` (la colonna salva i valori).
IN_CORSO = "in_progress"
REGISTRATA = "completed"

#: Le sfide normali in corso firmate da uno solo, contro un non registrato
#: che non ha firmato. Il primo giocatore ha firmato e il secondo, non
#: registrato, no — o il contrario.
_CANDIDATE = """
SELECT m.id, m.player1_id, m.player2_id, m.player1_score, m.player2_score,
       m.player1_confirmed, m.player1_confirmed_at, m.player2_confirmed_at
FROM individual_match m
JOIN "user" u1 ON u1.id = m.player1_id
JOIN "user" u2 ON u2.id = m.player2_id
WHERE m.status = ? AND m.scorer_id IS NULL
  AND (
    (m.player1_confirmed = 1 AND m.player2_confirmed = 0
     AND u2.is_placeholder = 1 AND u1.is_placeholder = 0)
    OR
    (m.player2_confirmed = 1 AND m.player1_confirmed = 0
     AND u1.is_placeholder = 1 AND u2.is_placeholder = 0)
  )
"""


def _colonne(cursor, tabella):
    return {riga[1] for riga in cursor.execute(f'PRAGMA table_info("{tabella}")')}


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db") -> None:
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        for tabella, colonna, tipo in COLONNE:
            presenti = _colonne(cursor, tabella)
            if not presenti:
                print(f"  ⏭️  tabella {tabella} assente")
                continue
            if colonna in presenti:
                print(f"  ⏭️  {tabella}.{colonna} già esistente")
                continue
            cursor.execute(f'ALTER TABLE "{tabella}" ADD COLUMN {colonna} {tipo}')
            print(f"  ✓ Aggiunta colonna {tabella}.{colonna}")
        if _colonne(cursor, "individual_match"):
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS ix_individual_match_recorded_by_id "
                "ON individual_match (recorded_by_id)"
            )

        necessarie = {"scorer_id", "recorded_by_id", "player1_confirmed_at"}
        if not necessarie <= _colonne(cursor, "individual_match"):
            print("  ⏭️  individual_match senza le colonne necessarie")
            conn.commit()
            return
        if "is_placeholder" not in _colonne(cursor, "user"):
            print("  ⏭️  user.is_placeholder assente: nessun non registrato")
            conn.commit()
            return

        chiuse = 0
        for (
            match_id,
            p1,
            p2,
            s1,
            s2,
            p1_firmato,
            p1_quando,
            p2_quando,
        ) in cursor.execute(_CANDIDATE, (IN_CORSO,)).fetchall():
            firmatario = p1 if p1_firmato else p2
            quando = p1_quando if p1_firmato else p2_quando
            vincitore = (
                p1 if (s1 or 0) > (s2 or 0) else (p2 if (s2 or 0) > (s1 or 0) else None)
            )
            cursor.execute(
                "UPDATE individual_match SET status = ?, recorded_by_id = ?, "
                "winner_id = ?, ended_at = COALESCE(ended_at, ?, CURRENT_TIMESTAMP) "
                "WHERE id = ? AND status = ?",
                (REGISTRATA, firmatario, vincitore, quando, match_id, IN_CORSO),
            )
            chiuse += cursor.rowcount
        print(f"  ✓ Sfide contro un non registrato chiuse da sole: {chiuse}")
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    upgrade_sqlite()
