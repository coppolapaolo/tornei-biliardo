# ADR-070 · I gruppi ordinano, e «I miei allievi» dice fatti

**Stato**: accettata · **Data**: 2026-09-20 · **Issue**: #173
**Fase**: 8c del redesign «TPA ed esercizi»
([PIANO.md](../redesign-7c/canvas-tpa-esercizi/PIANO.md)) · **Segue**
[ADR-069](ADR-069-istruttore-e-allievo.md)

## Contesto

L'ADR-069 ha dato all'istruttore il ruolo e il legame: le schede che gli allievi
gli aprono, una per una. Restava da dargli i due attrezzi con cui si lavora
davvero in una sala: **un posto dove ordinare venti persone** (D12, i gruppi con
storico) e **un elenco che dica a chi badare oggi**.

Il secondo è il punto delicato. Un elenco che divide gli allievi in tre sezioni
sta esprimendo dei giudizi, e un programma può calcolarli con qualunque
formula: «è costante», «è a rischio», «sta migliorando» sembrano vere comunque
siano state ottenute, e chi le legge non ha modo di controllarle. L'istruttore
ci crede — è il motivo per cui apre la pagina — e agisce di conseguenza su un
ragazzo di quattordici anni.

## Decisione

### 1 · Un gruppo ordina, e non apre niente

`training_group` e `training_group_member`. Nessuna delle due tabelle concede
alcun accesso: **l'unico posto in cui è scritto chi legge che cosa resta
`training_sheet_reader`** (ADR-069 §2). Da questa frase discende tutto:

* **ci si mette solo chi ti ha già aperto una scheda.** Se si potesse
  aggiungere chiunque, il gruppo diventerebbe una richiesta che l'altro non ha
  mai accettato;
* **se poi te la richiude, la riga del gruppo resta** — è storia — ma di quella
  scheda non vedi più niente di nuovo. Le due tabelle non si parlano;
* nella pagina del gruppo **non c'è una casella di ricerca**: c'è l'elenco dei
  tuoi allievi liberi. L'assenza è la decisione.

### 2 · «Un allievo in un gruppo solo» lo impone il database

Indice unico **parziale** su `(instructor_id, user_id) WHERE left_at IS NULL`.
Perché ci stia, `instructor_id` è copiato sulla riga del membro: un indice non
attraversa due tabelle, e la colonna è sicura perché non cambia mai — un gruppo
appartiene al suo istruttore per sempre.

Non è pignoleria. Un'unicità che vive in un `if` di Python è invisibile a chi
scrive in blocco: `UserMergeService` decide **dallo schema** se spostare una
colonna riga per riga, ed è esattamente così che unendo due account un
giocatore è finito iscritto due volte alla stessa gara (produzione, gara 39).

Conseguenza operativa: **chiudere un gruppo data l'uscita di chi c'era**, col
giorno di chiusura. Senza, per il database quelle persone sarebbero ancora
dentro e non si potrebbero iscrivere al corso dell'anno dopo.

### 3 · Il calendario è una previsione, lo stato è un atto

`started_on`/`ended_on` sono il **periodo dichiarato**; `closed_at` è la
chiusura. Sono due colonne perché sono due cose, e tenerle in una sola è un
difetto che si vede subito e si capisce tardi: «dal 15/09 al **15/12**» si
scrive a settembre, e leggendo `ended_on` come stato quel gruppo nascerebbe già
archiviato — con i suoi allievi non aggiungibili. È successo scrivendo questa
fase, al primo dato vero.

Chiudere un corso **prima** della data prevista sposta `ended_on` a oggi: lo
storico non deve contenere una fine mai avvenuta. Una data già passata si
tiene, perché è quella giusta.

### 4 · Le tre sezioni, e cosa ciascuna ha il diritto di dire

Sono in `models/istruttore/allievi_view.py`, con le costanti dichiarate lì.

| Sezione | Definizione | Che cos'è |
|---|---|---|
| **Valuta il passaggio di livello** | tante sedute di fila sopra la soglia quante la scheda ne chiede (`streak_above_threshold`) | il gradino della scheda (ADR-067), non una stima |
| **Da guardare** | «non si allena da N giorni» (N ≥ 14) · «da 5 sedute non supera il suo massimo» | due **fatti**, ciascuno con la sua costante |
| **Tutto bene** | il resto | **non è una misura**: sotto il nome c'è un fatto — l'ultima seduta, e quante in quattro settimane |

