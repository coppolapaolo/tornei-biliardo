# Pagina gara del direttore — stato del canvas

Canvas: <https://claude.ai/code/artifact/2a185d1b-19e1-4e16-8456-b866787dcc1c>
(disegnato il 31/08/2026, versionato l'11/09). Le sorgenti stanno in
`sorgenti/`: `gen_gara_direttore.py` (il kit — token 7c copiati alla lettera
da `tokens-7c.css` e `theme-7c.css` — e le tre direzioni del primo giro),
`gen_fasi.py` (le schermate delle cinque fasi e il `canvas.json` completo),
`gen_decisioni.py` (la pagina «0 · Decisioni», vedi sotto),
`gen_locandina.py` (la locandina di prova 1200×630 dello schermo in sala,
`locandina.png`, con Pillow). Si rigenera con
`python3 sorgenti/gen_decisioni.py`, che richiama gli altri due; il canvas seminato
(`pagina-gara-direttore.html`, 3 MB) non è committato, vedi «Nota sui file».

## Da dove viene

Il primo giro proponeva **tre direzioni sulla stessa schermata** (la gara in
gioco), telefono e desktop:

* **A · Regia** — la pagina di oggi con una fascia in cima che dice a che
  punto è il turno e cosa lo tiene aperto (tavoli da assegnare, risultati
  mancanti). Costo minimo: aggiunge un blocco, non toglie niente.
* **B · Console** — il turno in corso diventa la pagina: punteggio segnato
  sulla card, tavolo sulla card, a destra «da fare adesso» e la mappa dei
  tavoli. Il più costoso: tocca il segnapunti, non solo l'impaginazione.
* **C · Fasi** — niente quattro linguette: una striscia mostra il ciclo e la
  pagina è la fase in corso; direttori, tavoli, squadre, categorie e turni
  finiscono sotto «Impostazioni gara». In gioco il 90% di quelle sezioni non
  serve; costa un tap in più per un co-direttore a gara iniziata.

Valutarle in astratto non funzionava: la domanda giusta per questa pagina
non è «quale impaginazione» ma **«cosa deve fare il direttore adesso»**. Da
lì il secondo giro: gli **user journey completi, fase per fase**, una pagina
di canvas per fase. Le schermate sono una sintesi — la fascia di fase di C in
cima (dove siamo, l'unica cosa da fare), il linguaggio di B nel gioco (la
console del primo giro riusata come panoramica, artboard «Main»).

**Nessuna delle tre direzioni è stata scelta formalmente**: le fasi sono la
proposta, e vanno guardate prima di scrivere codice.

## Le cinque fasi, 33 schermate, più le 4 del campionato

Ogni schermata mostra **comandi che esistono davvero**: etichette e
condizioni vengono da `_gara_management.html`, `_round_management.html`,
`_gara_tables_config.html`, `_gara_inscriptions.html`,
`_match_admin_controls.html`, `_ssr_section.html`, `admin/gara_vetrina.html`.
Dove il mockup propone qualcosa che l'app non fa, lo dice il bigliettino
accanto all'artboard.

1. **Preparazione** — panoramica con l'elenco di cosa manca prima di aprire
   le iscrizioni; turni e distanze (ADR-027, il turno modificato si distingue
   con la pastiglia); tavoli come tessere da toccare nell'ordine di
   assegnazione; co-direttori con ricerca; vetrina (locandina, indirizzo
   pubblico, link esterno) come voce della preparazione; il foglio «Apri le
   iscrizioni» con date, minimo e massimo; il desktop senza linguette.
2. **Iscrizioni** — «7 su 16, ne servono 8» come numero che decide se la gara
   parte, link pubblico in alto; elenco raggruppato con categoria accanto al
   nome e lista d'attesa a parte con «Fai entrare»; iscrivi un giocatore per
   cognome, nome o username; iscrizioni scadute (stato derivato: estendi o
   annulla, o avvia se il minimo c'è); il foglio «Avvia la gara» che dice
   **prima** chi prende la X, che i turni nascono tutti adesso, l'ordine dei
   tavoli.
3. **Gioco** — panoramica del turno (la console); assegna o cambia il tavolo
   (gli occupati mostrano da chi); segna il risultato con gli stepper sulla
   card (scelta 3C); valida un
   risultato chiuso dai giocatori (è ciò che libera il tavolo); correggi un
   risultato chiuso a gara in corso (issue #90) con le due conseguenze
   scritte; classifica dopo il turno con la nota sull'ordinamento e sul
   valore della X; turno concluso con le tre uscite separate per gravità;
   il direttore che gioca (la sua partita in cima, scura); il turno su
   desktop.
4. **Spareggio** — serve uno spareggio (parimerito fino alla posizione
   configurata, con la strada indietro); i punti SSR con gli stessi stepper,
   un gruppo per posizione contesa; termina la gara e cosa comporta, con
   «Annulla lo spareggio» accanto.
5. **Conclusa** — la classifica finale come soggetto, podio in card accento,
   pastiglia SSR dove lo spareggio ha deciso; «cosa resta dopo»: dove sono
   finiti i punti, la pagina pubblica, cosa non si tocca più.

## Cosa il canvas ha trovato nell'app

Rilievi veri, non del mockup. Verificati ancora validi l'11/09/2026:

* i **tavoli si scelgono solo a iscrizioni aperte** (`_gara_tables_config.html`,
  `status == INSCRIPTION`) e si scrivono come «3, 1, 2» in un campo di
  testo, pur essendo una decisione di preparazione;
* il modale «Apri le iscrizioni» ha solo le due date: **minimo e massimo
  stanno nella modifica gara**, cioè altrove;
* la **vetrina** (locandina, indirizzo pubblico, link esterno) è una pagina
  separata raggiungibile dal menu, non una voce della preparazione;
* i co-direttori si aggiungono da un **select** con tutti i direttori in zona;
* il risultato si segna con **campi numerici** e l'errore sulla distanza
  arriva **dopo**, con un avviso rosso;
* a turno chiuso le tre uscite (avvia il prossimo, annulla l'avvio, azzera i
  risultati) sono **tre bottoni della stessa forma**, uno sotto l'altro;
* nella griglia dei tavoli l'occupato appare **grigio come «non
  disponibile»** invece che evidenziato con chi c'è;
* a gara conclusa la linguetta **Gestione resta ma non contiene più niente**
  (già nello STATO generale del redesign);
* il **referto TPA non esiste sulle partite di gara** (`TpaReferto` ha la
  sola chiave `individual_match_id`): è un fatto di dominio, non un rilievo.

Superato dopo il canvas: il badge «N da chiudere» in dashboard, che non
portava da nessuna parte — dalla #295 la tessera della gara annuncia il
comando che aspetta («Termina la gara», «Avvia il turno N»).

## Deciso il 12/09/2026 (pagina «0 · Decisioni»)

Le cinque decisioni stanno **a confronto nella pagina «0 · Decisioni»** del
canvas (`gen_decisioni.py`): una riga per decisione, le alternative fianco a
fianco con **gli stessi dati** — cambia solo la forma — e un bigliettino per
riga con motivazione, costo e la risposta. Le scelte sono già applicate alle
pagine 1–5:

1. **La forma**: 1B Console in gioco, con la **card riassuntiva scura** come
   la fascia di fase; 1S Sintesi in preparazione. Regola corretta: **i tavoli
   si scelgono sempre**, di solito prima di avviare un turno, perché è allora
   che si sa quanti ne servono; la riga mostra quanti ne ha la sala. Oggi
   l'app li lascia modificare **solo a iscrizioni aperte**, e lo vieta anche
   il servizio (`GaraService.update_tables_config` → `ConflictError`), non
   solo il template.
2. **La striscia di fase** al posto delle linguette. **Da confermare**:
   come si arriva alla gestione nelle altre fasi. Proposta disegnata e
   corretta la sera del 12/09 col codice alla mano (2S · Il menu del turno,
   2S · Il menu della partita, 2S · Impostazioni gara, 2S · nello
   spareggio):
   * il **turno** ha un solo comando in gioco, annullarne l'avvio, e solo
     finché nessuna partita ha un punteggio > 0, X esclusa
     (`Gara.can_cancel_round`, use case 8): sta nei tre puntini accanto a
     «Turno N»;
   * la **partita** ha i suoi sulla card: cambia tavolo (3.2), azzera
     (`reset_match`, finché il turno dopo non è avviato), e su una chiusa
     «correggi il risultato» (3.4). La partita **da validare** è la 3.3:
     arrivata alla distanza dal segnapunti dei giocatori senza doppia
     conferma, mostra «Valida» (`is_at_distance and not is_player_validated`
     in `_match_card.html`), che la chiude e libera il tavolo
     (`MatchValidationService.validate_and_complete`);
   * l'**azzeramento in blocco del turno** era nella prima versione del
     disegno: nell'app esiste («Reset ultimo turno»,
     `bulk_reset_round_matches`) ma compare solo a gara finita, prima di
     terminarla. Tolto dal disegno su indicazione dell'utente;
   * «**Impostazioni gara**» in gioco contiene solo ciò che si tocca
     davvero: direttori e vetrina (nessun guard di stato), e i tavoli, oggi
     bloccati dopo l'avvio — la regola vuole che si cambino **anche a
     iscrizioni chiuse e fra un turno e l'altro**. La gara si modifica solo
     in preparazione senza iscritti (`Gara.can_be_modified`), si elimina
     solo fino alle iscrizioni. La prima versione della schermata li
     inventava;
   * lo spareggio ha la sua tacca, che compare solo nelle gare che ce
     l'hanno.
3. **Il punteggio sulla card** (3C): la 3.3 «Segna il risultato» è uscita
   dalla pagina 3.
4. **Gli esercizi** sono due cose, entrambe anche con Amalfi: gli **esercizi
   fra i turni** (`GaraChallenge.round_number`, tentativi contati,
   classifica a parte) — oggi mostrati solo col casuale, ma il limite sta
   nei template, non nel servizio — e la **X con esercizio** (policy
   «Bye+Challenge», SPECIFICHE.md riga 138), che è una voce di «Chi riposa»
   e oggi vale con qualunque strategia tranne i tabelloni
   (`x_challenge_section.js`). **Aperto**: i testi delle due righe
   (schermata 4 · Le due forme).
5. **Le partite restano in pagina** a gara conclusa (5S). La pagina pubblica
   mostra la classifica finale (`vetrina_gara.html`, `vetrina.conclusa`):
   la riga lo dice.

Aggiunte la sera del 12/09, su richiesta: il **desktop di ogni fase** (2.6,
4.4, 5.3 accanto a 1.7 e 3.8 — in preparazione si usa quasi sempre, e
qualche direttore lo preferisce anche in gioco) e lo **schermo in sala**
(3.9): pubblico, senza menu, da leggere a tre metri, con i tavoli, la
classifica dopo l'ultimo turno chiuso e il turno precedente. Non esiste
nell'app: `gara_detail_public` rimanda alla pagina gara, la vetrina a gara in
corso dice solo «Gara in corso»; SPECIFICHE.md riga 357 chiede «i risultati
dei match in tempo reale». Per i tabelloni va disegnato col tabellone.

## Revisione del 12/09 sera (rilievi dell'utente sulle pagine 1–5)

Verificato nel codice, e applicato al canvas:

* **1.2**: la descrizione della gara («Al 5 · Palla 8») prende sempre i
  valori della creazione (`gara_detail.html` usa `gara.distance`): quando i
  turni cambiano dovrebbe dirlo. Rilievo nuovo, sul bigliettino.
* **1.3 tavoli**: elenco ordinato con il nome che si scrive, l'ordine che
  si trascina, si toglie e si aggiunge; i nomi vengono dalla sala
  (`BilliardHall.get_table_names`) e `available_tables` è già una lista di
  nomi liberi. Fra i passi della preparazione (1.2–1.7) c'è ora avanti e
  indietro, senza tornare alla 1.1.
* **1.4–1.5 esercizi fra i turni**: elenco e foglio di aggiunta con i tre
  campi del modale di oggi (esercizio, dopo quale turno, tentativi).
* **1.9 e ogni desktop**: la colonna laterale ha il comando per nasconderla
  (issue #153, chiusa ma non implementata: `base.html` non ha alcun
  collapse); lo schermo in sala non la ha affatto.
* **2.2**: il campo per iscrivere sta in cima, sempre visibile; la
  categoria è un chip che si tocca (oggi un combo per riga, un nome nuovo
  crea la categoria); la lista d'attesa entra da sola quando un iscritto si
  ritira (`InscriptionService._promote_and_notify`): **«Fai entrare» non
  esiste** ed è stato tolto.
* **2.5**: turni, distanze, disciplina e X si toccano solo in preparazione
  (`_round_management.html` solo con `status=setup`, `Gara.can_be_modified`
  solo senza iscritti): con le iscrizioni aperte nulla cambia sotto i piedi
  degli iscritti. Il foglio riporta soltanto.
* **3.2**: i tavoli occupati mostrano i due giocatori.
* **3.3 da validare**: rifatta con la geometria degli stepper (nome sopra,
  numero grande sotto, vincitore in evidenza); la regola è
  `is_at_distance and not is_player_validated`.
* **3.5–3.6 classifica**: sistema a vittorie e sistema RACK (vinti/persi),
  con la freccia di tendenza rispetto al turno prima.
* **3.7 turno concluso**: solo «Avvia il turno 3». Annullare l'avvio e
  avviare il turno dopo sono alternativi: si annulla finché nessuna partita
  ha un triangolo (`Gara.can_cancel_round`), si avvia quando tutte sono alla
  distanza, in mezzo nessuno dei due. Niente azzeramento in blocco: le
  partite si azzerano una per una (`reset_match`).
* **3.8 il direttore gioca**: card scura con i due giocatori nella forma
  delle altre card, «Vai al segnapunti».
* **3.9 desktop**: una partita da validare fra le card; nella colonna
  destra solo ciò che si modifica in gioco.
* **3.10 schermo in sala**: rifatto con la locandina in testa, i tavoli come
  tabelloni, le medaglie in classifica.
* **5.1 e 5.3**: podio e posizioni 1–3 nei colori delle medaglie dell'app
  (`--c7-oro`, `--c7-argento`, `--c7-bronzo`).
* **Pagina 7, campionato e playoff** (mobile e desktop): la pagina del
  campionato per chi lo dirige e la fase playoff, dagli inviti alla gara
  playoff. Da rivedere insieme come le altre.

## Rifatte il 13/09 (rilievi del 12/09 notte)

Applicate al canvas e ripubblicate. La regola generale dell'utente: **lo
spazio vuoto non è buon design**, si riempie con ciò che serve o si toglie.

* **3.10 schermo in sala**: la locandina è il banner social della vetrina,
  1200×630 (`admin/gara_vetrina.html`), in testa **a tutta larghezza**,
  ritagliata al centro come fanno le anteprime social; sotto, una barra
  scura con nome della gara, dati e turno. I quattro tavoli riempiono
  l'altezza (`flex:1`), la classifica dopo il turno 1 arriva in fondo con
  tutti e dieci i giocatori, il turno 1 sotto. La locandina di prova la
  genera `gen_locandina.py`; nel seed va passata con `--image`.
* **3.9 desktop del gioco**: la colonna sinistra è una griglia di sei
  caselle che riempiono l'altezza — le cinque partite del turno (da
  validare, due in corso, una in attesa di tavolo, una conclusa) e il turno
  1 compatto; la destra arriva in fondo con «da fare adesso», i tavoli e la
  classifica dopo il turno 1 (dieci righe). «Impostazioni gara» sale in
  testata accanto a «Iscritti»: direttori, vetrina, tavoli.
* **3.3 e 3.4**: le card in sola lettura (da validare, concluse) usano la
  geometria degli stepper — nome sopra, numero grande sotto, chi ha vinto
  pieno e l'altro spento (`score_read`, `closed_card`). In 3.3 c'è tutto il
  turno 2, e la card verde dice a chi passa il tavolo. In 3.4 dietro il
  foglio c'è il turno 1 concluso, con la card da cui si parte in cima e
  «Correggi» sulla card; il risultato corretto è coerente con il turno 1
  mostrato ovunque (g.verdi 5–4 p.marini, registrato al contrario).
* **3.2**: via il bottone «Assegna il tavolo 2»: si tocca la tessera libera,
  che è evidenziata. È già così nell'app: `selectTableFromModal` in
  `gara_detail.html` salva al tocco. I tavoli sono quattro e le tessere
  più grandi, due per riga.
* **Storia unica del turno 2** su tutta la pagina 3 (Main compreso): 10
  giocatori, 4 tavoli, 5 partite — m.rossi 4–2 g.verdi al tavolo 1,
  d.bianchi 3–3 l.ferrari al 2, a.galli 5–1 r.neri al 3 da validare,
  f.costa 5–3 e.sala conclusa, s.conti vs p.marini in attesa del tavolo 4
  appena aggiunto. Verificato nel codice: alla validazione il tavolo
  liberato passa da solo alla prima partita in attesa
  (`MatchValidationService.validate_and_complete` →
  `TableAssignmentService.release_and_reassign_table`), e le card lo dicono.
  La card riassuntiva di Main ora dice 1/5 chiuse e 3/4 tavoli.
* Restano da revisionare dall'utente: 1.x, 2.x, 4.x, 5.x rifatte, la pagina
  7 (campionato e playoff), e le due conferme aperte (gestione con la
  striscia, testi degli esercizi). Il canvas si apre sulla pagina 3.

## Secondo giro del 13/09 (rilievi dell'utente su 1.x, 3.x, 5.x, 7.x)

Verificato nel codice e applicato al canvas:

* **1.3 tavoli**: via l'interruttore «usa tutti i tavoli della sala» (era
  un'invenzione; nell'app l'elenco vuoto vale «tutti», qui l'elenco parte
  pieno). «Dalla sala» — che voleva dire «prendi i nomi dei tavoli della
  sala», `TableAssignmentService.get_table_names` — è diventato una riga
  di chip «Altri tavoli della sala: +4 +5 +6», più «Un altro nome».
