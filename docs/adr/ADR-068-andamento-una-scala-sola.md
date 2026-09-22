# ADR-068 L'andamento mette insieme catalogo e schede su una scala sola, senza sommarli

**Data**: 2026-09-20
**Stato**: Accepted
**Decisori**: Paolo Coppola

## Contesto

L'**ADR-067**, al punto 6, ha lasciato aperta una domanda e ha detto dove si
sarebbe chiusa:

> Il numero di una voce di scheda — «4 su 5 tiri» — non è tarato come il
> punteggio dello stesso esercizio nel catalogo. […] Incrociare i due mondi
> nell'andamento è una scelta della fase 7, dove si guarda l'insieme; farlo qui
> vorrebbe dire prenderla senza dirlo.

Questa è quella scelta. La fase 7 costruisce «Il tuo allenamento» (#181): il
radar per abilità e per gesto, i due numeri del periodo, la riga di ogni asse.
Per disegnarli bisogna decidere **che cosa entra** in un asse.

I numeri che un giocatore produce allenandosi stanno in tre posti, e sono
tarati in tre modi:

| dove | il numero | il massimo |
|---|---|---|
| `challenge_attempt` (catalogo e gara) | il punteggio della prova, o l'esito | `challenge.max_score`, **facoltativo** |
| `training_entry` (caselle delle schede) | riusciti, punteggio, partite, minuti, spunta | `target_amount` copiato sulla casella, o `max_score` |
| `exam_challenge_result` (esami) | l'esito deciso dall'esaminatore | `ExamChallenge.max_score`, **per quell'esame** |

La issue #181 aveva già isolato il nodo: *«la percentuale non è calcolabile per
tutti»* — `Challenge.max_score` è facoltativo per una ragione dichiarata, ci
sono prove che si ripetono finché si sbaglia. E lasciava aperto se gli esercizi
**superato/non superato** possano stare nello stesso radar degli altri.

## Decisione

### 1. L'unità è la **quota di ciò che era ottenibile**

Un 12 su 15 e un 4 su 5 tiri valgono entrambi l'ottanta per cento. È l'unica
scala su cui esercizi diversi si possono confrontare: senza, un radar sommerebbe
punteggi tarati in modi incomparabili e direbbe che chi si allena su prove da 50
punti è più bravo di chi si allena su prove da 5.

Ne segue, e non è un effetto collaterale ma il prezzo dichiarato: **entra solo
ciò che ha un massimo**. Restano fuori le prove su un esercizio senza tetto
dichiarato, i minuti e le spunte. Non spariscono: si contano, e la pagina dice
quante sono. Un numero che sparisce senza spiegazione è un numero sbagliato.

### 2. I due mondi entrano **insieme**, e non si sommano mai su un esercizio

L'ADR-067 vieta di mescolare catalogo e schede **sullo stesso esercizio**, e
quel divieto resta intero: media e record di un esercizio sono quelli del
catalogo, il registro di una scheda è quello della scheda.

Qui la domanda è un'altra. Un asse del radar non chiede «quanto vale questo
esercizio», chiede «quanto bene tiro di draw» — e la risposta non cambia a
seconda di dove il numero è stato segnato. Le due fonti entrano quindi
**entrambe, una osservazione per registrazione**, ridotte alla quota del punto
1. Quello che non si fa mai è fonderle prima: un 10 su 10 nel catalogo e un 5 su
10 tiri in scheda fanno un asse al 75 per cento — la media di due osservazioni —
non un «15 su 20», che sarebbe un punteggio che nessuno ha mai fatto.

Perché il lettore lo sappia, la riga di ogni asse dice **quante osservazioni
vengono dalle schede**: la scala unica permette di confrontare, non dichiara che
le due cose siano la stessa.

> **Emendata il 2026-09-22** dall'[ADR-072](ADR-072-le-prove-in-scheda-sono-prove.md):
> le caselle «riusciti» e «punteggio» sono fatte di prove del catalogo, e
> entrano dal lato del catalogo — una osservazione per prova, segnata come
> «dalla scheda». La casella non si conta più, o si conterebbe due volte. Le
> caselle senza prove (fatto, vinte, minuti) restano lette come prima.

*Scartata*: due serie separate sul radar, una per mondo. Sono già due i poligoni
(adesso e prima), e quattro poligoni sovrapposti su otto assi non si leggono su
un telefono. Soprattutto, separarle risponderebbe a una domanda che nessuno fa:
nessuno vuole sapere se tira meglio di draw *in scheda* che *dal catalogo*.

*Scartata*: tenere fuori le schede. Per chi si allena con una scheda sono la
maggior parte dei numeri che produce, e il suo radar sarebbe costruito sulle
poche prove sciolte.

### 3. Superato/non superato vale tutto o niente

Un esercizio a esito netto entra con **100 o 0**, e mediato su molte prove dà la
percentuale di successo. È la stessa domanda degli altri — «quanto di quello che
potevi» — con l'ottenibile a uno.

Il costo, dichiarato: un esercizio superato una volta su due somiglia, sul
radar, a un esercizio in cui si fa metà del punteggio massimo. Sono due fatti
diversi resi con lo stesso numero. Si accetta perché l'alternativa — tenerli
fuori — toglierebbe dal radar interi assi per i giocatori che si allenano
soprattutto su prove a esito netto, e un asse assente mente più di un asse
approssimato.

### 4. Un esercizio con due abilità entra in **entrambe**, per intero

Le categorie sono un vocabolario, non una partizione (ADR-065): dividere il
punteggio fra le abilità di un esercizio direbbe che quel tiro è valso meno.

### 5. Sotto cinque osservazioni un asse sta sul grafico, ma non prende un numero

La forma del radar si legge come un insieme, e togliere un raggio la
deformerebbe. Una **riga** con una percentuale e una banda è invece
un'affermazione, e su due prove è rumore disegnato bene (#181). Gli assi magri
restano quindi disegnati, e una riga sotto il grafico li nomina.

### 6. Il confronto è con la finestra di **pari durata** subito prima

Trenta giorni contro i trenta prima, novanta contro novanta. Con «Sempre» un
prima non c'è, e sparisce invece di essere inventato tagliando lo storico a
metà.

Il **secondo poligono** si disegna solo quando *ogni* asse del radar ha numeri
anche nel periodo precedente. Un vertice mancante non si può mettere a zero:
zero vorrebbe dire «andavo malissimo», mentre il fatto è «non l'avevo
allenato», e sono due frasi diverse. Quando il poligono non si può disegnare il
confronto resta nei numeri, asse per asse.

## Conseguenze

* Un pacchetto suo, `models/andamento/`: legge `models/challenge` e
  `models/training_sheet`, e non può stare dentro nessuno dei due senza
  importare l'altro.
* La quota si tronca a cento. Una voce a minuti si può superare
  (`SheetMeasure.caps_value` lo dice), ma il fondoscala del radar è condiviso da
  tutti gli assi: uno sforato renderebbe illeggibili gli altri. È la stessa
  ragione per cui `trend_chart` usa il massimo dichiarato e non il miglior
  punteggio.
* La casella si legge col **suo** «su quanto» (`target_amount`), non con quello
  della voce di oggi: è la regola dell'ADR-067, e vale anche qui — rileggere la
  scheda di oggi rifarebbe i conti di sei mesi fa su una scheda cambiata.
* Le prove d'**esame** restano fuori da questa versione. Lì il massimo è quello
  che l'esame ha deciso per quella prova (`ExamChallenge.max_score`, ADR-042), e
  il voto lo dà un esaminatore davanti al candidato: è una misura di un altro
  tipo, e mescolarla senza dirlo sarebbe esattamente l'errore che questa ADR
  evita. Se un giorno entrerà, sarà con una riga che lo dice.
* Le due soglie che separano «solido», «in crescita» e «da costruire» (70 e 50)
  non sono del dominio: sono un modo di dire a parole ciò che il numero dice in
  cifre, e stanno in un posto solo.

## Note di attuazione

* `models/andamento/view.py` — le osservazioni, le finestre, le righe.
* `models/andamento/radar.py` — la geometria, come `trend_chart`: i conti qui, il
  template stampa.
* `tests/new/unit/test_andamento.py` — la verifica che il piano chiede: le due
  fonti sulla stessa scala, che non si sommano, e ciò che resta fuori.

## Riferimenti

* Issue **#181**; `docs/redesign-7c/canvas-tpa-esercizi/PIANO.md`, fase 7.
* [ADR-067](ADR-067-scheda-di-allenamento.md) — punto 6: la domanda che questa
  ADR chiude.
* [ADR-065](ADR-065-profilo-dell-esercizio.md) — i due vocabolari, e perché i
  radar sono due.
* [ADR-042](ADR-042-certified-exam.md) — i due `max_score`, e perché le prove
  d'esame stanno in un'altra tabella.
