# Pagina gara del direttore — stato del canvas

Canvas: <https://claude.ai/code/artifact/2a185d1b-19e1-4e16-8456-b866787dcc1c>
(disegnato il 31/08/2026, versionato l'11/09). Le sorgenti stanno in
`sorgenti/`: `gen_gara_direttore.py` (il kit — token 7c copiati alla lettera
da `tokens-7c.css` e `theme-7c.css` — e le tre direzioni del primo giro),
`gen_fasi.py` (le schermate delle cinque fasi e il `canvas.json` completo),
`gen_decisioni.py` (la pagina «0 · Decisioni», vedi sotto). Si rigenera con
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

## Le cinque fasi, 30 schermate

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
# poi si semina il canvas con seed-canvas.mjs della skill `design`
# (stesso file → stesso URL dell'artefatto)
```

## Nota sui file

Il canvas seminato (`pagina-gara-direttore.html`, 3 MB) **non è committato**:
è l'editor impacchettato, e si rigenera dalle sorgenti. Gli `.dc.html` sì:
sono piccoli, leggibili, e rendono la cartella comprensibile senza eseguire
niente. Vedi `../canvas-dashboard/STATO.md` per lo stesso schema.