* **1.9 desktop**: una pagina sola che scorre (artboard 1440×1560,
  `ALTEZZE` nel registro): fascia; turni in sintesi con la riga degli
  esercizi fra i turni; direzione di gara con la ricerca dei co-direttori
  aperta in linea; tavoli con l'ordine e i chip; vetrina con lo spazio
  1200×630 e i tre campi. La colonna destra è la lista di cosa manca, ogni
  riga scorre alla sua sezione. Turni ed esercizi aprono la **1.10, nuova**:
  i quattro turni e gli esercizi fra i turni con il modulo di aggiunta in
  linea (i tre campi di `_challenge_management_modal.html`).
* **3.3 e 3.9**: l'alternativa a validare è correggere. Oggi sulla stessa
  card ci sono «Inserisci risultato» (`openQuickResult`) e la spunta
  «Valida» (`_match_card.html`, riga 186 e 192): nel canvas la partita da
  validare ha gli **stepper attivi** e «Valida» sotto, e la nota lo dice.
* **3.8**: la card scura usa la geometria delle altre (nome sopra, numero
  sotto, niente «vs»); anche la card «da giocare» del kit ora ha i due
  riquadri con il trattino al posto del numero.
* **3.10**: le tessere scure dicono «TAVOLO» sopra il numero.
* **5.1 e 5.3**: frecce di tendenza rispetto alla classifica dopo l'ultimo
  turno; dove lo spareggio ha invertito l'ordine, si vede.
