# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Quick Reference

### Essential Commands
```bash
# Start development server
python app.py

# Run all tests (use -n 4 for integration to avoid SQLite deadlocks)
pytest tests/new/ -n 4

# Run specific test types
pytest tests/new/unit/ -n auto          # Unit tests: -n auto OK
pytest tests/new/integration/ -n 4      # Integration: MUST use -n 4 (SQLite concurrency)

# Run single test file
pytest tests/new/unit/test_specific.py -v -n auto

# Debug single test (no parallel, with output)
pytest tests/new/unit/test_file.py::test_name -v -s

# Frontend headless tests (jsdom, Node — gamification badge/anti-invasività)
cd tests/frontend && npm install && npm test   # run after editing JS under static/js/ that has a suite here (list: package.json `test`)

# Type check (MANDATORY before commits)
pyright

# Format code
black . && flake8

# Internationalization (i18n) — NON copiare i comandi a memoria: invoca la
# skill `translate`. I flag obbligatori (--ignore-dirs, --ignore-obsolete) e il
# divieto di usare msgfmt al posto di pybabel stanno lì.

# Documentation
python scripts/generate_schema_docs.py          # Regenerate DB schema docs
```

### CI/CD & Deployment

**Production URL**: https://www.torneibiliardo.it

Le quattro cose che devono essere note **sempre**, non solo quando si deploya. Il
resto — i job della CI, la procedura manuale PythonAnywhere, le env negli
script da console, l'ordine degli import, gli scheduled task, GlitchTip, la
convenzione dry-run degli script sui dati storici — sta nella skill **`deploy`**
(`.claude/skills/deploy/SKILL.md`), che si carica quando serve.

> ⚠️ **1. Il merge su `main` NON deploya il codice, e la CI non tocca la
> produzione.** Il codice nuovo arriva su PythonAnywhere quando gira lo
> scheduled task giornaliero `scripts/auto_deploy.py`, che fa pull, dipendenze,
> migration e reload: fra il merge e la produzione può passare fino a **un
> giorno**. Fino al 2026-09-14 un job `deploy` della CI faceva un reload a ogni
> merge: non portava codice, e riavviare l'app sotto gli utenti costava errori
> 5xx — con tre merge ravvicinati i reload si sovrapponevano. **Non
> rimetterlo.**
>
> Le migration pendenti le applica da solo `auto_deploy.py` al giro successivo.
> Quindi dopo un merge **non c'è nulla da ricordare all'utente**: niente
> promemoria sul deploy, niente istruzioni su Disabled/Enabled, a meno che non
> sia lui a chiedere di andare in produzione subito.

**⚠️ 2. Branch protection su `main` (dal 2026-06)**: `main` è protetto e
`enforce_admins=true` — **niente push diretti, neanche da admin** (`git push
origin main` → `protected branch hook declined`). Ogni modifica passa da una PR
e il merge è bloccato finché `test-and-typecheck` non è verde.

```bash
git checkout -b claude/descrizione   # branch di lavoro
# ... commit ...
git push -u origin claude/descrizione
gh pr create --title "fix: descrizione in italiano"   # il prefisso è obbligatorio
# attendi che la CI sia verde, poi merge (il codice va in produzione dopo, vedi sopra)
```

Una trappola: una **PR con base diversa da `main` non fa girare nessun check** e
resta bloccata per sempre — le PR impilate vanno riportate su `main`. Gli
status check richiesti sono due, `test-and-typecheck` e `pr-title` (vedi il
punto 4).

`test-and-typecheck` parte sempre, ma su una PR di **sola documentazione**
(Markdown, testo, `docs/` senza sorgenti Python) salta test e pyright e chiude
in pochi secondi: il passo «Decide what to run» lo scrive nel log. Un `.py`
toccato per un docstring, un template o uno YAML della guida contano come
codice, e allora dura i soliti 4-5 minuti.

> ⚠️ **3. Non rimettere `PRAGMA journal_mode=WAL`** in `models/base.py`, nemmeno
> condizionato a `FLASK_ENV`: su NFS la memoria condivisa del WAL non è coerente
> fra processi e corrompe il DB (due incidenti `database disk image is
> malformed`). Una env var assente in un task lo riattiverebbe in silenzio per
> tutti, ed è persistito dentro il file `.db`. Rimosso il 2026-08-17
> (**ADR-045**), presidio in `tests/new/unit/test_sqlite_pragmas.py`.
>
> Regola operativa correlata: ogni script/comando console che **scrive** sul DB
> di produzione va eseguito con la web app su **Disabled**.

> ⚠️ **4. Il titolo della PR decide il numero di versione.** Le PR si uniscono
> in **squash**, quindi il titolo diventa il messaggio di commit su `main`, e da
> lì [release-please](.github/workflows/release-please.yml) calcola la versione
> mostrata nel footer (`Config.VERSION`). Il prefisso è **obbligatorio** — il
> job `pr-title` blocca la PR senza — mentre la descrizione resta in italiano:
>
> | Titolo | Effetto |
> |---|---|
> | `fix: la X va all'ultimo iscritto` | 1.0.0 → 1.0.**1** |
> | `feat: referto TPA sui match singoli` | 1.0.1 → 1.**1**.0 |
> | `feat!: nuovo schema dei rack` | 1.1.0 → **2**.0.0 |
> | `chore:` `docs:` `test:` `ci:` `refactor:` `style:` `build:` | nessuno |
>
> Unita la PR, il bot apre — o aggiorna — una PR **«chore(main): release
> X.Y.Z»** che porta il numero in `config.py` e la voce in `docs/RELEASES.md`.
> È unendo *quella* che si rilascia: nasce il tag `vX.Y.Z` e il numero nuovo
> parte verso la produzione col solito `auto_deploy.py`. Finché non la unisci,
> il footer mostra la versione precedente — ed è corretto, perché è quella che
> sta girando.
>
> ⚠️ **Niente parentesi annidate nel corpo del commit.** Il parser
> Conventional Commits di release-please legge una `(` come apertura di uno
> *scope* e si aspetta la chiusura: `matchMedia('(min-width: 992px)')` in un
> corpo lo fa fallire con «unexpected token '(' … valid tokens [)]». Il commit
> viene allora **saltato in silenzio** — il workflow resta verde e la PR di
> rilascio «remained the same» — quindi quella PR non compare in
> `docs/RELEASES.md` e, se fosse l'unica `feat:`, non alzerebbe la versione.
> Successo il 2026-08-30 con la #287. Il rimedio è a valle e costa una PR:
> il commit su `main` non si riscrive. **Quando un corpo deve citare del
> codice con parentesi dentro parentesi, riscrivilo** — «`matchMedia` sul
> breakpoint lg» dice la stessa cosa. Il titolo, dove le parentesi servono
> davvero, non è mai un problema: `(#287)` lo mette GitHub e il parser lo
> conosce.

