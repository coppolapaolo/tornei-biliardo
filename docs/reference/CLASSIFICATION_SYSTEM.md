# Sistema di Classificazione

Questo documento definisce il sistema di classificazione per gare e campionati.

## Indice

1. [Sistemi di Classifica](#1-sistemi-di-classifica)
2. [Vincoli per Sistema](#2-vincoli-per-sistema)
3. [Gestione Dispari](#3-gestione-dispari)
4. [Forfait](#4-forfait)
5. [Spareggi (Tiebreaker)](#5-spareggi-tiebreaker)
6. [Handicap](#6-handicap)
7. [Campionato](#7-campionato)
8. [Matchmaking](#8-matchmaking)
9. [Regole di Validazione](#9-regole-di-validazione)
10. [Combinazioni Valide](#10-combinazioni-valide)
11. [Schema Decisionale](#11-schema-decisionale)

---

## 1. Sistemi di Classifica

Esistono **3 sistemi di classifica** mutuamente esclusivi:

| Sistema | Criteri ordinamento | Uso tipico |
|---------|---------------------|------------|
| **RACK** | 1) Rack totali vinti ↓ 2) Spareggio | Gare con focus su rack accumulati |
| **WINS** | 1) Match vinti ↓ 2) Diff rack ↓ 3) Spareggio | Gare con focus su vittorie |
| **POSITION** | Punti per posizione nel tabellone | Eliminazione / Doppio KO |

### 1.1 Sistema RACK

Ordina i giocatori per **rack totali vinti** (decrescente).

- **Uso**: Gare dove ogni rack conta, indipendentemente da vittorie/sconfitte.
- **Filosofia**: Premia l'accumulo costante di rack.

### 1.2 Sistema WINS

Ordina i giocatori per:
1. **Match vinti** (decrescente)
2. **Differenza rack** (rack vinti - rack persi, decrescente)
3. Spareggio se necessario

- **Uso**: Gare tradizionali dove vincere il match è prioritario.
- **Filosofia**: Prima conta vincere, poi conta il margine.

### 1.3 Sistema POSITION

Assegna **punti per posizione** nel tabellone di eliminazione.

- **Uso**: Tornei a eliminazione diretta o doppio KO.
- **Configurazione**: Punti per posizione configurabili a livello campionato.
- **Esempio**: 1° = 25, 2° = 18, 3° = 15, 4° = 12, 5°-8° = 8, ecc.
- **Gara standalone**: Non servono punti, la classifica è determinata dal tabellone.

---

## 2. Vincoli per Sistema

### 2.1 Distanza

| Sistema | Distanze permesse | Note |
|---------|-------------------|------|
| **RACK** | Exactly N (qualsiasi) | Tutti giocano lo stesso numero di rack |
| **RACK** | Race to N | ⚠️ Permesso con warning (distorce: chi perde di misura accumula più rack) |
| **WINS** | Race to N | Sempre un vincitore |
| **WINS** | Exactly N (dispari) | Sempre un vincitore |
| **WINS** | Exactly N (pari) | Pareggi possibili: 0 vittorie e 0 diff a entrambi |
| **POSITION** | Race to N | Sempre un vincitore |
| **POSITION** | Exactly N (dispari) | Sempre un vincitore |

### 2.2 Multi-set

| Sistema | Multi-set | Note |
|---------|-----------|------|
| **RACK** | ❌ No | Match più lunghi darebbero più opportunità di rack |
| **WINS** | ✅ Sì | Conta chi vince il match (più set) |
| **POSITION** | ✅ Sì | Conta chi vince il match |

### 2.3 Gestione Dispari

| Sistema | NO | Trio | Bye semplice | Bye + Challenge | Bye + N rack |
|---------|-----|------|--------------|-----------------|--------------|
| **RACK** | ✅ | ✅ (dist. 2-7) | ❌ (0 rack = penalizzato) | ✅ | ✅ |
| **WINS** | ✅ | ✅ (dist. 2-7) | ✅ (1 win, 0 diff) | ✅ | N/A |
| **POSITION** | ❌ | N/A | Bye bracket | N/A | N/A |

**NO**: Se abilitato, i giocatori che rendono il numero dispari vanno in lista d'attesa fino a quando non si iscrive un altro giocatore. Vedi [sezione 3.5](#35-no-nessuna-gestione-dispari).

### 2.4 Forfait Policy

| Sistema | EXCLUDE | FORFEIT |
|---------|---------|---------|
| **RACK** | ✅ | ✅ |
| **WINS** | ✅ | ✅ |
| **POSITION** | ❌ | ✅ (solo) |

### 2.5 Matchmaking

| Sistema | Random | Amalfi | Round Robin | Eliminazione | Doppio KO |
|---------|--------|--------|-------------|--------------|-----------|
| **RACK** | ✅ | ✅ | ✅ | ❌ | ❌ |
| **WINS** | ✅ | ✅ | ✅ | ❌ | ❌ |
| **POSITION** | ❌ | ❌ | ❌ | ✅ | ✅ |

---

## 3. Gestione Dispari

### 3.1 Trio

Il trio permette a 3 giocatori di giocare contemporaneamente quando il numero di partecipanti è dispari.

#### Distanze permesse: 2, 3, 4, 5

| Distanza | Mini gironi | Rack per giocatore | Rack totali |
|----------|-------------|-------------------|-------------|
| 2 | 1 | 2 | 3 |
| 3 | 1 | 2 | 3 |
| 4 | 2 | 4 | 6 |
| 5 | 2 | 4 | 6 |

#### Struttura
- Ogni giocatore affronta gli altri due in mini-match da 1 rack ciascuno.
- Con 1 giro: 3 rack totali (A-B, A-C, B-C).
- Con 2 giri: 6 rack totali (ripetizione).

#### Risultati possibili

**Distanza 2-3 (1 giro):**

| Distribuzione | Vincitore | Diff rack |
|---------------|-----------|-----------|
| (2,1,0) | Chi ha 2 | +2, 0, -2 |
| (1,1,1) | Nessuno | 0, 0, 0 |

**Distanza 4-5 (2 giri):**

| Distribuzione | Vincitore | Diff rack |
|---------------|-----------|-----------|
| (4,1,1) | Chi ha 4 | +4, -2, -2 |
| (3,2,1) | Chi ha 3 | +2, 0, -2 |
| (3,3,0) | Nessuno | +2, +2, -4 |
| (2,2,2) | Nessuno | 0, 0, 0 |

#### Punteggio per Sistema RACK
- Score = rack vinti (distanza pari)
- Score = 1 + rack vinti (distanza dispari)

Questo rende il punteggio comparabile ai match normali.

#### Punteggio per Sistema WINS
- **Vincitore unico** (score massimo non condiviso): 1 vittoria
- **Pareggio** (2+ con stesso score massimo): 0 vittorie a tutti
- **Diff rack**: sempre calcolata dai risultati effettivi

### 3.2 Bye semplice

- **Solo per Sistema WINS**
- Il giocatore con bye riceve: **1 vittoria, 0 diff rack**
- Non gioca quel turno.

### 3.3 Bye con Challenge

- **Per Sistema RACK e WINS**
- Il giocatore con bye esegue una challenge con punteggio 0-N (N = distanza).

| Sistema | Risultato |
|---------|-----------|
| **RACK** | Punteggio challenge = rack ottenuti |
| **WINS** | 1 vittoria, punteggio challenge = diff rack |

### 3.4 Bye con N rack (solo RACK)

- **Solo per Sistema RACK**
- Il giocatore con bye riceve automaticamente **N rack** (N = distanza).
- Equivalente a vincere senza giocare.
- Alternativa più semplice a Bye+Challenge.

### 3.5 NO (nessuna gestione dispari)

- **Per Sistema RACK e WINS** (non per POSITION)
- La gara richiede sempre un numero **pari** di giocatori.
- Se un giocatore si iscrive e rende il numero dispari, va automaticamente in **lista d'attesa**.
- Resta in lista d'attesa fino a quando non si iscrive un altro giocatore (che pareggia il conto).
- Quando un secondo giocatore si iscrive, entrambi passano agli iscritti effettivi.

#### Comportamento lista d'attesa con opzione NO

| Evento | Comportamento |
|--------|---------------|
| Iscrizione con N pari → N+1 dispari | Giocatore va in lista d'attesa |
| Iscrizione con N dispari → N+1 pari | Giocatore si iscrive + primo in lista d'attesa si iscrive |
| Disiscrizione con N pari → N-1 dispari | Ultimo iscritto va in lista d'attesa |
| Disiscrizione con N dispari → N-1 pari | Normale disiscrizione |

#### Differenza con lista d'attesa standard

La lista d'attesa standard (con massimo iscritti) gestisce l'**overflow** di iscrizioni.
L'opzione NO gestisce la **parità** indipendentemente dal massimo.

Se entrambe sono attive (massimo iscritti + opzione NO):
1. Prima si applica il controllo di parità (NO)
2. Poi si applica il controllo del massimo

---

## 4. Forfait

### 4.1 Nel match corrente

Quando un giocatore dà forfait durante un match:
- L'avversario vince tutti i rack rimanenti fino alla distanza.
- **Esempio**: Race to 5, punteggio 3-2, forfait → avversario vince 5-2.
- **Nel trio**: gli altri due giocatori vincono i rack rimanenti.

### 4.2 Policy per abbinamenti successivi

| Policy | Comportamento |
|--------|---------------|
| **EXCLUDE** | Giocatore rimosso dagli abbinamenti futuri. Cambia la parità → si applica gestione dispari. Resta in classifica con i punti accumulati. |
| **FORFEIT** | Giocatore resta negli abbinamenti. Avversari vincono automaticamente con rack pieni (distanza). |

### 4.3 Vincoli per sistema

- **RACK e WINS**: possono usare EXCLUDE o FORFEIT.
- **POSITION**: solo FORFEIT (l'avversario avanza nel bracket).

---

## 5. Spareggi (Tiebreaker)

### 5.1 Quando si applicano

Lo spareggio si applica alla **fine della gara** per risolvere i parimerito.

### 5.2 Configurazione posizioni

È configurabile per quali posizioni applicare lo spareggio:
- **Esempio 1**: Solo podio (posizioni 1-3).
- **Esempio 2**: Solo posizione 1.
- **Esempio 3**: Tutte le posizioni.
- **Default**: Da una certa posizione in poi, i parimerito restano tali.

### 5.3 Opzioni di spareggio

| Sistema | Opzione 1 | Opzione 2 |
|---------|-----------|-----------|
| **RACK** | SSR (Spot Shot Rally) | Scontro diretto |
| **WINS** | SSR (Spot Shot Rally) | Scontro diretto |
| **POSITION** | N/A (bracket determina) | - |

#### SSR (Spot Shot Rally)
Challenge speciale dove i giocatori accumulano punti. Chi ha più punti vince lo spareggio.

#### Scontro diretto
Se due giocatori sono pari e si sono affrontati nella gara, vince chi ha vinto lo scontro diretto.
- Se non si sono affrontati o lo scontro è pari, si usa l'altro metodo o restano parimerito.

---

## 6. Handicap

### 6.1 Applicazione

L'handicap si applica a livello di **match** e modifica il conteggio dei rack.

### 6.2 Funzionamento

- Un giocatore parte con rack in più o in meno.
- **Esempio**: Giocatore A (categoria alta) parte da -2 rack contro Giocatore B (categoria bassa).
- Il punteggio finale tiene conto dell'handicap.

### 6.3 Impatto sulla classifica

- I rack conteggiati nella classifica sono quelli **effettivi** (post-handicap).
- La vittoria/sconfitta è determinata dal punteggio post-handicap.

---

## 7. Campionato

### 7.1 Vincolo di omogeneità

**Tutte le gare di un campionato devono usare lo stesso sistema di classifica.**

Non è permesso mescolare gare RACK con gare WINS nello stesso campionato.

- **La gara di playoff** riceve il sistema del campionato come le altre; se si
  gioca a tabellone è POSITION, l'unico sistema che un tabellone ammette.
  Fino al 2026-09-14 nasceva sempre WINS.
- **Il sistema si cambia solo prima delle iscrizioni**: se una gara (non
  eliminata né annullata) ha lasciato la preparazione o ha già degli iscritti,
  `TournamentService.update_campionato` rifiuta il cambio. Altrimenti il
  sistema nuovo arriva a tutte le gare, e una gara che con quel sistema non
  sarebbe valida (per esempio a triangoli totali con la X semplice) ferma il
  cambio intero. Presidio: `test_specifiche_conformita.py` e
  `test_sistema_classifica_campionato.py`.

### 7.2 Aggregazione

La classifica del campionato **aggrega sommando** le classifiche delle singole gare.

| Sistema | Aggregazione |
|---------|--------------|
| **RACK** | Σ rack totali vinti |
| **WINS** | Σ vittorie, Σ diff rack |
| **POSITION** | Σ punti posizione |

### 7.3 Partecipazione parziale

- **Non c'è un minimo** di gare per apparire in classifica campionato.
- Un giocatore che partecipa a 1 gara su 10 è comunque in classifica (con pochi punti).

### 7.4 Playoff

- I playoff possono avere **requisiti minimi di partecipazione**.
- **Esempio**: "Per accedere ai playoff bisogna aver partecipato ad almeno 5 gare."
- Questo è configurabile a livello di campionato.

### 7.5 Punti posizione (solo POSITION)

Per campionati con gare a eliminazione:
- I punti per posizione sono **configurabili a livello campionato**.
- **Esempio configurazione**:
  ```
  1° = 25 punti
  2° = 18 punti
  3° = 15 punti
  4° = 12 punti
  5°-8° = 8 punti
  9°-16° = 4 punti
  ```

Per gare standalone:
- Non servono punti.
- La classifica è determinata direttamente dal tabellone.

---

## 8. Matchmaking

### 8.1 Strategie disponibili

| Strategia | Descrizione | Sistema compatibile |
|-----------|-------------|---------------------|
| **Random** | Abbinamenti casuali, nessuna ripetizione nella stessa gara | RACK, WINS |
| **Amalfi** | Abbinamenti per prossimità in classifica, evita ripetizioni | RACK, WINS |
| **Round Robin** | Tutti contro tutti | RACK, WINS |
| **Eliminazione** | Bracket, chi perde esce | POSITION |
| **Doppio KO** | Bracket con ripescaggio (una sconfitta ti manda nel losers bracket) | POSITION |

### 8.2 Dettagli strategie

#### Random
- Abbinamenti estratti casualmente ogni turno.
- Anti-rematch: due giocatori non si affrontano mai due volte nella stessa gara.

#### Amalfi
- Gli abbinamenti dipendono dalla classifica corrente.
- Il giocatore in posizione N viene abbinato con quello in posizione N+T (dove T = turni rimanenti).
- Anti-rematch attivo.

#### Round Robin
- Ogni giocatore affronta tutti gli altri una volta.
- Numero turni = N-1 (dove N = numero giocatori).

#### Eliminazione
- Bracket a eliminazione diretta.
- Posizioni determinate dalla progressione nel bracket.
- Per numeri non potenza di 2: bye al primo turno per alcuni giocatori.

#### Doppio KO
- Due bracket: winners e losers.
- Una sconfitta ti sposta nel losers bracket.
- Due sconfitte = eliminato.
- Finale tra vincitore winners e vincitore losers.

---

## 9. Regole di Validazione

Il sistema deve validare la compatibilità delle opzioni scelte.

### 9.1 Validazioni per Sistema RACK

```
SE sistema = RACK:
  ✓ distanza = Exactly N (qualsiasi)
    OPPURE Race to N (con warning)
  ✓ multi-set = No
  ✓ dispari ∈ {NO, Trio, Bye+Challenge, Bye+N_rack}
  ✗ dispari ≠ Bye semplice
  ✓ matchmaking ∈ {Random, Amalfi, Round Robin}
  ✗ matchmaking ∉ {Eliminazione, Doppio KO}
```

### 9.2 Validazioni per Sistema WINS

```
SE sistema = WINS:
  ✓ distanza = Race to N
    OPPURE Exactly N (qualsiasi, pari ammette pareggi)
  ✓ multi-set = opzionale
  ✓ dispari ∈ {NO, Trio, Bye, Bye+Challenge}
  ✓ matchmaking ∈ {Random, Amalfi, Round Robin}
  ✗ matchmaking ∉ {Eliminazione, Doppio KO}
```

### 9.3 Validazioni per Sistema POSITION

```
SE sistema = POSITION:
  ✓ distanza = Race to N
    OPPURE Exactly N (dispari)
  ✗ distanza ≠ Exactly N (pari)
  ✓ multi-set = opzionale
  ✓ dispari = gestito dal bracket
  ✓ forfait = FORFEIT (solo)
  ✗ forfait ≠ EXCLUDE
  ✓ matchmaking ∈ {Eliminazione, Doppio KO}
  ✗ matchmaking ∉ {Random, Amalfi, Round Robin}
```

### 9.4 Validazioni Trio

```
SE dispari = Trio:
  ✓ distanza ∈ {2, 3, 4, 5}
  ✗ distanza ∉ {1, 6, 7, 8, ...}
```

### 9.5 Validazioni Campionato

```
TUTTE le gare del campionato DEVONO avere lo stesso sistema di classifica.
```

---

## 10. Combinazioni Valide

Riepilogo di tutte le combinazioni valide.

| # | Sistema | Distanza | Multi-set | Dispari | Forfait | Matchmaking |
|---|---------|----------|-----------|---------|---------|-------------|
| 1 | RACK | Exactly N | No | NO | EXCLUDE/FORFEIT | Random/Amalfi/RR |
| 2 | RACK | Exactly N | No | Trio (dist 2-7) | EXCLUDE/FORFEIT | Random |
| 3 | RACK | Exactly N | No | Trio (dist 2-7) | EXCLUDE/FORFEIT | Amalfi |
| 4 | RACK | Exactly N | No | Trio (dist 2-7) | EXCLUDE/FORFEIT | Round Robin |
| 5 | RACK | Exactly N | No | Bye+Challenge | EXCLUDE/FORFEIT | Random |
| 6 | RACK | Exactly N | No | Bye+Challenge | EXCLUDE/FORFEIT | Amalfi |
| 7 | RACK | Exactly N | No | Bye+Challenge | EXCLUDE/FORFEIT | Round Robin |
| 8 | RACK | Exactly N | No | Bye+N rack | EXCLUDE/FORFEIT | Random |
| 9 | RACK | Exactly N | No | Bye+N rack | EXCLUDE/FORFEIT | Amalfi |
| 10 | RACK | Exactly N | No | Bye+N rack | EXCLUDE/FORFEIT | Round Robin |
| 11 | RACK | Race to N ⚠️ | No | NO/Trio/Bye+Ch/Bye+N | EXCLUDE/FORFEIT | Random/Amalfi/RR |
| 12 | WINS | Race to N | Sì/No | NO | EXCLUDE/FORFEIT | Random/Amalfi/RR |
| 13 | WINS | Race to N | Sì/No | Trio (dist 2-7) | EXCLUDE/FORFEIT | Random |
| 14 | WINS | Race to N | Sì/No | Trio (dist 2-7) | EXCLUDE/FORFEIT | Amalfi |
| 15 | WINS | Race to N | Sì/No | Trio (dist 2-7) | EXCLUDE/FORFEIT | Round Robin |
| 16 | WINS | Race to N | Sì/No | Bye | EXCLUDE/FORFEIT | Random |
| 17 | WINS | Race to N | Sì/No | Bye | EXCLUDE/FORFEIT | Amalfi |
| 18 | WINS | Race to N | Sì/No | Bye | EXCLUDE/FORFEIT | Round Robin |
| 19 | WINS | Race to N | Sì/No | Bye+Challenge | EXCLUDE/FORFEIT | Random |
| 20 | WINS | Race to N | Sì/No | Bye+Challenge | EXCLUDE/FORFEIT | Amalfi |
| 21 | WINS | Race to N | Sì/No | Bye+Challenge | EXCLUDE/FORFEIT | Round Robin |
| 22 | WINS | Exactly N disp | Sì/No | NO/Trio/Bye/Bye+Ch | EXCLUDE/FORFEIT | Random/Amalfi/RR |
| 23 | WINS | Exactly N pari | Sì/No | NO/Trio/Bye/Bye+Ch | EXCLUDE/FORFEIT | Random/Amalfi/RR |
| 24 | POSITION | Race to N | Sì/No | Bracket bye | FORFEIT | Eliminazione |
| 25 | POSITION | Race to N | Sì/No | Bracket bye | FORFEIT | Doppio KO |
| 26 | POSITION | Exactly N disp | Sì/No | Bracket bye | FORFEIT | Eliminazione |
| 27 | POSITION | Exactly N disp | Sì/No | Bracket bye | FORFEIT | Doppio KO |

**Legenda:**
- ⚠️ = Permesso con warning (comportamento potenzialmente controintuitivo)
- Exactly N pari (combo 23) = pareggi possibili (0 vittorie, 0 diff a entrambi)
- NO = nessuna gestione dispari, giocatori dispari vanno in lista d'attesa

---

## 11. Schema Decisionale

```
                         ┌─────────────────────────┐
                         │  SCEGLI IL SISTEMA DI   │
                         │      CLASSIFICA         │
                         └───────────┬─────────────┘
                                     │
         ┌───────────────────────────┼───────────────────────────┐
         ▼                           ▼                           ▼
  ┌─────────────┐            ┌─────────────┐            ┌─────────────┐
  │    RACK     │            │    WINS     │            │  POSITION   │
  │(rack totali)│            │(vittorie +  │            │(punti per   │
  │             │            │ diff rack)  │            │ posizione)  │
  └──────┬──────┘            └──────┬──────┘            └──────┬──────┘
         │                          │                          │
         ▼                          ▼                          ▼
  ┌─────────────┐            ┌─────────────┐            ┌─────────────┐
  │ DISTANZA    │            │ DISTANZA    │            │ DISTANZA    │
  │             │            │             │            │             │
  │ • Exactly N │            │ • Race to N │            │ • Race to N │
  │   (prefer.) │            │ • Exactly N │            │ • Exactly N │
  │ • Race to N │            │   (disp/pari│            │   (dispari) │
  │   ⚠️ warning│            │    ok)      │            │             │
  └──────┬──────┘            └──────┬──────┘            └──────┬──────┘
         │                          │                          │
         ▼                          ▼                          ▼
  ┌─────────────┐            ┌─────────────┐            ┌─────────────┐
  │ MULTI-SET   │            │ MULTI-SET   │            │ MULTI-SET   │
  │             │            │             │            │             │
  │     NO      │            │   SÌ / NO   │            │   SÌ / NO   │
  └──────┬──────┘            └──────┬──────┘            └──────┬──────┘
         │                          │                          │
         ▼                          ▼                          ▼
  ┌─────────────┐            ┌─────────────┐            ┌─────────────┐
  │ DISPARI     │            │ DISPARI     │            │ DISPARI     │
  │             │            │             │            │             │
  │ • NO        │            │ • NO        │            │ Bye bracket │
  │ • Trio      │            │ • Trio      │            │             │
  │   (dist 2-7)│            │   (dist 2-7)│            │             │
  │ • Bye+Chall │            │ • Bye       │            │             │
  │ • Bye+N rack│            │ • Bye+Chall │            │             │
  └──────┬──────┘            └──────┬──────┘            └──────┬──────┘
         │                          │                          │
         ▼                          ▼                          ▼
  ┌─────────────┐            ┌─────────────┐            ┌─────────────┐
  │ FORFAIT     │            │ FORFAIT     │            │ FORFAIT     │
  │             │            │             │            │             │
  │ • EXCLUDE   │            │ • EXCLUDE   │            │ • FORFEIT   │
  │ • FORFEIT   │            │ • FORFEIT   │            │   (solo)    │
  └──────┬──────┘            └──────┬──────┘            └──────┬──────┘
         │                          │                          │
         ▼                          ▼                          ▼
  ┌─────────────┐            ┌─────────────┐            ┌─────────────┐
  │ MATCHMAKING │            │ MATCHMAKING │            │ MATCHMAKING │
  │             │            │             │            │             │
  │ • Random    │            │ • Random    │            │ • Elimin.   │
  │ • Amalfi    │            │ • Amalfi    │            │ • Doppio KO │
  │ • Round Rob.│            │ • Round Rob.│            │             │
  └──────┬──────┘            └──────┬──────┘            └──────┬──────┘
         │                          │                          │
         ▼                          ▼                          ▼
  ┌─────────────┐            ┌─────────────┐            ┌─────────────┐
  │ SPAREGGIO   │            │ SPAREGGIO   │            │ SPAREGGIO   │
  │             │            │             │            │             │
  │ • SSR       │            │ • SSR       │            │ N/A (bracket│
  │ • Scontro   │            │ • Scontro   │            │  determina) │
  │   diretto   │            │   diretto   │            │             │
  └─────────────┘            └─────────────┘            └─────────────┘
```

---

## Changelog

- **2025-10-XX**: Creazione documento con specifiche complete del sistema di classificazione.
- **2026-01-24**: Verificato allineamento con codebase.