* **7.1 e 7.3**: la classifica generale segna la **zona playoff** — barra
  accento sulle prime 8, etichetta sopra, «fuori dai playoff» dopo
  l'ottava. NUOVO: oggi `_campionato_general_classification.html` non la
  segna; il numero è `playoff_elite_participants`.
* **7.2 e 7.4**: sulle righe in attesa il direttore risponde per conto del
  giocatore, «Accetta» e «Rifiuta» con conferma: esiste già
  (`playoff_respond_for_player`, `admin/campionato_detail.html`); la riga
  di chi ha rifiutato dice chi è stato invitato al suo posto. Otto invitati
  coerenti con «4 confermati su 8, 3 in attesa».
* Restano da revisionare dall'utente: 2.x, 4.x, e le due conferme aperte
  (gestione con la striscia, testi degli esercizi). Il canvas si apre sulla
  pagina 3.

## Terzo giro del 13/09

* **1.3 e 1.9 tavoli**: torna il **campo di testo** «3, 1, 2», separati da
  virgola nell'ordine di assegnazione, come oggi in
  `_gara_tables_config.html`: dopo due versioni a elenco l'utente ha
  confermato che è la forma migliore. Sotto, il suggerimento dice quanti
  tavoli ha la sala; resta l'interruttore «assegna in base alla classifica».
