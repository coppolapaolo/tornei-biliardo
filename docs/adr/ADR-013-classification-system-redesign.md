# [013] Redesign Sistema di Classificazione

**Data**: 2026-01-13
**Stato**: Accepted
**Decisori**: Paolo, Claude

## Contesto

Il sistema di classificazione esistente aveva diverse ambiguità e configurazioni implicite:
- Non era chiaro quali combinazioni di opzioni fossero valide
- Il trio era documentato con distanze 3-7, ora supporta distanze 2-7
- Mancava una visione complessiva delle dipendenze tra le varie opzioni
- La gestione dispari aveva opzioni limitate

### Problemi identificati

1. **Sistemi di classifica non formalizzati**: Il codice supportava sia classifiche basate su rack che su vittorie, ma senza una chiara separazione e documentazione.

2. **Vincoli impliciti**: Ad esempio, il sistema RACK non funziona bene con "Race to N" perché chi perde di misura accumula più rack.

3. **Gestione dispari limitata**: Solo Bye e Trio, senza opzioni come "nessuna gestione" o "Bye con punteggio fisso".

4. **Spareggi non configurabili**: Non era chiaro come e quando applicare gli spareggi.

5. **Campionato con gare miste**: Non era esplicitato che tutte le gare devono usare lo stesso sistema.

## Decisione

### 1. Tre Sistemi di Classifica Formali

| Sistema | Criteri | Uso |
|---------|---------|-----|
| **RACK** | Rack totali vinti ↓, SSR | Gare dove conta ogni rack |
| **WINS** | Match vinti ↓, Diff rack ↓, SSR | Gare tradizionali |
| **POSITION** | Punti per posizione nel bracket | Eliminazione, Doppio KO |

### 2. Matrice di Compatibilità

| Opzione | RACK | WINS | POSITION |
|---------|------|------|----------|
| **Distanza: Exactly N (qualsiasi)** | ✅ preferita | ✅ (pari = pareggi) | ❌ |
| **Distanza: Race to N** | ⚠️ warning | ✅ | ✅ |
| **Distanza: Exactly N dispari** | ✅ | ✅ | ✅ |
| **Multi-set** | ❌ | ✅ | ✅ |
| **Dispari: NO** | ✅ | ✅ | ❌ |
| **Dispari: Trio** | ✅ (dist 2-5) | ✅ (dist 2-5) | ❌ |
| **Dispari: Bye** | ❌ | ✅ | Bracket |
| **Dispari: Bye+Challenge** | ✅ | ✅ | ❌ |
| **Dispari: Bye+N rack** | ✅ | ❌ | ❌ |
| **Forfait: EXCLUDE** | ✅ | ✅ | ❌ |
| **Forfait: FORFEIT** | ✅ | ✅ | ✅ (solo) |
| **Matchmaking: Random/Amalfi/RR** | ✅ | ✅ | ❌ |
| **Matchmaking: Eliminazione/Doppio KO** | ❌ | ❌ | ✅ |

### 3. Nuova Opzione: NO (Nessuna gestione dispari)

Quando abilitata:
- Se un giocatore si iscrive e rende il numero dispari → va in lista d'attesa
- Resta in attesa finché non si iscrive un altro giocatore
- Modifica la logica della lista d'attesa esistente

### 4. Bye con Punteggio Fisso (solo RACK)

- Alternativa semplice a Bye+Challenge
- Assegna automaticamente N rack (distanza)
- Equivalente a "vincere senza giocare"

### 5. Distanze Trio Corrette

Il trio è possibile per distanze **2, 3, 4, 5, 6, 7**.

| Distanza | Mini gironi | Rack/giocatore | Punteggio RACK |
|----------|-------------|----------------|----------------|
| 2 | 1 | 2 | rack vinti |
| 3 | 1 | 2 | 1 + rack vinti |
| 4 | 2 | 4 | rack vinti |
| 5 | 2 | 4 | 1 + rack vinti |
| 6 | 3 | 6 | rack vinti |
| 7 | 3 | 6 | 1 + rack vinti |

### 6. Trio con Sistema WINS