> `CHANGELOG.md` **resta scritto a mano**: è il racconto. `docs/RELEASES.md` è
> l'indice generato. Non scambiare i due, e non modificare `Config.VERSION` o
> `.release-please-manifest.json` a mano (presidio:
> `tests/new/unit/test_version_single_source.py`).

---

## Things to Remember

Before writing any code:

1. **State how you will verify** this change works (test, bash command, browser check, etc.)
2. **Write the test or verification step first**
3. **Then implement the code**
4. **Run verification and iterate** until it passes

### 0. Prima di tutto: la specifica, se c'è

Se stai per toccare una **regola di dominio** — punteggi, classifiche,
abbinamenti, criteri di qualificazione, cicli di vita — **apri prima
[`docs/reference/SPECIFICHE.md`](docs/reference/SPECIFICHE.md) e cerca la
regola.** Non è una formalità: è un difetto già capitato due volte, con lo
stesso identico meccanismo.

1. La specifica fissa una regola numerica.
2. L'implementazione ne scrive un'altra, e nessuno se ne accorge perché nessun
   test confronta il codice con la specifica: i test confrontano il codice con
   sé stesso.
3. Una code review trova **due parti del codice incoerenti fra loro** e le
   allinea — alla parte sbagliata — aggiungendo un test di regressione che da
   quel momento **difende la deviazione**. Chi provasse a correggere vedrebbe
   un test rosso, motivato bene, e si fermerebbe.

Le due volte in cui è successo, entrambe scoperte il 2026-08-23:

* **quanto vale la X in classifica** (SPECIFICHE.md, «Strategia di abbinamento»: una vittoria
  e **zero** differenza rack; il codice dava +distanza). **Corretto** lo stesso
  giorno in `round_creation.py`: la X nasce con `player1_score = 0`. Notevole
  che un terzo punto del codice — `validators._validate_rack_system`, che
  vieta il bye semplice col sistema RACK «perché il giocatore con bye
  riceverebbe 0 rack» — fosse d'accordo con la specifica da sempre: nessuno
  aveva mai confrontato i tre. **Corretta lo stesso giorno anche la variante
  con challenge** (stessa sezione): la differenza torna a essere il punteggio della
  prova, e il limite `[0, effective_distance]` è passato dal *lettore* del dato
  a chi lo *registra*. Difendersi a valle, scartando il punteggio, equivaleva a
  cancellare la regola che si voleva applicare — vedi
  `tests/new/unit/test_x_replacement_score_scale.py`;
* **a chi passa l'invito ai playoff quando qualcuno rifiuta** (SPECIFICHE.md, «Playoff»: «al
  primo degli esclusi»; il codice non lo trovava mai e la finale partiva con un
  posto vuoto). **Corretta** il 2026-08-23: `evaluate_qualifications(posti=…)`
  sa allargare la finestra oltre `max_participants`, e
  `find_replacement_player` la chiama così. La causa era una domanda sola usata
  per due scopi — «chi entra?» si ferma ai posti, «chi viene dopo?» deve
  guardare oltre — e la lista tagliata conteneva solo giocatori che avevano già
  una qualificazione, declinante compreso.

Che un test difenda la deviazione va **verificato, non assunto**: un test può
passare in entrambi i mondi (`test_declined_player_not_repicked` ha quattro
giocatori per quattro posti).

Regole operative, tre:

* **La specifica vince.** Se il codice diverge, o si corregge il codice o si
  emenda la specifica con una nota datata che dice perché. Non si lascia la
  divergenza muta.
* **Ogni regola numerica va in
  [`tests/new/unit/test_specifiche_conformita.py`](tests/new/unit/test_specifiche_conformita.py)**,
  con la citazione della riga nel docstring. È l'unico posto in cui la
  specifica diventa eseguibile.
* **Una divergenza trovata e non ancora corretta si scrive
  `xfail(strict=True)`**, mai si silenzia e mai si adatta il test al codice:
  `strict` accende la suite il giorno in cui qualcuno corregge.

E quando una review trova due punti del codice incoerenti, la domanda giusta
non è «quale allineo all'altro» ma **«cosa dice la specifica»**.

---

## Critical Conventions

### 1. Timezone Handling
The application uses **UTC-based datetime convention** throughout via the `utc_now()` utility.

```python
# ✅ CORRECT
from models.base import utc_now
now = utc_now()

# ❌ WRONG
from datetime import datetime
now = datetime.now()       # Local time, not UTC
now = datetime.utcnow()   # Deprecated in Python 3.12+
```

`utc_now()` uses `datetime.now(timezone.utc).replace(tzinfo=None)` internally — non-deprecated API, but returns naive datetimes compatible with SQLite.

