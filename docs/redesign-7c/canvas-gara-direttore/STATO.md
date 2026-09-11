# Pagina gara del direttore — stato del canvas

Canvas: <https://claude.ai/code/artifact/2a185d1b-19e1-4e16-8456-b866787dcc1c>
(disegnato il 31/08/2026, versionato l'11/09). Le sorgenti stanno in
`sorgenti/`: `gen_gara_direttore.py` (il kit — token 7c copiati alla lettera
da `tokens-7c.css` e `theme-7c.css` — e le tre direzioni del primo giro),
`gen_fasi.py` (le schermate delle cinque fasi e il `canvas.json` completo).
Si rigenera con `python3 sorgenti/gen_fasi.py`; il canvas seminato
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

## Le cinque fasi, 27 schermate

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
   (gli occupati mostrano da chi); segna il risultato con gli stepper e la
   riga verde che dice chi vince secondo la regola del turno; valida un
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

## Da decidere

Le due segnate sul canvas:

1. **La spunta «Esercizi» in preparazione** compare solo con accoppiamento
   casuale: con Amalfi va nascosta del tutto o lasciata spenta?
2. **«Riepilogo partite» a gara conclusa**: sul canvas è un link, nell'app la
   sezione partite resta in pagina. Quale delle due?

E le tre che vengono prima di tutto:

3. **La forma** — la sintesi fasi + console va bene, o si torna a una delle
   tre direzioni? Da guardare per fase, come per la dashboard.
4. **La striscia di fase sul telefono** sostituisce le quattro linguette
   Turni · Classifica · Iscritti · Gestione? Le linguette sono un filtro CSS
   su un solo DOM (STATO generale del redesign): cambiare la forma cambia
   anche quel meccanismo.
5. **Cosa si fa dalla pagina e cosa si apre**: la console segna il punteggio
   sulla card, senza modale. È la scelta più costosa (tocca il segnapunti).

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
python3 sorgenti/gen_fasi.py        # riscrive gli artboard e canvas.json
# poi si semina il canvas con seed-canvas.mjs della skill `design`
# (stesso file → stesso URL dell'artefatto)
```

## Nota sui file

Il canvas seminato (`pagina-gara-direttore.html`, 3 MB) **non è committato**:
è l'editor impacchettato, e si rigenera dalle sorgenti. Gli `.dc.html` sì:
sono piccoli, leggibili, e rendono la cartella comprensibile senza eseguire
niente. Vedi `../canvas-dashboard/STATO.md` per lo stesso schema.
