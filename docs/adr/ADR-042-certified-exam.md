# ADR-042 L'esame è un evento di persona, e l'esito è un sì o un no

**Data**: 2026-08-15
**Stato**: Accepted
**Decisori**: Paolo Coppola

## Contesto

Il modello dati degli esami **esisteva già** — quattro tabelle in `models/exam/`,
un `ExamService` con quindici metodi — ed era **codice orfano**: zero route, zero
template, zero i18n, zero test attivi. Non solo inutilizzato: rotto.
`Exam.get_max_possible_score()` e `ExamChallenge.get_weighted_max_score()`
leggevano `challenge.max_score`, una colonna che su `Challenge` **non esiste**.

Lo stesso `challenge.max_score` inesistente era letto anche in codice **vivo**,
dentro un `except Exception: pass` che lo inghiottiva — ed è il motivo per cui lo
storico drill del profilo è stato sempre vuoto, senza un errore da nessuna parte.

> Nota per chi legge dopo: quella colonna **oggi esiste** (dal 2026-08-18, vedi
> l'emendamento più sotto). Il difetto raccontato qui resta reale — allora non
> c'era, e il codice la leggeva lo stesso — ma non provare a riprodurlo cercando
> un `AttributeError`: non lo troveresti più.

Le tabelle esistevano anche in produzione (create da `db.create_all()`) ma erano
**vuote per costruzione**: nessun codice ci scriveva.

La domanda da rispondere era quindi cosa deve *essere* un esame, non come
salvarlo.

## Decisione

### L'esito è booleano

Superato o non superato. Niente voto A–F, niente griglia di valutazione, nessuna
nota di certificazione.

Una griglia sembra più ricca ma chiede a chi certifica di **motivare**, e chi
certifica sta in piedi accanto a un tavolo da biliardo con un telefono in mano.
Un sì/no è un fatto che si registra in un gesto; un voto è un giudizio che si
argomenta, e che il giorno dopo qualcuno contesta.

Con il voto sparisce anche il `weight` sui drill: esisteva per pesarli nel
calcolo, e senza calcolo non serve. Chi vuole dare più rilievo a un drill gli
assegna un `max_score` più alto.

### Solo la sessione di persona certifica

Un esame si può fare **da soli**, ed è allenamento: nessun percorso lo trasforma
in certificato, nemmeno a posteriori. La certificazione richiede un esaminatore
che guarda, e le due nature convivono nello stesso `ExamAttempt` con `mode`
`self_practice` | `certified`.

Il corollario che vale la pena scrivere: **il candidato accetta l'inizio**. Fino
a quel momento nessun punteggio è registrabile, e il rifiuto sta **nel
servizio**, non nella UI — una POST diretta aggira una schermata, non un
dominio. Nessuno viene valutato a propria insaputa.

### `max_score` su `ExamChallenge`, non su `Challenge`

Il punteggio massimo **dell'esame** è per-esame: lo stesso esercizio può valere
10 in un esame e 15 in un altro. Derivarlo dal catalogo lo renderebbe globale, e
obbligherebbe a toccare il catalogo per tarare un esame.

`NULL` significa superato/non superato: vale 1 punto se superato, 0 altrimenti.
Obbligatorio se l'esercizio non è superato/non superato, vietato se lo è.

> **Emendamento del 2026-08-18.** `Challenge` ha ora un `max_score` **suo**,
> facoltativo, e la convivenza è voluta: le due colonne rispondono a domande
> diverse.
>
> | | domanda | chi decide |
> |---|---|---|
> | `Challenge.max_score` | *quanto vale al massimo questa prova* | chi crea l'esercizio |
> | `ExamChallenge.max_score` | *quanto pesa dentro questo esame* | chi compone l'esame |
>
> Quindici bilie sono quindici bilie in qualunque contesto; quanto quell'esercizio
> **pesi** in un esame è un'altra cosa. La decisione originale resta intatta —
> `effective_max_score` **non** guarda il catalogo, e derivarlo da lì
> renderebbe di nuovo impossibile far pesare diversamente lo stesso esercizio in
> due esami (presidio: `test_max_score_is_per_exam_not_per_challenge`).
>
> Quello che cambia è che *fuori* dagli esami un tetto non c'era da nessuna
> parte: chi si allena dal catalogo vedeva «12» senza sapere su quanto, e una
> POST con `score=40` su una prova da 15 entrava senza che niente la fermasse.
> Vedi «Debito noto» in fondo: questa colonna è metà di quel debito, saldata.

### Entità gemelle di `MatchProposal`, non un'astrazione condivisa

L'appuntamento d'esame (`ExamRequest` / `ExamRequestRecipient` /
`ExamTimeProposal`) **ricopia i pattern** delle proposte di match individuale —
richiesta a N destinatari, il primo che accetta chiude gli altri, indice parziale
anti-TOCTOU — ma non ne condivide le tabelle.

Due motivi, di peso diverso:

1. `MatchProposal` porta sette colonne di configurazione di gioco (disciplina,
   distanza, regola di spacco, multi-set…) e una 1:1 hardcodata con
   `IndividualMatch`. Un esame non ha nulla di tutto ciò.
2. **Soprattutto: il ciclo di vita diverge nel punto critico.** Là l'orario lo
   fissa il proponente e il destinatario può solo accettare o rifiutare; qui si
   contratta a oltranza, e la controproposta introduce stati e invarianti che
   `MatchProposal` non ha e non avrebbe motivo di avere.

Le **disponibilità** invece si riusano identiche: `UserLocationAvailability` non
nomina mai il match, e serviva solo l'intersezione «disponibile in questa sala ED
esaminatore di questo esame». Ciò che si duplica è la richiesta, e solo perché
il suo ciclo di vita è davvero diverso.

### La negoziazione regge su due invarianti

1. **Può accettare solo chi non ha fatto l'ultima proposta**
   (`last_proposed_by_id`). Senza, ci si accetterebbe la propria.
2. **La prima controproposta fissa l'interlocutore** (`negotiating_with_id`). Da
   lì la trattativa è a due; gli altri destinatari possono ancora accettare la
   proposta sul tavolo, o lasciar scadere, ma non inserirsi. Senza questo
   vincolo N esaminatori controproporrebbero in parallelo sullo stesso
   `scheduled_at`, e l'ultimo a scrivere sovrascriverebbe gli altri **in
   silenzio**.

Chi si sfila libera la trattativa: l'invariante serve a evitare le
sovrascritture, non a lasciare la richiesta ostaggio di chi si è tirato indietro.

### Il presidio anti-TOCTOU **non** è quello dei match

Nei match, `accept()` crea subito l'`IndividualMatch`: è l'indice UNIQUE su
`individual_match.proposal_id` a far vincere un solo accettante. Qui accettare
fissa **solo l'appuntamento** — l'`ExamAttempt` nasce molto dopo, all'apertura
della sessione. Quell'indice proteggerebbe un'altra corsa.

Per «due esaminatori accettano insieme» servono due cose:

- indice UNIQUE **parziale** `(request_id) WHERE status = 'accepted'` su
  `exam_request_recipient`: un solo destinatario può risultare accettante;
- l'accettazione come **UPDATE condizionato** (`WHERE accepted_by_id IS NULL`)
  con controllo del rowcount, così il perdente riceve un `ConflictError` invece
  di sovrascrivere il vincitore.

L'indice su `exam_attempt.exam_request_id` resta, ma per la **sua** corsa: due
sessioni aperte dallo stesso appuntamento.

### Lo schema si rifà da zero

Le tabelle erano vuote per costruzione, quindi la migration fa
**drop-and-recreate previa verifica**, non una sequenza di `ALTER`. Il rework
avrebbe richiesto un `RENAME COLUMN` e tre `DROP COLUMN`, e il progetto evita
`DROP COLUMN` per prassi (la versione di SQLite in produzione non è verificabile
da qui, e `DROP COLUMN` richiede ≥ 3.35). Se una tabella contiene righe, la
migration **si ferma rumorosamente** invece di distruggerle.

## Alternative Considerate

### Alternativa 1: voto e griglia di valutazione

**Descrizione**: esito su scala, con criteri pesati per drill.

- **Pro**:
  - Più informazione per il candidato su *dove* migliorare.
- **Contro**:
  - Chiede a chi certifica di argomentare, in piedi accanto a un tavolo.
  - Un voto si contesta; un sì/no si ripete.
  - Trascina `weight`, il calcolo pesato, e la domanda «con che voto si passa».

### Alternativa 2: coda asincrona dei tentativi da certificare

**Descrizione**: il candidato registra da solo, un esaminatore convalida dopo.

- **Pro**:
  - Nessun appuntamento da costruire: niente disponibilità, niente negoziazione.
  - Molto meno codice.
- **Contro**:
  - **Certifica un racconto, non un fatto.** L'esaminatore non ha visto niente e
    firma sulla parola, il che svuota la certificazione del suo unico valore.
  - Sposta il problema sulla fiducia invece di risolverlo.

### Alternativa 3: astrazione condivisa con `MatchProposal`

**Descrizione**: una `Proposal` generica, specializzata per match ed esame.

- **Pro**:
  - Un solo posto per la logica «richiesta a N, il primo che accetta chiude».
- **Contro**:
  - I due cicli di vita divergono proprio nel punto che conta (la
    controproposta): l'astrazione dovrebbe ospitare stati che a metà dei suoi
    utenti non servono.
  - `MatchProposal` è in produzione con dati veri: rifattorizzarla sotto
    un'astrazione per far posto a un dominio nuovo è rischio pagato dal dominio
    sbagliato.

## Conseguenze

### Positive

- La certificazione ha un significato univoco: qualcuno era lì e ha visto.
- Il tentativo in autonomia resta utile (allenamento, XP, streak) senza inquinare
  il curriculum.
- La negoziazione risolve un problema reale — trovarsi in due, di persona — che
  nei match individuali era rimasto scoperto.
- Il fix alla notifica degli invitati scartati è tornato indietro anche ai match
  individuali, dove mancava.

### Negative

- Due tabelle di richiesta quasi gemelle, con il rischio che un fix su una non
  arrivi all'altra. Il rimedio è che i punti di contatto siano dichiarati nei
  docstring, non che le tabelle si fondano.
- Il flusso completo è lungo: richiesta, negoziazione, appuntamento, apertura,
  accettazione dell'inizio, punteggi, certificazione. È il costo di modellare un
  evento di persona invece di una firma.

### Rischi

- **Nessuna conseguenza modellata per il no-show.** Lo stato esiste
  (`ExamAttempt.abandoned`) ma non ci sono penalità né contatori di assenze. Se
  gli appuntamenti disertati diventassero un problema, è una storia in più.
- Le disponibilità restano una **ricorrenza settimanale grezza**, non un'agenda
  con slot prenotabili: nessun controllo di conflitto fra appuntamenti. Coerente
  con l'esistente, ma va detto.

## Debito noto

**Saldato il 2026-08-18.** Diceva:

> `Challenge` resta **senza `name` e senza `max_score`**, in disallineamento con
> `SPECIFICHE.md` §Challenge («È identificata da un nome. Ha un punteggio minimo
> e massimo»). È una scelta consapevole — `max_score` è per-esame, e il nome è un
> lavoro sul catalogo drill che non appartiene a questo dominio — ma il costo si
> vede: il catalogo mostra la descrizione troncata a 50 caratteri
> (`Challenge.get_display_name()`) al posto di un nome, e le schermate d'esame
> mostrano il punteggio senza fondoscala.

Entrambe le metà sono state pagate, in due momenti e per due ragioni diverse:

- **il nome** (`Challenge.title`, facoltativo) perché venti esercizi che
  cominciano con «Disponi le bilie…» erano venti card indistinguibili. Senza
  titolo l'esercizio si chiama col suo progressivo — «Esercizio 12» — non con
  mezza istruzione;
- **il tetto** (`Challenge.max_score`, facoltativo) perché fuori da un esame non
  c'era nessun posto dove dire quanto vale al massimo una prova. Vedi
  l'emendamento sopra: non sostituisce quello per-esame, e non lo alimenta.

Facoltativi tutti e due, e per la stessa ragione: `NULL` non è un dato mancante.
Dice «questo esercizio non ha un nome scelto» e «questa prova non ha un tetto» —
ci sono esercizi che si ripetono finché non si sbaglia, dove un massimo non
esiste, e obbligare a dichiararlo vorrebbe dire farlo inventare.

## Emendamento 2026-09-19 — comporre un esame che ha già una storia

Fino a oggi la composizione si cambiava solo il primo giorno: aggiungere e
togliere erano gli unici comandi, riordino e modifica di peso e prove avevano
il servizio e la route ma nessuna interfaccia. Con la pagina «Componi l'esame»
(`exam.compose_exam`, salvataggio unico con `ExamService.save_composition`) la
composizione si ritocca davvero, e bisogna dire cosa succede a chi l'esame lo
sta sostenendo. Due regole, e una cosa che **non** si è decisa.

* **Sessione certificata aperta → la composizione è bloccata.** La griglia
  delle prove nasce all'apertura della sessione (`create_placeholder_results`):
  cambiarla a sessione aperta vorrebbe dire valutare il candidato su un esame
  diverso da quello che ha accettato. Il blocco è del servizio
  (`ConflictError`), e la pagina lo dice **prima**, senza lasciar lavorare a
  vuoto. Non trattiene nessuno a lungo: una sessione certificata dura una sera
  e si può interrompere.
* **Allenamento in autonomia aperto → la griglia si riallinea.** Un
  allenamento può restare aperto per mesi e non può bloccare chi compone.
  Nascono le caselle che mancano, spariscono quelle in più *mai usate*; una
  prova già registrata non si tocca, e `get_progress` conta solo le prove che
  l'esame prevede oggi, così un «3 su 2» non compare.
* **Non deciso: la versione dell'esame.** I tentativi conclusi tengono i
  totali che avevano (`total_score`, `max_possible_score` sono scritti sul
  tentativo), ma togliere un esercizio ne cancella le righe di dettaglio a
  cascata, anche dai tentativi certificati: resta l'esito, resta il punteggio,
  sparisce il «come». Era già così col vecchio «Togli». La cura vera è una
  composizione versionata — la stessa che il piano del redesign prevede per le
  schede di allenamento («una scheda pubblicata che cambia non riscrive le
  sedute fatte») — e va decisa insieme a quella, non qui di passaggio.

Le cinque route di prima (`update_exam`, `add_challenge`, `update_challenge`,
`remove_challenge`, `reorder_challenges`) sono state tolte: tre non avevano mai
avuto un comando, e i metodi del servizio che servivano restano — li compone
`save_composition` dentro una transazione sola (ADR-061).

## Emendamento 2026-09-19 (bis) — la sessione guarda un esercizio per volta

La pagina della sessione non elenca più tutti gli esercizi con un campo
ciascuno: mette a fuoco **un esercizio**, e la prova si scrive da un tastierino
agganciato in basso. Due scelte che restano, entrambe senza toccare lo schema:

- **Rinunciare a una prova non si persiste.** «Conta la migliore» rende
  legittimo fermarsi alla seconda di tre, e il modello lo reggeva già: una prova
  vuota non è uno zero (`ExamAttempt.recompute_scores`) e la chiusura non
  pretende tutte le caselle piene (`ExamService.complete_attempt`). Rinunciare è
  quindi *andare avanti*: un indirizzo (`?at=`), non una colonna `skipped`. Una
  colonna avrebbe chiesto una migration e introdotto un terzo stato della prova
  — scritta, vuota, rinunciata — che nessun calcolo distingue dal secondo.
- **Il fuoco riparte dall'ultimo esercizio che ha un risultato**, non dal primo
  con una casella vuota: altrimenti la prova a cui si è rinunciato richiamerebbe
  indietro l'esaminatore a ogni ricarica. La regola vive in
  `models/exam/session_view.py`, sola lettura, ed è provata in
  `tests/new/integration/test_exam_session_page.py`.

L'esito resta netto e deciso dall'esaminatore: i due pulsanti stanno nel
riepilogo, e la conferma è un foglio, non il `confirm()` del browser.

## Riferimenti

- ADR-041 — il ruolo di esaminatore, concedibile e ortogonale
- ADR-031 — i tre layer di gating
- ADR-028 — allowlist endpoint in produzione
- ADR-025 — traduzione di `IntegrityError` in eccezioni di dominio
- `docs/usecases/esami.md` — i sette journey
- File correlati: `models/exam/models.py`, `models/exam/request_models.py`,
  `models/exam/request_service.py`, `models/exam/services.py`,
  `models/exam/events.py`, `routes/exam/`,
  `migrations/20260816_exam_schema_rework.py`,
  `migrations/20260817_add_exam_request_tables.py`
