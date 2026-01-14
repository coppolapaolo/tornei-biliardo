# Handoff: Redesign Sistema di Classificazione

**Data**: 2026-01-13 (aggiornato 2026-01-14)
**Sessione**: Analisi e documentazione sistema di classificazione
**Stato**: Validatore backend completato, integrazione e UI da fare

---

## Sommario

È stata condotta un'analisi approfondita del sistema di classificazione per gare e campionati, identificando le dipendenze tra le varie opzioni (sistema classifica, distanza, gestione dispari, forfait, matchmaking) e documentando tutte le combinazioni valide.

---

## Decisioni Prese

### 1. Tre Sistemi di Classifica

| Sistema | Criteri | Matchmaking Compatibile |
|---------|---------|------------------------|
| **RACK** | Rack totali vinti → SSR | Random, Amalfi, Round Robin |
| **WINS** | Match vinti → Diff rack → SSR | Random, Amalfi, Round Robin |
| **POSITION** | Punti per posizione bracket | Eliminazione, Doppio KO |

### 2. Vincoli Chiave

- **RACK**: NO multi-set, preferisce "Exactly N", Bye semplice non permesso
- **WINS**: Tutto permesso, pareggi possibili con "Exactly N pari"
- **POSITION**: Solo eliminazione/doppio KO, solo FORFEIT policy

### 3. Gestione Dispari (5 opzioni)

| Opzione | RACK | WINS | POSITION |
|---------|------|------|----------|
| **NO** (lista attesa) | ✅ | ✅ | ❌ |
| **Trio** (dist 2-5) | ✅ | ✅ | ❌ |
| **Bye semplice** | ❌ | ✅ | Bracket |
| **Bye + Challenge** | ✅ | ✅ | ❌ |
| **Bye + N rack** | ✅ | ❌ | ❌ |

### 4. Distanze Trio Corrette

Range corretto: **2-5** (non 3-7 come precedentemente documentato)

### 5. Campionato

- Tutte le gare DEVONO usare lo stesso sistema di classifica
- Aggregazione = somma classifiche gare
- Punti posizione configurabili per POSITION

### 6. Spareggi

- Configurabili per quali posizioni (es. solo podio)
- Opzioni: SSR o scontro diretto
- Non applicabili a POSITION

---

## File Creati/Modificati

### Nuovi
- `docs/CLASSIFICATION_SYSTEM.md` - Specifiche complete (documento principale)
- `docs/adr/ADR-013-classification-system-redesign.md` - Architecture Decision Record
- `models/competition/validators.py` - Validatore configurazione gara ✅
- `tests/new/unit/test_gara_validation.py` - 56 test TDD ✅

### Modificati
- `docs/SPECIFICHE.md` - Allineato con nuove specifiche, corretto trio 2-5

---

## Cosa È Stato Fatto ✅

### Validatore Backend (completato 2026-01-14)

```python
# models/competition/validators.py
from models.competition.validators import (
    validate_gara_configuration,  # Validazione con enum
    validate_gara,                # Bridge per Gara esistenti
    ClassificationSystem,         # RACK, WINS, POSITION
    DistanceType,                 # RACE_TO, EXACTLY
    OddHandling,                  # NO, TRIO, BYE, BYE_CHALLENGE, BYE_N_RACK, BRACKET_BYE
    ForfeitPolicy,                # EXCLUDE, FORFEIT
    MatchmakingStrategy,          # RANDOM, AMALFI, ROUND_ROBIN, ELIMINATION, DOUBLE_KO
)

# Uso diretto con enum
errors, warnings = validate_gara_configuration(
    classification_system=ClassificationSystem.RACK,
    distance_type=DistanceType.EXACTLY,
    distance=5,
    multi_set=False,
    odd_handling=OddHandling.TRIO,
    forfeit_policy=ForfeitPolicy.EXCLUDE,
    matchmaking=MatchmakingStrategy.AMALFI,
)

# Uso con oggetto Gara esistente (bridge function)
errors, warnings = validate_gara(gara)  # Inferisce classification_system dal matchmaking
errors, warnings = validate_gara(gara, classification_system=ClassificationSystem.RACK)
```

**Test**: 56 test in `tests/new/unit/test_gara_validation.py`

### Integrazione GaraService (completato 2026-01-14)

La validazione è integrata in `GaraService.create_gara()` e `update_gara()`:
- **Errori** → bloccano creazione/modifica (raise ValueError)
- **Warning** → loggati ma non bloccano

