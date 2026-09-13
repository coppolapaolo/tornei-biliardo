# ADR-059: La pagina gara del direttore è la fase in corso

**Data**: 2026-09-13
**Stato**: Accepted
**Decisori**: Paolo, Claude

## Contesto

Fino al 12/09/2026 chi dirigeva una gara e chi la guardava aprivano lo
stesso template, `gara_detail.html`, con quattro linguette (Turni,
Classifica, Iscritti, Gestione) e i rami di gestione accesi da condizioni
sparse. La pagina rispondeva a tutto e a nessuno: in gioco il 90% delle
sezioni non serviva, e il comando che la gara aspettava — aprire le
iscrizioni, avviare il turno, terminare — stava in fondo alla linguetta
Gestione, in un pannello che ogni fase riordinava a modo suo (vedi
`UI_CONVENTIONS.md`, «Ordine Dinamico Sezioni»).

Il canvas «Pagina gara del direttore» (approvato il 13/09/2026, versione 9)
ha messo a confronto tre direzioni sulla stessa schermata. La scelta,
decisione 2 del 12/09, è la **C · Fasi**: la pagina è la fase in corso.
Restava da decidere come farlo senza creare una seconda macchina a stati
della gara, visto che la dashboard del direttore ne aveva già una
(`models/dashboard/comandi.py`) per la sua tessera.

## Decisione

1. **Due pagine, non una con i rami.** Chi dirige vede
   `templates/direttore/gara.html`; chi guarda — iscritto, ospite — resta su
   `gara_detail.html`, che ha perso i rami di gestione e il JavaScript del
   direttore. La scelta la fa la route (`routes/admin/competition/detail.py`).
2. **Una striscia di fase al posto delle linguette**: preparazione →
   iscrizioni → in gioco → [spareggio] → chiusura. La tacca dello spareggio
   compare solo nelle gare che ce l'hanno (`spareggio_nella_striscia`), e il
   contenuto sotto la striscia è la fase attiva (`_fase_*.html`). Ciò che non
   appartiene a nessuna fase — direttori, vetrina, tavoli, squadre,
   categorie — va nella pagina «Impostazioni gara»
   (`/admin/gara/<id>/impostazioni`).
3. **La fase e i conteggi si calcolano in Python, senza database**
   (`models/competition/direttore_view.py`): `fase_della_gara`, `striscia`,
   `conteggi_turno`, `stato_partita`. Il template disegna, non decide.
4. **Il comando della fascia scura viene da `comando_per`**
   (`models/dashboard/comandi.py`), lo stesso che usa la tessera della
   dashboard. Due macchine a stati per la stessa domanda — «cosa aspetta
   questa gara dal direttore?» — si staccherebbero al primo cambiamento, e il
   direttore leggerebbe due risposte diverse fra la dashboard e la gara.

## Alternative Considerate

### Alternativa 1: A · Regia — la pagina di prima con una fascia in cima

**Descrizione**: si aggiunge un blocco che dice a che punto è il turno e cosa
lo tiene aperto; le quattro linguette restano.

- **Pro**:
  - costo minimo, non toglie niente.
- **Contro**:
  - la pagina resta quella che non si capiva: la fascia si somma al rumore
    invece di toglierlo.

### Alternativa 2: B · Console — il turno in corso diventa la pagina

**Descrizione**: punteggio e tavolo sulla card, a destra «da fare adesso» e la
mappa dei tavoli.

- **Pro**:
  - la serata di gioco diventa velocissima.
- **Contro**:
  - risponde solo alla fase di gioco: preparazione, iscrizioni e chiusura
    restano da inventare. È confluita dentro la C come contenuto della fase
    «in gioco» (card con gli stepper, tessere dei tavoli).

### Alternativa 3: un solo template con la fase come ramo principale

**Descrizione**: tenere `gara_detail.html` e riordinarlo per fase, anche per
chi guarda.

- **Pro**:
  - un file solo.
- **Contro**:
  - chi guarda non ha fasi da attraversare: vuole partite e classifica. Le
    condizioni «è direttore?» sarebbero rimaste in ogni blocco.

### Alternativa 4: calcolare il comando dentro `direttore_view.py`

- **Pro**:
  - il modulo della pagina sarebbe autosufficiente.
- **Contro**:
  - una seconda macchina a stati accanto a `comandi.py`, con i test che
    confrontano ciascuna con sé stessa: lo stesso meccanismo che ha
    prodotto le due classifiche generali divergenti (CLAUDE.md, «due
    percorsi»).

## Conseguenze

### Positive

- In ogni fase la prima cosa sotto la striscia è l'unica da fare adesso.
- Dashboard e pagina della gara dicono sempre lo stesso comando.
- Le fasi si sono potute rifare una per PR (#343, #345, #347, #349, #351,
  #354, #355), perché ogni fase è un template suo.

### Negative

- Due template per la stessa gara: una funzione nuova visibile a entrambi va
  pensata due volte (per esempio la classifica, che il direttore vede in
  righe con le frecce e chi guarda con i componenti di prima).
- Un co-direttore che a gara iniziata cerca una sezione di configurazione fa
  un tocco in più: sta in «Impostazioni gara».

### Rischi

- Chi aggiunge uno stato alla gara deve toccarlo in tre punti:
  `fase_della_gara`, `comando_per` e il template della fase.
  `fase_della_gara` ripiega su «preparazione» per uno stato che non conosce;
  perche' non succeda in silenzio,
  `test_direttore_view.py::test_nessuno_stato_della_gara_resta_senza_fase`
  diventa rosso se un `GaraStatus` non ha una fase.
- Restano fuori dalla striscia, perché il canvas non li disegna: gare a
  tabellone (lo schermo in sala le rimanda al tabellone, issue #352), trio e
  multi-set (card di prima), squadre e categorie oltre all'elenco.

## Note Implementative

- Striscia: `templates/direttore/_striscia.html`, CSS `.c7-fasi` (theme-7c,
  sezione 20). Le etichette delle tacche inattive si vedono solo da 992px.
- Fasi: `templates/direttore/_fase_preparazione.html`, `_fase_iscrizioni.html`,
  `_fase_gioco.html`, `_fase_spareggio.html`, `_fase_conclusa.html`.
- Menu del turno e della partita come fogli `c7-sheet`: `_menu_turno.html`,
  `_menu_partita.html`.
- Stato dell'implementazione fase per fase:
  `docs/redesign-7c/canvas-gara-direttore/STATO.md`.

## Riferimenti

- Canvas: <https://claude.ai/code/artifact/2a185d1b-19e1-4e16-8456-b866787dcc1c>
  e sorgenti in `docs/redesign-7c/canvas-gara-direttore/`.
- ADR-047 (colonne della classifica dal sistema di classifica), ADR-057
  (aggiornamenti live), ADR-060 (tavoli in ogni stato).