- **Column defaults**: Use `default=utc_now` (no parens — callable reference)
- **Frontend**: Use `|datetime_local` filter to display UTC → **ora di chi legge**
  (`User.timezone`, dedotto dal browser; ripiego su ora italiana per chi non ce
  l'ha). Il fuso lo conosce **solo** `utils/local_time.py`: `resolve_timezone()`
  per il lettore corrente, `resolve_timezone_for_user_id()` per un destinatario
  preciso. Un `ZoneInfo("Europe/Rome")` scritto altrove è un bug (ADR-043).
- **Testo scritto per qualcun altro** (notifiche, promemoria, scheduled task):
  passa `tz=` esplicito. Senza, si formatta nel fuso di chi ha premuto il
  pulsante — o, fuori da una richiesta, in quello di nessuno.

### 2. "Race to N" Terminology (NOT "Best of N")
The application uses **"Race to N"** terminology (Italian: "Al N").

- **"Race to 5"** = First player to WIN 5 racks wins
- **Maximum racks** = (2 × distance) - 1 = 9 racks for race to 5
- **Database field**: `distance` = winning score threshold

```python
# ✅ CORRECT
gara.distance = 5  # Race to 5 (first to 5 racks wins)
gara.is_race_to = True  # "al N": first to N wins; False = exactly N racks

# ❌ WRONG
gara.distance = 9  # This means "race to 9", not "best of 9"
```

### 3. Transaction Management
All service methods that modify database state MUST use `@transactional`:

```python
from models.transaction.manager import transactional

class GaraService:
    @transactional(domain="competition")
    def create_gara(self, campionato_id: int, data: dict) -> Gara:
        gara = Gara(campionato_id=campionato_id, name=data['name'])
        db.session.add(gara)
        return gara  # Commit happens automatically
```

### 4. Soft Delete (User Model)
User model has soft delete with automatic session-level filtering.

```python
# Automatic filtering - excludes is_deleted=True
users = User.query.all()

# Include deleted records (same filter on User, Gara, Campionato:
# models/soft_delete/filter.py)
all_users = db.session.execute(
    select(User).execution_options(include_deleted=True)
).scalars().all()

# ✅ CORRECT - Soft delete preserves relationships
user.anonymize()

# ❌ WRONG - Never hard delete User records
db.session.delete(user)  # Breaks foreign key relationships
```

### 5. Enum Comparisons
```python
# ✅ CORRECT - Use .value
if gara.status == GaraStatus.PLAYING.value:

# ❌ WRONG - Compares to enum object
if gara.status == GaraStatus.PLAYING:
```

### 6. Value Objects (Distance & Score)
Use immutable value objects for distance and score business logic:

```python
from models.match.distance import Distance

# Via factory method
distance = Distance.from_gara(gara)
winning_racks = distance.get_winning_racks()

# Via model property
distance_cfg = match.distance_config
```

**ADR-027 — `Distance` VO is the single source of truth for match scoring.**

In ogni path di scoring/validation/aggregation usa `match.distance_config` o
le property `Match.effective_*`. NON leggere `match.gara.distance` o
`match.gara.is_race_to` direttamente — gli override per turno
(`RoundConfiguration`) verrebbero silenziosamente persi.

```python
# ✅ CORRECT - rispetta override per turno
distance = match.distance_config
if distance.is_race_to_racks:
    winning = distance.get_winning_racks()
else:
    total = match.player1_score + match.player2_score
    if total == distance.racks: ...

# ❌ WRONG - bypassa RoundConfiguration
if match.gara.is_race_to:  # override per turno persi!
    winning = match.gara.distance_config.get_winning_racks()
```

L'unico posto autorizzato a leggere `self.gara.distance`/`is_race_to` sono i
fallback dentro `Match.effective_*` (per restituire il default della gara
quando non c'è override). Vedi `docs/adr/ADR-027-round-level-configuration-enforcement.md`.

### 7-8. Stringhe tradotte e attributi `onclick` nei template

`|tojson` è obbligatorio per ogni stringa tradotta incorporata in JavaScript:
gli apostrofi italiani (`l'avvio`, `l'errore`) altrimenti rompono la stringa JS
e bloccano *tutto* il JavaScript della pagina. Gli attributi `onclick` che lo
usano vogliono apici singoli, e i placeholder `%(nome)s` non vanno usati in
stringhe interpolate da JavaScript.

Regole complete con esempi corretti/sbagliati: **`templates/CLAUDE.md`**, che si
carica da solo quando si lavora sotto `templates/`.

### 9. Sequential Date Validation for Campionato Gare
Gare within a campionato must have dates in chronological order by `number`:

```python
# ✅ CORRECT - Gara 2 after Gara 1
gara1.date = date(2026, 1, 15)  # number=1
gara2.date = date(2026, 1, 22)  # number=2

# ❌ WRONG - Gara 2 before Gara 1 raises ValueError
gara1.date = date(2026, 1, 22)  # number=1
gara2.date = date(2026, 1, 15)  # number=2 → raises ValueError

# Same-day gare are allowed if time is sequential
gara1.date, gara1.time = date(2026, 1, 15), time(14, 0)  # number=1
gara2.date, gara2.time = date(2026, 1, 15), time(18, 0)  # number=2 → OK
```

**Rules**:
- Gara N must have date/time `>=` the gara with highest number `< N`
- Gara N must have date/time `<=` the gara with lowest number `> N`
- Standalone gare (no campionato) have no sequential validation

See `docs/adr/ADR-016-gara-sequential-date-validation.md` for details.

### 10. Migration Naming Convention
New migrations use date-prefixed naming:

```bash
# Create new migration file
touch migrations/20260125_description.py
```

Migration files must:
- Define `migration_name` variable for tracking
- Be idempotent (safe to run multiple times)
- Use `op.execute()` for raw SQL on SQLite

### 11. Email Service (Flask-Mail)
Ogni invio passa da `EmailService` (`models/shared/email_service.py`) — mai SMTP
a mano. Configurazione via env: `MAIL_SERVER`, `MAIL_PORT`, `MAIL_USERNAME`,
`MAIL_PASSWORD`. Vedi `docs/reference/AUTHENTICATION.md`.

### 12. Gamification Frontend Bridge
Gli eventi di dominio diventano toast passando da
`flash_gamification_event` (`models/gamification/frontend_bridge.py`). Tipi di
evento e sistema di animazioni in `docs/reference/GAMIFICATION_V2.md`.

### 13. Production Endpoint Allowlist (ADR-028)
Endpoint visibility in production is gated by an explicit role matrix in `utils/feature_flags.py`. **Endpoint not listed = admin-only in production.** In development (`DEBUG_MODE=true`) and tests (`TESTING=true`) the middleware is pass-through.

**ADR-028 — When you add a new route, decide its visibility explicitly.**

```python
# utils/feature_flags.py
ENDPOINT_ROLES = {
    "main.public_garas_list":     {"anonimo", "player", "director"},  # public
    "dashboard.dashboard":        {"player", "director"},              # logged-in
    "player.inscribe_to_gara":    {"player", "director"},              # logged-in, non admin
    "admin.competition.start_first_round": {"director"},               # director only
    # NOT in matrix → admin-only in prod by default
}
```

Steps when adding a route:

1. **Decide who should see it** in production. Roles: `anonimo`, `player`, `director`. Admin always sees everything.
2. **Add an entry** to `ENDPOINT_ROLES` with the role set, OR leave it out if it should stay admin-only for now.
3. **If the route appears in a menu/link**, wrap with `{% if feature_visible('endpoint.name') %}…{% endif %}` (vedi `templates/base.html`).
4. **Verify**: the test `tests/new/integration/test_endpoint_allowlist.py::test_endpoint_roles_names_are_real` catches typos in endpoint names.

A 404 reported by a real user that should NOT be 404 is evidence of a missing matrix entry. Find the real endpoint name (`app.url_map`) and add it.

See `docs/adr/ADR-028-production-endpoint-allowlist.md` (incl. **Open Items**) for full design and follow-up work.

### 14. Naming Conventions
I termini di dominio (`campionato`, `gara`, `iscrizione`, `partita`, `turno`)
sono in **italiano** con **plurale italiano**. Mai anglicizzare con `-s`.

```python
# ✅ CORRECT
campionati = Campionato.query.all()
def gare_attive(): ...
template = "campionati_list.html"

# ❌ WRONG (anti-pattern: italian root + english -s)
campionatos = ...
def garas_attive(): ...
template = "campionatos_list.html"
```

I suffissi tecnici/pattern restano in inglese (`Service`, `Builder`,
`Strategy`, ecc.). Le classi `Service` usano il singolare del modello
(es. `GaraService`, non `GareService`; `TournamentService` è un'eccezione storica).

Vedi `docs/reference/NAMING_CONVENTIONS.md` per regole complete (URL,
DB columns, test, eccezioni storiche come `Match`).

---

## Database

- **Development**: SQLite (`instance/billiard_campionato.db`)
- **Production**: SQLite su PythonAnywhere
  (`/home/paolocoppola/mysite/instance/billiard_campionato.db`)

**Matchmaking**: sia la strategia Random Anti-Rematch sia Amalfi (caso pari, vedi
ADR-029) usano `networkx` per il maximum (cardinality / weighted) matching sul
grafo anti-rematch. Non reimplementare algoritmi su grafi — usa `nx`, è già in
`requirements.txt`.

---

## Development Guidelines

### Type Safety (MANDATORY)
- Run `pyright` before every commit - maintain 0 errors
- Pyright config (`pyrightconfig.json`) disables `reportCallIssue` due to SQLAlchemy mixin inheritance issues (pyright doesn't recognize that `db.Model` generates constructors accepting column names as kwargs)

### Testing Requirements
- All new features MUST have tests in `tests/new/`
- Test isolation: use `db_session.get()` not `refresh()`
- Unit tests: `-n auto` OK; Integration tests: `-n 4` (SQLite concurrency)
- **EventBus isolation**: Never clear `EventBus._handlers = {}` in tests - preserve and restore:
  ```python
  @pytest.fixture(autouse=True)
  def preserve_handlers():
      original = {k: list(v) for k, v in EventBus._handlers.items()}
      yield
      EventBus._handlers = original
  ```

---

## Common Mistakes to Avoid

Qui stanno gli errori trasversali. Quelli di un solo dominio stanno nel
`CLAUDE.md` della sua cartella, sezione «Errori già commessi», che si carica
lavorando lì.

| Mistake | Correct Approach |
|---------|------------------|
| Rimettere `WTF_CSRF_SSL_STRICT` (o fidarsi del default di Flask-WTF) | Su HTTPS pretende anche l'header `Referer`, che browser con la privacy stretta, webview e proxy tolgono: per quegli utenti **ogni** POST è 400 — login compreso, quindi restano fuori. La difesa è il token + `SameSite=Lax` + il controllo di `Origin` in `app.py` (ADR-050) |
| Lasciare a Flask-WTF il default di `WTF_CSRF_TIME_LIMIT` (un'ora) | Si conta dalla generazione della pagina, non dall'ultimo uso: sul telefono il browser non si chiude, la scheda di ieri sera ha il cookie buono e il token scaduto → 400 «sessione scaduta» al primo invio. `None` lega il token alla sessione (ADR-050, emendamento) |
| Modifica di sicurezza trasversale (CSRF, cookie, header) dentro una PR che parla d'altro | Il CSRF è nato il 2026-08-16 **dentro la PR #107, «drill negli esami»**: quando la settimana dopo sono piovuti i 400 al login, nessuno li ha collegati a un cambiamento del sito — nel diario dei rilasci era invisibile. Una modifica così viaggia in una PR dedicata, col suo nome, i default esaminati uno a uno (qui: referrer obbligatorio e token a scadenza oraria, entrambi sbagliati per noi) e un occhio ai log nei giorni successivi (ADR-050) |
| `font-size: 13px` in un CSS o in uno `style=` | `calc(13 * var(--c7-tpx))`: in pixel il testo non segue «Dimensioni testo» dell'iPhone, e fino al 24/10/2026 chi lo alzava doveva zoomare. `--c7-tpx-lento` per titoli e cifre da 24px in su e comandi fitti (tetto più basso). Alla misura normale valgono un pixel esatto. Presidio `test_testo_segue_il_telefono.py`, regole in `UI_CONVENTIONS.md` |
| Cercare *tutte* le partite di un giocatore nella sola tabella `match` | Le sfide individuali stanno su `individual_match`: sono due tabelle. `PlayerHistoryService.get_unified_match_history` le unisce nella stessa forma — interrogarne una sola non dà errore, mostra meno partite di quelle giocate. **Ci sono ricascati i due profili** (proprio e altrui) fino al 2026-08-20: query sul solo `match` e conteggio del solo `CLOSED_UNILATERALLY`, quindi una sfida individuale non compariva né fra le partite recenti né nelle statistiche, mentre lo storico completo la mostrava. Il profilo altrui filtra le voci con `PlayerHistoryService.filter_visible_entries`, che guarda la **provenienza**: gli id delle due tabelle si sovrappongono, e nascondere la partita di gara 7 nascondeva anche la sfida 7 |
| Decidere con un filtro proprio quali sfide individuali contano in una statistica | `models/certificazione.py` (ADR-083): `livello_di_sfida`, `sfide_della_vista` in SQL, `sfida_conta_per_elo`. Fino al 2026-10-17 TPA e runout contavano anche sfide annullate o mai firmate, e il ricalcolo dell'ELO globale contava i pareggi che l'evento saltava: quattro regole per la stessa domanda |
| `Match.status == CLOSED_UNILATERALLY` per «partita giocata» | `MatchStatus.finished_values()`: `CONFIRMED_BY_BOTH` è la chiusura **dei due giocatori**, ed è giocata quanto l'altra. Filtrare solo la prima è il bug che teneva monco lo storico |
| `RoundConfiguration` salvato solo in `localStorage` | API endpoint `POST /admin/gara/<id>/round-config/<n>` (ADR-027) |
| `match.status in ["completed", "validated"]` (letterale raw) | `MatchStatus.is_finished(match.status)` / `is_active(...)` (typo-safe) |
| Credere che `"validated"` sia la validazione del direttore | È il contrario: `CONFIRMED_BY_BOTH` (valore `"validated"`) = chiusa dai **giocatori** con doppia conferma; `CLOSED_UNILATERALLY` (valore `"completed"`) = chiusa dal direttore/forfait/bye. I nomi dei membri sono stati corretti il 2026-08-17, **i valori persistiti no** |
| `user.role == "director"` (o `"admin"`/`"player"`/`"guest"` letterali) | `UserRole.DIRECTOR.value` ecc. da `models/user/role_enum.py` — mai letterali per valori di dominio |
| Interfaccia scritta "a memoria" senza aprire il prototipo | Invoca la skill `ui-7c`: la schermata di riferimento e' in `docs/redesign-7c/Redesign Mobile.dc.html` |
| Nuova impostazione da env scritta nel corpo di `Config` | Va in `Config.environment_settings()` — il corpo della classe si esegue all'import e congela il valore: per gli scheduled task, che caricano le env *dopo*, sarebbe sbagliato per sempre |
| `from app import create_app` in cima a uno script con `prod_env` | `prod_env.bootstrap_and_create_app()` — importa l'app **dopo** aver letto le env dal WSGI (presidio: `test_script_import_order.py`) |
| Migration che solleva su una condizione permanente dell'ambiente | Deve riuscire (no-op dichiarato) o rimediare: se solleva, il runner non la marca applicata e `auto_deploy` la ritenta ogni notte, disabilitando la web app per niente |
| Derivare `ExamChallenge.max_score` da `challenge.max_score` | Sono due cose diverse: il primo è **quanto pesa in quell'esame**, il secondo **quanto vale al massimo la prova**. Derivarlo rende impossibile far pesare lo stesso esercizio in due modi (ADR-042 + emendamento 2026-08-18). Entrambi facoltativi; `challenge.name` non esiste, il nome mostrato è `get_display_name()` |
| `datetime.strptime`/`fromisoformat` su un `datetime-local` | `utils.local_time.parse_local_datetime` — l'input arriva nell'**ora di chi scrive**, il DB tiene naive-UTC: salvarlo grezzo sposta l'orario, in silenzio (ADR-043) |
| `ZoneInfo("Europe/Rome")` scritto in un filtro o in una route | `resolve_timezone()` da `utils.local_time` — il fuso è quello del lettore, e un solo modulo lo sa (ADR-043) |
| Orario formattato una volta per N destinatari | Se il testo contiene un'ora, si compone **per destinatario** col suo `tz`: due giocatori in due fusi leggono due frasi diverse |
| `title=_("...")`, `message=f"..."` o un letterale passati a una notifica | Si passano **da comporre**: `lazy_gettext` o una funzione senza argomenti, che `create_notification` risolve nella lingua di chi **riceve** (`User.language`). Un `_()` sul posto traduce nella lingua di chi preme il pulsante, e in sviluppo non si vede mai: chi preme e chi riceve parlano italiano entrambi. Presidio in `test_notifiche_testi_non_tradotti_da_chi_preme.py` (ADR-062) |
| Disciplina come stringa scritta a mano (`"palla_8"`, `"8_ball"`) | `Discipline.*.value` da `models/status_enum.py` — **unico** vocabolario; per dati storici/esterni `Discipline.normalize()` (torna `None` sull'ignoto). Il nome mostrato è `display_name`, tradotto. Presidiato da `test_discipline_single_vocabulary.py` |
| Scegliere una dipendenza, o una versione di Python per la CI, senza guardare il Python della **produzione** | `.python-version` è il Python di PythonAnywhere (oggi 3.12, dal 27/09/2026), e la CI lo legge da lì. Fino al 27/09/2026 CI, sviluppo, produzione e pyright avevano quattro versioni diverse: SQLAlchemy 2.1 (che vuole 3.11) avrebbe passato la CI e fatto fallire `auto_deploy` ogni notte. Si cambia il file **dopo** aver migrato la produzione, mai prima (`test_python_di_produzione.py`) |
| Scheduled task PythonAnywhere lanciato con `python script.py` | `venv/bin/python script.py`: `python` nudo è l'interprete **di sistema** — non ha i pacchetti del progetto, ha quelli di PythonAnywhere (da cui il guasto `pyOpenSSL`), e un `pip install` da lì fallisce per permessi (incidente 2026-08-17, `/aiuto` in 500 per due giorni) |
| `gara.matchmaking_strategy == "random"`, `campionato_type == "amalfi"` | `MatchmakingStrategy.*.value` da `models/matchmaking/configuration.py`, iniettato nei template. Esiste un **secondo enum omonimo** in `models/competition/validators.py` (`elimination`/`double_ko`) che non sta mai in colonna: citarlo dà un confronto sempre falso, senza errori. Presidiato da `test_match_status_no_raw_literals.py`, che vede anche `campionato_type\|lower == '...'` |
| Funzione visibile all'utente cambiata senza toccare `/aiuto` | Invoca la skill `help-docs`: la guida non si rompe, **invecchia** — continua a descrivere un'app che non esiste più. Contenuti in `help_content/`, schermate rigenerate da `scripts/help_docs/` |
| Categoria del giocatore cercata su `User` o in `models/rating/` | Vive su `Inscription.categoria_id`, ed è **per gara**: `models/categoria/`. `PlayerCategory` e l'enum `CategoryLevel` A/B/C/D sono stati rimossi — erano globali per utente e mai scritti da nessuno |
| Leggere una regola della partita dalla gara (`match.gara.break_rule`, la categoria dall'iscrizione) per una partita già nata | Le regole si **fissano sulla partita** quando nasce (ADR-075): `match.effective_*`, `match.categories_snapshot` via `RatingEligibility`. Un cambio della gara vale dal turno successivo; rileggere la gara lo renderebbe retroattivo. Le correzioni di dati scritti male passano da `regole_fissate.correggi_categoria` e dagli script `set_gara_*`, che toccano anche le partite |
| `DROP TABLE` di una tabella referenziata da una FK, anche vuota | Con `PRAGMA foreign_keys=ON` (`models/base.py:104`) **ogni INSERT sulla tabella figlia fallisce**, pure con la FK a NULL. E la colonna non si toglie: SQLite rifiuta `DROP COLUMN` su una colonna citata in una chiave esterna, anche sulla 3.51. Resta il no-op dichiarato (vedi `migrations/20260819`) |
| Migration che crea una tabella senza `created_at`/`updated_at` | `BaseModel` le aggiunge a ogni entità: l'ORM fallisce con «no such column» e la funzione muore in silenzio in produzione (incidente `categoria`, 2026-08-19). I test di comportamento non lo vedono — creano lo schema con `db.create_all()` — quindi il presidio legge il **testo** delle migration: `tests/new/unit/test_migrations_timestamps.py` |
| Correggere la migration che ha creato la tabella sbagliata | Non serve a niente: è già marcata applicata e non gira più, e comunque è `CREATE TABLE IF NOT EXISTS`. Un DB già storto si ripara solo con una **migration nuova** che aggiunga le colonne (`20260820_timestamps_basemodel.py`) |
| Schermata della guida ritoccata a mano in un editor | Le immagini si **generano** dall'app (`capture_screenshots.py`) sul dataset di `seed_demo.py`: una ritoccata sopravvive al cambio di interfaccia e diventa una bugia permanente |
| Dare per scontato che una partita abbia sempre un vincitore | In «esattamente N rack» con **N pari** il pareggio esiste: a 3-3 la partita è chiusa e `winner_id` resta `None`. Chi somma le vittorie senza contemplarlo perde una riga di classifica; chi scrive «ha vinto X» in una notifica scrive una frase falsa. Con N dispari non può capitare, ed è per questo che il caso passa inosservato (`test_stagione_e2e_risultati.py`) |
| Contare su un `if` applicativo per l'unicità di una riga | `UserMergeService` decide **dallo schema** se spostare una colonna riga per riga o in blocco (`_is_constrained`): un'unicità che vive solo in Python — com'era «un giocatore, un'iscrizione per gara», dentro `inscribe_user` — gli è invisibile, e l'`UPDATE` di massa la viola in silenzio. È così che unendo due account il giocatore restava iscritto **due volte** alla stessa gara, una con la categoria del direttore e una senza (produzione, gara 39, settembre 2026). Se una tabella ha un'unicità logica, si dichiara con un `UniqueConstraint`. E il vincolo da solo non basta: la dedup generica tiene la riga del **destinatario**, quindi dove i dati vanno conservati serve una fusione esplicita (`models/competition/inscription_dedup.py`) |
| Creare una scheda in casa dell'allievo per «assegnargliela» | `AssegnazioneService.proponi`: la scheda **nasce quando lui accetta**, e nasce sua — proprietario lui, che la cambia e decide chi la legge. Si propone **solo a chi ti ha già aperto una scheda**, e il permesso di lettura è una casella del suo modulo, non un effetto della proposta: senza spunta la scheda nasce lo stesso e non legge nessuno (ADR-071) |
| Tenere in **memoria del processo** un dato che un'altra richiesta deve rileggere (dizionario a livello di modulo, cache «globale») | In produzione la web app sono **tre processi** uWSGI (pid diversi nel server log): ogni processo ha la sua copia e le richieste si distribuiscono a caso. L'archivio degli eventi live ha vissuto così per sette mesi facendone arrivare uno su tre, e in sviluppo — un processo solo — non si vedeva mai. Ciò che deve sopravvivere alla richiesta va nel DB (ADR-057, `live_event`); una cache in memoria è ammessa solo se perderla costa una query, non un dato |

---

## Additional Documentation

Puntatori: il dettaglio sta nel documento, qui c'è solo a cosa serve.

- **[docs/reference/SPECIFICHE.md](docs/reference/SPECIFICHE.md)**: requisiti completi della piattaforma. **Si apre prima di toccare una regola di dominio** (vedi sezione 0)
- **[docs/reference/DATABASE_SCHEMA.md](docs/reference/DATABASE_SCHEMA.md)**: schema DB autogenerato — si rigenera con `python scripts/generate_schema_docs.py`
- **[docs/reference/AUTHENTICATION.md](docs/reference/AUTHENTICATION.md)**: verifica email, reset password, Flask-Mail
- **[docs/reference/GAMIFICATION_V2.md](docs/reference/GAMIFICATION_V2.md)**: frontend bridge, toast, mascotte
- **[docs/reference/UI_CONVENTIONS.md](docs/reference/UI_CONVENTIONS.md)**: icone, colori, decisioni di design
- **[docs/reference/NAMING_CONVENTIONS.md](docs/reference/NAMING_CONVENTIONS.md)**: plurali italiani, split italiano/inglese, URL, test, colonne DB
- **[docs/reference/PRODUCTION_INVENTORY.md](docs/reference/PRODUCTION_INVENTORY.md)**: inventario route/UI/permessi, base della matrice ADR-028
- **[docs/usecases/gare.md](docs/usecases/gare.md)** · **[docs/usecases/esami.md](docs/usecases/esami.md)**: flussi di gara; i sette journey degli esami
- **[help_content/](help_content/)**: contenuti di `/aiuto` in YAML (`it/pages/*.yaml` le pagine, `it/hints.yaml` i micro-aiuti, `screenshots.yaml` il manifest). Si aggiorna con la skill `help-docs`; le schermate si **generano**, non si ritoccano
- **CLAUDE.md annidati** (si caricano lavorando in quella cartella): [models/](models/CLAUDE.md) · [routes/](routes/CLAUDE.md) · [tests/](tests/CLAUDE.md) · [templates/](templates/CLAUDE.md) · [models/gamification/](models/gamification/CLAUDE.md) · [models/tpa/](models/tpa/CLAUDE.md) (referto Accu-Stats) · [models/transaction/](models/transaction/CLAUDE.md)

**[Architecture Decision Records](docs/adr/)** — quando serve il *perché* di una scelta:

| ADR | Decisione |
|-----|-----------|
| [027](docs/adr/ADR-027-round-level-configuration-enforcement.md) | override per turno persistiti server-side; `Distance` VO obbligatorio nello scoring |
| [028](docs/adr/ADR-028-production-endpoint-allowlist.md) | allowlist endpoint deny-by-default in produzione, matrice ruoli con bypass admin |
| [038](docs/adr/ADR-038-bracket-persistence.md) | tabellone persistito su `Match`, seat derivato, dimensionamento sugli iscritti effettivi |
| [039](docs/adr/ADR-039-team-separation-in-the-draw.md) | squadre a due livelli; separazione dei compagni come obiettivo lessicografico, non vincolo |
| [040](docs/adr/ADR-040-position-classification-ties.md) | classifica POSITION per bande a pari merito, spareggio **deliberatamente** spento |
| [041](docs/adr/ADR-041-grantable-roles-and-delegation.md) | `RoleGrant` ortogonali a `user.role`; delega a catena per-ruolo; revoca solo admin |
| [042](docs/adr/ADR-042-certified-exam.md) | esame come sequenza di esercizi a esito booleano; `max_score` per-esame **e** per-esercizio |
| [043](docs/adr/ADR-043-reader-timezone.md) | gli orari sono nel fuso di **chi legge**, salvato su `User.timezone`; nessun backfill |
| [044](docs/adr/ADR-044-tpa-scoresheet.md) | referto TPA: punteggio **derivato** dal referto, registro dei comandi unica verità |
| [045](docs/adr/ADR-045-no-wal-on-network-storage.md) | niente `journal_mode=WAL` su NFS; il file `.db` ricorda il journal mode |
| [046](docs/adr/ADR-046-beta-tester-visibility.md) | beta tester = `RoleGrant` che apre tutto **tranne** `@admin_required` |
| [047](docs/adr/ADR-047-classification-system-drives-the-standings.md) | la classifica segue `classification_system`, non `campionato_type` |
| [048](docs/adr/ADR-048-gara-scoped-participant-reassignment.md) | riassegnare la partecipazione a una gara: i fatti si spostano, i derivati si ricalcolano |
| [049](docs/adr/ADR-049-same-category-restores-elo-in-handicap-events.md) | con handicap l'ELO si muove solo fra **stessa categoria**; categorie per competizione |
| [050](docs/adr/ADR-050-csrf-origin-instead-of-referrer.md) | CSRF su `Origin` e non `Referer`; `WTF_CSRF_TIME_LIMIT = None` |
| [051](docs/adr/ADR-051-quick-start-moves-the-acceptance-to-the-end.md) | avvio rapido: partita già in corso, accettazione spostata alla doppia conferma |
| [053](docs/adr/ADR-053-playoff-weight-and-final-ranking-mode.md) | `Gara.weight` con aggregazione per gara; modalità di classifica finale del playoff |
| [054](docs/adr/ADR-054-version-from-pull-request-titles.md) | la versione nasce dai titoli delle PR (Conventional Commits + release-please); `CHANGELOG.md` a mano, `docs/RELEASES.md` generato |
| [055](docs/adr/ADR-055-session-bound-to-credential.md) | la sessione porta un'impronta della credenziale: cambiare password invalida le sessioni aperte |
| [056](docs/adr/ADR-056-apertura-e-runout-sul-segnapunti.md) | acchito, regola di apertura ereditata campionato→gara, runout marcato sul trattino |
| [057](docs/adr/ADR-057-live-events-shared-across-workers.md) | aggiornamenti live su tabella `live_event` condivisa fra i worker; cursore a id; evento atomico col fatto |
| [058](docs/adr/ADR-058-competizione-di-prova.md) | competizione di prova: invisibile per default (filtro di sessione con opt-in), giocatori fittizi cancellati fisicamente, ELO e gamification fuori |
| [059](docs/adr/ADR-059-pagina-gara-del-direttore-per-fasi.md) | la pagina del direttore è la fase in corso: striscia di fase, due template, comando da `comandi.py` |
| [060](docs/adr/ADR-060-tavoli-scelti-in-ogni-stato.md) | i tavoli si scelgono in ogni stato; la lista nuova vale per le assegnazioni successive |
| [061](docs/adr/ADR-061-transactional-annidato-salva-solo-il-piu-esterno.md) | un `@transactional` annidato chiude il proprio savepoint, salva solo il più esterno; `BEGIN` su SQLite prima del savepoint |
| [062](docs/adr/ADR-062-notifiche-nella-lingua-di-chi-riceve.md) | le notifiche nella lingua di **chi riceve**, salvata su `User.language`; testi passati da comporre, nessun backfill |
| [063](docs/adr/ADR-063-admin-scollegato-dopo-inattivita.md) | l'**admin** viene scollegato dopo 30 minuti senza aprire pagine; ultima attività nel cookie, i poll non contano |
| [064](docs/adr/ADR-064-sessione-che-dura-trenta-giorni.md) | casella «Resta collegato», spuntata per default: sessione di **30 giorni**; il cookie non si rimanda a ogni risposta, la scadenza si rinnova al più una volta al giorno e mai sui poll |
| [065](docs/adr/ADR-065-profilo-dell-esercizio.md) | profilo dell'esercizio: abilità e gesto come vocabolari **fissi** (enum) in `challenge_category`, livello *dichiarato* 1–5, varianti come etichette e mai come secondo esercizio, voto 1–5; «quanti l'hanno provato» si conta e non si salva |
| [066](docs/adr/ADR-066-prova-fatta-di-colpi.md) | prova fatta di colpi: `ChallengeShot` sotto il tentativo, punteggio **derivato** dai colpi e punti persistiti sul colpo; `recording_mode` sull'esercizio; il bersaglio è una voce della scena del disegnatore; la prova aperta nasce col primo colpo e si chiude con un gesto |
| [068](docs/adr/ADR-068-andamento-una-scala-sola.md) | l'andamento mette prove del catalogo e caselle delle schede su **una scala sola** — la quota di ciò che era ottenibile — senza sommarle su un esercizio; entra solo ciò che ha un massimo, e ciò che resta fuori si conta e si dice |
| [069](docs/adr/ADR-069-istruttore-e-allievo.md) | il legame è **allievo–scheda–istruttore**: non c'è nessuna tabella dei legami, «I miei istruttori» e «I miei allievi» sono la stessa riga di `training_sheet_reader` letta dai due lati; il ruolo rende trovabili, non fa vedere niente |
| [070](docs/adr/ADR-070-gruppi-di-allievi-e-triage.md) | i gruppi **ordinano** chi ti ha già aperto una scheda e non aprono niente (indice unico parziale nello schema, `closed_at` distinto dal calendario); le tre sezioni di «I miei allievi» sono definite per esteso — e «Tutto bene» è il resto, con sotto un fatto |
| [071](docs/adr/ADR-071-una-scheda-si-propone.md) | una scheda si **propone**: nasce quando l'allievo accetta e nasce **sua**, si propone solo a chi ti è già allievo, e il permesso di lettura è una casella del modulo di accettazione — spuntata, ma togliibile |
| [072](docs/adr/ADR-072-le-prove-in-scheda-sono-prove.md) | le prove fatte in scheda sono prove del catalogo: la misura discende dall'esercizio, ogni tentativo entra nel catalogo |
| [073](docs/adr/ADR-073-classifica-generale-un-calcolo-solo.md) | la classifica generale si calcola in **un posto solo** (somma delle classifiche delle gare); le righe `Classification` ne sono la copia, senza cache |
| [074](docs/adr/ADR-074-le-conferme-seguono-cosa-fa-l-azione.md) | le conferme seguono **cosa fa l'azione**: Annulla in tre secondi se frequente e reversibile, foglio col nome dell'azione se tocca altri o non si disfa; mai `confirm()` del browser |
| [075](docs/adr/ADR-075-modifiche-tracciate-invece-che-impedite.md) | le impostazioni si **correggono e restano scritte** invece di bloccarsi: storia delle modifiche, regole fissate sulla partita, cambio valido dal turno successivo, il campionato propone e la gara decide. Attuazione completata il 2026-09-29 (`docs/usecases/regolamento-di-gara.md`) |
| [076](docs/adr/ADR-076-appartenenza-al-girone-sull-iscrizione.md) | gironi multipli nel girone all'italiana: tetto «fino a N» sulla gara, numero esatto all'avvio, appartenenza su `Inscription.group_index` (copiata in `Match.bracket_group`); classifica della gara primi poi secondi **per partita giocata** |
| [083](docs/adr/ADR-083-livelli-di-certificazione.md) | le prestazioni hanno **livelli di certificazione** (torneo, confermata, in attesa) e tre viste cumulative; il livello si decide solo in `models/certificazione.py`, un pool ELO per vista |
| [084](docs/adr/ADR-084-tpa-tenuto-da-un-terzo.md) | istruttori e direttori tengono il TPA della partita di **altri due**: `scorer_id`, nessuna firma d'ufficio, conferma o rifiuto **per giocatore**; livello per giocatore, ELO per coppia |
| [085](docs/adr/ADR-085-giocatori-non-ancora-registrati.md) | direttori e istruttori creano giocatori **non ancora registrati**: `User.is_placeholder`, `created_by_id`, `claimed_at`; niente login, notifiche né proposte, ma partite, classifiche ed ELO veri; segno «non registrato» da `components/_nome_giocatore.html` |
| [086](docs/adr/ADR-086-riscatto-dei-giocatori-non-registrati.md) | chi si registra **riscatta** il suo giocatore non registrato: `ClaimRequest` con destinatari, conferma il **creatore** (l'admin solo per chi non ne ha); «Sei tu? Riscatta» nella macro del nome, intenzione in sessione e richiesta al login, mai da un GET; l'approvazione è `merge_users(..., riscatto_approvato=True)` |
| [077](docs/adr/ADR-077-limite-di-tempo-visivo-interrompe-il-direttore.md) | il limite di tempo affianca la distanza ed è **solo visivo**: parte all'acchito o con «Avvia partita», si fissa sulla partita (ADR-075); a tempo scaduto non chiude niente, interrompe il direttore |
| [078](docs/adr/ADR-078-catena-degli-spareggi-motore-unico.md) | i pari merito si risolvono con una **catena** di criteri applicata a gruppi da un motore solo (`models/classification/ordinamento.py`); turno, gara e campionato hanno ciascuno la sua; sorteggio deterministico, mai l'id; le catene si configurano (sulla gara, proposte dal campionato, più quella della classifica generale) e lo spareggio SSR è il criterio `ssr:N` della catena di gara; la classifica a punti (`POINTS`, vittoria/pareggio/sconfitta di norma 3/1/0, `classification/punti.py`) ordina solo sui punti |
| [079](docs/adr/ADR-079-listino-quote-categorie-senza-handicap.md) | listino quote per categoria, **solo informazione**: `Categoria.entry_fee`; le categorie esistono anche senza handicap (`Gara.usa_categorie`) e lì non toccano l'ELO |
| [080](docs/adr/ADR-080-campionato-a-piazzamenti-con-gare-di-ogni-formato.md) | il sistema del campionato dice **come le gare entrano**: sommando i totali (stesso sistema, girone unico) o **a piazzamenti** (gare di ogni formato, punti per posto); il sistema delle serate lo propone `default_gara_classification_system`, letto da `models/campionato/piazzamenti.py`; a pari punti decide la catena generale con criteri sui piazzamenti (più primi posti, poi secondi…), mai vittorie e triangoli |
| [081](docs/adr/ADR-081-tabellone-dopo-i-gironi.md) | il **tabellone dopo i gironi** (primi `K` di ogni girone) lo genera la strategia del girone all'italiana con `_TabelloneFinale`; teste di serie per colonne, separazione per girone; la classifica finale è il tabellone e poi i gironi (`classification/fase_finale.py`), senza spareggio SSR; limite di tempo della fase finale: turno → fase finale → gara (`tempo.limite_del_turno`) |
| [082](docs/adr/ADR-082-preset-dei-direttori.md) | i **preset** dei direttori sono personali, condividerli crea una **copia**; precompilano soltanto (il modulo passa dal parser di sempre) e nessuna gara resta legata al preset; whitelist positiva in `models/preset/payload.py`, `schema_version` e lettura tollerante |

---

## Debugging Tips

Dati che cambiano in memoria ma non finiscono su DB: quasi sempre il decoratore
`@transactional` non è applicato davvero (o è quello sbagliato, per import
circolare). Diagnosi passo-passo in **`models/transaction/CLAUDE.md`** e
casistica completa in `docs/adr/ADR-012-transactional-circular-import-fix.md`.

---

## Development Notes

- Application usually running - no need to restart for most changes

---