```python
# In services.py
from models.competition.validators import validate_gara

classification_errors, classification_warnings = validate_gara(gara)
if classification_errors:
    raise ValueError(f"Configurazione classificazione non valida: {', '.join(classification_errors)}")
```

**Test integrazione**: 6 test aggiuntivi (totale 62 test)

### Model Updates (completato 2026-01-14)

Aggiunti campi per esplicitare il sistema di classificazione:

```python
# models/competition/models.py
class Gara:
    classification_system = db.Column(db.String(10), default="WINS")  # RACK, WINS, POSITION

# models/campionato/models.py
class Campionato:
    default_classification_system = db.Column(db.String(10), default="WINS")
```

**Migrazione**: `migrations/add_classification_system_field.py`
- SQLite: Eseguita automaticamente
- PostgreSQL: Da eseguire in produzione

**Test**: 3 test aggiuntivi (totale 65 test validazione)

---

## Cosa NON È Stato Fatto

### UI Wizard
- Aggiornare wizard campionato/gara per nascondere opzioni incompatibili
- Mostrare warning per combinazioni problematiche (es. RACK + Race to N)

### Migrazione Dati
- Verificare gare esistenti con configurazioni ora invalide
- Decidere strategia migrazione (correzione o flag legacy)

### Opzione NO - Logica Lista Attesa
- Implementare logica che mette in lista attesa chi rende dispari
- Gestire promozione automatica quando arriva altro giocatore

### ~~Model Updates~~ ✅ COMPLETATO
- ~~Aggiungere campo `classification_system` a Gara/Campionato~~ ✅
- Aggiungere campo `odd_handling` con nuove opzioni (opzionale, per opzione NO)
- Aggiungere configurazione spareggi (già esistente: tiebreaker_*)

---

## Domande Aperte Risolte

| Domanda | Risposta |
|---------|----------|
| RACK + Race to N permesso? | Sì, con warning |
| WINS + pareggi? | Sì, 0 vittorie e 0 diff a entrambi |
| Trio con WINS? | Sì, vincitore unico = 1 win, pareggio = 0 wins |
| Distanze trio? | 2, 3, 4, 5 (non 3-7) |
| Gare miste in campionato? | No, tutte devono avere stesso sistema |
| Handicap come funziona? | Aggiunge/toglie rack al match, classificia usa rack effettivi |

---

## Come Riprendere il Lavoro

### ~~Per integrare validazione in GaraService~~ ✅ COMPLETATO
1. ~~Leggere `docs/CLASSIFICATION_SYSTEM.md` sezione 9~~ ✅
2. ~~Creare `models/competition/validators.py`~~ ✅
3. ~~Integrare in `GaraService.create_gara()` e `update_gara()`~~ ✅
4. ~~Aggiungere test~~ ✅ (62 test totali)

### Per implementare opzione NO:
1. Leggere `docs/CLASSIFICATION_SYSTEM.md` sezione 3.5
2. Modificare `models/competition/services.py` - logica iscrizione
3. Aggiornare `Inscription` model se necessario
4. Aggiungere test per scenari lista attesa

### Per aggiornare UI:
1. Modificare `templates/admin/campionato_wizard_step*.html`
2. Aggiungere JavaScript per hide/show dinamico
3. Usare matrice compatibilità da `CLASSIFICATION_SYSTEM.md`

---

## Riferimenti

- **Documento principale**: `docs/CLASSIFICATION_SYSTEM.md`
- **ADR**: `docs/adr/ADR-013-classification-system-redesign.md`
- **Specifiche generali**: `docs/SPECIFICHE.md`
- **ADR trio dettagli**: `docs/adr/ADR-005-distance-classification-trio-rules.md`
- **Modelli classifica**: `models/classification/`
- **Modelli trio**: `models/match/trio_config.py`

---

## Contesto Conversazione

La sessione è partita dalla domanda "come è gestito il sistema di punteggio della classifica di campionato? dipende dal sistema usato per le gare?" e si è evoluta in un'analisi completa delle dipendenze tra:
- Sistema di classifica (RACK/WINS/POSITION)
- Tipo distanza (Race to N / Exactly N)
- Multi-set
- Gestione dispari (NO/Trio/Bye/Bye+Challenge/Bye+N rack)
- Policy forfait (EXCLUDE/FORFEIT)
- Strategia matchmaking

Il risultato è una documentazione completa con 27 combinazioni valide e regole di validazione esplicite.
