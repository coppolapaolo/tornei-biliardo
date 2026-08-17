# ADR-045 Niente WAL: SQLite sta su storage di rete

**Data**: 2026-08-17
**Stato**: Accepted
**Decisori**: Paolo Coppola

## Contesto

Il DB di produzione si è corrotto due volte — `database disk image is
malformed` — il **2026-06-10** e il **2026-08-17**. Entrambe le volte con
traffico quasi nullo.

Dal 2026-02-09 (commit `3b56b6bf`, "security: add security headers, **WAL
mode**, health check, cache busting…") ogni connessione SQLite eseguiva:

```python
cursor.execute("PRAGMA journal_mode=WAL")
```

In WAL i processi non si coordinano soltanto con i lock sul file: condividono
un indice del write-ahead log in un file `-shm` mappato in **memoria condivisa
via mmap**. Su NFS — lo storage di PythonAnywhere — quella mappatura non è
coerente fra processi: web app e scheduled task possono vedere due versioni
diverse dell'indice e leggere pagine che non corrispondono al contenuto reale.
La documentazione SQLite è esplicita: *WAL does not work over a network
filesystem*.

Due dettagli hanno reso il guasto difficile da inquadrare:

1. **È reversibile.** Quando cade l'ultima connessione, SQLite fa il checkpoint
   e butta lo `-shm`, che viene ricostruito da zero: l'errore sparisce con un
   semplice reload. Sembra una corruzione che si auto-ripara — non esiste — e
   invece i dati non erano mai stati toccati.
2. **Non è un problema di carico.** `utils/activity.py` ha un throttle di 60
   minuti, quindi la web app scrive pochissimo, e l'unico altro scrittore è
   `send_match_reminders.py`, orario. Un guasto da contesa avrebbe una firma
   statistica (peggiora nelle ore di punta); qui bastava che due processi si
   sfiorassero.

La diagnosi del 2026-06-10, registrata in `CLAUDE.md`, attribuiva la corruzione
alle sole **scritture concorrenti da console**, e la contromisura era
procedurale (disabilitare la web app prima di lanciare script). Era una causa
plausibile ma incompleta: il 2026-08-17 il DB si è corrotto senza che nessuno
avesse lanciato niente dalla console.

Il 2026-08-17, con la web app disabilitata, `PRAGMA integrity_check` è
risultato `ok` **sia prima sia dopo** il checkpoint del WAL (395 KB) nel file
principale — la prova che la corruzione viveva interamente nello strato di
coordinamento e mai nei dati.

## Decisione

**Rimuovere `PRAGMA journal_mode=WAL`**, senza sostituirlo con nulla: un file
SQLite nuovo nasce già con un rollback journal, che è il default sicuro.

Contestualmente si aggiunge `PRAGMA busy_timeout` (5000 ms), che non c'era: il
default di SQLite è 0, quindi la prima contesa di lock diventava subito
`database is locked`. Con il journal classico i lock su NFS sono più lenti, ma
sono **onesti**: al peggio si aspetta o si prende un errore ritentabile, invece
di leggere silenziosamente dati incoerenti.

Il valore di `journal_mode` è **persistito dentro il file `.db`**, quindi
rimuovere la riga non basta per un DB già convertito: sul file di produzione è
stato eseguito una tantum `PRAGMA journal_mode=DELETE` (2026-08-17, con la web
app Disabled).

## Alternative Considerate

### Alternativa 1: WAL condizionale sull'ambiente

**Descrizione**: mantenere il WAL in sviluppo e nei test, disattivarlo solo
quando `FLASK_ENV=production`.

- **Pro**:
  - Conserva il beneficio del WAL dove il filesystem lo regge.
- **Contro**:
  - **Fragile nel modo peggiore.** Negli scheduled task e nelle console
    `FLASK_ENV` non è sempre presente: è esattamente ciò che ha reso muto il
    recupero password per cinque settimane nell'incidente `ENCRYPTION_KEY` del
    2026-06-25. Basterebbe *un solo* processo che non vede la variabile per
    riconvertire il file in WAL, in silenzio e per tutti.
  - Il beneficio difeso è inesistente (vedi sotto).

### Alternativa 2: lasciare il WAL e presidiare per procedura

**Descrizione**: tenere il WAL e affidarsi alla regola "web app Disabled prima
di ogni script".

- **Pro**:
  - Nessuna modifica al codice.
- **Contro**:
  - È la contromisura adottata a giugno, e il 2026-08-17 ha fallito: la
    corruzione è arrivata senza alcuno script da console.
  - Una regola che dipende dalla memoria di chi opera non protegge dai processi
    automatici, che sono la maggioranza degli scrittori.

### Alternativa 3: migrare a PostgreSQL / MySQL

**Descrizione**: togliere SQLite dalla produzione.

- **Pro**:
  - Elimina in radice tutta la classe di problemi (lock su NFS, backup a caldo,
    scritture concorrenti).
- **Contro**:
  - Costo e portata fuori scala rispetto all'incidente da chiudere oggi.
  - Resta l'opzione giusta se il traffico cresce; questa decisione non la
    preclude.

## Conseguenze

### Positive

- Sparisce la causa di due incidenti di produzione su due mesi.
- Nessuna condizione da valutare a runtime: non esiste un ambiente in cui il
  fix possa degradare in silenzio.
- `busy_timeout` trasforma le contese di lock da errore immediato ad attesa
  breve.

### Negative

- Si perde la concorrenza lettori/scrittore del WAL. In pratica: **niente**.
  Nei test è sempre stata inerte (la suite gira su `sqlite:///:memory:`, dove
  `journal_mode` è sempre `memory`); in sviluppo c'è un processo solo, e il DB
  locale sta dentro Google Drive, che è anch'esso un filesystem sincronizzato
  con gli stessi problemi.
- Con il journal classico uno scrittore blocca i lettori per la durata della
  transazione. Le transazioni di questa app sono brevi e il traffico è basso.

### Rischi

- **Un DB già in WAL resta in WAL**: il listener non riconverte. Farlo a ogni
  connessione richiederebbe un lock esclusivo e potrebbe fallire in silenzio,
  quindi si è preferito l'intervento una tantum. Se un domani si ripristina un
  backup prodotto quando il WAL era attivo, verificare
  `PRAGMA journal_mode` prima di rimetterlo in servizio.
- Il WAL può tornare da un'altra strada (config, `SQLALCHEMY_ENGINE_OPTIONS`,
  un secondo listener). Per questo il presidio è **comportamentale** e non
  testuale: apre una connessione vera su un DB su file e legge il PRAGMA.