Precedentemente il trio era considerato solo per RACK. Ora è supportato anche per WINS:
- **Vincitore unico** (score massimo non condiviso): 1 vittoria
- **Pareggio**: 0 vittorie a tutti
- Diff rack sempre calcolata dai risultati effettivi

### 7. Spareggi Configurabili

- **Posizioni**: configurabile per quali posizioni applicare (es. solo podio, tutte, ecc.)
- **Metodi**: SSR (Spot Shot Rally) o scontro diretto
- Non applicabile a POSITION (bracket determina)

### 8. Campionato: Vincolo Omogeneità

Tutte le gare di un campionato DEVONO usare lo stesso sistema di classifica.

- Aggregazione: somma delle classifiche delle singole gare
- Non permesse gare miste (RACK + WINS nello stesso campionato)

### 9. Pareggi in WINS (Exactly N pari)

Per "Exactly N" con N pari:
- Pareggi possibili (es. 3-3 in Exactly 6)
- Entrambi i giocatori ricevono: 0 vittorie, 0 diff rack
- Permesso ma non raccomandato

### 10. RACK + Race to N (con warning)

Permesso ma con warning esplicito:
- Chi perde di misura (es. 4-5) accumula più rack di chi vince nettamente (5-0)
- Comportamento potenzialmente controintuitivo
- Director deve confermare esplicitamente

## Alternative Considerate

### Alternativa 1: Sistemi separati non intercambiabili

Creare implementazioni completamente separate per ogni sistema.

- **Pro**: Più semplice da capire
- **Contro**: Duplicazione codice, difficile manutenzione

### Alternativa 2: Un solo sistema flessibile

Usare sempre WINS con configurazioni diverse.

- **Pro**: Meno complessità
- **Contro**: Non copre tutti i casi d'uso (es. gare dove ogni rack conta)

### Alternativa 3: Vietare combinazioni problematiche

Invece di permettere con warning, vietare completamente RACK + Race to N.

- **Pro**: Nessuna confusione
- **Contro**: Limita flessibilità per tornei che lo vogliono consapevolmente

## Conseguenze

### Positive

- Sistema coerente e ben documentato
- Validazioni esplicite prevengono configurazioni invalide
- Più flessibilità con nuove opzioni (NO, Bye+N rack)
- Chiarezza su come aggregare classifiche campionato

### Negative

- Complessità iniziale per capire tutte le opzioni
- Possibile necessità di migrazione per gare esistenti con configurazioni ora invalide
- UI più complessa per mostrare solo opzioni valide

### Rischi

- Gare esistenti potrebbero avere configurazioni implicite diverse
- Performance validazione se fatta ad ogni operazione

## Note Implementative

### File Creati/Modificati

1. **Nuovo**: `docs/CLASSIFICATION_SYSTEM.md`
   - Documentazione completa del sistema
   - Matrice combinazioni valide
   - Schema decisionale

2. **Modificato**: `docs/SPECIFICHE.md`
   - Aggiornate distanze trio (2-7)
   - Aggiunta sezione sistemi di classifica
   - Aggiornata gestione dispari
   - Aggiornata gestione forfait

3. **Da implementare**: Validazione backend
   ```python
   # models/competition/validators.py
   def validate_gara_configuration(
       classification_system: str,
       distance_type: str,
       distance: int,
       multi_set: bool,
       odd_handling: str,
       forfeit_policy: str,
       matchmaking: str
   ) -> list[str]:  # Returns list of errors/warnings
   ```

4. **Da implementare**: UI Wizard
   - Nascondere opzioni incompatibili dinamicamente
   - Mostrare warning per combinazioni permesse ma problematiche

### Migrazione

Per gare esistenti:
1. Verificare quali usano configurazioni ora documentate come invalide
2. Se presenti, decidere se:
   - Migrarle a configurazione valida più vicina
   - Mantenerle con flag "legacy"

## Riferimenti

- `docs/CLASSIFICATION_SYSTEM.md` - Documentazione completa
- `docs/SPECIFICHE.md` - Specifiche aggiornate
- ADR-005 - Regole distanza, classifica e trio (superseded parzialmente)
- `models/classification/` - Implementazione esistente
- `models/match/trio_config.py` - Configurazione trio
