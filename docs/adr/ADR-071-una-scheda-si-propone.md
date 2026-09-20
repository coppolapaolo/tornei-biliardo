# ADR-071 · Una scheda si propone, non si assegna

**Stato**: accettata · **Data**: 2026-09-20 · **Issue**: #173
**Fase**: 8d del redesign «TPA ed esercizi»
([PIANO.md](../redesign-7c/canvas-tpa-esercizi/PIANO.md)) · **Segue**
[ADR-069](ADR-069-istruttore-e-allievo.md) e
[ADR-070](ADR-070-gruppi-di-allievi-e-triage.md)

## Contesto

L'ADR-069 ha dato all'istruttore il ruolo e il legame, l'ADR-070 i gruppi e
l'elenco che dice a chi badare oggi. Mancava il gesto per cui tutto il resto
esiste: **dargli una scheda da fare**.

È anche il punto in cui è più facile buttare via le due ADR precedenti. In ogni
piattaforma di corsi «assegnare» vuol dire scrivere nell'area dell'allievo: il
maestro compila, l'allievo trova. Fatto così, il consenso rovesciato che
l'utente aveva chiesto — è il giocatore che aggiunge l'istruttore — tornerebbe
a girare nel verso di prima, e per la porta di servizio: non con una decisione
sul consenso, ma con una funzione di comodità.

## Decisione

### 1 · È una proposta, e la scheda nasce quando l'altro la prende

`training_assignment`: chi propone, a chi, quale scheda (il **modello**, che
resta dell'istruttore), con che biglietto. Finché l'allievo non risponde non
esiste nessuna scheda sua, e l'istruttore non ha guadagnato **una sola
lettura**.

Accettando, la scheda nasce — con `create_sheet` e `save_composition`, cioè
passando dalle stesse convalide di una composta a mano — e nasce **sua**:
`owner_id` è lui, la cambia, la archivia, decide chi la legge. Da quel momento
i due fogli non si parlano più: se domani l'istruttore corregge il modello,
quello dell'allievo non si muove. È lo stesso schema di
[ADR-066](ADR-066-prova-fatta-di-colpi.md) e
[ADR-056](ADR-056-apertura-e-runout-sul-segnapunti.md) — ciò che è stato dato
resta com'era.

### 2 · Si propone solo a chi ti è già allievo

Cioè a chi ti ha già aperto una scheda. È la stessa frase dei gruppi (ADR-070
§1) e qui pesa di più: una proposta è un **messaggio** che arriva a qualcuno
che spesso è minorenne, e un istruttore che potesse scrivere per primo a
chiunque avrebbe in mano una rubrica.

Conseguenza voluta: **la prima mossa resta sempre dell'allievo.** Non c'è modo
di cominciare un rapporto dal lato del maestro, nemmeno in buona fede.

### 3 · Il permesso di lettura è una casella, spuntata

Nel modulo con cui l'allievo accetta c'è «Fai vedere a *X* come va», **già
spuntata**, con sotto cosa vedrà e come si toglie. Decisione dell'utente del
2026-09-20, fra tre strade:

| | Cosa costa |
|---|---|
| spuntata *(scelta)* | un default che qualcuno non legge |
| da spuntare | in molti la saltano, l'istruttore non vede niente, e la funzione sembra rotta |
| due gesti separati | il più pulito, e il più faticoso: due pagine per una cosa sola |

Resta una scelta dell'allievo in tutti i sensi che contano: è lui a premere,
la casella è accanto al pulsante e non in fondo alla pagina, e il permesso si
toglie da «Chi la legge» come tutti gli altri. Soprattutto, **non è la
proposta a dare l'accesso**: senza la spunta la scheda nasce lo stesso e
nessuno legge niente — è il caso che il presidio verifica per primo.

Due cose che di proposito **non** si copiano dal modello: i lettori e
`readers_see_notes`. Chi legge una scheda e chi ne legge le note sono due
decisioni del proprietario, e il proprietario qui è un altro.

### 4 · Una proposta in attesa per volta, e lo impone il database

Indice unico **parziale** su `(instructor_id, user_id) WHERE closed_at IS
NULL`. Non è pignoleria: un'unicità che vive in un `if` di Python è invisibile
a chi scrive in blocco, ed è così che unendo due account un giocatore è finito
iscritto due volte alla stessa gara (ADR-070 §2).

Il limite è **per coppia**, non per allievo: due istruttori possono proporre
insieme allo stesso ragazzo, perché il legame è per scheda e uno non chiude la
porta all'altro (ADR-069, D11).

Chi ha già una proposta in attesa viene **saltato**, non rifiutato: mandarne
una seconda non aggiungerebbe niente, e far fallire l'invio a tutto un gruppo
per uno che non ha ancora risposto sarebbe peggio. Chi chiama confronta i due
numeri e lo dice.

### 5 · Chi avvisa chi

Non è simmetrico, come già in ADR-069:

* **la proposta avvisa l'allievo** — è un messaggio, esiste per essere letto;
* **la risposta avvisa l'istruttore**, sia il sì sia il no: sta aspettando;
* **ritirare una proposta non avvisa nessuno.** Era un invito, e ritirarlo
  prima che l'altro risponda non è una notizia: è non aver detto niente.

## Alternative scartate

**L'istruttore scrive la scheda in casa dell'allievo.** La forma di ogni
piattaforma di corsi, e quella che l'utente ha già rifiutato in grande: qui
tornerebbe travestita da comodità. Con l'aggravante che una scheda comparsa
senza che tu l'abbia presa è, per chi la trova, indistinguibile da un dato che
qualcun altro controlla.

**Copiare la scheda al momento della proposta, e non dell'accettazione.**
Congelare il modello renderebbe la proposta un contratto: l'istruttore non
potrebbe più correggere un refuso senza rifarla. Si copia **com'è il giorno in
cui si accetta**, e il prezzo — chi accetta lunedì e chi giovedì possono
ricevere due versioni — è minore del beneficio, perché da lì in poi le due
schede sono comunque indipendenti.

**Un legame vivo fra modello e copia** («l'istruttore aggiorna, e la scheda di
tutti cambia»). Sarebbe l'unico modo per tenere venti allievi davvero
allineati, ed è esattamente ciò che l'ADR-069 vieta: una mattina il tuo
allenamento è diverso e non l'hai deciso tu. Se servirà, sarà una proposta
nuova — cioè di nuovo un gesto dell'allievo.

## Conseguenze

* La pagina «I miei allievi» costa una query in più (`attese_di`), una per
  l'intera pagina e non una per riga.
* Un istruttore che non ha composto nessuna scheda non ha niente da dare: la
  pagina glielo dice e lo manda a comporne una. È giusto che l'ordine sia
  questo — una scheda si dà, non si inventa mentre la si manda.
* `TrainingAssignment` porta `group_id` fin da ora, perché la proposta a tutto
  un gruppo (stessa fase) è la stessa riga con un campo in più — ed è quel
  campo a rendere dicibile «la media del gruppo, su 60» (ADR-070 §5).

## Presidi

* `tests/new/unit/test_assegnare_una_scheda.py` — le regole: a chi si propone,
  di chi è la copia, che il permesso è un atto dell'allievo, una proposta per
  volta, il modello che cambia dopo e non tocca la copia.
* `tests/new/unit/test_proposte_migration.py` — lo schema, e l'indice unico
  parziale provato con un `INSERT` a mano.
* `tests/new/integration/test_pagina_proposte.py` — le route, la casella che
  arriva **dal modulo** (spuntata e non), il 404 sulla proposta di un altro, e
  l'allowlist di produzione.
