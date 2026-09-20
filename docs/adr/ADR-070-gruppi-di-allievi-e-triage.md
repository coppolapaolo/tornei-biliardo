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
  60» avrà un significato unico. → **Rinvio chiuso**: vedi l'emendamento del
  2026-09-20 in fondo.

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

---

## Emendamento del 2026-09-20 · i quattro numeri del gruppo (fase 8d₃)

Il §5 aveva rinviato «Media del gruppo, su 60» a quando fosse esistita una
**scheda comune**. Con l'[ADR-071](ADR-071-una-scheda-si-propone.md) quella
scheda esiste — si propone, e `training_assignment.group_id` dice da quale
corso è partita — quindi i tre numeri dell'artboard e l'esito dello storico si
possono definire. Le definizioni stanno in `models/istruttore/gruppo_view.py`;
qui c'è il perché.

### 1 · La scheda del gruppo è l'ultima proposta *dal* gruppo

Il «giro» sono tutte le proposte partite da quel corso con quel modello, anche
quelle mandate più tardi a chi è arrivato dopo. Proporne una diversa — il
livello dopo, a metà corso — **cambia** la scheda del gruppo, perché è ciò che
è successo davvero.

«L'hanno presa in 4 su 5» conta le **proposte partite**, non gli allievi di
adesso: è l'unica domanda a cui quelle righe possano rispondere («di quelli a
cui l'ho data, quanti l'hanno presa»). Chi è entrato nel corso dopo il giro non
è un «no»: non ha mai ricevuto niente, e la pagina lo dice a parte, con i nomi,
perché è una cosa da fare. Chi aveva già una proposta in attesa viene **saltato**
dal servizio in silenzio (una per coppia, indice unico): a confrontare i due
numeri e a dirlo è la route.

Accanto alle «prese» c'è un secondo conto, **«te la fanno leggere»**: prendere
una scheda e aprirla a chi l'ha proposta sono due decisioni dello stesso modulo
(ADR-071), e la seconda si può togliere il giorno dopo. Quel numero è il
denominatore della media, e per questo si mostra sempre.

### 2 · La media è in quota, e su una seduta a testa

Due scelte, entrambe contro la formula che viene spontanea.

**Una seduta a testa, l'ultima.** Mediando tutte le sedute, chi si allena tre
volte a settimana sposterebbe da solo la media di un corso di cinque persone:
il numero direbbe quanto si allena lui invece che a che punto è il gruppo.

**In quota, non sui totali grezzi.** `TrainingSession.max_total` si legge dalle
registrazioni — è «il su 60 che quella sera era vero» — quindi una seduta
compilata a metà ha un massimo più basso; una scheda a giorni ha un massimo per
giorno (A · B · C non sono mai confrontabili fra loro in numeri assoluti); e
soprattutto **la copia è dell'allievo, che può cambiarla**. Si media perciò la
quota di ciò che era ottenibile e la si riporta sulla scala del modello: è la
stessa scala sola dell'[ADR-068](ADR-068-andamento-una-scala-sola.md), e per le
stesse ragioni.

Entra solo ciò che ha un massimo. Una copia che non ha ancora fatto numeri si
**conta e si dice** («1 non ha ancora fatto numeri»), invece di sparire in un
denominatore o, peggio, di entrare come zero — che è la bugia più facile da
scrivere in questa pagina. Se non c'è nessuna copia con numeri, o la scheda di
totale non ne ha, **non si mostra nessuna media**.

### 3 · «Questa settimana» è la settimana del corso

Il riquadro in cima dice «settimana 3 di 13»: le sedute contate sotto sono
quelle di *quella* settimana, che comincia nel giorno in cui è cominciato il
corso e non il lunedì. Un corso senza data d'inizio non ha settimane — lì sono
gli ultimi sette giorni, e l'etichetta cambia invece di far finta di niente.

Si contano su **tutte** le schede che l'istruttore legge dei suoi allievi, non
solo sulla scheda del gruppo: la domanda è se il corso si muove, e chi si allena
sulla scheda che aveva già si è allenato lo stesso.

### 4 · «N al livello dopo» sono i timbri, non le promozioni proposte

La fonte è `training_sheet.passed_at` — il **fatto** ([ADR-071](ADR-071-una-scheda-si-propone.md),
D8) — caduto nella finestra in cui quella persona faceva parte del corso
(`joined_at` → `left_at`, o la chiusura del gruppo).

L'alternativa era contare le proposte accettate con `promotes_sheet_id` di quel
gruppo. È stata scartata perché misurerebbe **un gesto dell'istruttore** (avergli
dato la scheda dopo) più l'accettazione dell'allievo, non il traguardo: con
`level_up=auto` non esiste nessuna proposta, quindi un corso in cui tutti sono
passati per soglia direbbe **zero**.

Si contano solo i timbri che l'istruttore **leggeva** quando sono avvenuti
(`training_sheet_reader.granted_at ≤ passed_at`, e non ancora revocato). Questo
rende il numero **stabile nel tempo**: un ex allievo che oggi ti richiude le
schede non può cambiare ciò che il tuo storico dice di tre anni fa. Lo storico
dice quello che hai visto succedere.

Per lo stesso motivo la query **non filtra le schede attive**: il passaggio di
livello di solito *archivia* la scheda superata (è la casella del modulo di
accettazione), e cercarla fra le attive vorrebbe dire non trovare mai i
passaggi andati a buon fine fino in fondo.

### 5 · Il vincolo dell'ADR-069 resta intero

Proporre una scheda «a tutto il corso» resta **N proposte**, una per allievo,
ciascuna con la sua casella della lettura. Il gruppo decide **a chi parte
l'invito**, non chi lo accetta — e non apre niente, come il §1 di questa ADR.
Dove si vede: «è il livello dopo» promuove, per ciascuno, **la sua** copia
della scheda del gruppo. È la ragione per cui `AssegnazioneService.proponi`
prende una mappa allievo→scheda e non un solo id.

### Presidi dell'emendamento

* `tests/new/unit/test_scheda_del_gruppo.py` — le quattro definizioni, ciascuna
  contro la definizione sbagliata che le somiglia (la media di tutte le sedute,
  i totali grezzi, lo zero al posto del dato mancante, il timbro fuori
  finestra, quello arrivato dopo la revoca).
* `tests/new/integration/test_scheda_del_gruppo_route.py` — il giro dalle
  route: N proposte, il saltato che si dice, la mappa delle promozioni,
  l'allowlist.