Tre cose che questo tavolo dice e che vanno lette con attenzione.

**«Valuta il passaggio di livello» mostra, non agisce.** La fase 6 aveva
lasciato aperto chi sancisce il gradino (D8), «dove c'è qualcuno che può
confermare». Qui c'è, e vede il segnale; ma **dare la scheda del livello dopo è
un gesto della fase 8d**. In questa pagina l'istruttore scrive soltanto i propri
gruppi: non tocca mai un dato dell'allievo.

**La regola del gradino è una funzione sola.** `streak_above_threshold` la
usano la fine seduta — che le sedute se le va a prendere — e questa pagina, che
le ha già in mano per venti schede. Due copie che divergessero direbbero
all'istruttore che l'allievo è pronto e all'allievo di no.

**Chi è al massimo possibile non è in stallo.** Chi fa 60 su 60 da sei sedute
non «non supera il suo massimo»: ha finito i numeri disponibili, e dirglielo
sarebbe falso. Serve anche una seduta *prima* del blocco, altrimenti non c'è un
massimo «di allora» da non superare.

### 5 · Ciò che è stato deliberatamente lasciato fuori

* **«6 sedute su 7 previste»** (l'artboard). «Previste» non esiste nel modello:
  una scheda dichiara le settimane e i giorni A · B · C, non la frequenza.
  Dedurre «un giro a settimana» sarebbe la metrica inventata che questa ADR
  rifiuta. Al suo posto c'è un conteggio: «6 sedute in quattro settimane».
* **«Media del gruppo, su 60»** (l'artboard). Si può dire solo se tutti fanno
  la stessa scheda. Torna con la scheda di gruppo (fase 8d), quando quel «su
  60» avrà un significato unico.

## Alternative scartate

**Il gruppo come contenitore che dà accesso.** È la forma che ha ogni
piattaforma di corsi: iscrivi l'allievo e ne vedi i dati. Sarebbe comodo, e
sarebbe la stessa cosa che l'ADR-069 ha già rifiutato in grande — con
l'aggravante che qui passerebbe per una funzione di comodità, non per una
decisione sul consenso.

**Un allievo in più gruppi insieme.** Più libero, e toglie il bisogno della
colonna denormalizzata. Ma «sposta» — il gesto che l'artboard mostra — non
avrebbe più senso, la riga dell'allievo non potrebbe dire *il* suo gruppo, e i
filtri smetterebbero di essere una partizione. Se un giorno servirà (un allievo
che segue due corsi), si toglie l'indice e si decide come mostrarlo.

**Lasciare «Da guardare» e «Tutto bene» senza definizione, a occhio.** Il modo
in cui nasce una metrica inventata: si guarda l'artboard, si scrive una formula
plausibile, e da quel momento un numero senza padre guida le decisioni di un
istruttore. L'alternativa onesta era lasciarle fuori del tutto e mostrare un
elenco piatto; si è scelta la terza strada — definirle, scriverle e
presidiarle — perché i due fatti scelti sono verificabili da chi legge.

## Conseguenze

* La pagina costa **una query per le sedute**, non una per allievo: con venti
  allievi e due schede a testa sarebbero quaranta interrogazioni per disegnare
  un elenco. Si guardano le ultime venti sedute per scheda, come il registro
  che l'istruttore apre subito dopo, e non oltre un anno indietro.
* Un istruttore che non usa i gruppi vede la pagina funzionare lo stesso: le
  linguette non compaiono, il triage sì. I gruppi sono un ordinamento, e un
  ordinamento è facoltativo.
* Le costanti (14 giorni, 5 sedute, 7 giorni, 4 settimane) sono scelte, non
  leggi: stanno in cima al modulo con il loro perché, e si ritoccano lì.

## Presidi

* `tests/new/unit/test_gruppi_di_allievi.py` — il modello e le regole: chi crea,
  chi ci entra, un gruppo solo per volta, la chiusura, il calendario che non
  chiude niente.
* `tests/new/unit/test_allievi_triage.py` — **le tre definizioni**, ciascuna col
  caso che la fa scattare e quello che non la deve far scattare.
* `tests/new/unit/test_gruppi_migration.py` — lo schema, e l'indice unico
  parziale provato con un `INSERT` a mano.
* `tests/new/integration/test_pagina_allievi.py` — le route, il 404 a chi non ha
  il ruolo, e l'allowlist di produzione.
