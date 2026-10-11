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

Esistono **4 sistemi di classifica** mutuamente esclusivi:

| Sistema | Criteri ordinamento | Uso tipico |
|---------|---------------------|------------|
| **RACK** | 1) Rack totali vinti ↓ 2) Spareggio | Gare con focus su rack accumulati |
| **WINS** | 1) Match vinti ↓ 2) Diff rack ↓ 3) Spareggio | Gare con focus su vittorie |
| **POINTS** | 1) Punti ↓ (vittoria/pareggio/sconfitta, di norma 3/1/0) 2) Catena degli spareggi | Gironi e serate «a punti», dove il pareggio esiste |
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

### 1.3 Sistema POINTS (dal 2026-10-07)

Ogni partita dà i **punti del suo esito**; si ordina **solo sui punti**, e fra
chi è a pari punti decide la catena degli spareggi (§5.0).

- **Punti**: vittoria, pareggio, sconfitta sulla gara (`Gara.points_win/draw/loss`),
  proposti dal campionato (`Campionato.default_points_*`) e copiati sulla gara
  quando nasce (ADR-075). Default 3/1/0; interi 0–99 con
  vittoria ≥ pareggio ≥ sconfitta e vittoria > sconfitta. Struttura: a gara
  avviata non si cambiano. Si leggono da `models/classification/punti.py`.
