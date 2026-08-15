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

Il punteggio massimo è **per-esame**: lo stesso drill può valere 10 in un esame
e 15 in un altro. Metterlo su `Challenge` lo renderebbe globale, e obbligherebbe
a toccare il catalogo dei drill per tarare un esame.

`NULL` significa pass/fail: vale 1 punto se superato, 0 altrimenti. Obbligatorio
se il drill non è pass/fail, vietato se lo è.

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

`Challenge` resta **senza `name` e senza `max_score`**, in disallineamento con
`SPECIFICHE.md` §Challenge («È identificata da un nome. Ha un punteggio minimo e
massimo»). È una scelta consapevole — `max_score` è per-esame, e il nome è un
lavoro sul catalogo drill che non appartiene a questo dominio — ma il costo si
vede: il catalogo mostra la descrizione troncata a 50 caratteri
(`Challenge.get_display_name()`) al posto di un nome, e le schermate d'esame
mostrano il punteggio senza fondoscala.

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
