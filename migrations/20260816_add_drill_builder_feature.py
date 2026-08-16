"""Semina la feature ABAC ``use_drill_builder``.

Il builder è un'alternativa al caricare una foto, non una scorciatoia: chi lo
usa disegna il drill che poi tutti gli altri eseguiranno, e un disegno
sbagliato si propaga a ogni tentativo senza che nessuno possa accorgersene dal
risultato. Per questo ha un gate **suo** e più severo di ``create_challenge``,
invece di ereditarne uno.

Solo condizioni ``METRIC``. ``create_challenge`` chiede anche il livello 5, ma
ADR-031 §1-2 è esplicito: le responsabilità si gattano su metriche d'attività,
mai sul livello — il livello è un riscontro, non una barriera. Non tocco quella
regola qui perché è preesistente e cambiarla di straforo sposterebbe l'accesso
a chi oggi ce l'ha; per la feature nuova si parte giusti.

La soglia è sui drill **completati**, non su quelli creati: si impara a
disegnare un esercizio avendone eseguiti tanti, non avendone pubblicati tanti.
Ritarabile senza deploy da ``/gamification/admin/features``.

Idempotente: l'INSERT è condizionato all'assenza del codice.
"""

import json
import sqlite3

migration_name = "20260816_add_drill_builder_feature"


BUILDER_FEATURE = {
    "code": "use_drill_builder",
    "name": "Disegna un drill",
    "description": (
        "Disegnare la disposizione di un drill col builder, "
        "invece di caricare una foto del tavolo preparato"
    ),
    "rules": [
        {
            "description": "30+ drill completati",
            "conditions": [
                {
                    "type": "METRIC",
                    "metric": "challenges_completed",
                    "operator": "gte",
                    "value": 30,
                }
            ],
        }
    ],
}


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db") -> None:
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
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
                BUILDER_FEATURE["code"],
                BUILDER_FEATURE["name"],
                BUILDER_FEATURE["description"],
                json.dumps(BUILDER_FEATURE["rules"]),
                BUILDER_FEATURE["code"],
            ),
        )
        seeded = bool(cursor.rowcount)
        conn.commit()
    finally:
        conn.close()

    if seeded:
        print("  Seeded feature_config: use_drill_builder")
    else:
        print("  use_drill_builder già seminata: nulla da fare")


if __name__ == "__main__":  # pragma: no cover - uso manuale
    upgrade_sqlite()
