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

### 6 · Il passaggio di livello ha tre sancitori e due gesti (D8)

La fase 6 aveva lasciato aperta una domanda — **chi dice che hai passato il
livello?** — e l'ADR-070 l'aveva *mostrata* senza chiuderla: «Valuta il
passaggio di livello» diceva all'istruttore che l'allievo era pronto, e poi non
c'era niente da premere. Qui si chiude.

La risposta sta sulla scheda, in `level_up` (`LevelUp`), e sono **tre**:

| | Chi sancisce | Per chi è |
|---|---|---|
| `none` | nessuno | la scheda non è fatta a livelli |
| `auto` *(default)* | la soglia stessa, alla seduta in cui viene tenuta | chi si allena da solo — senza, il suo gradino non lo timbrerebbe mai nessuno |
| `instructor` | una persona, fra quelle che leggono la scheda | chi va in sala da un maestro |

Il default è `auto` perché è ciò che la scheda faceva già prima di questa
colonna: la fine seduta diceva «gradino raggiunto» e nessuno lo scriveva. Le
schede che esistono già prendono lo stesso default, e **non c'è backfill** di
`passed_at`: una scheda superata è un fatto avvenuto in un giorno, e inventarne
la data scriverebbe nello storico qualcosa che non è successo.

Conseguenza sul triage (ADR-070 §4): «Valuta il passaggio di livello» compare
**solo** per le schede `instructor`. Con `auto` non c'è niente da valutare, e
mettere in elenco chi non ha bisogno di te è un invito a premere qualcosa che
non esiste.

**Superato è un fatto, non uno stato che va e viene.** Timbrato `passed_at`, la
scheda resta superata anche se le sedute dopo vanno peggio: un attestato, non
un termometro. È la stessa ragione per cui `break_player_id` si persiste invece
di essere dedotto a ogni lettura (ADR-056), ed è anche ciò che permette al
gradino di essere contato — «5 al livello dopo» nello storico di un gruppo.

E **il gradino è un fatto anche per chi lo conferma**: `GradinoService.conferma`
rifiuta se la soglia non è stata tenuta. Un istruttore non promuove chi non è
arrivato — potrebbe volerlo, e il posto per dirlo non è un pulsante che scrive
nello storico dell'allievo una cosa non avvenuta.

**I gesti sono due, e il secondo è facoltativo.** «Confermo» timbra; «Dai il
livello dopo» è una proposta come le altre, con `promotes_sheet_id` a dire
quale scheda lascia indietro. Si può essere promossi prima di avere in mano la
scheda nuova — succede sempre, in sala — e accettandola l'allievo può mettere
nello storico quella superata: una casella del **suo** modulo, perché la scheda
è sua e archiviare non è cancellare.

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

**Un solo sancitore del gradino.** Sarebbe stato più semplice: o lo timbra la
soglia, o lo conferma un istruttore. Ma le due risposte servono due persone
diverse, e sceglierne una sola avrebbe lasciato fuori l'altra — chi si allena
da solo senza nessuno che confermi, o l'allievo promosso da un conteggio
mentre il suo maestro lo guardava sbagliare.

**Il timbro senza la scheda dopo, o la scheda dopo senza il timbro.** Ciascuno
da solo racconta metà: il primo promuove e lascia l'allievo sulla stessa
scheda, il secondo gli dà la scheda nuova senza dire che ha passato la
precedente — e allora «quanti sono andati al livello dopo» non si può contare.
Sono due gesti perché sono due decisioni, e in sala avvengono in momenti
diversi.

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
* `tests/new/unit/test_passaggio_di_livello.py` — le tre risposte di `level_up`,
  il timbro che resta dopo una seduta storta, e l'istruttore che non promuove
  chi non è arrivato.
* `tests/new/unit/test_allievi_triage.py` — che una scheda `auto` **non**
  comparisca in «Valuta il passaggio di livello».
