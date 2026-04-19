# ADR-002 Bug Fix: Anti-Rematch Encounter Cleanup

**Data**: 2025-12-28
**Stato**: Accepted (superseded in part by [ADR-026](ADR-026-reset-match-preserves-pair-semantics.md) per la parte `reset_match_complete`; la parte `cancel_round` resta valida)
**Tipo**: Bug Fix

## Problema Riscontrato

In una gara Amalfi con `anti_rematch_enabled=True`, venivano generati match tra gli stessi giocatori nonostante l'opzione anti-rematch fosse attiva. Il bug si verificava dopo operazioni di reset (match reset o round cancel).

### Comportamento Atteso
Secondo le specifiche, con anti-rematch abilitato:
- Due giocatori non devono mai essere abbinati più di una volta nella stessa gara
- Se un match viene resettato o un round cancellato, i giocatori devono poter essere nuovamente abbinati

### Comportamento Osservato
Dopo reset di match o cancellazione di round:
- I record `PlayerEncounter` rimanevano nel database
- L'anti-rematch bloccava abbinamenti che dovevano essere validi
- Oppure, in altri scenari, permetteva re-match perché il sistema era in stato inconsistente

### Passi per Riprodurre
1. Creare gara Amalfi con anti-rematch attivo
2. Avviare round 1, completare alcuni match
3. Resettare un match o cancellare il round
4. Generare nuovi abbinamenti
5. L'anti-rematch poteva avere dati inconsistenti

## Analisi Root Cause

Il problema era nella gestione dei record `PlayerEncounter`:

1. **Record creato**: Quando un match viene completato (`MatchService.to_completed()`), viene registrato un `PlayerEncounter` via `record_match_encounters()`

2. **Record MAI eliminato**: Né `RackService.reset_match_complete()` né `AdvancedRoundManager.cancel_round()` eliminavano i record `PlayerEncounter`

3. **Conseguenza**: Dati orfani nel database che influenzavano la logica anti-rematch

### Codice Problematico

```python
# round_manager.py - cancel_round()
# Eliminava solo classifiche, non encounter:
RoundClassification.query.filter_by(
    gara_id=gara_id, round_number=round_number
).delete()
# PlayerEncounter NON veniva toccato!

# match/services.py - reset_match_complete()
# Eliminava rack e resettava score, ma non encounter
```

## Soluzione Implementata

### 1. Nuovi metodi in `PlayerEncounter`

Aggiunti due metodi per eliminare encounter:

```python
# models/classification/models.py

@staticmethod
@transactional(domain="classification")
def delete_encounter(gara_id: int, player1_id: int, player2_id: int) -> bool:
    """Delete encounter for single match reset."""

@staticmethod
@transactional(domain="classification")
def delete_round_encounters(gara_id: int, round_number: int) -> int:
    """Delete all encounters for round cancellation."""
```

### 2. Modifiche ai servizi

**`RackService.reset_match_complete()`** - ora elimina l'encounter:
```python
if match.player2_id:
    PlayerEncounter.delete_encounter(
        gara_id=match.gara_id,
        player1_id=match.player1_id,
        player2_id=match.player2_id
    )
```

**`AdvancedRoundManager.cancel_round()`** - ora elimina tutti gli encounter del round:
```python
PlayerEncounter.delete_round_encounters(gara_id, round_number)
```

## Test di Regressione

Creati in `tests/new/unit/test_anti_rematch_regression.py`:

- `test_encounter_cleanup_on_match_reset`: Verifica che l'encounter venga eliminato dopo reset match
- `test_encounter_cleanup_on_round_cancel`: Verifica che gli encounter vengano eliminati dopo cancel round
- `test_player_encounter_have_played_returns_true_after_match`: Test unitario base
- `test_amalfi_strategy_respects_encounter_history`: Test integrazione strategia Amalfi

## Note Aggiuntive

### Vincolo Matematico (Miglioramento Futuro)

Con k giocatori, il numero massimo di round senza rematch è k-1. Questo vincolo non è attualmente validato alla creazione della gara. Un test `xfail` documenta questo miglioramento futuro:

```
- 8 giocatori → max 7 round senza rematch
- 6 giocatori → max 5 round senza rematch
- 4 giocatori → max 3 round senza rematch
```

### Impatto

- Nessun breaking change nelle API
- Migliora la consistenza dei dati
- Previene bug futuri con operazioni di reset/cancel
