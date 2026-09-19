# Redesign TPA ed esercizi — piano di esecuzione

Scritto il 2026-09-19. Serve a portare il redesign **fino in fondo, una fase per
sessione, ciascuna in contesto fresco**. Chi apre una sessione legge la sezione
«Protocollo», poi «Decisioni», poi **solo la propria fase**. Lo stato schermata
per schermata sta in [`STATO.md`](STATO.md); il passato nelle memorie di
sessione `project_redesign_tpa_esercizi`, `project_scheda_allenamento_ronin`,
`feedback_generico_con_opzioni`.

**Dalla fase 1 questa è l'unica copia che fa fede**, insieme ai sorgenti in
`sorgenti/`: la cartella di lavoro da cui sono nati, fuori dal repo, non si
aggiorna più. Si modifica come ogni altro file — in una PR.

Canvas: https://claude.ai/artifact/SM1jiBNtVU9z1ATTvSTwqi
Sorgenti del canvas: `sorgenti/` (`kit.py`, `tpa.py`, `esercizi.py`,
`schede.py`, `esami.py`, `disegnatore.py`, `boards_extra.py`, `decisioni.py`,
`gen.py`, `measure.py`, e `canvas.json`, l'indice pubblicato).

---

## Stato

| Fase | Cosa | Stato |
|---|---|---|
| — | PR #469 allowlist esercizi di gara | unita il 19/09 |
| — | PR #470 difetti in produzione | unita il 19/09 |
| 0 | Canvas, tre giri + pagina di decisioni | **chiusa il 19/09** — canvas v20, 46 artboard in 8 pagine; D1–D20 congelate; issue #471 e #472 aperte |
| 1 | Sorgenti e STATO.md nel repo | **fatta il 19/09** — PR #473 |
| 2 | Referto TPA | da fare |
| 3 | Esami | da fare |
| 4 | Modello dell'esercizio (#168 #252 #253) | da fare |
| 5 | Eseguire un esercizio (#183 #452) | da fare |
| 6 | Schede di allenamento (#172) | da fare |
| 7 | Andamento, obiettivi, consigli (#181 #316 #184 #174 #175) | da fare |
| 8 | Istruttori (#173) | da fare |
| 9 | Disegnatore (#179) | da fare — indipendente, si può anticipare dopo la 4 |
| 10 | Chiusura: guida, racconto, issue | da fare |

Chi chiude una fase aggiorna questa tabella e quella di `STATO.md` (stato,
numeri di PR) **dentro l'ultima PR della fase**, e la riga corrispondente in
memoria.

---

## Protocollo di ogni sessione

1. Leggere questo file (Protocollo, Decisioni, la propria fase) e le tre memorie.
   Non rileggere le altre fasi.
2. Aprire gli artboard della fase **dal canvas dal vivo** (`read_file`), non dai
   sorgenti: l'utente li modifica a mano. Leggere i commenti (`action:
   comments`). Un commento non inviato a Claude non si può chiudere: si dice
   all'utente quale resta aperto.
3. Se la fase ha un **cancello** con domande ancora aperte, farle subito, una
   alla volta, con la raccomandazione. Se sono già decise, non rifarle.
4. Invocare la skill `ui-7c` prima di toccare template o CSS. Il prototipo e il
   canvas vincono sulle preferenze tecniche. Verifica nel browser a 500px **e**
   su desktop, in una finestra nuova di Chrome, app locale su `PORT=5099` con DB
   nello scratchpad (memoria `project_ambiente_locale_help_docs`).
5. Prima il test, poi il codice (CLAUDE.md). Regole di dominio: aprire prima
   `docs/reference/SPECIFICHE.md`; ogni regola numerica nuova va in
   `test_specifiche_conformita.py`.
6. Lavorare in un **worktree** nello scratchpad, un ramo `claude/...` per PR.
   Una PR per sotto-fase, titolo con prefisso (`feat:`/`fix:`/`docs:`),
   descrizione in italiano via `--body-file`, `Closes #N` in inglese, niente
   parentesi annidate nel corpo del commit. Commit con `git commit -F - <<'EOF'`.
7. Ogni PR: `pyright` 0 errori, `black`/`flake8`, unit `-n auto`, integrazione
   `-n 4`, skill `translate` se ci sono stringhe nuove, skill `help-docs` se
   cambia qualcosa di visibile, `ENDPOINT_ROLES` per ogni route nuova, migration
   con `created_at`/`updated_at` e idempotente, ADR per le scelte durature.
8. **L'unione la concede l'utente, PR per PR.** Copilot non si aspetta (quota).
   Dopo l'unione: pull sul working tree principale. Il deploy non si ricorda.
9. Modifiche trasversali di sicurezza: PR dedicata, mai dentro una di queste.
10. A fine fase: tabella «Stato» qui sopra, memoria, e all'utente il prompt
    della fase successiva (in fondo a ogni fase).

**Ripubblicare il canvas**: `action: read` sull'artifact (**obbligatoria subito prima del publish**: `read_file` e `list_files` non bastano, il publish dà «conflict» anche se hai già fuso tutto), poi `read_file` degli
artboard toccati; portare nei sorgenti le modifiche a mano dell'utente; fondere
`project/canvas.json` **partendo da quello dal vivo** (tiene `attachments`,
toglie `size`, aggiunge `w` ai titoli); `python3 gen.py`, `venv/bin/python
measure.py`; pubblicare; salvare l'indice pubblicato in `sorgenti/canvas.json`.
**Mai `force`.**

---

## Decisioni

### Prese dall'utente (19/09, commenti sul canvas e messaggi)

**TPA**
- Il tastierino è quello dell'originale `Accustat TPA/tpa.html`: uno, sempre
  tutto visibile, tre colonne, i tasti non ammessi si spengono.
- **Passare il tavolo = toccare il riquadro del giocatore in alto.** Niente
  pulsante «Passa il tavolo».
- Servono **due annulla**: (a) annulla l'annotazione parziale in corso;
  (b) undo/redo che scorre il referto avanti e indietro e permette di
  **ricominciare da un punto del passato**.
- Nel tabellone **il TPA conta almeno quanto il punteggio**: lo spazio vuoto va
  usato per dargli la stessa evidenza.
- Il «TPA semplificato» **non esiste**: al più una issue su GitHub.
- Vocabolario: «Primo tiro di calcio?», «Referto» (non «Il foglio»),
  «Chiuse in un **turno**» (non «visita»).

**Esercizi**
- Due vocabolari di categorie, **abilità** e **gesto**, zero-una-più voci per
  esercizio (tabelle di associazione). Voto 1–5 e «quanti l'hanno provato» sulla
  card, ordinamento «i più provati».
- «Colpo per colpo» è **troppo uguale a Bullseye**: ispirarsi sì, copiare no —
  almeno i colori, meglio anche la forma.
- Durante l'esecuzione serve un **grafico di avanzamento** dal vivo.
- Va disegnato **come si impostano gli obiettivi** (oggi nel canvas compaiono
  già impostati).
- Gli esercizi possono essere anche **giochi**. Giochi a due o più: **non ora**.
- «Esordienti» non è una categoria: è **uno dei livelli** che ci sono già.

**Disegnatore**
- Le misure dei bersagli (largo, alto, raggio: «in diamanti») accettano anche
  le **frazioni 1/2 e 1/4**, come già fa la griglia. Vale anche per il formato
  dei bersagli come dato (D14): le misure sono in quarti di diamante.

**Schede**
- **Una sola scheda**, senza la distinzione «da palestra / a caselle». Ogni
  esercizio ha il suo «quanto farne», libero. **Livello e soglia sono
  facoltativi.** I modelli di partenza, se restano, sono solo precompilazioni.
- Il giocatore può dare **accesso in lettura alla scheda a uno o più
  istruttori**.

**Istruttori**
- Il consenso va **al contrario** di com'è disegnato: è il **giocatore** che
  aggiunge (o toglie) un istruttore e gli permette di seguirlo.
- Lo **storico corso per corso** non c'è e va fatto: è il modo in cui
  l'istruttore **organizza i suoi allievi**.
- Foto del profilo: **non ora** (issue #283). Area «con password»: no — la
  visibilità la dà il consenso del giocatore, e per i minorenni è un motivo in
  più per tenerla stretta.
- L'app resta generica: il materiale di un'associazione spiega il dominio, non
  diventa la struttura. Decide l'utente, non il cliente.

### Prese il 19/09 sera (commenti sulla pagina 8 e messaggio)

- **D3 rovesciata: «Oggi» (B) subito**, non il catalogo. Conseguenza sul piano:
  «Oggi» nasce in **fase 4** con ciò che c'è già — riprendi l'ultimo esercizio,
  preferiti, i più provati, il catalogo dietro «Apri il catalogo» — e si
  riempie da sola: la scheda da riprendere in fase 6, obiettivi e consigli in
  fase 7. La PR 4c diventa «Oggi + catalogo che si filtra».
- **D11 e il legame: `allievo–scheda–istruttore`**, non `allievo–istruttore`.
  Ogni scheda ha i suoi n lettori, aggiunti e tolti dal giocatore. Non esiste
  «Luca mi segue»: «I miei istruttori» e «I miei allievi» sono **viste
  derivate** dalle schede. L'andamento generale **non** si condivide. Nel
  modello: una tabella sola (scheda, istruttore, da quando, fino a quando).
  Tocca le fasi 6 (la tabella nasce con la scheda) e 8.
- **D19 · niente «serie × ripetizioni»**: al biliardo una voce è un numero di
  tiri, di partite o di minuti. Una voce lunga si conta tiro per tiro
  (riuscito / sbagliato) o si scrive il totale.
- **D20 bis · kick-in e fallo** (ultimo commento del 19/09): il primo tiro di
  calcio si scrive come **numero del giocatore (1 o 2) cerchiato in piccolo,
  in una riga sopra l'annotazione** — così fa l'originale (`kickSequence`,
  classe `.circle-kick`). **L'app di oggi sbaglia**: `tpa_referto.html` disegna
  una freccia `↺` (righe ~254-260 nel riquadro, ~395 nel referto). Va corretto
  in fase 2b/2e. Il fallo P/N sta nella casella ombreggiata; dopo un fallo
  `available_buttons` torna vuoto: tasti tutti spenti, resta passare il tavolo.
  **Allineamento** (commento del 19/09, 15:23): nelle due caselle le annotazioni
  sono **centrate e sulla stessa riga**; il numero cerchiato del calcio sta
  **subito sopra la casella bianca, fuori dal bianco**, in una riga che c'è
  sempre (anche vuota) perché le caselle dei due giocatori restino allineate.
- **D20 · notazione del TPA**: TPA da **0 a 1000 senza punto**; le bilie in
  spaccata come **apice** prima del totale (mai «1/3»); il triangolo vinto è un
  **cerchio** attorno alle bilie, non una «G»; vanno mostrati anche `M^n`,
  `S^x`, `S^p`, i falli P e N nella casella ombreggiata, il kick-in `↺`. Il
  motore li produce già (`main_note`, `secondary_note`): in fase 2 è lavoro di
  resa, più il cambio di scala del numero mostrato. Verificato: `tpa_score` torna già i
  millesimi interi e troncati (780 = .780), quindi «0–1000» è **solo formato**:
  si toglie il punto dove il template lo mette.
- **I radar sono due**, uno per asse (abilità e gesto). Fase 7a.
- **Il modulo dell'esercizio ha anche il gesto** (le categorie di Bullseye),
  non solo l'abilità. Fase 4b.
- **Vocabolari corretti a mano dall'utente**: abilità = Fondamentali, Tiro,
  Battente, Posizione, Sponde, Difesa, **Spaccata**; gesto = stop, stun, follow,
  draw, **spin**, forza, bank, kick, jump, massé.
- **Soglia**: «sedute di fila sopra la soglia», numero sulla scheda, default 1. OK.
- **D12 · gruppi dell'istruttore con storico**: OK, e **nel piano** (fase 8c),
  niente issue a parte. Niente lezioni né programma.
- **Voto degli esercizi**: **nel piano** (fase 4d), niente issue a parte.
- **Dove si diventa istruttore**: nel profilo, sezione Ruoli, stesso percorso di
  «Diventa esaminatore» (`RoleRequest` → `RoleGrant`); «scuola o associazione»
  è un testo facoltativo della richiesta. Fase 8a.
- **Disegnatore, immagine di un solo pezzo**: si disegna sempre sul tavolo
  intero; l'inquadratura è una cornice (preset o libera, agganciata ai
  diamanti) salvata accanto alla scena. Fase 9c.
- Obiettivi, testi dell'utente: «al livello successivo», «allenarmi con una
  certa frequenza».
- Issue aperte: **#471** TPA semplificato, **#472** giochi a due o più giocatori.

### Confermate il 19/09 (l'utente: «se non ho commentato significa che è ok»)

Tutta la tabella qui sotto è **decisa**, non più presunta. Cambia solo con una
nota datata. Le voci barrate sono quelle che l'utente ha deciso diversamente:
valgono le righe di «Prese il 19/09 sera».

| # | Decisione | Presunta |
|---|---|---|
| D1 | Direzione del TPA | **B · Tavolo** (l'utente ha commentato solo B) |
| D2 | La parola sotto ogni lettera del tastierino | sì, spegnibile |
| ~~D3~~ | Porta d'ingresso | decisa: vedi sopra (B subito) |
| D4 | Vocabolari abilità/gesto | **fissi di piattaforma**; famiglia e passo liberi dell'autore; radar su abilità |
| D5 | Livello | 1–5 dichiarato, misurato accanto quando c'è (#174) |
| D6 | Voto | vota solo chi ha provato; 1–5; nei consigli non entra subito |
| D7 | Seduta di una scheda | **entità con inizio e fine**, sopravvive alla chiusura dell'app |
| D8 | Passaggio di livello | opzione a tre valori: nessuno · automatico alla soglia · conferma dell'istruttore |
| D9 | «Contro il ghost» | esercizio a punteggio, nessun tipo suo |
| D10 | Istruttore | `RoleGrant` `INSTRUCTOR`, distinto da `EXAMINER` (ADR-041) |
| ~~D11~~ | Legame e fine del legame | decisa: vedi sopra (per scheda) |
| ~~D12~~ | Corsi | decisa: gruppi con storico, nel piano |
| D13 | Disegnatore | pannello ai token 7c, tavolo scuro |
| D14 | Bersagli | dato strutturato: centro, raggio, valore per anello |
| D15 | Ordine | quello di questo piano |
| D16 | Ripartire da un turno del passato (TPA) | **passo esplicito** «Riparti da questo turno…» con foglio di conferma che nomina i turni tolti — così fa l'originale (`enterEditMode`), che scorre in sola lettura. Alternativa: troncatura implicita al primo tasto |
| D17 | Cosa somma la soglia di una scheda | **solo le voci «a riusciti»**; partite, minuti e «fatto» restano fuori dal conto |
| D18 | Dopo che il giocatore aggiunge l'istruttore | **vale subito**: notifica all'istruttore, che può togliersi; nessuno stato «in attesa» |

### Ancora da chiedere (fase 0)
- ~~Vocabolari~~ e ~~soglia~~: risposte avute, vedi «Prese il 19/09 sera».
- Il programma dei corsi e le statistiche «dovrebbero esserci già»: **verificato
  il 19/09**. NON esistono corsi/lezioni/programmi, ruolo istruttore, legami
  utente→utente, schede, sedute, obiettivi, categorie dell'esercizio (`Challenge`
  ha 11 colonne, nessuna di queste). ESISTONO: `TrainingHistoryService` (storico
  per giocatore), `PlayerHistoryService.get_drill_trend`/`trend_chart`
  (andamento su un esercizio), `Challenge.get_statistics` (solo direttori),
  `UserPrivacySetting.show_challenge_stats` (tutto o niente, default spento; il
  gate è solo nel template `player/profile.html`). Commento obsoleto da togliere
  in fase 4: `_player_training.html` dice che `Challenge` non ha `max_score`.
  Resta da far confermare all'utente la proposta D12 (gruppi, niente lezioni).

**Fatto nel disegno della fase 0** (per chi riprende): la situazione del TPA è
ora «3 M» annotato — a «bilie?» il motore ammette solo i numeri, il primo giro
sbagliava. Nuovi artboard: `TpaIndietro`, `TpaRiparti`, `Obiettivo`,
`SchedaVoce`, `SchedaLettori`, `IstruttoreAggiungi`, `IstruttoreGruppo`,
`Decisioni`, `DecisioniAperte`. Tolti: `SchedaModello`,
`SchedaComponiPalestra`, `RegistroPalestra` (copie in `vivo-prima-del-giro2/`,
sorgente vecchio in `schede_giro1.py.bak`). Il bersaglio ha anelli a PUNTI in
tinta oro (`kit.bullseye`), il grafico dal vivo è `kit.livechart`. Proposta dei
vocabolari: abilità = Fondamentali, Tiro, Battente, Posizione, Sponde, Difesa,
Spacco; gesto = stop, stun, follow, draw, effetto laterale, forza, bank, kick,
jump, massé. Issue GitHub del punto 10: **non ancora aperte**, serve il sì.

---

## Fase 0 · Canvas, secondo giro e pagina di decisioni

**Scopo**: recepire gli 11 commenti del 19/09 e le decisioni qui sopra, chiudere le
«presunte», congelare il disegno. **Nessun codice dell'app.**

**Da fare**
1. Leggere dal vivo i 37 artboard toccati e i commenti. Portare nei sorgenti la
   modifica a mano su «Referto chiuso» («Chiuse in un turno») e il titolo
   «Referto».
2. TPA (`tpa.py`): B senza «Passa il tavolo», riquadro del giocatore toccabile
   con un segno che lo dica; due annulla distinti (parziale nel tastierino,
   undo/redo come coppia sotto); tabellone con TPA e punteggio alla pari; A, C e
   desktop allineati; bigliettino che dichiara C scartata se D1 è confermata.
3. Eseguire (`esercizi.py`): grafico di avanzamento dal vivo nella cornice
   comune; «Colpo per colpo» ridisegnato lontano da Bullseye.
4. Andamento: schermata «Imposta un obiettivo» (#316).
5. Schede (`schede.py`): una forma sola; via gli artboard doppi
   palestra/caselle; livello e soglia come interruttori; «chi può leggere questa
   scheda» con uno o più istruttori.
6. Disegnatore (`disegnatore.py`): nei campi di misura dei bersagli passi da
   1/4 di diamante, come la griglia.
7. Istruttori: consenso rovesciato (il giocatore aggiunge/toglie); «I miei
   allievi» per gruppo/corso con storico (D12), **dopo** aver verificato nel
   codice cosa esiste già.
8. Nuova **pagina 8 · Decisioni**: la tabella delle presunte, una riga per
   decisione, con cosa cambia se si sceglie diversamente.
9. `measure.py`, ripubblicare (mai force), dire all'utente quali thread restano
   aperti perché non inviati a Claude.
10. Issue GitHub da aprire (chiedere conferma prima): «TPA semplificato per gli
   allievi», «Giochi a due o più giocatori», «Voto degli esercizi», «Gruppi di
   allievi dell'istruttore con storico» (o estendere la #173).

**Cancello d'uscita**: l'utente conferma o corregge D1–D15 e le tre domande
aperte. Le risposte si scrivono in «Decisioni» spostandole fra le prese.

**Prompt**: «Leggi `…/canvas-tpa-esercizi/PIANO.md` ed esegui la fase 0.»

---

## Fase 1 · Sorgenti e STATO nel repo

**Scopo**: rendere il redesign versionato, come fece la PR #334.
- `docs/redesign-7c/canvas-tpa-esercizi/sorgenti/` (i `.py`), `STATO.md` (una
  riga per schermata: artboard → template → PR → stato), copia di questo piano.
- Niente nomi di clienti nella struttura; il messaggio dell'istruttore **non**
  entra nel repo (è pubblico).
- Riga in `docs/redesign-7c/STATO.md` e in `docs/ROADMAP.md`.
- PR `docs:`. La CI **non** chiude in pochi secondi, come si era scritto: il
  filtro «sola documentazione» lascia fuori i `.py` sotto `docs/`, e qui ce ne
  sono dieci (nota del 19/09).

**Prompt**: «…esegui la fase 1.»

---

## Fase 2 · Referto TPA

**Issue**: nessuna dedicata; residui #208 (`SetRack`) e #241 da rileggere.
**Leggere prima**: `models/tpa/CLAUDE.md`, ADR-044, ADR-056,
`templates/individual_match/tpa_referto.html` (~345 righe di JS inline),
`routes/individual_match/tpa.py`, `models/tpa/services.py`, il CSS `.c7-tpa-*` in
`static/css/theme-7c.css`, e `Accustat TPA/tpa.html` (l'app originale, **fuori
dal repo**: sta accanto alla cartella dei progetti) per il tastierino e per
`navigateBack`/`navigateForward`.

**Attenzione**: oggi `TpaRefertoService.undo` **toglie** l'ultimo comando. Il
redo con ripartenza dal passato chiede un **cursore sul registro** (i comandi
oltre il cursore restano finché non se ne annota uno nuovo, che li tronca). È
un emendamento all'ADR-044: il registro resta l'unica verità, il punteggio
continua a discendere dal rigioco **fino al cursore**. Le regole Accu-Stats
restano solo in `engine.py`.

**PR**
- 2a `refactor:` il JS esce dal template in `static/js/tpa-referto.js`; URL da
  `data-*`, niente `confirm()` nativo (foglio 7c). Nessun cambiamento visibile;
  test frontend jsdom sul modulo.
- 2b `feat:` direzione B su telefono: tastierino unico sempre visibile, tasti
  spenti invece che nascosti, caselle dentro la card del giocatore, tocco sul
  riquadro per passare il tavolo, TPA alla pari del punteggio, annulla parziale.
- 2c `feat:` undo/redo sul registro (migration del cursore, servizio, route,
  ADR-044 emendato, test di rigioco: undo·undo·redo·nuovo comando tronca).
- 2d `feat:` desktop a tre colonne.
- 2e `feat:` referto chiuso come racconto (errori per tipo, tre numeri,
  triangoli ripiegati); i numeri vengono da `stats_service.py`, non da conti
  nuovi. «Turno» al posto di «visita» in tutta l'app.
- 2f `docs:` guida `/aiuto` (skill `help-docs`), schermate rigenerate.

**Verifica**: Playwright con tocco emulato (memoria
`project_playwright_emula_il_tocco`), una partita intera segnata dal tastierino,
confronto del TPA con quello dell'originale sugli stessi tocchi.

**Prompt**: «…esegui la fase 2. Una PR alla volta; fermati a ogni PR per il via
all'unione solo se la successiva dipende da quella.»

---

## Fase 3 · Esami

**Vincolo**: ADR-042 non si tocca (esito netto, deciso dall'esaminatore;
`ExamChallenge.max_score` ≠ `challenge.max_score`).
**Leggere prima**: `models/exam/`, `routes/exam/`, `templates/exam/*`,
`docs/usecases/esami.md`, artboard della pagina 6.

**PR**
- 3a `feat:` comporre: scelta dell'esercizio da un selettore (oggi si scrive
  l'ID a mano), riordino e modifica delle voci, modifica dell'esame — le tre
  route `reorder_challenges`/`update_challenge`/`update_exam` hanno finalmente
  un'interfaccia. Il componente «sequenza di esercizi con quanto farne» nasce
  qui, **riusabile**: lo userà la fase 6.
- 3b `feat:` catalogo e dettaglio (via le quattro statistiche a zero, date nel
  formato dell'app).
- 3c `feat:` appuntamento («Accetto» nella barra d'azione, non sotto la nav).
- 3d `feat:` sessione dell'esaminatore col tastierino, punteggio mostrato una
  volta; esito.
- 3e `docs:` guida.

**Prompt**: «…esegui la fase 3.»

---

## Fase 4 · Il modello dell'esercizio

**Issue**: #168 (prerequisito di quasi tutto), #252, #253; voto (issue nuova).
**Leggere prima**: `models/challenge/` (+ `CLAUDE.md`), `routes/challenge.py`,
`templates/challenge/*`, artboard pagine 2 e 4, memoria Ronin per famiglie,
passi e varianti.

**Modello** (ADR nuovo): `Abilita` e `Gesto` come tabelle con associazione
molti-a-molti (D4), `livello` 1–5, `famiglia` + `passo` liberi, **varianti**
etichettate di uno stesso esercizio (dx/sx, A/B: N etichette, registrate
separate — mai un secondo esercizio), `riposizionare`, voto e conteggio dei
giocatori. Niente colonne che servono a un cliente solo. Migration idempotenti
con timestamp; nessun backfill inventato: gli esercizi esistenti restano senza
categoria finché l'autore non la mette.

**PR**
- 4a `feat:` modello, migration, servizio, ADR.
- 4b `feat:` modulo unico crea/modifica/duplica (#252 #253) con il foglio «ha
  già delle prove» — sostituisce la modifica minima della PR #470.
- 4c `feat:` **«Oggi» come porta d'ingresso** (D3: riprendi l'ultimo, preferiti,
  i più provati), con dietro il catalogo che si filtra (abilità, gesto, livello,
  voto, i più provati) e la scheda dell'esercizio.
- 4d `feat:` voto.
- 4e `docs:` guida.

**Prompt**: «…esegui la fase 4.»

---

## Fase 5 · Eseguire un esercizio

**Issue**: #183, #452, #326 (la domanda va chiusa qui con una risposta).
**Idea portante**: «prova = sequenza di colpi con esito» — **un** modello per
colpo per colpo, estrazione e schede. ADR nuovo.

**PR**
- 5a `feat:` cornice unica di esecuzione + grafico di avanzamento dal vivo; la
  modalità a punteggio di oggi ci entra senza cambiare dati.
- 5b `feat:` colpo per colpo e punto preciso (#183), nel disegno **non** copiato
  da Bullseye.
- 5c `feat:` estrazione casuale (#452).
- 5d `feat:` fine sessione.
- 5e `docs:` guida.

**Prompt**: «…esegui la fase 5.»

---

## Fase 6 · Schede di allenamento

**Issue**: #172. **Dipende da**: 3a (componente sequenza), 4a (varianti), 5a.
Una scheda sola; per voce: esercizio, variante, «quanto farne», come si misura;
opzioni facoltative di scheda: totale, soglia, livello (D8), giorni, durata.
Versione: una scheda pubblicata che cambia **non riscrive** le sedute fatte.
Seduta come entità (D7). Inserimento a un tocco per casella.

**PR**: 6a modello+ADR · 6b comporre · 6c seduta e fine seduta · 6d registro
(che è anche l'andamento della scheda) · 6e guida.

**Verifica di generalità**: nei test si compongono **due** schede molto diverse
con lo stesso oggetto — una a riusciti-su-N con soglia e livelli, una a tiri,
partite e minuti su giorni A/B/C senza totale. (Nota del 19/09: qui c'era
scritto «serie × ripetizioni», rimasto dal secondo giro; la D19 l'ha tolto.)

**Prompt**: «…esegui la fase 6.»

---

## Fase 7 · Andamento, obiettivi, consigli

**Issue**: #181, #316, #184, #174, #175. Storico e tendenza, radar per abilità,
impostare un obiettivo e vederne l'avanzamento, traguardi (via
`flash_gamification_event`, filtrati dall'allowlist), difficoltà misurata
incrociata con l'Elo, consigli → porta d'ingresso B «Oggi» (D3).
In dev l'Elo è vuoto (memoria `project_dev_db_senza_elo`): i test costruiscono i
propri dati.

**PR**: 7a andamento · 7b obiettivi · 7c traguardi · 7d difficoltà misurata ·
7e consigli e «Oggi» · 7f guida.

**Prompt**: «…esegui la fase 7.»

---

## Fase 8 · Istruttori

**Issue**: #173 (+ gruppi, se aperta a parte). Il **giocatore** aggiunge o
toglie un istruttore e gli dà lettura di schede e andamento (uno o più
istruttori). `RoleGrant INSTRUCTOR` (D10). Gruppi/corsi dell'istruttore con
storico (D12). Assegnare una scheda a un allievo o a un gruppo. Alla fine del
legame vale D11. Notifiche nella lingua di chi riceve (ADR-062). Minorenni:
nessuna visibilità che non passi dal consenso; niente foto.

**PR**: 8a ruolo e legame+ADR · 8b «I miei istruttori» lato giocatore ·
8c «I miei allievi» e gruppi · 8d assegnare schede · 8e guida.

**Prompt**: «…esegui la fase 8.»

---

## Fase 9 · Disegnatore

**Issue**: #179, più varianti specchiate, inquadratura parziale del tavolo,
tratto di sponda evidenziato. Pannello ai token 7c (D13), bersagli come dato
(D14) con misure in quarti di diamante (1/2 e 1/4, come la griglia), telefono: strumenti in una striscia, il tavolo non finisce sotto «Salva».
Indipendente: si può fare dopo la fase 4.

**PR**: 9a lessico 7c e telefono · 9b bersagli, numeri, richiami (#179) ·
9c varianti, inquadratura, sponda · 9d guida.

**Prompt**: «…esegui la fase 9.»

---

## Fase 10 · Chiusura

`CHANGELOG.md` (a mano: il racconto), `docs/ROADMAP.md`, `STATO.md` tutto verde,
issue chiuse o riscritte, schermate della guida rigenerate una volta sola,
memoria aggiornata, e un giro sui log di produzione nei giorni dopo.

**Prompt**: «…esegui la fase 10.»
