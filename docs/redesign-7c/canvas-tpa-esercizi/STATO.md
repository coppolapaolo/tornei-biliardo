# TPA ed esercizi — stato del canvas

Canvas: <https://claude.ai/artifact/SM1jiBNtVU9z1ATTvSTwqi> (disegnato e
congelato il 19/09/2026, versionato lo stesso giorno). **46 schermate in 8
pagine**: referto TPA, esercizi (trovare, eseguire, andamento e creazione),
schede di allenamento e istruttori, esami, disegnatore, decisioni.

Il lavoro si esegue a fasi, una per sessione: il piano è in
[`PIANO.md`](PIANO.md). Questo file dice **a che punto è ogni schermata**.

## Come si rigenera

```bash
cd docs/redesign-7c/canvas-tpa-esercizi/sorgenti
python3 gen.py                  # scrive root/project/*.dc.html e canvas.json
../../../../venv/bin/python measure.py   # screenshot in shots/, segna chi «SBORDA»
```

| File | Cosa contiene |
|---|---|
| `kit.py` | gusci (telefono, desktop), icone, tavolo, bersagli, grafici. Token e classi di base li **importa** dal kit del canvas accanto (`../canvas-gara-direttore/sorgenti/gen_gara_direttore.py`), copiati alla lettera da `tokens-7c.css` e `theme-7c.css`; qui si aggiungono le classi `.tpa-*` e i pezzi nuovi |
| `tpa.py` | pagina 1 |
| `esercizi.py` | pagine 2, 3, 4 |
| `schede.py` · `esami.py` · `disegnatore.py` | pagine 5, 6, 7 |
| `boards_extra.py` | l'elenco degli artboard delle pagine 5–7, coi bigliettini |
| `decisioni.py` | pagina 8 |
| `gen.py` | l'elenco delle pagine 1–4 e 8, e la scrittura dell'indice |
| `measure.py` | misura con Playwright: senza `support.js` un `.dc.html` si apre lo stesso in Chromium, e layout e CSS sono quelli veri |
| `canvas.json` | **l'indice pubblicato**, scaricato dal canvas il 19/09. Non è quello che scrive `gen.py` (che finisce in `root/`, non versionato): l'editor del canvas salva da sé — toglie `size` dai bigliettini, aggiunge `w` ai titoli, tiene `attachments` e le posizioni che l'utente sposta a mano. **Una ripubblicazione parte da questo, non da quello generato** |

Ciò che il generatore produce (`sorgenti/root/`, circa 2 MB, e `sorgenti/shots/`)
non è versionato: si rifà in un secondo. Verificato il 19/09: dai sorgenti di
questa cartella escono 46 artboard **identici byte per byte** a quelli che
uscivano dalla cartella di lavoro fuori dal repo, e i sette del TPA coincidono
con quelli pubblicati. Gli altri 39 pubblicati differiscono dai generati per
due sole regole CSS del kit (`.kickrow`, `.ntk`), aggiunte con l'ultima
correzione del TPA e usate solo lì: alla vista non cambia niente, e si
riallineano alla prima ripubblicazione.

**Per ripubblicare** vale la procedura di `PIANO.md` («Ripubblicare il
canvas»): l'utente modifica gli artboard a mano, quindi prima si rilegge il
canvas dal vivo e si portano qui le sue modifiche. Mai `force`.

## Da dove viene

Tre giri sullo stesso canvas, il 19/09/2026, col metodo degli altri due
redesign ([gara del direttore](../canvas-gara-direttore/STATO.md),
[dashboard](../canvas-dashboard/STATO.md)): direzioni a confronto, poi percorsi
completi, poi una pagina di decisioni.

* **Il referto TPA non era mai passato dal redesign 7c**: nessuna schermata nel
  prototipo, JavaScript tutto dentro il template, tastierino che su desktop si
  stira su sei colonne e rompe la disposizione del foglio cartaceo. Tre
  direzioni (A · Ordine, B · Tavolo, C · Foglio vivo): **scelta B**.
* **Per chi usa l'app «esercizi» comprende schede ed esami.** Il primo giro si
  era fermato al catalogo; l'area ha quattro stanze — Esercizi, Schede, Esami,
  Andamento.
* **Una scheda di allenamento e un esame sono la stessa forma**: una sequenza
  ordinata di esercizi con «quanto farne». Il componente che la compone nasce
  con gli esami (fase 3) e lo riusano le schede (fase 6).
* **Generico, con opzioni.** Il materiale di chi insegna davvero serve a capire
  il dominio, non a diventarne la struttura: le differenze fra una scuola e
  l'altra sono opzioni della scheda (livello, soglia, giorni, durata), non
  forme diverse. Nei test della fase 6 si compongono due schede molto diverse
  con lo stesso oggetto.