## Note Implementative

`models/base.py`:

```python
SQLITE_BUSY_TIMEOUT_MS = 5000


@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
        cursor.close()
```

Presidio: `tests/new/unit/test_sqlite_pragmas.py`. Il test usa un DB **su
file** (`tmp_path`) e non quello in memoria della suite, perché è l'unico
contesto in cui `journal_mode` significa qualcosa.

Procedura eseguita sul DB di produzione il 2026-08-17 (web app Disabled):

```bash
cp instance/billiard_campionato.db* ~/safe/          # reperto, prima di tutto
sqlite3 instance/billiard_campionato.db "PRAGMA integrity_check;"   # ok
sqlite3 instance/billiard_campionato.db "PRAGMA journal_mode=DELETE;"  # delete
sqlite3 instance/billiard_campionato.db "PRAGMA integrity_check;"   # ok ← il test vero
```

Il secondo `integrity_check` è quello che conta: è dopo il checkpoint, cioè
dopo che il WAL è stato fuso nel file principale.

## Riferimenti

- [SQLite — Write-Ahead Logging, §"How WAL Works"](https://www.sqlite.org/wal.html)
  («WAL does not work over a network filesystem»)
- [SQLite — `PRAGMA journal_mode`](https://www.sqlite.org/pragma.html#pragma_journal_mode)
- Incidente 2026-06-25 (`ENCRYPTION_KEY` assente negli scheduled task): stessa
  classe di guasto, una condizione d'ambiente che degrada senza sintomi
- File correlati: `models/base.py`, `tests/new/unit/test_sqlite_pragmas.py`,
  `scripts/backup_db.py`