* **2.6**: il campo per iscrivere sta in cima alla colonna, sempre
  visibile, come in 2.2; via il «Fai entrare» dalla lista d'attesa e la
  categoria è il chip.
* **3.3 e 3.9**: confermato che si corregge con − e + prima di validare; il
  **+ si spegne alla distanza** del turno (`match.effective_distance`,
  ADR-027) e la card lo dice.
* **3.10**: i quattro tavoli in **griglia 2×2**, ogni casella piena con i
  due giocatori in due riquadri (nome a 24 px, punteggio a 96 px), il
  tavolo libero con la prossima partita al centro. La classifica e il turno
  1 a destra come prima.
* Restano da revisionare dall'utente: 2.x (rifatta la 2.6), 4.x, e le due
  conferme aperte (gestione con la striscia, testi degli esercizi). Il
  canvas si apre sulla pagina 3.

## Approvato il 13/09: si implementa

Revisione chiusa («va bene»): il canvas pubblicato — versione 9, con i tre
giri del 13/09 — è approvato per intero, comprese la gestione con la striscia
di fase (menu del turno «⋯», menu della partita, pagina «Impostazioni gara»,
tacca dello spareggio) e le due forme degli esercizi. Da qui in poi il canvas
**è la specifica**: si implementa una fase alla volta con la skill `ui-7c`,
una PR `feat:` per fase da `main`, nell'ordine impalcatura comune →
preparazione → iscrizioni → gioco → schermo in sala → spareggio e conclusa →
campionato e playoff. Dove un dettaglio non è nel canvas valgono i
bigliettini di questo file; dove manca anche qui si sceglie la soluzione più
vicina al canvas e la si scrive nella PR. Lo stato dell'implementazione si
aggiorna in fondo a questo file, fase per fase.

## Non ancora disegnato