Le venti decisioni (D1–D20) sono congelate: stanno nella pagina 8 del canvas e,
con le motivazioni, in `PIANO.md`. Cambiano solo con una nota datata.

## Le schermate

Stato: **da fare** · **in corso** · **fatto** · **scartato**. La colonna
«Template» dice cosa c'è oggi; «nuovo» vuol dire che la schermata non ha un
antenato nell'app.

### 1 · Referto TPA — fase 2

| Artboard | Schermata | Template | PR | Stato |
|---|---|---|---|---|
| `Main` | A · Ordine | — | — | scartato (D1) |
| `TpaTavolo` | B · Tavolo: tastierino unico, tavolo passato toccando il riquadro, TPA alla pari del punteggio | `individual_match/tpa_referto.html` + `static/js/tpa-referto.js` | #475, #478 | **fatto** |
| `TpaIndietro` | B · Indietro nel referto, in sola lettura | `individual_match/tpa_referto.html` | #479 | **fatto** — è una vista del browser, nessun cursore salvato |
| `TpaRiparti` | B · Ripartire da un turno del passato (D16) | foglio `#tpaRipartiModal` | #479 | **fatto** |
| `TpaFoglio` | C · Foglio vivo | — | — | scartato (D1); l'idea sopravvive su desktop |
| `TpaDesktop` | Desktop a tre colonne | `individual_match/tpa_referto.html` | #481 | **fatto** — tre colonne da 1400px, due da lg: a 1024px le tre non ci stanno |
| `TpaChiuso` | Referto chiuso, come racconto | `individual_match/tpa_referto.html` | #482 | **fatto** — i numeri per giocatore, non sommati |

