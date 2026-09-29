# [075] Le impostazioni si correggono e restano scritte, invece di bloccarsi

**Data**: 2026-09-29
**Stato**: Accepted — attuazione completata il 2026-09-29 (vedi «Attuazione»)
**Decisori**: Paolo Coppola, Claude

Specifica completa, con i casi e la verifica sul codice:
[`docs/usecases/regolamento-di-gara.md`](../usecases/regolamento-di-gara.md).
Riprende la issue #265 e la #549.

## Contesto

Il 28 settembre 2026 il direttore ha creato in produzione la finale dei playoff
del campionato e non è riuscito a cambiarne né la sala né chi spacca. La finale
nasce con gli iscritti dentro (chi ha accettato l'invito), e
`Gara.can_be_modified()` vale solo in preparazione **e senza nessuna riga
d'iscrizione**: per la finale, mai.

Non era un caso isolato. Il blocco è un solo booleano che chiude insieme una
ventina di campi eterogenei:

- `Gara.can_be_modified()`: preparazione e zero iscritti;
- `Campionato.can_be_modified()`: basta una gara aperta, in corso o conclusa,
  anche senza iscritti, e il campionato non si tocca più;
- `RoundConfiguration`: solo in preparazione;
- `PlayoffService.update_configuration`: tutto chiuso appena partono gli inviti.

Le correzioni oneste restano impossibili (il peso sbagliato di una gara, la
sala che cambia, la gara da rimandare per mancanza di iscritti, #549), e gli
aggiramenti — cancellare e rifare — sono peggio, perché il blocco si vede e
l'aggiramento no.

D'altra parte, alcune cose **non** possono cambiare, e non per prudenza:

- le regole con cui una partita è già stata giocata;
- la struttura di una gara avviata: nell'Amalfi il salto dipende dal numero
  totale di turni (`amalfi.py:107`), nella casuale i turni esistono tutti
  dall'avvio, nel tabellone il sistema di classifica è imposto;
- i criteri di qualificazione ai playoff dopo gli inviti: qualcuno ha già
  accettato o rifiutato su quei criteri.

La verifica sul codice ha trovato che oggi diverse regole la partita le
**rilegge dalla gara** a ogni accesso («al N», disciplina, triangoli per set,
chi apre, chi spacca, handicap, categorie per l'ELO). Togliere il blocco senza
cambiare questo renderebbe ogni correzione retroattiva.

## Decisione

**Non impedire, tracciare.** Il direttore può correggere quasi tutto, quasi
sempre; ogni correzione resta scritta e visibile a tutti.

1. **Storia delle modifiche**, per gara, campionato e playoff: una voce per
   salvataggio, righe campo per campo (prima → dopo), chi (nome e ruolo),
   quando, da dove, motivo **facoltativo**. Non si cancella e non si corregge.
   Appartiene alla gara: se la gara viene cancellata, la storia va con lei.
2. **Le regole si fissano sulla partita** quando nasce. Un cambio di regola
   vale **dal turno successivo**: il turno in corso e quelli giocati restano
   come erano. Il turno è `round_number`, che in tutti i formati tranne la
   casuale parte solo a turno precedente chiuso (`verifica_turno_chiuso`);
   nella casuale, dopo l'avvio, le regole di gioco sono bloccate.
3. **Struttura bloccata dopo l'avvio** (strategia, numero di turni, sistema di
   classifica): si cambia solo con «Annulla l'avvio», che esiste già.
4. **Il campionato propone, la gara decide.** I valori del campionato sono
   copiati nella gara; quando cambiano, l'app propone di aggiornare le gare non
   ancora avviate, gara per gara. Chi apre, chi spacca e handicap, che oggi
   seguono il campionato in diretta, passano allo stesso sistema. Due
   eccezioni: il **sistema di classifica** vale per tutto il campionato e si
   blocca al primo avvio; **locandina, link esterno e link al regolamento**
   restano in diretta, perché sono presentazione e non regole.
5. **Playoff**: criteri di qualificazione bloccati dopo gli inviti; valori
   della finale proposti come per il campionato; gli strumenti a mano
   (aggiungere, togliere, rispondere per conto) entrano nella storia. Una
   correzione che sposta la classifica dopo gli inviti produce una
   **proposta** di inviti che il direttore accetta, rifiuta o corregge a mano.
6. **A gara finita** si corregge solo *quanto conta* (peso, punti per
   posizione), con un segno visibile: il vecchio valore barrato nell'elenco
   delle gare e una riga di ricalcolo sopra la classifica.
7. **Notifiche accorpate e riconferma**: le modifiche ravvicinate partono in
   una sola notifica (stato di partenza contro stato attuale); data, ora oltre
   un'ora, sala e quota in aumento chiedono la riconferma. Chi non riconferma
   resta iscritto «da riconfermare» e decide il direttore, che può
   riconfermare per conto del giocatore.
8. **Una pagina pubblica, «Regolamento di gara»**: regole in vigore, per turno,
   storia, e il documento del regolamento in fondo.

## Alternative considerate

### Rilassare il blocco senza traccia

- Pro: il lavoro più piccolo.
- Contro: una correzione a gara in corso diventa invisibile, e con le regole
  rilette dalla gara anche retroattiva. È il contrario di quello che serve in
  caso di contestazione.

### Eredità in diretta dal campionato per tutti i valori

Discussa e scartata durante l'intervista.

- Pro: un cambio nel campionato raggiunge tutte le gare da solo.
- Contro: le gare cambiano senza che nessuno le tocchi, e la storia della gara
  dovrebbe raccontare modifiche fatte altrove. I valori del campionato sono
  nati come valori di partenza (`SPECIFICHE.md`, «tutti i valori vengono
  precompilati»).

### Storia legata a «campionato + numero di gara» (#265)

- Pro: sopravvive alla cancellazione e ricreazione della gara.
- Contro: complica il modello per un caso che il direttore ha giudicato
  raro. Deciso: la storia appartiene alla gara.

### Blocco durante il turno invece di «dal turno successivo»

- Pro: più semplice da spiegare.
- Contro: il direttore deve ricordarsi di tornare fra un turno e l'altro. Con
  i turni sequenziali le due soluzioni danno lo stesso risultato; scelto il
  salvataggio subito.

## Conseguenze

### Positive

- La finale dei playoff, e ogni gara con iscritti, si corregge.
- Una partita giocata non cambia più per una modifica successiva: vale anche
  per l'ELO, che oggi rilegge le categorie correnti a ogni ricalcolo.
- Le contestazioni hanno un documento a cui riferirsi.

### Negative

- Colonne nuove sulla partita e riempimento delle righe esistenti.
- Il modulo di modifica deve sapere quali campi sono stati davvero cambiati.
- Ogni servizio che modifica impostazioni deve ricevere chi agisce.

### Rischi

- Una strada di modifica dimenticata non scrive la storia. Il presidio è un
  test che elenca le strade note (inventario in
  `docs/usecases/regolamento-di-gara.md`, «Tutte le strade che cambiano
  impostazioni»).

## Attuazione

**Completata il 2026-09-29**, rilasciata nelle versioni dalla 1.49.1 alla 1.53.0. Una PR
per parte, ciascuna con le note datate in `SPECIFICHE.md` e negli ADR che
emenda, così specifica e codice non divergono mai:

| # | Parte | PR | Presidio principale |
|---|---|---|---|
| 1 | Storia delle modifiche della gara; modifica con iscritti prima dell'avvio | #585 | `test_storia_modifiche_gara.py` |
| 2 | Regole fissate sulla partita | #586 | `test_regole_fissate_sulla_partita.py` |
| 3 | Modifica a gara avviata, dal turno successivo | #588 | `test_modifica_a_gara_avviata.py` |
| 4 | Campionato: valori proposti | #589 | `test_campionato_valori_proposti.py` |
| 5 | Playoff: criteri bloccati, proposta alla finale, storia | #591 | `test_playoff_storia_e_proposta.py` |
| 6 | Correzione a gara finita, segno in classifica, proposta di inviti | #592 | `test_ricalcolo_a_gara_finita.py` |
| 7 | Notifiche accorpate | #594 | `test_notifiche_accorpate.py` |
| 8 | Riconferma | #595 | `test_riconferma_iscritti.py` |
| 9 | Date che scavalcano le gare successive; capienza che ripesca | #596 | `test_sposta_gare_successive.py` |
| 10 | Pagina «Regolamento di gara» e `/aiuto` | #597 | `test_regolamento_di_gara.py` |
| 11 | Pagina «Regolamento del campionato» | #599 | `test_regolamento_campionato.py` |

La specifica è stata scritta nella #584. Nella stessa giornata è entrata la
#583, che non discende da questo ADR ma chiude un difetto trovato durante la
verifica: le route dei playoff non controllavano che configurazione e invito
fossero del campionato dell'indirizzo.

ADR emendati: 016, 027, 047, 049, 053, 056, 058. I criteri di accettazione
della specifica sono spuntati, ciascuno col test che lo presidia.
