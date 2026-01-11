# Handoff: Creare Test per Use Case Mancanti

## Contesto

Durante il cleanup del 11 Gennaio 2026, sono stati rimossi 19 test di integrazione che fallivano per problemi di SQLite concurrency e session isolation. Tra questi, i test per gli use case 1, 2, 3, 5, 6, 8 documentati in `docs/usecases/gare.md`.

**Use case con test funzionanti:**
- UC 4: `test_gare_usecase_4_campionato_workflow.py` (3 passed, 1 skipped)
- UC 7: `test_gare_usecase_7_player_availability.py` (3 passed)

**Use case senza test:**
- UC 1: Amalfi complete workflow (3 turni, anti-rematch, challenge tiebreaker)
- UC 2: Random strategy (challenge dopo turno, cambio disciplina)
- UC 3: Round-robin (multi-set matches)
- UC 5: Guest access (visualizzazione risultati live)
- UC 6: Individual match (proposta match tra player)
- UC 8: Match modification (reset match, annulla turno)

## Vincoli Architetturali

**NON MODIFICARE:**
- Il decorator `@transactional` nei service - è un requisito architetturale
- La struttura del TransactionManager in `models/transaction/manager.py`

**Il problema NON è `@transactional`**, ma l'interazione con:
- SQLite che non gestisce bene la concorrenza (`-n auto` causa deadlock)
- Test troppo lunghi e complessi che fanno timeout

## Pattern da Seguire

Basato su `test_gare_usecase_4_campionato_workflow.py` che funziona:

### 1. Fixture con commit esplicito
```python
@pytest.fixture
def players_6(db_session) -> List[User]:
    batch_id = str(uuid.uuid4())[:8]
    players = []
    for i in range(6):
        player = User(
            username=f"player_{i}_{batch_id}",
            email=f"player_{i}_{batch_id}@test.com",
            role=UserRole.PLAYER.value,
        )
        player.set_password("player123")
        players.append(player)

    db_session.add_all(players)
    db_session.commit()  # IMPORTANTE: commit esplicito
    return players
```

### 2. Test brevi e focalizzati
```python
# MALE: un test che fa tutto
def test_complete_amalfi_workflow_with_all_rounds_and_challenges():
    # 200+ righe, timeout garantito

# BENE: test separati per ogni aspetto
def test_amalfi_first_round_random_pairing():
    # 30-50 righe, focalizzato

def test_amalfi_second_round_respects_anti_rematch():
    # 30-50 righe, focalizzato

def test_amalfi_challenge_resolves_tiebreaker():
    # 30-50 righe, focalizzato
```

### 3. Helper methods per operazioni comuni
```python
def _complete_match_simple(self, match: Match, db_session) -> None:
    """Complete a match with random results."""
    winner_id = match.player1_id if random.choice([True, False]) else match.player2_id
    # ... logica semplificata
    MatchService.to_completed(match.id)
```

### 4. Esecuzione con -n 4
```bash
pytest tests/new/integration -n 4 --tb=short
# MAI usare -n auto per integration tests
```

## Use Case da Implementare

### UC 1: Amalfi Complete Workflow
Scomporre in:
1. `test_amalfi_gara_creation_with_3_rounds` - creazione gara con parametri corretti
2. `test_amalfi_inscription_and_waitlist` - 8 iscritti, variante 11 con waitlist
3. `test_amalfi_first_round_random_pairing` - primo turno abbinamento casuale
4. `test_amalfi_anti_rematch_enforcement` - secondo/terzo turno senza rematch
5. `test_amalfi_classification_ordering` - ordinamento (vinti, diff rack, ordine precedente)
6. `test_amalfi_challenge_tiebreaker` - challenge per parità nei primi 3

### UC 2: Random Strategy
1. `test_random_gara_with_discipline_change` - cambio disciplina per turno
2. `test_random_challenge_after_round` - challenge inserite dopo primo turno
3. `test_random_trio_odd_handling` - gestione dispari con trio
4. `test_random_three_way_tiebreaker` - parità tra 3 giocatori

### UC 3: Round-Robin
1. `test_round_robin_all_vs_all_pairing` - tutti giocano contro tutti
2. `test_round_robin_multi_set_scoring` - match con set multipli
3. `test_round_robin_live_classification_update` - classifica aggiornata dopo ogni match

### UC 5: Guest Access
1. `test_guest_can_view_campionato_info` - info campionato visibili senza login
2. `test_guest_can_view_completed_gara_results` - risultati gare finite
3. `test_guest_can_view_live_match_scores` - risultati in tempo reale (SSE)

### UC 6: Individual Match
1. `test_player_can_propose_individual_match` - proposta match
2. `test_both_players_validate_scores` - validazione punteggi reciproca
3. `test_director_can_propose_match` - variante director

### UC 8: Match Modification
1. `test_reset_match_reopens_round` - reset match riapre turno
2. `test_modify_match_recalculates_classification` - modifica ricalcola classifica
3. `test_cannot_modify_locked_round` - turni passati non modificabili
4. `test_cancel_round_enables_previous_modifications` - annulla turno sblocca precedente

## File da Creare

```
tests/new/integration/
├── test_gare_usecase_1_amalfi.py       # 6 test
├── test_gare_usecase_2_random.py       # 4 test
├── test_gare_usecase_3_round_robin.py  # 3 test
├── test_gare_usecase_5_guest.py        # 3 test
├── test_gare_usecase_6_individual.py   # 3 test
└── test_gare_usecase_8_modification.py # 4 test
```

## Verifica Post-Implementazione

```bash
# Eseguire tutti i test di integrazione
pytest tests/new/integration -n 4 --tb=short -q

# Risultato atteso: tutti i nuovi test passano
# Se un test fallisce intermittentemente, scomporlo ulteriormente
```

## Note

- Riferimento documentazione use case: `docs/usecases/gare.md`
- Pattern di riferimento: `tests/new/integration/test_gare_usecase_4_campionato_workflow.py`
- Ogni test deve essere indipendente e non dipendere da altri test
- Usare `uuid.uuid4()[:8]` per generare ID unici nei nomi utente/email