**Fase 2 chiusa il 19/09/2026.** Oltre alle schermate: il JavaScript è uscito
dal template ed è provato in jsdom (#475); il primo tiro di calcio è il numero
del giocatore cerchiato sopra la casella, non più la freccia `↺` (#478, D20
bis); in tutta l'app si dice «turno» e non «visita» (#482); guida e schermate
rifatte (#483). Tre difetti trovati strada facendo e corretti a parte: #476
(triangolo vinto senza G mostrato come non vinto), #477 e #480 (due test che
dipendevano dall'ambiente).

**Due scarti dal canvas, voluti.** La 2c non ha il cursore salvato che il piano
prevedeva: l'ha superato la D16, e i motivi stanno nell'emendamento
all'ADR-044. Nella casella resta il solo suggerimento «bilie?»: «perché finisce
il turno?» andava a capo e rompeva l'allineamento delle caselle.

### 2 · Esercizi: trovare — fase 4 (e 7)

| Artboard | Schermata | Template | PR | Stato |
|---|---|---|---|---|
| `TrovareOggi` | B · Oggi, la porta d'ingresso (D3). Nasce in 4c con ciò che c'è, si riempie in 6 e 7 | nuovo | 4c, 7e | da fare |
| `TrovareCatalogo` | A · Catalogo che si filtra, dietro «Apri il catalogo» | `challenge/catalog.html` | 4c | da fare |
| `SchedaEsercizio` | La scheda di un esercizio | `player/challenge_detail.html` | 4c, 4d | da fare |

### 3 · Esercizi: eseguire — fase 5

| Artboard | Schermata | Template | PR | Stato |
|---|---|---|---|---|
| `EseguiPunteggio` | A punteggio, con l'avanzamento dal vivo | `challenge/training.html`, `challenge/start_attempt.html` | 5a | da fare |
| `EseguiColpo` | Colpo per colpo (#183) | nuovo | 5b | da fare |
| `EseguiZoom` | Il punto preciso (#183) | nuovo | 5b | da fare |
| `EseguiCasuale` | Con estrazione (#452) | nuovo | 5c | da fare |
| `EseguiFine` | Fine sessione | nuovo | 5d | da fare |

### 4 · Andamento e creazione — fasi 4 e 7

| Artboard | Schermata | Template | PR | Stato |
|---|---|---|---|---|
| `Andamento` | Il tuo allenamento, radar per abilità | `components/_player_training.html` | 7a | da fare |
| `AndamentoGesto` | Lo stesso, radar per gesto | nuovo | 7a | da fare |
| `Obiettivo` | Imposta un obiettivo (#316) | nuovo | 7b | da fare |
| `CreaModulo` | Crea, modifica, duplica: un modulo solo (#168 #252 #253) | `challenge/create.html` | 4b | da fare |
| `CreaCopia` | «Ha già delle prove» (#252) | nuovo (foglio) | 4b | da fare |

### 5 · Schede di allenamento e istruttori — fasi 6 e 8

| Artboard | Schermata | Template | PR | Stato |
|---|---|---|---|---|
| `SchedeElenco` | Le tue schede | nuovo | 6b | da fare |
| `SchedaComponi` | Comporre | nuovo (riusa il componente di 3a) | 6b | da fare |
| `SchedaVoce` | Quanto farne (D19: niente serie × ripetizioni) | nuovo | 6b | da fare |
| `SchedaInCorso` | La seduta, una voce con varianti | nuovo | 6c | da fare |
| `SedutaPalestra` | La stessa seduta, una voce lunga | nuovo | 6c | da fare |
| `SchedaRegistro` | Il registro | nuovo | 6d | da fare |
| `SchedaFine` | Fine seduta | nuovo | 6c | da fare |
| `SchedaLettori` | Chi la legge (D11: il legame è allievo–scheda–istruttore) | nuovo | 6b, 8b | da fare |
| `IstruttoreConsenso` | Chi legge le mie schede | nuovo | 8b | da fare |
| `IstruttoreAggiungi` | Aprire una scheda a un istruttore (D18: vale subito) | nuovo | 8b | da fare |
| `IstruttoreDiventa` | Diventare istruttore: lo stesso percorso di «Diventa esaminatore» (D10) | `roles/request_form.html` | 8a | da fare |
| `IstruttoreAllievi` | I miei allievi | nuovo | 8c | da fare |
| `IstruttoreGruppo` | Un gruppo, e lo storico (D12) | nuovo | 8c | da fare |

### 6 · Esami — fase 3

| Artboard | Schermata | Template | PR | Stato |
|---|---|---|---|---|
| `EsamiCatalogo` | Gli esami | `exam/catalog.html` | 3b | da fare |
| `EsameDettaglio` | Un esame | `exam/detail.html` | 3b | da fare |
| `EsameAppuntamento` | L'appuntamento | `exam/request_detail.html`, `exam/request_form.html` | 3c | da fare |
| `EsameSessione` | La sessione dell'esaminatore | `exam/session.html` | 3d | da fare |
| `EsameChiusura` | L'esito | `exam/session.html` | 3d | da fare |
| `EsameComponi` | Comporre un esame | `exam/manage.html`, `exam/detail.html` | 3a | da fare |

### 7 · Disegnatore — fase 9

| Artboard | Schermata | Template | PR | Stato |
|---|---|---|---|---|
| `DisegnatoreDesktop` | Desktop, pannello ai token 7c (D13) | `challenge/builder.html` | 9a | da fare |
| `DisegnatoreMobile` | Telefono: strumenti in una striscia | `challenge/builder.html` | 9a | da fare |
| `DisegnatoreCerchi` | Il bersaglio come dato, misure in quarti di diamante (D14, #179) | `challenge/builder.html` | 9b | da fare |
| `DisegnatoreInquadratura` | L'inquadratura: una cornice salvata accanto alla scena | nuovo | 9c | da fare |
| `DisegnatoreVarianti` | Variante specchiata, tratto di sponda evidenziato | nuovo | 9c | da fare |

### 8 · Decisioni

`Decisioni` e `DecisioniAperte` non diventano schermate: sono la memoria di
cosa si è scelto, cosa si è scartato e perché.

## Le fasi

| Fase | Cosa | PR | Stato |
|---|---|---|---|
| 0 | Canvas, tre giri, pagina di decisioni | — | chiusa il 19/09 |
| 1 | Sorgenti e questo file nel repo | #473 | fatta il 19/09 |
| 2 | Referto TPA | | da fare |
| 3 | Esami | | da fare |
| 4 | Il modello dell'esercizio (#168 #252 #253), «Oggi», voto | | da fare |
| 5 | Eseguire un esercizio (#183 #452) | | da fare |
| 6 | Schede di allenamento (#172) | | da fare |
| 7 | Andamento, obiettivi, consigli (#181 #316 #184 #174 #175) | | da fare |
| 8 | Istruttori (#173) | | da fare |
| 9 | Disegnatore (#179) — indipendente, si può anticipare dopo la 4 | | da fare |
| 10 | Chiusura: guida, racconto, issue | | da fare |

Fuori dal piano, come issue: **#471** TPA semplificato, **#472** giochi a due o
più giocatori.

## Materiale di terzi

I sei esercizi che compaiono nelle schermate delle schede (linea tangente,
ghost ball, stop, follow, draw, angolo naturale) e la loro disposizione in
«riusciti su cinque tiri, destra e sinistra» vengono dalla *Scheda di
allenamento* di Rōnin ASD (<https://roninasd.it>, v0.6, licenza **CC BY**),
vista il 19/09/2026. Qui sono un **esempio di contenuto** dentro un mockup: la
struttura dell'app non dipende da quel foglio, e nessuna tabella o colonna
nasce per un'associazione sola.

Il tastierino del referto segue quello dell'app Accu-Stats TPA da cui è stato
portato il motore (`models/tpa/`, ADR-044).