- **X**: vale una vittoria (punti della vittoria, zero differenza; con
  l'esercizio la differenza è il punteggio della prova).
- **Pareggio** (exactly N con N pari, interruzione a tempo a parità fuori dal
  tabellone): i punti del pareggio a entrambi.
- **Trio**: con un vincitore, vittoria a lui e sconfitta agli altri due; senza,
  pareggio a chi è a pari merito in testa e sconfitta al terzo staccato; chi
  si ritira prende la sconfitta.
- **Classifica generale**: somma dei punti delle gare, moltiplicati per il
  peso della gara (ADR-053); la copia sta in `Classification.total_position_points`.

### 1.4 Sistema POSITION

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
| **POINTS** | come WINS | Il pareggio dà i punti del pareggio |
| **POSITION** | Race to N | Sempre un vincitore |
| **POSITION** | Exactly N (dispari) | Sempre un vincitore |

### 2.2 Multi-set

| Sistema | Multi-set | Note |
|---------|-----------|------|
| **RACK** | ❌ No | Match più lunghi darebbero più opportunità di rack |
| **WINS** | ✅ Sì | Conta chi vince il match (più set) |
| **POINTS** | ✅ Sì | Come WINS |
| **POSITION** | ✅ Sì | Conta chi vince il match |

### 2.3 Gestione Dispari

| Sistema | NO | Trio | Bye semplice | Bye + Challenge | Bye + N rack |
|---------|-----|------|--------------|-----------------|--------------|
| **RACK** | ✅ | ✅ (dist. 2-7) | ❌ (0 rack = penalizzato) | ✅ | ✅ |
| **WINS** | ✅ | ✅ (dist. 2-7) | ✅ (1 win, 0 diff) | ✅ | N/A |
| **POINTS** | ✅ | ✅ (dist. 2-7) | ✅ (punti vittoria, 0 diff) | ✅ | N/A |
| **POSITION** | ❌ | N/A | Bye bracket | N/A | N/A |

**Girone all'italiana (Round Robin)**: l'unica formula è il **riposo**, che non vale niente con qualunque sistema — 0 vittorie, 0 punti, 0 rack, nessun match giocato. Per questo col girone il riposo è ammesso anche col sistema RACK (ognuno riposa una volta, e lo zero tocca tutti), e la X con challenge non si può scegliere: se il campionato la propone, la gara a girone ripiega sul riposo. Vedi [sezione 3.2](#32-bye-semplice) e SPECIFICHE.md, nota del 2026-10-11.

**NO**: Se abilitato, i giocatori che rendono il numero dispari vanno in lista d'attesa fino a quando non si iscrive un altro giocatore. Vedi [sezione 3.5](#35-no-nessuna-gestione-dispari).

### 2.4 Forfait Policy

| Sistema | EXCLUDE | FORFEIT |
|---------|---------|---------|
| **RACK** | ✅ | ✅ |
| **WINS** | ✅ | ✅ |
| **POINTS** | ✅ | ✅ |
| **POSITION** | ❌ | ✅ (solo) |

### 2.5 Matchmaking

| Sistema | Random | Amalfi | Round Robin | Eliminazione | Doppio KO |
|---------|--------|--------|-------------|--------------|-----------|
| **RACK** | ✅ | ✅ | ✅ | ❌ | ❌ |
| **WINS** | ✅ | ✅ | ✅ | ❌ | ❌ |
| **POINTS** | ✅ | ✅ | ✅ | ❌ | ❌ |
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

- **Per Sistema WINS e POINTS** (Random, Amalfi)
- Il giocatore con bye riceve: **1 vittoria, 0 diff rack**
- Non gioca quel turno.

**Il riposo del girone all'italiana** (dal 2026-10-11). Col Round Robin la stessa
formula non vale niente: il match di riposo nasce **senza vincitore**
(`Match.is_riposo`), e chi riposa riceve 0 vittorie, 0 punti, 0 rack — resta in
classifica, ma senza niente in più. Vale con WINS, POINTS e RACK. L'avversario di
un giocatore **escluso** a girone in corso (policy EXCLUDE) non riposa: vince a
tavolino, rack pieni fino alla distanza del turno, come contro un forfait.

### 3.3 Bye con Challenge

- **Per Sistema RACK e WINS** (Random, Amalfi: col Round Robin non c'è)
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

### 5.0 La catena degli spareggi (ADR-078)

Dal 2026-10-07 i pari merito si risolvono con una **catena di criteri**,
applicata a gruppi da un motore solo (`models/classification/ordinamento.py`).
Turno, gara e campionato hanno ciascuno la sua catena; le catene di default e
cosa è cambiato rispetto a prima stanno in SPECIFICHE.md, «Classifica», «Come
si risolvono i pari merito». In breve:

| Classifica | WINS | RACK |
|---|---|---|
| Turno | vittorie → differenza → posizione precedente → sorteggio | rack → posizione precedente → sorteggio |
| Gara | vittorie → differenza → SSR fino al 3° | rack → SSR fino al 3° |
| Campionato | vittorie → differenza → SSR (somma) → posizione dopo la gara precedente → sorteggio | rack → SSR (somma) → posizione dopo la gara precedente → sorteggio |

A punti (POINTS) le catene di default sono quelle WINS col principale «punti»:
turno punti → differenza → posizione precedente → sorteggio; gara punti →
differenza → SSR fino al 3°; campionato punti → differenza → SSR (somma) →
posizione dopo la gara precedente → sorteggio. «Vittorie» lì è un criterio
che si può aggiungere alla catena.

Lo **scontro diretto** è un criterio del motore: ogni coppia di pari che si è
incontrata dice chi sta davanti (chi ha vinto più scontri fra i due); chi si è
battuto a vicenda in giro resta pari; fra chi non si è incontrato decide il
criterio successivo, senza rovesciare un risultato diretto (§5.3).

Le catene **si configurano** (emendamento del 2026-10-07): la gara ha la
catena di turno e quella di gara, il campionato le propone alle sue gare e ha
in più quella della classifica generale. Il direttore le compone nell'editor
dei moduli di gara e di campionato; il principale non si sceglie, il sorteggio
è sempre in fondo (e nel turno e nel campionato c'è sempre), lo SSR una volta
sola e mai nel turno. Le regole complete stanno in SPECIFICHE.md, «Le catene si
configurano»; il codice in `models/classification/catene.py`.

### 5.1 Quando si applicano

Lo spareggio si applica alla **fine della gara** per risolvere i parimerito.

### 5.2 Configurazione posizioni

Lo spareggio SSR è un criterio della catena di gara, «fino al N° posto»
(`ssr:N`, di norma 3): oltre quel posto i parimerito restano tali. Toglierlo
dalla catena vuol dire che la gara non lo prevede. Fino al 2026-10-07 erano
due campi della gara, `tiebreaker_enabled` e `tiebreaker_until_position`: la
migration `20261007_catene_degli_spareggi` li ha fusi nella catena.

### 5.3 Opzioni di spareggio

| Sistema | Opzione 1 | Opzione 2 |
|---------|-----------|-----------|
| **RACK** | SSR (Spot Shot Rally) | Scontro diretto |
| **WINS** | SSR (Spot Shot Rally) | Scontro diretto |
| **POSITION** | N/A (bracket determina) | - |

#### SSR (Spot Shot Rally)
Challenge speciale dove i giocatori accumulano punti. Chi ha più punti vince lo spareggio.

#### Scontro diretto
Se due giocatori sono pari e si sono affrontati, vince chi ha vinto lo scontro diretto.
- Se non si sono affrontati o lo scontro è pari, si usa l'altro metodo o restano parimerito.
- Più incontri fra gli stessi due (in gare diverse del campionato) si contano tutti: sta davanti chi ne ha vinti di più.
- **Fra tre o più** (dal 2026-10-07): ogni coppia che si è incontrata dà un vincolo «X davanti a Y»; chi si è battuto a vicenda in giro (A>B>C>A) resta pari sullo scontro; l'ordine rispetta tutti i vincoli, e fra chi non ha più nessuno davanti decide il criterio successivo della catena. La X e il trio non sono scontri; nel campionato non contano le gare che pesano zero.

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

### 7.0 Sommando i totali o a piazzamenti (dal 2026-10-11, ADR-080)

Un campionato sceglie **come le gare entrano** nella classifica generale:

- **sommando i totali** (`default_classification_system` = WINS, RACK o
  POINTS): si sommano vittorie, rack o punti delle classifiche finali. Le gare
  hanno tutte il sistema del campionato e restano a **girone unico**
  (`GaraService._verifica_gironi_ammessi`,
  `TournamentService._verifica_gironi_del_campionato`): fra gironi di taglia
  diversa chi sta nel girone più numeroso gioca una partita in più;
- **a piazzamenti** (`default_classification_system` = POSITION, o un tipo di
  campionato a tabellone): ogni gara dà i punti del **posto** nella sua
  classifica finale (`GaraClassification.position`), con la tabella della
  sezione 7.5, pesati. Le gare hanno **qualunque formato** — Amalfi, casuale,
  girone all'italiana a uno o più gironi, tabellone — e il loro sistema serve
  solo a ordinare la serata: lo propone il campionato
  (`default_gara_classification_system`, NULL = WINS) e la gara lo può
  cambiare; il tabellone resta POSITION. Chi non gioca prende zero; i pari
  merito di una gara prendono i punti del posto condiviso; oltre la tabella si
  prende zero. A **pari punti** decide la catena della classifica generale
  (`Campionato.catena_generale`), con criteri suoi: migliori piazzamenti
  (`Criterio.PIAZZAMENTI`: più primi posti, poi più secondi…; il posto è
  quello della classifica della gara, pesato come i punti), posizione dopo la
  gara precedente, scontri diretti, sorteggio. Di default «migliori
  piazzamenti → sorteggio». Vittorie, rack, differenza e SSR non sono
  ammessi (emendamento del 2026-10-11: prima decidevano vittorie e
  differenza sommate, e i pari condividevano il posto).

Le regole di lettura stanno in `models/campionato/piazzamenti.py`
(`e_a_piazzamenti`, `sistema_delle_gare`, `sistema_per_la_gara`). Presidi:
`tests/new/unit/test_campionato_a_piazzamenti.py`,
`test_specifiche_conformita.py::TestIlCampionatoAPiazzamenti`.

### 7.1 Vincolo di omogeneità

**Nei campionati che sommano i totali tutte le gare devono usare lo stesso
sistema di classifica** (fino al 2026-10-11 valeva per ogni campionato).

Non è permesso mescolare gare RACK con gare WINS nello stesso campionato che
somma i totali. A piazzamenti sì: della gara si prende solo il posto.

- **La gara di playoff dipende dalla modalità della classifica finale**
  (ADR-053). Se il suo punteggio **si somma** (`campionato_plus_playoff`) ha il
  sistema del campionato, quindi è a tabellone solo se lo è anche il
  campionato: POSITION non si somma a vittorie o triangoli. Se la classifica finale è **solo quella dei playoff**
  (`playoff_only`) della finale conta solo l'ordine d'arrivo
  (`_apply_playoff_final_order` legge `GaraClassification.position`), quindi il
  sistema può essere diverso e il tabellone è ammesso (POSITION). Il passaggio a
  `campionato_plus_playoff` è rifiutato se la finale esistente ha un altro
  sistema o la strategia è a tabellone; salvare il peso senza cambiare modalità
  non è mai bloccato. Fino al 2026-09-14 la finale nasceva sempre WINS. In un
  campionato a piazzamenti la finale si somma col suo posto, qualunque formato
  abbia.
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
| **POINTS** | Σ punti (pesati) |
| **POSITION** | Σ punti del posto in ogni gara (pesati), poi Σ vittorie e Σ diff rack; i pari condividono il posto |

### 7.3 Partecipazione parziale

- **Non c'è un minimo** di gare per apparire in classifica campionato.
- Un giocatore che partecipa a 1 gara su 10 è comunque in classifica (con pochi punti).

### 7.4 Playoff

- I playoff possono avere **requisiti minimi di partecipazione**.
- **Esempio**: "Per accedere ai playoff bisogna aver partecipato ad almeno 5 gare."
- Questo è configurabile a livello di campionato.

### 7.5 Punti posizione (solo POSITION)

Per i campionati a piazzamenti, con gare di qualunque formato (dal 2026-10-11;
prima solo con gare a eliminazione):
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
| **Round Robin** | Tutti contro tutti | RACK, WINS, POINTS |
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
- Numero turni = N-1 con N pari, **N con N dispari** (N = numero giocatori):
  nel dispari ognuno riposa una volta, e il riposo non vale niente.
- Dispari: solo il riposo (vedi [sezione 3.2](#32-bye-semplice)).
- **Gironi multipli** (dal 2026-10-11, ADR-076): la gara può dividersi in
  gironi giocati in parallelo, «fino a N» (`Gara.max_groups`; vuoto o 1 =
  girone unico, proposto dal campionato con `default_max_groups`). Il numero
  esatto lo sceglie il direttore all'avvio (almeno 3 giocatori per girone,
  proposta un girone ogni 6 iscritti per eccesso); la **composizione dei
  gironi** (`Gara.group_seeding`: sorteggio, per ELO, per categoria) mette gli
  iscritti in fila e li distribuisce uno per girone a turno, andata e ritorno.
  L'appartenenza sta su `Inscription.group_index`, e le partite la ripetono in
  `Match.bracket_group`. I turni sono quelli del girone più numeroso.

  Classifiche: **dentro il girone** si ordina col sistema e la catena della
  gara (`group_index`, `group_position` sulle righe di turno e di gara);
  **nella gara** prima tutti i primi, poi tutti i secondi, confrontati **per
  partita giocata** — vittorie, rack, differenza e punti divisi per le
  partite giocate (il riposo non è una partita, il tavolino sì). Fra gironi
  diversi lo scontro diretto non decide. Calcolo puro in
  `models/classification/gironi.py`, lettura dei numeri in
  `gironi_della_gara.py`. I gironi esistono nelle gare singole e nei
  campionati a piazzamenti, dove la gara entra col suo posto (sezione 7.0).

- **Tabellone dopo i gironi** (dal 2026-10-11, ADR-081): con
  `Gara.final_phase_mode = "tabellone"` i primi `K` di ogni girone
  (`qualifiers_per_group`, di norma 2) giocano un'eliminazione diretta dopo
  l'ultimo turno dei gironi; la finalina è `third_place_match`. Teste di serie
  per colonne (prima i primi, poi i secondi; dentro la colonna l'ordine della
  classifica a gironi), bye ai migliori, chi viene dallo stesso girone tenuto
  lontano (1ºA–2ºB, 1ºB–2ºA). Al taglio decide la catena di gara senza lo
  spareggio SSR, poi il sorteggio. Le partite del tabellone si giocano «al N».

  Classifica finale (`models/classification/fase_finale.py`): prima il
  tabellone — 1° e 2° dalla finale, 3° e 4° dalla finalina, senza finalina due
  terzi a pari merito, chi esce prima della semifinale per piazzamento nel
  girone — poi i non qualificati nell'ordine dei gironi. Il sistema della gara
  (WINS, RACK, POINTS) ordina i gironi e non cambia; nei turni del tabellone i
  numeri delle righe restano quelli dei gironi. **Lo spareggio SSR non si
  gioca**: il podio lo dà il tabellone, come nel sistema POSITION. Nessuna
  fase finale nei campionati che sommano i totali.

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
  ✗ dispari ≠ Bye semplice, tranne col Round Robin (il riposo, che non vale niente)
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
  ✓ Round Robin: dispari = solo il riposo (Bye, che non vale niente)
```

### 9.2-bis Validazioni per Sistema POINTS

```
SE sistema = POINTS:
  come WINS (stessa funzione `_validate_wins_system`)
  ✓ punti: interi 0–99, vittoria ≥ pareggio ≥ sconfitta, vittoria > sconfitta
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
| 1 | RACK | Exactly N | No | NO | EXCLUDE/FORFEIT | Random/Amalfi |
| 2 | RACK | Exactly N | No | Trio (dist 2-7) | EXCLUDE/FORFEIT | Random |
| 3 | RACK | Exactly N | No | Trio (dist 2-7) | EXCLUDE/FORFEIT | Amalfi |
| 4 | RACK | Exactly N | No | Bye+Challenge | EXCLUDE/FORFEIT | Random |
| 5 | RACK | Exactly N | No | Bye+Challenge | EXCLUDE/FORFEIT | Amalfi |
| 6 | RACK | Exactly N | No | Bye+N rack | EXCLUDE/FORFEIT | Random |
| 7 | RACK | Exactly N | No | Bye+N rack | EXCLUDE/FORFEIT | Amalfi |
| 8 | RACK | Exactly N | No | Riposo (non vale) | EXCLUDE/FORFEIT | Round Robin |
| 9 | RACK | Race to N ⚠️ | No | NO/Trio/Bye+Ch/Bye+N | EXCLUDE/FORFEIT | Random/Amalfi |
| 10 | RACK | Race to N ⚠️ | No | Riposo (non vale) | EXCLUDE/FORFEIT | Round Robin |
| 11 | WINS | Race to N | Sì/No | NO | EXCLUDE/FORFEIT | Random/Amalfi |
| 12 | WINS | Race to N | Sì/No | Trio (dist 2-7) | EXCLUDE/FORFEIT | Random |
| 13 | WINS | Race to N | Sì/No | Trio (dist 2-7) | EXCLUDE/FORFEIT | Amalfi |
| 14 | WINS | Race to N | Sì/No | Bye | EXCLUDE/FORFEIT | Random |
| 15 | WINS | Race to N | Sì/No | Bye | EXCLUDE/FORFEIT | Amalfi |
| 16 | WINS | Race to N | Sì/No | Riposo (non vale) | EXCLUDE/FORFEIT | Round Robin |
| 17 | WINS | Race to N | Sì/No | Bye+Challenge | EXCLUDE/FORFEIT | Random |
| 18 | WINS | Race to N | Sì/No | Bye+Challenge | EXCLUDE/FORFEIT | Amalfi |
| 19 | WINS | Exactly N disp | Sì/No | NO/Trio/Bye/Bye+Ch | EXCLUDE/FORFEIT | Random/Amalfi |
| 20 | WINS | Exactly N pari | Sì/No | NO/Trio/Bye/Bye+Ch | EXCLUDE/FORFEIT | Random/Amalfi |
| 21 | WINS | Exactly N | Sì/No | Riposo (non vale) | EXCLUDE/FORFEIT | Round Robin |
| 22 | POSITION | Race to N | Sì/No | Bracket bye | FORFEIT | Eliminazione |
| 23 | POSITION | Race to N | Sì/No | Bracket bye | FORFEIT | Doppio KO |
| 24 | POSITION | Exactly N disp | Sì/No | Bracket bye | FORFEIT | Eliminazione |
| 25 | POSITION | Exactly N disp | Sì/No | Bracket bye | FORFEIT | Doppio KO |

**Legenda:**
- ⚠️ = Permesso con warning (comportamento potenzialmente controintuitivo)
- Exactly N pari (combo 20, e 21 con N pari) = pareggi possibili (0 vittorie, 0 diff a entrambi)
- Riposo (non vale) = il riposo del girone all'italiana: 0 vittorie, 0 punti, 0 rack (SPECIFICHE.md, nota del 2026-10-11). Col girone le altre formule dei dispari non si possono scegliere (`STRATEGY_CONSTRAINTS`). Fino al 2026-10-11 questa tabella elencava anche Trio, NO, Bye+Challenge e Bye+N rack col Round Robin, che il codice non ammetteva già prima
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
- **2026-10-07**: Sistema POINTS (classifica a punti), ADR-078 emendamento.
- **2026-10-11**: Gironi multipli nel girone all'italiana (ADR-076): classifica per girone, e nella gara primi poi secondi per partita giocata. Lo stesso giorno il riposo del girone ha smesso di valere una vittoria (SPECIFICHE.md, nota del 2026-10-11).
