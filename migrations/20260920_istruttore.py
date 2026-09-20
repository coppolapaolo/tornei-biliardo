"""Il ruolo di istruttore: la regola ABAC che ne apre la richiesta, e la scuola.

Due cambiamenti, un motivo solo (ADR-069). Nessuna tabella nuova:

* la feature ``request_instructor`` in ``feature_config``, come fece
  ``20260818_add_exam_abac_features`` per l'esaminatore;
* la colonna ``user.organization``: la scuola o l'associazione di chi insegna,
  facoltativa, che compare accanto al nome quando un allievo cerca a chi aprire
  una scheda. Sta sulla **persona** e non sulla richiesta perché è un dato che
  cambia — si cambia scuola senza rifare il percorso del ruolo — e perché è
  l'interessato a doverlo poter correggere. Non è cifrata come il telefono: chi
  la scrive lo fa per farsi trovare.

**Solo condizioni METRIC, mai LEVEL** (ADR-031 §1-2).

⚠️ **Perché la soglia è bassa, e molto più bassa di quella dell'esaminatore.**
Chiedere di diventare esaminatore vuole 20 esercizi completati: è un mestiere
che si fa *dentro* l'app, e quei venti esercizi sono la prova di saperla usare.
Insegnare invece è un mestiere che si fa **in sala**, e il filtro vero non è
una metrica: è che un altro istruttore — o un amministratore — dica di sì. Un
maestro invitato sulla piattaforma dalla sua associazione ha zero di tutto il
primo giorno, e pretendere da lui venti esercizi personali vorrebbe dire
tenerlo fuori per settimane da una cosa che nel frattempo fa davvero.

Restano cinque esercizi, e non zero, perché il pulsante non compaia a chi si è
appena registrato e non ha ancora visto com'è fatta l'area allenamento: una
richiesta mandata senza sapere che cosa si sta chiedendo è lavoro per chi deve
valutarla. La soglia si ritocca da ``/gamification/admin/features`` senza
deploy, con anteprima d'impatto.

Idempotente: ``INSERT`` solo se il codice non c'è già, così rieseguirla non
sovrascrive una soglia che l'admin ha nel frattempo cambiato dalla console.
"""

import json
import sqlite3

migration_name = "20260920_istruttore"


INSTRUCTOR_FEATURE = {
    "code": "request_instructor",
    "name": "Chiedi di diventare istruttore",
    "description": (
        "Chiedere il ruolo di istruttore agli istruttori esistenti "
        "(o ad admin, se non ce n'è ancora nessuno)"
    ),
    "rules": [
        {
            "description": "5+ esercizi completati",
            "conditions": [
                {
                    "type": "METRIC",
                    "metric": "challenges_completed",
                    "operator": "gte",
                    "value": 5,
                }
            ],
        }
    ],
}


def _aggiungi_organization(cursor) -> bool:
    """`ALTER TABLE ADD COLUMN` se non c'è già: SQLite non ha `IF NOT EXISTS`."""
    colonne = {riga[1] for riga in cursor.execute("PRAGMA table_info(user)")}
    if "organization" in colonne:
        return False
    cursor.execute("ALTER TABLE user ADD COLUMN organization VARCHAR(120)")
    return True


def upgrade_sqlite(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        colonna = _aggiungi_organization(cursor)
        cursor.execute(
            """
            INSERT INTO feature_config
                (code, name, description, rules, is_active,
                 created_at, updated_at)
            SELECT ?, ?, ?, ?, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            WHERE NOT EXISTS (
                SELECT 1 FROM feature_config WHERE code = ?
            )
            """,
            (
                INSTRUCTOR_FEATURE["code"],
                INSTRUCTOR_FEATURE["name"],
                INSTRUCTOR_FEATURE["description"],
                json.dumps(INSTRUCTOR_FEATURE["rules"]),
                INSTRUCTOR_FEATURE["code"],
            ),
        )
        seminata = bool(cursor.rowcount)
        conn.commit()
    finally:
        conn.close()

    print(
        "  ✓ user.organization"
        if colonna
        else "  user.organization c'era già: nulla da fare"
    )
    print(
        "  ✓ feature_config: request_instructor"
        if seminata
        else "  feature_config già seminata: nulla da fare"
    )


if __name__ == "__main__":  # pragma: no cover - uso manuale
    upgrade_sqlite("instance/billiard_campionato.db")
