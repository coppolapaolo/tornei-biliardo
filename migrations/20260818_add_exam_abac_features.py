"""Semina le due regole ABAC del dominio esame (ADR-042).

Feature: ``take_exam`` (sostenere un esame) e ``request_examiner`` (chiedere il
ruolo di esaminatore). Nessuna tabella nuova: si scrive solo in
``feature_config``, che esiste dalla migration ABAC originale.

**Solo condizioni METRIC, mai LEVEL** — ADR-031 §1-2: le responsabilità si
gattano su metriche d'attività, i livelli sono feedback e non barriera.

⚠️ **Perché la soglia non chiede anche un esame già superato.** Sembrerebbe
sensato pretendere che un aspirante esaminatore abbia sostenuto almeno un
esame, ma è un **deadlock di bootstrap**: per superare un esame certificato
serve un esaminatore, e per diventare esaminatore servirebbe un esame
certificato. Finché admin non nomina il primo titolare a mano nessuno potrebbe
chiedere il ruolo, e anche a regime l'accesso resterebbe legato alla presenza
di un esaminatore in zona. Se un giorno si vorrà pretendere quell'esperienza,
si aggiunge come **secondo ruleset in OR** (``UnlockEngine`` valuta i ruleset
in OR, le condizioni dentro un ruleset in AND), non in AND qui dentro.

Le soglie restano tarabili senza deploy da ``/gamification/admin/features``,
con anteprima d'impatto.

Idempotente: ``INSERT`` solo se il codice non c'è già, così rieseguirla non
sovrascrive una soglia che l'admin ha nel frattempo ritoccato dalla console.
"""

import json
import sqlite3

migration_name = "20260818_add_exam_abac_features"


EXAM_FEATURES = [
    {
        "code": "take_exam",
        "name": "Sostieni un esame",
        "description": (
            "Sostenere un esame: in autonomia come allenamento, "
            "oppure certificato davanti a un esaminatore"
        ),
        "rules": [
            {
                "description": "3+ drill completati",
                "conditions": [
                    {
                        "type": "METRIC",
                        "metric": "challenges_completed",
                        "operator": "gte",
                        "value": 3,
                    }
                ],
            }
        ],
    },
    {
        "code": "request_examiner",
        "name": "Chiedi di diventare esaminatore",
        "description": (
            "Chiedere il ruolo di esaminatore agli esaminatori esistenti "
            "(o ad admin, se non ce n'è ancora nessuno)"
        ),
        "rules": [
            {
                "description": "20+ drill completati",
                "conditions": [
                    {
                        "type": "METRIC",
                        "metric": "challenges_completed",
                        "operator": "gte",
                        "value": 20,
                    }
                ],
            }
        ],
    },
]


def upgrade_sqlite(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        seeded = []
        for feature in EXAM_FEATURES:
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
                    feature["code"],
                    feature["name"],
                    feature["description"],
                    json.dumps(feature["rules"]),
                    feature["code"],
                ),
            )
            if cursor.rowcount:
                seeded.append(feature["code"])
        conn.commit()
    finally:
        conn.close()

    if seeded:
        print(f"  Seeded feature_config: {', '.join(seeded)}")
    else:
        print("  feature_config già seminata: nulla da fare")


if __name__ == "__main__":  # pragma: no cover - uso manuale
    upgrade_sqlite("instance/billiard_campionato.db")