Il canvas non copriva squadre e categorie (ADR-039, ADR-049), esercizi di
gara, trio e multi-set, forfait e ritiro a gara in corso con la
riassegnazione (ADR-048), tabellone a eliminazione (ADR-038), gara dentro un
campionato (peso, playoff, ADR-053), eliminazione della gara, competizione
di prova (ADR-058, arrivata dopo il canvas), e lo schermo in sala per le
gare a tabellone (issue #352). Sono stati fatti tutti il 13/09, senza
disegno, con la soluzione piu' vicina alla grammatica del canvas scritta in
ogni PR: vedi le voci dopo «H · Chiusura» in fondo. Resta fuori per scelta
la riassegnazione (ADR-048), che resta uno script da console.

## Come ricostruire

```bash
cd docs/redesign-7c/canvas-gara-direttore
python3 sorgenti/gen_decisioni.py   # riscrive tutti gli artboard e canvas.json
# poi si semina il canvas con seed-canvas.mjs della skill `design`, passando
# anche `--image sorgenti/locandina.png` (la locandina dello schermo in sala;
# `python3 sorgenti/gen_locandina.py` la rigenera, serve Pillow)
# (stesso file → stesso URL dell'artefatto)
```

## Nota sui file

Il canvas seminato (`pagina-gara-direttore.html`, 3 MB) **non è committato**:
è l'editor impacchettato, e si rigenera dalle sorgenti. Gli `.dc.html` sì:
sono piccoli, leggibili, e rendono la cartella comprensibile senza eseguire
niente. Vedi `../canvas-dashboard/STATO.md` per lo stesso schema.

## Implementazione

**Implementato** il 13/09/2026: tutte le fasi sono su `main`, dalla 1.11.0
alla 1.19.0. Le decisioni con conseguenze durature stanno in ADR-059 (la
pagina del direttore e' la fase in corso) e ADR-060 (i tavoli si scelgono in
ogni stato); i pattern nuovi in `docs/reference/UI_CONVENTIONS.md`, sezione
«Pagina gara del direttore». La seconda tornata, lo stesso giorno, ha fatto
anche tutte le voci di «Non ancora disegnato» (PR dalla #363 alla #379,
rilasci dalla 1.20.0), ciascuna registrata in fondo; resta fuori per scelta
la riassegnazione, e restano aperte due decisioni di dominio scritte nella
voce di chiusura.

Una fase per PR, nell'ordine fissato sopra. Qui lo stato e le trappole.

* **A · Impalcatura comune** (PR `feat: la pagina gara del direttore per
  fasi`, 2026-09-12). Chi dirige vede `templates/direttore/gara.html`: la
  striscia di fase (`_striscia.html`) al posto delle quattro linguette, con
  la tacca dello spareggio solo dove c'è (`spareggio_nella_striscia`); la
  fascia scura per fase (`_fase_*.html`), che legge il comando da
  `models/dashboard/comandi.py` — la stessa macchina a stati della
  dashboard, non una seconda; la card della console a turno in corso, con i
  conteggi di `models/competition/direttore_view.py`; il menu del turno
  («⋯» accanto al titolo, `_menu_turno.html`) e il menu della partita (sulla
  card, `_menu_partita.html`), entrambi fogli `c7-sheet`; la pagina
  «Impostazioni gara» (`/admin/gara/<id>/impostazioni`, direttori, vetrina,
  tavoli, squadre, categorie; turni e accoppiamento in sola lettura dopo
  l'avvio). Chi guarda (iscritto, ospite) resta su `gara_detail.html`, che ha
  perso i rami di gestione e il JavaScript del direttore.
  Trovato strada facendo: la colonna laterale richiudibile (issue #153) era
  **già implementata** dalla PR #281 (`c7-sidetoggle` in `base.html`), lo
  STATO sopra diceva il contrario; `_gara_management.html` non ha più chi
  lo includa ed è stato tolto; il seed della guida (`seed_demo.py`) falliva
  la sera perché fissava un appuntamento d'esame «oggi alle 21».
  Nelle fasi A i contenuti dentro la fase sono ancora i componenti di prima
  (card partita, elenco iscritti, configurazione turni): li rifanno le fasi
  B–G.
* **B · Preparazione** (PR `feat: la preparazione della gara, passo per
  passo`, 2026-09-13). Le schermate 1.1–1.10: sul telefono la panoramica
  con «Da preparare» e i passi come pagine con avanti e indietro
  (`/admin/gara/<id>/preparazione/<passo>`: turni, tavoli, esercizi,
  direttori; la vetrina e' il quinto passo sulla sua pagina); sul desktop la
  pagina lunga (1.9) con turni in sintesi, direzione di gara con la ricerca
  in linea, tavoli nel campo «3, 1, 2», vetrina; la pagina dei turni ed
  esercizi (1.10). I tavoli si scelgono **in ogni stato**
  (`GaraService.update_tables_config` senza guard, test aggiornati). Il
  foglio «Apri le iscrizioni» ha minimo e massimo
  (`InscriptionService.open_inscriptions`). Gli esercizi fra i turni valgono
  con ogni formula a turni (`Gara.ammette_esercizi_fra_i_turni`): il limite
  al casuale stava nelle route (challenges.py, match/challenges.py,
  match/detail.py) oltre che nei template, non solo nei template come
  diceva il canvas. La testata dice i turni modificati («turno 2: Palla 9 al
  3 triangoli», rilievo del 12/09). Co-direttori con ricerca client-side sui
  candidati (`_direttori.html`, usato anche da «Impostazioni gara»). Via
  `_round_management.html`, `_gara_directors.html` e il modale degli
  esercizi, sostituiti dai passi.
* **C · Iscrizioni** (PR `feat: le iscrizioni, con il campo per iscrivere
  in cima`, 2026-09-13). Le schermate 2.1–2.6: il campo per iscrivere sta
  in cima, sempre visibile, e i candidati compaiono sotto mentre si scrive,
  ognuno con «Iscrivi» sulla riga (via la tendina;
  `static/js/iscritti_ricerca.js` riscritto, test jsdom in
  `tests/frontend/`); l'elenco con avatar, nome, data, la categoria come
  chip (ADR-049) e la squadra dove serve; la lista d'attesa a parte
  (`_gara_lista_attesa.html`), che entra da sola — nessun «Fai entrare».
  Le iscrizioni scadute sono stato derivato: la fascia propone «Estendi le
  iscrizioni» (foglio `_modify_dates_modal.html` rifatto) o «Annulla la
  gara», e «Avvia» se il minimo c'e'. Il foglio «Avvia la gara»
  (`_avvia_gara.html`) dice cosa succede — iscritti, turno 1 o tabellone,
  chi riposa con la scelta dell'ultimo iscritto, i tavoli nell'ordine
  scelto — e sostituisce il `confirm()` e `_x_choice_modal.html`. Desktop
  2.6 a due colonne (elenco a sinistra; link, attesa e «Da tenere
  d'occhio» a destra; squadre, categorie e informazioni sotto l'elenco).
  Trovato strada facendo: la dashboard cadeva con `TypeError` quando un
  turno aveva un tavolo con la lettera e uno senza
  (`gara_cards._ordine_delle_altre`, con test).
* **D1 · Gioco, le partite** (PR `feat: il punteggio sulla card della
  partita`, 2026-09-13). Le schermate 3.1–3.4, 3.7–3.9: la card della
  partita (`direttore/_card_partita.html`) con una geometria sola — nome
  sopra, numero sotto, niente «vs» — e la forma dello stato
  (`direttore_view.stato_partita`): in corso con gli stepper − e + che
  salvano al tocco (`POST /admin/match/<id>/punteggio`, JSON; il + si
  spegne a `match.effective_distance`, alla distanza la partita si chiude
  e il tavolo passa alla prima in attesa), da validare (card verde, si
  corregge con − e + e poi «Valida», la nota dice a chi passa il tavolo),
  da giocare (tavolo da assegnare), conclusa (sola lettura, chi ha vinto
  pieno, «Correggi»). La partita di chi dirige e gioca sta in cima, scura
  (3.8). Il tavolo si assegna toccando la tessera libera nel foglio (3.2,
  gli occupati mostrano i due giocatori). La correzione di un risultato
  chiuso ha il suo foglio (3.4, issue #90): stepper, il perche', le due
  conseguenze scritte, `next` per tornare alla gara. A turno concluso le
  partite sono righe con la matita (3.7). Desktop 3.9: griglia a due
  colonne, a destra «da fare adesso», le tessere dei tavoli e la
  classifica. Il poll live ignora i fatti scritti da chi guarda
  (`autore` nell'evento). Via il tavolo dei turni e le card di prima dalla
  fase di gioco (restano a chi guarda). Trovato strada facendo: il seed
  della guida lasciava `current_round=1` col turno 2 in gioco, e la fascia
  proponeva di avviare un turno gia' avviato (`seed_demo.py`). Recepiti
  quattro rilievi della revisione automatica: l'endpoint del punteggio
  rifiuta partite chiuse, bloccate, a tre, a set o X; il multi-set resta
  sulla card di prima; stepper a 48px; il log del server fuori dal
  repository.
* **D2 · Gioco, la classifica** (PR `feat: la classifica del direttore con
  le frecce`, 2026-09-13). Le schermate 3.5 e 3.6: la classifica dopo
  l'ultimo turno chiuso (`direttore/_classifica.html`) in righe con
  posizione, freccia di tendenza rispetto al turno prima
  (`previous_position`, trattino se fermo o al primo turno), avatar e nome;
  le colonne seguono `gara.classification_system` (ADR-047): «Vinte · Diff»
  a vittorie, «Vinti · Persi» a RACK, con la nota su come si ordina e quanto
  vale la X (SPECIFICHE righe 64 e 71). Prime sei e tutti con due pillole.
  Una forma sola su telefono e desktop; chi guarda resta sui componenti di
  prima. Le fasi spareggio e conclusa passano a questa classifica, con le
  medaglie, nella fase F.
* **E · Schermo in sala** (PR `feat: lo schermo in sala`, 2026-09-13). La
  schermata 3.10 e' una route nuova, pubblica e senza menu:
  `/g/<indirizzo>/sala` (`main.schermo_sala`), dallo stesso indirizzo della
  vetrina, quindi una prova risponde 404 e gli id non si enumerano. In testa
  la locandina 1200×630 a tutta larghezza e la barra scura con nome, dati e
  turno; sotto i tavoli come caselle con i due giocatori, nome grande e
  punteggio grandissimo, il tavolo libero con la prossima partita in attesa;
  a destra la classifica gia' calcolata con le medaglie (`c7-pos--1..3`) e il
  turno prima. Non scrive sul database (`classifica_gia_calcolata`). Si
  ricarica agli eventi della gara con un poll pubblico per indirizzo
  (`sse.poll_sala`, ADR-057). Le gare a tabellone dicono «non ancora
  disponibile» e rimandano al tabellone: issue #352. Dati in
  `models/competition/schermo_sala.py`; il direttore la apre dalla pagina
  della gara in gioco («Schermo in sala»). Il seed della guida da' uno slug
  alla gara 2, perche' la schermata abbia un indirizzo stabile.
* **F · Spareggio e gara conclusa** (PR `feat: lo spareggio e la gara
  conclusa`, 2026-09-13). Le schermate 4.1–4.4 e 5.1–5.3. In gioco, quando
  serve uno spareggio, la fascia elenca i parimerito con la pastiglia
  «pari» (4.1). In spareggio i punti SSR si segnano con gli stepper da 48px
  delle card (`_ssr_section.html`): il numero e' un campo vero, che
  `saveSsrGroup` legge come prima; «Termina» resta spento finche' i gruppi
  non sono sciolti, poi la fascia dice chi ha preso quale posto, con
  «Annulla lo spareggio» e cosa comporta chiudere (4.2–4.4). La classifica
  a destra ha la pastiglia «pari» sui parimerito aperti. A gara conclusa la
  fascia dice chi ha vinto, con il podio nei colori delle medaglie
  (`direttore/_podio.html`, classi `c7-podio-finale`: `.c7-podio` e' gia' il
  podio compatto della tessera in dashboard); la classifica finale ha le
  medaglie, la freccia rispetto al turno prima e la pastiglia SSR dove lo
  spareggio ha deciso; le partite restano in righe, tutti i turni (5S).
* **G1 · Classifica generale e zona playoff** (PR `feat: la zona playoff
  nella classifica generale`, 2026-09-13). Le schermate 7.1 e 7.3, parte
  classifica: `_campionato_general_classification.html` passa alle righe
  della classifica di gara (freccia, avatar, colonne dal sistema, gare
  giocate, prime dieci e tutti) e segna la **zona playoff**: barra sulle
  righe dentro, etichetta sopra, «Fuori dai playoff» dopo l'ultima.
  `playoff_elite_participants` e' il campo del wizard, non una colonna: alla
  creazione del campionato diventa `max_participants` della configurazione
  «Playoff Elite» (`_create_playoff_config`), che quindi c'e' gia' durante
  la stagione. La zona la decide il dominio (`models/playoff/zona.py`) —
  prima degli inviti chi
  `evaluate_qualifications` sceglierebbe, dopo chi ha un invito in attesa o
  confermato, quindi chi rifiuta esce e chi subentra entra. Il test confronta
  la zona (righe `Classification`) con i primi della pagina
  (`calculate_general_classification`), i due percorsi della classifica
  generale. Vale per la pagina del direttore e per quella pubblica.
  Trovato strada facendo: la scheda informazioni del campionato leggeva
  `campionato.playoff_elite_enabled` e `playoff_elite_participants`, cioe' i
  campi del wizard, e il blocco dei playoff non compariva mai; ora legge le
  configurazioni attive.
* **G2 · La pagina del campionato** (PR `feat: la pagina del campionato per
  chi lo dirige`, 2026-09-13). Le schermate 7.1–7.4 in `admin/campionato_detail.html`:
  in cima una fascia scura con la stagione («Gara 3 conclusa · 3 gare giocate
  su 6, poi il playoff fra i primi 8 · prossima gara 4») e «Nuova gara», che
  a campionato terminato diventa la fase playoff («Avvia i playoff», poi
  «Crea la gara playoff · N confermati»); sul telefono tre linguette
  (Classifica, Gare, Gestione o Playoff), sul desktop due colonne. Le gare
  sono righe con stato, peso e comandi; la gestione e' fatta di righe
  (Playoff, Direttori, Vetrina, Impostazioni) che aprono le schede di prima.
  Gli invitati sono righe: su chi e' in attesa «Accetta» e «Rifiuta» per
  conto del giocatore, chi ha rifiutato dice «al suo posto X» e chi e'
  subentrato «invitato al posto di Y». Trovato strada facendo: le colonne
  `replaced_by_id` e `replacement_position` di `PlayoffQualification`
  esistevano ma nessuno le scriveva; ora `find_replacement_player` le scrive
  sulla qualificazione rifiutata o scaduta. Via `_campionato_garas.html`.
* **H · Chiusura** (PR `docs: la chiusura del canvas della pagina gara del
  direttore`, 2026-09-13). ADR-059 e ADR-060, i pattern nuovi in
  `UI_CONVENTIONS.md` con le righe datate del registro, la voce in
  `CHANGELOG.md`, questo file segnato «implementato». Trovato strada
  facendo: `fase_della_gara` ripiega su «preparazione» per uno stato che non
  conosce, e il test elencava gli stati a mano; ora un `GaraStatus` senza
  fase fa rosso (`test_nessuno_stato_della_gara_resta_senza_fase`).
* **Tabellone al posto della classifica** (PR `feat: il tabellone al posto
  della classifica nelle gare a eliminazione`, 2026-09-13, issue #240). Il
  canvas non disegnava le gare a tabellone. Un modulo di vista puro,
  `models/competition/tabellone_view.py`, costruisce l'albero intero con i
  nodi futuri gia' dal sorteggio: le regole di avanzamento di ADR-038 stanno
  in una funzione sola, `_uscite`, da cui discendono sia i posti dei nodi
  futuri sia la nota della card «Chi vince: Semifinali contro chi vince A –
  B». La pagina del tabellone disegna i nodi vuoti
  (`.c7-bracket__node--vuoto`). Sulla pagina del direttore: in preparazione
  e a iscrizioni aperte la riga «Tabellone da 8 · 2 passano il turno · 3
  turni» dagli iscritti, stimata sulla capienza quando non bastano, e il nome
  leggibile della formula; fra un turno e l'altro «Semifinali pronte» e
  «Avvia le semifinali», con gli incroci gia' fissati dal tabellone; il menu
  del turno 1 dice «Annulla il sorteggio»; in gioco il nome del turno nella
  card scura e nelle testate, la card della X «passa il turno», e nella
  colonna laterale **al posto della classifica** il tabellone compatto del
  turno visto, di quello prima e di quello dopo, vincenti sopra e ripescati
  sotto, con la riga al tabellone intero; a gara finita «Tabellone concluso
  · N turni giocati», che conta la bella se c'e'; a gara conclusa podio e
  classifica **a bande** («3°–4°», «5°–8°») dal tabellone, con il turno
  d'uscita e il pari merito dichiarato. Le gare a turni restano come prima.
  Scelte dove il canvas tace: nel doppio KO il turno si chiama con i due
  round che contiene («Turno 2 dei vincenti · Recupero 1»); sul podio senza
  finalina i due terzi stanno sullo stesso gradino; la finalina sta nella
  colonna accanto alla finale anche nel tabellone compatto. Trovato strada
  facendo: la riga «Accoppiamento» e la scheda informazioni mostravano il
  valore grezzo in colonna («Direct Elimination»); ora un nome tradotto
  (`nome_formula`).
* **Schermo in sala per le gare a tabellone** (PR `feat: lo schermo in sala
  per le gare a tabellone`, 2026-09-13, issue #352). Prima lo schermo diceva
  «non ancora disponibile». Ora i tavoli restano quelli della 3.10, con il
  nome del round accanto alla tessera e nel kicker della barra scura
  («Turno 1 di 3 · Quarti»); nella colonna destra, **al posto della
  classifica**, il turno del tabellone che si gioca e il turno dopo, con i
  nodi futuri vuoti che dicono chi arrivera'; nel doppio KO vincenti sopra e
  ripescati sotto, insieme e senza rotazione; fra un turno e l'altro la
  colonna del turno chiuso accanto a quella dopo, gia' fissata dall'albero; a
  gara conclusa il podio dalle posizioni del tabellone e sotto le bande con
  il turno d'uscita. Niente albero intero: a tre metri un 16 o un 32 non si
  legge. Dati puri in `schermo_sala.py`, l'albero da `tabellone_view`
  riusato con una finestra nuova, `Tabellone.finestra`, e `nome_del_nodo`
  per nominare il ramo sulla casella di un tavolo, dove la colonna intorno
  non c'e'. La pagina resta senza scritture: `bracket_positions` si legge
  nella route, solo a gara conclusa. CSS nella sezione 30. Scelte dove il
  canvas tace: la colonna destra si allarga a 560px sul desktop; i nodi si
  stringono quando le righe impilate superano otto; il podio e' quello di
  `_podio.html` ingrandito, le bande sono righe dello schermo e non
  `_classifica_bande.html`, che porta la nota per il direttore; a gara
  conclusa con piu' di otto giocatori le bande vanno su due colonne; nella
  formula a gironi le lavagne dei gironi si impilano tutte, fitte.
  Secondo giro, a tre metri niente coi puntini: il nome del round sta in
  una riga sua sotto la testa della casella, i nomi vanno a capo, e un posto
  futuro dice «chi vince» o «chi perde» con sotto i due nomi, oppure «Tavolo
  N» quando quella partita si gioca a un tavolo e lo spazio e' poco, cioe'
  oltre quattro righe o con i due rami del doppio KO (`TabelloneSala.stretto`).

* **Trio, multi-set e X con esercizio** (PR `feat: trio, multi-set e X con
  esercizio sulla card della partita`, 2026-09-13). Il canvas disegnava solo
  la partita a due: le altre forme restavano sulla card di prima, con il
  risultato secco in un modale e, per la X, un campo numerico e un
  `confirm()`. Ora la card ha una forma per partita
  (`direttore_view.scheda_partita`: due, trio, set, x, x_esercizio) e la
  stessa geometria. Il **trio** ha tre lati con − e + dei triangoli vinti,
  che salvano al tocco (`POST /admin/gara/trio/<id>/punteggio`); quali +
  sono accesi lo dice il server (`models/match/trio_punteggio.py`), perche'
  l'ordine del girone rende impossibili certi totali, per esempio un
  triangolo al terzo giocatore dopo un solo triangolo giocato; al totale dei
  triangoli si chiude, «da validare» quando l'hanno giocato i giocatori senza
  le tre firme, con la corona al vincitore e a nessuno nel pareggio. La
  **partita a set** mostra i set vinti in sola lettura e sotto gli stepper
  del set in corso (`POST /admin/match/<id>/set/punteggio`); a set chiuso
  «Inizia il set N». La **X con esercizio** ha un lato solo, lo stepper da
  0 alla distanza del turno (ADR-027) e «Convalida»; «Azzera la prova» sta
  nel menu. A turno concluso il trio e' una riga con tre nomi e tre numeri,
  senza matita. Le regole degli stepper stanno in un modulo solo,
  `static/js/card_partita.js`, con il suo test jsdom; anche il foglio della
  correzione le usa. Scelte dove il canvas tace: lo stepper del trio va in
  colonna, + sopra e − sotto, per tenere i bersagli da 48px su tre lati a
  390px; la X non salva al tocco, perche' non esiste un punteggio
  «registrato ma non convalidato» scritto dal direttore; un triangolo tolto
  nel trio resta nello storico come l'annulla del segnapunti, e nel set si
  toglie l'ultimo vinto da quel giocatore. Trovato strada facendo:
  `trio_set_result` non guardava il turno bloccato ne' la partita chiusa e
  non annunciava niente; `trio_reset` rispondeva 500 a un rifiuto del
  dominio; la correzione della partita a set era vietata solo dal template,
  ora la rifiuta `MatchCorrectionService.can_correct`; `Match.is_at_distance`
  usava la modalita' dei triangoli anche per i set, e con i triangoli
  «esattamente» una partita al 2 set risultava alla distanza a 1–1.
* **La gara del campionato e la prova** (PR `feat: la gara del campionato
  e la prova nella pagina del direttore`, 2026-09-13). Il canvas non
  disegnava ne' la gara dentro un campionato ne' la competizione di prova.
  Un contesto puro, `direttore_view.contesto_campionato`, dice cosa la gara
  riceve dal campionato: numero sulle gare previste, peso scritto e peso
  efficace (`Gara.classification_weight`, 0 per il playoff che decide la
  classifica finale, ADR-053), se e' il playoff e con quale modalita', chi
  spacca e se e' ereditato (ADR-056), le gare vicine che fissano la finestra
  di date (ADR-016). Sulla pagina del direttore: sopra la striscia il kicker
  «Gara 4 di 6 · Campionato» che porta al campionato, con le pastiglie «×2»
  o «Playoff»; in preparazione e in «Impostazioni gara» il gruppo «Dal
  campionato» in righe (peso con la «?» di `gara-peso`, chi spacca con
  «eredita», date ammesse, pagina del campionato); i testi di chiusura in
  gioco, nello spareggio e a gara conclusa vengono dal contesto — niente
  punti per una gara singola, «vale ×N» per una gara che si somma, «il
  playoff decide la classifica finale» quando il peso efficace e' 0. Prova:
  il banner sta anche sui passi della preparazione e in «Impostazioni gara»
  (`direttore/_prova_in_testa.html`), con le schermate aggiunte ai `screens`
  di `prova.aiuto` e `prova.elimina`; la simulazione e' un foglio `c7-sheet`
  (`direttore/_simulazione.html`) aperto dalla riga «Fai giocare i fittizi»
  sotto la fascia, solo in gioco. Scelte dove il canvas tace: il kicker e'
  un collegamento a tutta riga e non una seconda testata; la «?» della
  simulazione sta sul titolo di sezione, perche' su una riga-pulsante
  cadrebbe dentro l'elenco; il gruppo «Dal campionato» sta sotto
  «Informazioni gara», nella colonna che sul telefono e' l'unica. Trovato
  strada facendo: `GaraService.update_gara` non applicava l'ADR-016, e una
  gara di campionato spostata prima della precedente passava senza errori;
  ora il controllo scatta quando cambiano data o ora, con test. Il foglio
  «Estendi le iscrizioni» cambia solo le date d'iscrizione, non la data
  della gara, e resta com'e'. Sulle sottopagine di una prova l'aiuto non si
  accendeva e «Elimina la prova» mancava. `deleteProva` in `_scripts.html`
  era codice morto, tolto con le sue tre stringhe.

* **Esercizi fra i turni** (PR `feat: gli esercizi fra i turni si segnano
  dalla pagina della gara`, 2026-09-13). Il canvas disegnava solo la loro
  preparazione (1.4–1.5, 1.10): a gara in corso i tentativi si registravano
  soltanto dalla pagina della partita, e la pagina del direttore aveva
  un elenco in sola lettura che diceva «dal turno N» mentre la regola e'
  «dopo il turno N». Ora, a turno N concluso, ogni `GaraChallenge` di quel
  turno e' una sezione «Esercizio dopo il turno N» con una riga per iscritto
  attivo: tentativi fatti sul massimo, il migliore o l'esito, «da fare» per
  chi non ha ancora tirato. Il tocco apre un foglio `c7-sheet` con i due tasti
  grandi dell'allenamento, «Riuscito» e «Non riuscito», che registrano al
  tocco, oppure lo stepper da 48px della card, forma `x` di
  `static/js/card_partita.js`, e «Registra il tentativo»; salva con
  l'endpoint JSON di chi dirige, `admin.match.record_challenge_attempt`, e
  la pagina si rifa' con `location.replace`. Finiti i tentativi la riga non
  si tocca piu'. Gli esercizi del turno non ancora concluso restano in una
  sezione in sola lettura sotto le partite: un elenco solo. Dati in
  `direttore_view.esercizi_fra_i_turni` e `turni_conclusi`, query in
  `detail._esercizi_turni`; CSS nella sezione 33. La fascia non cambia:
  nessuna regola ferma il turno dopo con un esercizio da registrare, e
  `comando_per` non ne inventa una. Scelte dove il canvas tace: fra un turno
  e l'altro gli esercizi con qualcuno ancora senza tentativi stanno sopra
  le partite, mentre un turno si gioca stanno sotto, perche' otto righe
  spingerebbero giu' di una schermata le card che servono adesso; il numero
  del turno registrato col tentativo e' quello che si vede; senza tetto
  `Challenge.max_score` lo stepper non si ferma; nessun comando per togliere
  un tentativo, perche' il servizio non ne ha uno.
  Trovato strada facendo: la pagina della partita mandava un direttore non
  admin all'endpoint del giocatore, che registra sempre per chi chiama, quindi
  403, e se il direttore era iscritto il tentativo dell'altro finiva a lui; ora
  sceglie dal permesso sulla gara. L'endpoint del direttore accettava un
  `user_id` qualsiasi, anche di chi non gioca la gara, che restava fuori dalla
  classifica ma prendeva gli XP del tentativo: ora vuole un iscritto attivo.
  `GaraChallengeService` non applicava il tetto `max_score` che l'allenamento
  applica, ne' rifiutava un punteggio negativo, e un esercizio a esito senza
  esito diventava «non riuscito» in silenzio: ora rifiuta tutti e tre. Le
  informazioni della gara dicevano «1 attive» degli esercizi. Il seed della
  guida aggancia un esercizio alla gara in corso, ma il suo campionato ha
  `challenge_mode` spento e `Gara.ammette_esercizi_fra_i_turni` lo nasconde
  ovunque: la guida ha il testo e nessuna schermata nuova, e accendere il
  flag cambierebbe altre schermate del campionato.
* **Squadre, categorie, ritiro ed eliminazione** (PR `feat: squadre,
  categorie, ritiro ed eliminazione nella pagina del direttore`,
  2026-09-13). Il canvas non le disegnava. Squadre (ADR-039) e categorie
  (ADR-049) sono righe, «Squadre» e «Categorie», che aprono un foglio
  `c7-sheet` con l'elenco e i comandi di prima, stesse route e stessi form
  (`direttore/_squadre_categorie.html`): in preparazione fra le righe di «Da
  preparare», a iscrizioni aperte in «Da tenere d'occhio», in «Impostazioni
  gara» fra cio' che si modifica e dopo il sorteggio fra cio' che e' fissato.
  Dopo il sorteggio la riga resta con la tessera bloccata e il foglio si
  legge soltanto: le categorie non spariscono piu'. La squadra di un iscritto
  e' un chip che apre un foglio, al posto della tendina che inviava al
  cambio; la fascia delle iscrizioni dice «k senza categoria», e il numero si
  riscrive a ogni salvataggio del combo. Il ritiro: nel menu della partita
  «Ritiro di …» per ogni giocatore, con un foglio che dice la regola della
  gara sui ritiri prima di confermare; `POST /admin/match/<id>/forfeit`
  (`ritiro_partita`) passa dallo stesso dominio del forfait del giocatore,
  con i rifiuti della card — X, partita chiusa, turno bloccato — e gli stessi
  eventi; il trio usa il suo ritiro dallo stesso comando. «Elimina la gara»
  e' una riga distruttiva in fondo alla preparazione, finche'
  `can_be_deleted()`, con il suo foglio; la prova si elimina dal banner.
  Scelte dove il canvas tace: nel foglio ogni voce e' un `<details>` con la
  riga per sommario; i form mandano `next` con l'ancora `#squadre` o
  `#categorie`, che riapre il foglio al ritorno; il ritiro si propone solo a
  partita da giocare o in corso, non da validare. Trovato strada facendo:
  eliminare una gara in preparazione con un turno modificato rispondeva 500,
  perche' l'ORM annullava `round_configuration.gara_id` (NOT NULL) prima del
  CASCADE del DB, e lo stesso valeva per esercizi e X con esercizio; il
  forfait del giocatore passava su una partita confermata dai due e ne
  riscriveva il risultato; togliendo la squadra a un iscritto il direttore
  leggeva «Giocherai senza squadra»; il messaggio dell'eliminazione non era
  tradotto. Domande aperte: se il ritiro nel trio debba applicare la regola
  della gara, e se il forfait del giocatore debba rispettare il turno
  bloccato come quello del direttore.
* **Chiusura della seconda tornata** (PR `docs: la chiusura della seconda
  tornata della pagina gara del direttore`, 2026-09-13). CHANGELOG, righe
  datate di `UI_CONVENTIONS.md`, questo file riordinato. Decisioni di
  dominio lasciate aperte, con la variante prudente implementata:
  il trio a pari punteggio in testa (4-4-1 alla distanza 6 da' la vittoria
  per scontro diretto, la specifica riga 160 dice zero a tutti: xfail strict
  in `test_specifiche_conformita.py::TestIlTrioInClassifica`); se il blocco
  dei turni successivi valga anche per l'esercizio della X; se il ritiro in
  un trio applichi la regola della gara sui ritiri; se il forfait dichiarato
  dal giocatore e quello del trio rispettino il turno bloccato, come gia' fa
  quello del direttore.
