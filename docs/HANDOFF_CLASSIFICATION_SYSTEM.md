# Handoff: Redesign Sistema di Classificazione

**Data**: 2026-01-13 (aggiornato 2026-01-14)
**Sessione**: Analisi e documentazione sistema di classificazione
**Stato**: ✅ COMPLETATO

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
- `docs/plans/2026-01-14-ui-wizard-classification-design.md` - Design document UI ✅
- `models/competition/validators.py` - Validatore configurazione gara ✅
- `tests/new/unit/test_gara_validation.py` - 71 test validazione ✅
- `tests/new/unit/test_parity_waitlist.py` - 8 test lista attesa parità ✅
- `migrations/add_classification_system_field.py` - Migrazione classification_system ✅
- `migrations/add_waitlist_reason_field.py` - Migrazione waitlist_reason ✅
- `scripts/verify_classification_configs.py` - Script verifica configurazioni ✅

### Modificati
- `docs/SPECIFICHE.md` - Allineato con nuove specifiche, corretto trio 2-5
- `models/competition/models.py` - Aggiunto `classification_system`, `WaitlistReason`, `waitlist_reason`
- `models/campionato/models.py` - Aggiunto `default_classification_system`
- `models/campionato/services.py` - Aggiunto parametro `default_classification_system` ✅
- `models/competition/inscription_service.py` - Logica lista attesa parità
- `models/matchmaking/configuration.py` - Aggiunto `NO` a `OddNumberPolicy`
- `routes/admin/campionato.py` - Gestione classification_system nel wizard ✅
- `templates/admin/campionato_wizard_step1.html` - Select sistema classifica ✅
- `templates/admin/campionato_wizard_step2.html` - Filtro odd_policies, opzione NO ✅
- `templates/components/_gara_edit_form.html` - Campo classification_system ✅
- `templates/admin/gara_edit.html` - JS filtraggio odd_policies ✅

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

### Opzione NO - Lista Attesa Parità (completato 2026-01-14)

Implementata la logica per gestire i numeri dispari con lista d'attesa basata sulla parità.

```python
# models/matchmaking/configuration.py
class OddNumberPolicy(str, Enum):
    NO = "no"  # Parity waitlist - nuovo!
    BYE = "bye"
    BYE_WITH_CHALLENGE = "bye_with_challenge"
    TRIO = "trio"

# models/competition/models.py
class WaitlistReason(str, Enum):
    CAPACITY = "capacity"  # max_participants superato
    PARITY = "parity"      # odd_number_policy="no"

class Inscription:
    waitlist_reason = db.Column(db.String(20), nullable=True)
```

**Logica iscrizione** (`inscription_service.py`):
- Se odd_number_policy="no" e count diventa dispari → waitlist PARITY
- Se odd_number_policy="no" e c'è qualcuno in parity waitlist → promuovi
- Ordine: prima capacità, poi parità

**Migrazione**: `migrations/add_waitlist_reason_field.py`
- SQLite: Eseguita automaticamente
- PostgreSQL: Da eseguire in produzione

**Test**: 8 test in `tests/new/unit/test_parity_waitlist.py`

### UI Wizard (completato 2026-01-14)

Implementata selezione sistema di classificazione nel wizard e form gara con filtraggio opzioni.

**Step 1 - Sistema Classifica:**
- Nuovo select "Sistema di Classifica" (WINS, RACK, POSITION)
- Filtro automatico matchmaking in base al sistema
- Descrizioni dinamiche per ogni opzione

**Step 2 - Gestione Dispari:**
- Opzioni filtrate in base al sistema scelto
- WINS: NO, Bye, Bye+Challenge, Trio
- RACK: NO, Bye+Challenge, Trio (no Bye semplice)
- Aggiunta opzione NO (lista attesa parità)

**Form Gara:**
- Sistema classifica readonly se gara in campionato
- Sistema classifica editabile se gara standalone
- Filtraggio odd_policies in base al sistema
- Aggiunta opzione NO

**File modificati:**
- `templates/admin/campionato_wizard_step1.html`
- `templates/admin/campionato_wizard_step2.html`
- `templates/components/_gara_edit_form.html`
- `templates/admin/gara_edit.html`
- `routes/admin/campionato.py`
- `models/campionato/services.py`

**Design document:** `docs/plans/2026-01-14-ui-wizard-classification-design.md`

---

## Cosa NON È Stato Fatto

### ~~UI Wizard~~ ✅ COMPLETATO
- ~~Aggiornare wizard campionato/gara per nascondere opzioni incompatibili~~
- ~~Mostrare warning per combinazioni problematiche (es. RACK + Race to N)~~

### ~~Migrazione Dati~~ ✅ COMPLETATO (2026-01-14)

**Risultato analisi:**
- 3 gare nel database di sviluppo
- 1 campionato
- ✅ Tutte le configurazioni sono già valide (classification_system=WINS)
- ❌ Nessuna migrazione correttiva necessaria

**Script di verifica creato:** `scripts/verify_classification_configs.py`
- Verifica tutte le gare contro le regole di validazione
- Opzione `--fix` per correzioni automatiche
- Può essere usato in produzione prima del deploy

### ~~Opzione NO - Logica Lista Attesa~~ ✅ COMPLETATO
- ~~Implementare logica che mette in lista attesa chi rende dispari~~ ✅
- ~~Gestire promozione automatica quando arriva altro giocatore~~ ✅

### ~~Model Updates~~ ✅ COMPLETATO
- ~~Aggiungere campo `classification_system` a Gara/Campionato~~ ✅
- ~~Aggiungere campo `waitlist_reason` a Inscription~~ ✅ (per opzione NO)
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

### ~~Per implementare opzione NO~~ ✅ COMPLETATO
1. ~~Leggere `docs/CLASSIFICATION_SYSTEM.md` sezione 3.5~~ ✅
2. ~~Modificare `models/competition/inscription_service.py` - logica iscrizione~~ ✅
3. ~~Aggiornare `Inscription` model con `waitlist_reason`~~ ✅
4. ~~Aggiungere test per scenari lista attesa~~ ✅ (8 test)

### ~~Per aggiornare UI~~ ✅ COMPLETATO
1. ~~Modificare `templates/admin/campionato_wizard_step*.html`~~ ✅
2. ~~Aggiungere JavaScript per hide/show dinamico~~ ✅
3. ~~Usare matrice compatibilità da `CLASSIFICATION_SYSTEM.md`~~ ✅

### ~~Per migrazione dati~~ ✅ COMPLETATO
1. ~~Verificare gare esistenti con configurazioni ora invalide~~ ✅ (tutte valide)
2. ~~Decidere strategia migrazione~~ ✅ (nessuna necessaria)
3. ~~Script per verifica/aggiornamento~~ ✅ `scripts/verify_classification_configs.py`

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
