"""Presidio: la mappa dello spostamento copre tutte le tabelle della gara.

`GaraParticipantReassignService` non può basarsi su un elenco scritto a memoria.
Questo test cammina il grafo delle chiavi esterne partendo da `gara` e pretende
che ogni tabella con una colonna verso `user.id`, raggiungibile dalla gara, sia
**classificata**: spostata, cancellata o esclusa con un motivo scritto.

Una tabella nuova che nessuno classifica fa diventare rosso questo test, non
lascia lo script a spostare metà partecipazione in silenzio.
"""

from models.base import db
from models.competition.participant_reassign_service import (
    _DELETE_SOURCE_SCOPES,
    _GARA_SCOPES,
    _SKIPPED_TABLES,
    GaraParticipantReassignService,
)

#: Quanti salti al massimo consideriamo "appartenente alla gara". Oltre, il
#: legame è troppo indiretto per essere partecipazione (es. campionato → gara).
_MAX_DEPTH = 3


def _tables_reachable_from_gara() -> set:
    """Tabelle che raggiungono `gara` seguendo le FK, entro `_MAX_DEPTH` salti."""
    reachable = {"gara"}
    for _ in range(_MAX_DEPTH):
        frontier = set()
        for table in db.metadata.sorted_tables:
            if table.name in reachable:
                continue
            for col in table.columns:
                for fk in col.foreign_keys:
                    if fk.column.table.name in reachable:
                        frontier.add(table.name)
        if not frontier:
            break
        reachable |= frontier
    return reachable


def _tables_with_user_fk() -> set:
    return {
        table.name
        for table, _ in GaraParticipantReassignService._user_fk_columns()
        if table.name != "user"
    }


def test_ogni_tabella_della_gara_e_classificata(app):
    with app.app_context():
        candidate = _tables_reachable_from_gara() & _tables_with_user_fk()
        classificate = (
            set(_GARA_SCOPES) | set(_DELETE_SOURCE_SCOPES) | set(_SKIPPED_TABLES)
        )
        non_classificate = candidate - classificate
        assert not non_classificate, (
            "Tabelle raggiungibili dalla gara con una colonna utente e non "
            f"classificate: {sorted(non_classificate)}. Vanno aggiunte a "
            "_GARA_SCOPES, _DELETE_SOURCE_SCOPES o _SKIPPED_TABLES (con motivo)."
        )


def test_la_mappa_non_cita_tabelle_inesistenti(app):
    with app.app_context():
        note = set(db.metadata.tables)
        for nome in set(_GARA_SCOPES) | set(_DELETE_SOURCE_SCOPES):
            assert nome in note, f"_GARA_SCOPES cita una tabella inesistente: {nome}"


def test_ogni_esclusione_ha_un_motivo(app):
    for tabella, motivo in _SKIPPED_TABLES.items():
        assert motivo.strip(), f"L'esclusione di {tabella} è senza motivo"


def test_le_scope_producono_sql_valido(app):
    """Ogni funzione di restrizione deve compilare contro la tabella reale."""
    with app.app_context():
        for nome, scope in _GARA_SCOPES.items():
            table = db.metadata.tables[nome]
            clause = scope(table, 1)
            assert str(clause), f"scope di {nome} non compila"
