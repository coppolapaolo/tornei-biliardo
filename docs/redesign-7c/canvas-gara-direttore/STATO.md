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

## Le cinque fasi, 36 schermate, più il campionato

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

## Non ancora disegnato

Da chiedere prima di implementare, perché il canvas non li copre: squadre e
categorie (ADR-039, ADR-049), esercizi di gara, trio e multi-set,
forfait/ritiro a gara in corso e riassegnazione (ADR-048), tabellone a
eliminazione (dove l'avvio è «Sorteggia il tabellone», ADR-038), gara dentro
un campionato (peso, playoff, ADR-053), eliminazione della gara, competizione
di prova (ADR-058, arrivata dopo il canvas).

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
