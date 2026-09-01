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
cd tests/frontend && npm install && npm test   # run after editing static/js/gamification.js

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

Le tre cose che devono essere note **sempre**, non solo quando si deploya. Il
resto — i 4 job della CI, la procedura manuale PythonAnywhere, le env negli
script da console, l'ordine degli import, gli scheduled task, GlitchTip, la
convenzione dry-run degli script sui dati storici — sta nella skill **`deploy`**
(`.claude/skills/deploy/SKILL.md`), che si carica quando serve.

> ⚠️ **1. Il merge su `main` NON deploya il codice.** Il job `deploy` fa **solo
> un reload** della web app, non un `git pull`. Il codice nuovo arriva su
> PythonAnywhere quando gira lo scheduled task giornaliero
> `scripts/auto_deploy.py`: fra il merge e la produzione può passare fino a **un
> giorno**. E se la PR **aggiunge una migration** non parte nemmeno il reload.
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

Due trappole: una **PR con base diversa da `main` non fa girare nessun check** e
resta bloccata per sempre (le PR impilate vanno riportate su `main`); e sulle PR
`check-migrations`, `deploy` e `skip-deploy-notification` risultano `skipped` di
proposito — è **normale**, non va segnalato come problema né richiesto come
status check. (`pr-title`, invece, sulle PR gira eccome: vedi il punto 4.)

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

* **quanto vale la X in classifica** (SPECIFICHE.md righe 64 e 71: una vittoria
  e **zero** differenza rack; il codice dava +distanza). **Corretto** lo stesso
  giorno in `round_creation.py`: la X nasce con `player1_score = 0`. Notevole
  che un terzo punto del codice — `validators._validate_rack_system`, che
  vieta il bye semplice col sistema RACK «perché il giocatore con bye
  riceverebbe 0 rack» — fosse d'accordo con la specifica da sempre: nessuno
  aveva mai confrontato i tre. **Corretta lo stesso giorno anche la variante
  con challenge** (riga 65): la differenza torna a essere il punteggio della
  prova, e il limite `[0, effective_distance]` è passato dal *lettore* del dato
  a chi lo *registra*. Difendersi a valle, scartando il punteggio, equivaleva a
  cancellare la regola che si voleva applicare — vedi
  `tests/new/unit/test_x_replacement_score_scale.py`;
* **a chi passa l'invito ai playoff quando qualcuno rifiuta** (riga 186: «al
  primo degli esclusi»; il codice non lo trovava mai e la finale partiva con un
  posto vuoto). **Corretta** il 2026-08-23: `evaluate_qualifications(posti=…)`
  sa allargare la finestra oltre `max_participants`, e
  `find_replacement_player` la chiama così. La causa era una domanda sola usata
  per due scopi — «chi entra?» si ferma ai posti, «chi viene dopo?» deve
  guardare oltre — e la lista tagliata conteneva solo giocatori che avevano già
  una qualificazione, declinante compreso.

**Nessuna delle due era difesa da un test come si temeva**:
`test_declined_player_not_repicked` ha quattro giocatori per quattro posti,
quindi passa in entrambi i mondi. Vale la pena notarlo, perché il sospetto che
un test difendesse la deviazione era ragionevole e si è rivelato infondato: va
verificato, non assunto.

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
gara.best_of = False  # Always False for Race to N

# ❌ WRONG
gara.distance = 9  # This means "race to 9", not "best of 9"
```

### 3. Transaction Management
All service methods that modify database state MUST use `@transactional`:

```python
from models.transaction.manager import transactional

class GaraService:
    @transactional
    def create_gara(self, campionato_id: int, data: dict) -> Gara:
        gara = Gara(campionato_id=campionato_id, nome=data['nome'])
        db.session.add(gara)
        return gara  # Commit happens automatically
```

### 4. Soft Delete (User Model)
User model has soft delete with automatic session-level filtering.

```python
# Automatic filtering - excludes is_deleted=True
users = User.query.all()

# Include deleted records
all_users = User.query.with_deleted().all()

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

### 7-8. Stringhe tradotte e attributi `onclick` nei template (CRITICAL)

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
    "player.inscribe_to_gara":    {"player"},                          # player only
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
(es. `CampionatoService`, non `CampionatiService`).

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
- `tests/legacy/` non esiste più: era rimasta indietro fino a non importarsi
  nemmeno (referenziava `UtilityMixin`, rimosso a giugno 2026), quindi nessuno
  di quei test girava. Cancellata.
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

| Mistake | Correct Approach |
|---------|------------------|
| `datetime.now()` or `datetime.utcnow()` | `utc_now()` from `models.base` |
| `gara.distance = 9` (thinking best of 9) | `gara.distance = 5` (race to 5) |
| `db.session.delete(user)` | `user.anonymize()` |
| `gara.status == GaraStatus.PLAYING` | `gara.status == GaraStatus.PLAYING.value` |
| `pytest tests/new/integration/ -n auto` | `pytest tests/new/integration/ -n 4` (SQLite deadlock) |
| Manual `db.session.commit()` | Use `@transactional` decorator |
| `<form method="POST">` senza `csrf_token()` | Prima riga dentro il form: `<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">`, altrimenti 400 «Sessione scaduta». **I test non lo vedono** (`WTF_CSRF_ENABLED = False`): presidio statico in `tests/new/integration/test_drill_exam_manual_findings.py` |
| Rimettere `WTF_CSRF_SSL_STRICT` (o fidarsi del default di Flask-WTF) | Su HTTPS pretende anche l'header `Referer`, che browser con la privacy stretta, webview e proxy tolgono: per quegli utenti **ogni** POST è 400 — login compreso, quindi restano fuori. La difesa è il token + `SameSite=Lax` + il controllo di `Origin` in `app.py` (ADR-050) |
| Lasciare a Flask-WTF il default di `WTF_CSRF_TIME_LIMIT` (un'ora) | Si conta dalla generazione della pagina, non dall'ultimo uso: sul telefono il browser non si chiude, la scheda di ieri sera ha il cookie buono e il token scaduto → 400 «sessione scaduta» al primo invio. `None` lega il token alla sessione (ADR-050, emendamento) |
| Modifica di sicurezza trasversale (CSRF, cookie, header) dentro una PR che parla d'altro | Il CSRF è nato il 2026-08-16 **dentro la PR #107, «drill negli esami»**: quando la settimana dopo sono piovuti i 400 al login, nessuno li ha collegati a un cambiamento del sito — nel diario dei rilasci era invisibile. Una modifica così viaggia in una PR dedicata, col suo nome, i default esaminati uno a uno (qui: referrer obbligatorio e token a scadenza oraria, entrambi sbagliati per noi) e un occhio ai log nei giorni successivi (ADR-050) |
| `alert('{{ _("l'errore") }}')` in JS | `alert({{ _("l'errore")\|tojson }})` |
| `{{ _("%(count)s items")\|tojson }}` + JS replace | Use `"{count} items"` with JS replace |
| `onclick="func({{ x\|tojson }})"` | `onclick='func({{ x\|tojson }})'` (single quotes) |
| Gara N with date before gara N-1 | Ensure date/time is sequential by number (ADR-016) |
| `EventBus._handlers = {}` in tests | Preserve and restore handlers (breaks notifications/gamification) |
| Manual SMTP sending | Use `EmailService` for all emails |
| `max(rack_number) WHERE is_deleted=False` | Include ALL records for sequential IDs with UNIQUE constraints |
| `@transactional` on facade AND inner service | Only decorate the innermost method (nested causes rollback) |
| `match.gara.distance` in scoring/validation | Use `match.distance_config` or `match.effective_*` (ADR-027) |
| Cercare *tutte* le partite di un giocatore nella sola tabella `match` | Le sfide individuali stanno su `individual_match`: sono due tabelle. `PlayerHistoryService.get_unified_match_history` le unisce nella stessa forma — interrogarne una sola non dà errore, mostra meno partite di quelle giocate. **Ci sono ricascati i due profili** (proprio e altrui) fino al 2026-08-20: query sul solo `match` e conteggio del solo `CLOSED_UNILATERALLY`, quindi una sfida individuale non compariva né fra le partite recenti né nelle statistiche, mentre lo storico completo la mostrava. Il profilo altrui filtra le voci con `PlayerHistoryService.filter_visible_entries`, che guarda la **provenienza**: gli id delle due tabelle si sovrappongono, e nascondere la partita di gara 7 nascondeva anche la sfida 7 |
| `Match.status == CLOSED_UNILATERALLY` per «partita giocata» | `MatchStatus.finished_values()`: `CONFIRMED_BY_BOTH` è la chiusura **dei due giocatori**, ed è giocata quanto l'altra. Filtrare solo la prima è il bug che teneva monco lo storico |
| `RoundConfiguration` salvato solo in `localStorage` | API endpoint `POST /admin/gara/<id>/round-config/<n>` (ADR-027) |
| Nuova route senza entry in `ENDPOINT_ROLES` | Sarà admin-only in prod (ADR-028) — aggiungila a `utils/feature_flags.py` se non è il comportamento voluto |
| "Il merge su `main` fa scattare il deploy" | **Falso**: il job `deploy` fa solo un *reload*, e se la PR aggiunge migration non parte neanche quello. Il codice lo porta lo scheduled task `auto_deploy.py` (fino a 24h dopo) |
| Link a endpoint in template senza `feature_visible(...)` | In prod il link compare ma porta a 404 (ADR-028) — avvolgi con `{% if feature_visible('endpoint.name') %}` |
| `match.status in ["completed", "validated"]` (letterale raw) | `MatchStatus.is_finished(match.status)` / `is_active(...)` (typo-safe) |
| Credere che `"validated"` sia la validazione del direttore | È il contrario: `CONFIRMED_BY_BOTH` (valore `"validated"`) = chiusa dai **giocatori** con doppia conferma; `CLOSED_UNILATERALLY` (valore `"completed"`) = chiusa dal direttore/forfait/bye. I nomi dei membri sono stati corretti il 2026-08-17, **i valori persistiti no** |
| `match.validated_by_admin` | Non esiste su `Match` (vive su `Rack` e `Set`). La validazione del direttore *è* lo stato; per chiudere una partita mai iniziata si passa `to_completed(..., closed_by_director=True)` |
| Rinominare un membro di un enum usato da una colonna `db.Enum(...)` | **Rompe i dati già scritti**: senza `values_callable` SQLAlchemy persiste il *nome* del membro, non il valore. I test non lo vedono (scrivono e rileggono lo stesso nome nello stesso processo). Elenco delle colonne a rischio e presidio in `tests/new/unit/test_enum_columns_store_values.py` — incidente 2026-08-17 |
| `raise ValueError(...)` per not-found / conflitto / permesso | Solleva la sottoclasse da `models.exceptions` (`NotFoundError`/`ConflictError`/`PermissionDeniedError`) → route mappano a 404/409/403 |
| Parsing form duplicato tra create / wizard / edit | Unica fonte `GaraFormParser` / `CampionatoFormParser` (vedi `routes/CLAUDE.md`) |
| `user.role == "director"` (o `"admin"`/`"player"`/`"guest"` letterali) | `UserRole.DIRECTOR.value` ecc. da `models/user/role_enum.py` — mai letterali per valori di dominio |
| Interfaccia scritta "a memoria" senza aprire il prototipo | Invoca la skill `ui-7c`: la schermata di riferimento e' in `docs/redesign-7c/Redesign Mobile.dc.html` |
| `Config.DEBUG_MODE` in una route | `current_app.config.get("DEBUG_MODE", False)` — la classe base legge la env var col default `true`, quindi in produzione il guard non scatta |
| Nuova impostazione da env scritta nel corpo di `Config` | Va in `Config.environment_settings()` — il corpo della classe si esegue all'import e congela il valore: per gli scheduled task, che caricano le env *dopo*, sarebbe sbagliato per sempre |
| `from app import create_app` in cima a uno script con `prod_env` | `prod_env.bootstrap_and_create_app()` — importa l'app **dopo** aver letto le env dal WSGI (presidio: `test_script_import_order.py`) |
| Migration che solleva su una condizione permanente dell'ambiente | Deve riuscire (no-op dichiarato) o rimediare: se solleva, il runner non la marca applicata e `auto_deploy` la ritenta ogni notte, disabilitando la web app per niente |
| Co-direttore con `role != director` | `GaraService`/`TournamentService.add_director` lo rifiutano (`ValidationError`): i co-direttori sono sempre `role=director` |
| Derivare `ExamChallenge.max_score` da `challenge.max_score` | Sono due cose diverse: il primo è **quanto pesa in quell'esame**, il secondo **quanto vale al massimo la prova**. Derivarlo rende impossibile far pesare lo stesso esercizio in due modi (ADR-042 + emendamento 2026-08-18). Entrambi facoltativi; `challenge.name` non esiste, il nome mostrato è `get_display_name()` |
| `datetime.strptime`/`fromisoformat` su un `datetime-local` | `utils.local_time.parse_local_datetime` — l'input arriva nell'**ora di chi scrive**, il DB tiene naive-UTC: salvarlo grezzo sposta l'orario, in silenzio (ADR-043) |
| `ZoneInfo("Europe/Rome")` scritto in un filtro o in una route | `resolve_timezone()` da `utils.local_time` — il fuso è quello del lettore, e un solo modulo lo sa (ADR-043) |
| Orario formattato una volta per N destinatari | Se il testo contiene un'ora, si compone **per destinatario** col suo `tz`: due giocatori in due fusi leggono due frasi diverse |
| `request.form.get("next")` passato a `redirect()` | `utils.safe_redirect.safe_next_url` — altrimenti è un open redirect |
| Disciplina come stringa scritta a mano (`"palla_8"`, `"8_ball"`) | `Discipline.*.value` da `models/status_enum.py` — **unico** vocabolario; per dati storici/esterni `Discipline.normalize()` (torna `None` sull'ignoto). Il nome mostrato è `display_name`, tradotto. Presidiato da `test_discipline_single_vocabulary.py` |
| Scheduled task PythonAnywhere lanciato con `python script.py` | `venv/bin/python script.py`: `python` nudo è l'interprete **di sistema** — non ha i pacchetti del progetto, ha quelli di PythonAnywhere (da cui il guasto `pyOpenSSL`), e un `pip install` da lì fallisce per permessi (incidente 2026-08-17, `/aiuto` in 500 per due giorni) |
| `campionato_type` per decidere **come si ordina** una classifica | `campionato.classification_system` (`ClassificationSystem`, ADR-047): il tipo dice come si formano le partite, il sistema su cosa si ordina. Sono scelte indipendenti e coincidono abbastanza spesso da rendere il bug invisibile per mesi (issue #89) |
| Sommare `rack_difference` e chiamarlo "triangoli totali" | `racks_won` è il totale, `rack_difference` la differenza (migration 20260728). Un totale negativo in classifica è la firma esatta di questo scambio |
| Dare per scontato che `rack_difference` in **produzione** sia sempre una differenza | Su ~400 righe storiche contiene ancora un totale: i dati non sono stati riparati **per scelta** (gare già premiate, nessuna schermata li legge con quel significato — ADR-047, sezione dedicata). Chi ci costruisce sopra qualcosa di nuovo — spareggio, statistica, export — lo trova |
| `gara.matchmaking_strategy == "random"`, `campionato_type == "amalfi"` | `MatchmakingStrategy.*.value` da `models/matchmaking/configuration.py`, iniettato nei template. Esiste un **secondo enum omonimo** in `models/competition/validators.py` (`elimination`/`double_ko`) che non sta mai in colonna: citarlo dà un confronto sempre falso, senza errori. Presidiato da `test_match_status_no_raw_literals.py`, che vede anche `campionato_type\|lower == '...'` |
| Funzione visibile all'utente cambiata senza toccare `/aiuto` | Invoca la skill `help-docs`: la guida non si rompe, **invecchia** — continua a descrivere un'app che non esiste più. Contenuti in `help_content/`, schermate rigenerate da `scripts/help_docs/` |
| TPA/errori calcolati fuori da `models/tpa/engine.py` | Le regole Accu-Stats stanno **solo** li'. Il resto persiste comandi e li rigioca (ADR-044) |
| Rack segnati a mano su un match con referto TPA aperto | Il punteggio **discende** dal referto: due segnapunti si contraddicono al primo tocco (ADR-044) |
| `match.effective_has_handicap` letto per decidere se una partita conta per l'ELO | `RatingEligibility.exclusion_reason(match)` (`models/rating/eligibility.py`): dall'ADR-049 l'handicap **da solo** non basta più a escludere — decide la differenza di **categoria**. Nei cicli passa l'indice di `build_index`, altrimenti il ricalcolo fa due query per match |
| Categoria del giocatore cercata su `User` o in `models/rating/` | Vive su `Inscription.categoria_id`, ed è **per gara**: `models/categoria/`. `PlayerCategory` e l'enum `CategoryLevel` A/B/C/D sono stati rimossi — erano globali per utente e mai scritti da nessuno |
| `DROP TABLE` di una tabella referenziata da una FK, anche vuota | Con `PRAGMA foreign_keys=ON` (`models/base.py:104`) **ogni INSERT sulla tabella figlia fallisce**, pure con la FK a NULL. E la colonna non si toglie: SQLite rifiuta `DROP COLUMN` su una colonna citata in una chiave esterna, anche sulla 3.51. Resta il no-op dichiarato (vedi `migrations/20260819`) |
| Migration che crea una tabella senza `created_at`/`updated_at` | `BaseModel` le aggiunge a ogni entità: l'ORM fallisce con «no such column» e la funzione muore in silenzio in produzione (incidente `categoria`, 2026-08-19). I test di comportamento non lo vedono — creano lo schema con `db.create_all()` — quindi il presidio legge il **testo** delle migration: `tests/new/unit/test_migrations_timestamps.py` |
| Correggere la migration che ha creato la tabella sbagliata | Non serve a niente: è già marcata applicata e non gira più, e comunque è `CREATE TABLE IF NOT EXISTS`. Un DB già storto si ripara solo con una **migration nuova** che aggiunga le colonne (`20260820_timestamps_basemodel.py`) |
| Schermata della guida ritoccata a mano in un editor | Le immagini si **generano** dall'app (`capture_screenshots.py`) sul dataset di `seed_demo.py`: una ritoccata sopravvive al cambio di interfaccia e diventa una bugia permanente |
| Dare alla X i triangoli della distanza | La X vale una vittoria e **zero** differenza (SPECIFICHE.md righe 64 e 71): nasce con `player1_score = 0` in `round_creation.py`, e `ScoreAggregator._process_bye_match` somma quello zero ai vinti senza contarne di persi. Fino al 2026-08-23 valeva `round_distance`, e con la classifica a vittorie — che ordina per `(vittorie, differenza triangoli)` — chi riposava scavalcava chi aveva vinto giocando. Presidiato da `test_stagione_e2e_x_e_abbinamenti.py` e `test_specifiche_conformita.py` |
| Assumere che la X con **challenge** segua la stessa regola | Non la segue: lì la differenza è **pari al punteggio della prova** (SPECIFICHE.md riga 65), non zero. Il punteggio arriva grezzo in classifica, ed è sicuro perché `complete_x_replacement_attempt` rifiuta tutto ciò che esce da `[0, effective_distance]` — la scala la impone chi registra il dato, non chi lo legge. Fino al 2026-08-23 il punteggio veniva **scartato** e sostituito dalla distanza, il che rendeva la variante con prova indistinguibile dalla X secca. Presidiato da `test_x_replacement_score_scale.py` |
| Validare il punteggio della prova contro `gara.distance` | `match.effective_distance` (ADR-027): in un turno «al 3» dentro una gara «al 5» il massimo è 3, e leggere la gara accetterebbe un punteggio che in quel turno nessuno può ottenere giocando |
| Cercare il sostituto ai playoff dentro `evaluate_qualifications()` senza `posti` | Quella lista è tagliata a `max_participants`, cioè contiene **solo chi ha già una qualificazione** — declinante incluso, che resta in elenco con status `DECLINED`. Il sostituto non si trovava mai e la finale partiva con un posto vuoto. Serve `evaluate_qualifications(posti=max_participants + qualificazioni_esistenti)`: «chi entra?» e «chi viene dopo?» sono due domande diverse (SPECIFICHE.md riga 188) |
| Sommare le partite di un campionato in un unico mucchio per fare la classifica | L'aggregazione è **per gara**, poi somma pesata su `Gara.classification_weight` (ADR-053): una gara può valere il doppio delle altre, e quella di playoff può valere **zero** quando è lei a decidere la classifica finale. Con tutti i pesi a 1 il risultato è quello di sempre |
| Cercare il peso del playoff su `PlayoffConfiguration` mentre si calcola una classifica | La fonte letta è `Gara.weight`; `playoff_weight` è il **valore di configurazione**, copiato sulla gara quando nasce (come distanza e turni). Cambiarlo senza propagarlo alla gara già creata è un comando che sembra funzionare e non sposta niente — `PlayoffService.update_scoring` lo fa |
| Credere che senza playoff-only il playoff «non conti» per il campionato | Conta da sempre: `create_playoff_gara` gli mette `campionato_id`, quindi l'aggregatore lo sommava già con peso 1. Il default `campionato_plus_playoff` **è** il comportamento storico, e la issue #64 proponeva il contrario partendo da questo equivoco |
| Bloccare modalità e peso del playoff dopo l'avvio, come gli altri campi | `update_configuration` è bloccata perché i criteri di qualificazione non si toccano a inviti partiti; modalità e peso sono decisioni di **punteggio** e passano da `update_scoring`, che non è bloccata e ricalcola la classifica |
| Interrogare `PlayoffQualification` senza far comparire `Campionato` nella query | Il filtro soft-delete è un `with_loader_criteria`: si applica solo alle entità **presenti nella query**. Senza join, un invito rimasto `PENDING` su un campionato eliminato compare in dashboard con due pulsanti che scrivono su dati orfani (`build_playoff_invitations`) |
| Spostare la X del primo turno riabbinando invece che **rietichettando** | Con la strategia casuale i turni nascono **tutti insieme** (circle method): chi ha la X al turno 1 non la riprende più, e nessuno reincontra nessuno. Toccare il solo turno 1 per dare la X a un altro gli regala una **seconda X** più avanti e introduce un reincontro — e nessun test di quel turno se ne accorge. La mossa giusta è scambiare le **identità** dei due giocatori su tutto lo schedule: è una permutazione dei nomi su una struttura che dipende solo dalle posizioni, quindi conserva ogni garanzia. Per Amalfi lo scambio va fatto anche sulla **classifica di partenza**, che è l'input da cui il turno 1 discende: al turno 1 l'algoritmo dipende solo dalle posizioni (matrice incontri vuota, nessuna X già data), quindi i due sono equivalenti — e lasciare il seeding com'era pubblicherebbe un «ordine sorteggio» che non spiega più gli abbinamenti. Regola in `models/matchmaking/bye_preference.py`, presidio in `test_x_al_ultimo_iscritto.py` |
| Dare per garantito l'anti-reincontro Amalfi con un numero dispari di giocatori | La garanzia di ADR-029 è per il caso **pari**, dove si risolve un matching di peso massimo sul grafo dei non-incontri. Nel dispari il sentinella della X si aggiunge **dopo** quel controllo: si passa al greedy, che dopo `len(players)` tentativi ammette esplicitamente il reincontro |
| Dare per scontato che una partita abbia sempre un vincitore | In «esattamente N rack» con **N pari** il pareggio esiste: a 3-3 la partita è chiusa e `winner_id` resta `None`. Chi somma le vittorie senza contemplarlo perde una riga di classifica; chi scrive «ha vinto X» in una notifica scrive una frase falsa. Con N dispari non può capitare, ed è per questo che il caso passa inosservato (`test_stagione_e2e_risultati.py`) |
| Datare a `today` una gara che il programma crea dentro un campionato | Le gare numerate stanno in ordine cronologico (ADR-016) e il controllo **non** salta le soft-eliminate. La gara di playoff nasceva datata oggi pur essendo l'ultima del calendario: con una gara ancora nel futuro — anche solo una pianificata e mai giocata, che la terminazione cancella — veniva rifiutata, e al posto della finale compariva un messaggio. La data si sceglie a partire dall'ultima gara, non dall'orologio (`test_playoff_gara_date_sequence.py`) |
| Parentesi annidate nel **corpo** del commit (`matchMedia('(min-width: 992px)')`) | Il parser di release-please le legge come apertura di *scope* e salta il commit **in silenzio**: workflow verde, PR di rilascio «remained the same», e la funzione non compare in `docs/RELEASES.md`. Successo il 2026-08-30 con la #287. Riscrivi la citazione senza parentesi dentro parentesi |
| Aprire una PR con un titolo senza prefisso `fix:`/`feat:`/… | Con lo squash merge il titolo **è** il messaggio di commit su `main`, e release-please ne ricava la versione: una PR senza prefisso non alza il numero e non compare in `docs/RELEASES.md`, senza dire niente a nessuno. Il job `pr-title` la blocca prima (vedi CI/CD, punto 4) |
| Modificare `Config.VERSION` (o `.release-please-manifest.json`) a mano | Le scrive release-please nella PR di rilascio, e il manifest è la sua memoria: correggere la versione a mano fa ripartire il rilascio successivo dal numero vecchio. La riga di `config.py` va lasciata con la sua annotazione `# x-release-please-version` — senza, il bot smette di aggiornarla e il footer si congela in silenzio (`test_version_single_source.py`) |
| Dedurre chi ha aperto un triangolo a ogni lettura invece di scriverlo sul rack | `break_player_id` si **persiste** alla creazione (ADR-056). Se domani il direttore cambia la regola di apertura della gara, i triangoli già giocati devono continuare a dire chi li ha aperti: dedurli a valle cambierebbe anche quali risultano *break and run*, cioè un numero nel profilo dei giocatori. Stesso schema dell'ADR-027 |
| Aggiungere un secondo flag `is_break_and_run` accanto a `is_run_out` | Il break and run **si deduce**: è un runout in cui `break_player_id == winner_id` (`Rack.is_break_and_run`). Due flag da tenere allineati a mano sono due flag che prima o poi si contraddicono |
| Stampare `tally.run_outs` come «runout totali» | Nel motore TPA i due contatori sono **disgiunti** (`is_run_out = not is_break_and_run and …`): il totale è `run_outs + break_and_runs`. Nel profilo invece runout è l'**insieme** e break and run un sottoinsieme — come parlano i giocatori. Chi confonde i due mondi mostra 17 invece di 26 (`models/user/runout_stats.py`) |
| Dedurre chi apre dal solo vincitore dell'acchito | Sono **due** fatti: «Regole generali pool» 1.2 dice che chi vince l'acchito **sceglie chi** apre, e può mandare al tavolo l'avversario. Per questo `lag_winner_id` e `first_break_player_id` sono due colonne |
| `first_break_player_id` NULL trattato come «apre il primo giocatore» | Dipende dalla regola: con `first_player` sì, con `lag` NULL vuol dire **non si sa ancora** — ed è il segnale che fa comparire le due domande sul tabellone (`breaker_of_first_rack`). Un ripiego lì cancellerebbe la domanda |
| Contare su un `if` applicativo per l'unicità di una riga | `UserMergeService` decide **dallo schema** se spostare una colonna riga per riga o in blocco (`_is_constrained`): un'unicità che vive solo in Python — com'era «un giocatore, un'iscrizione per gara», dentro `inscribe_user` — gli è invisibile, e l'`UPDATE` di massa la viola in silenzio. È così che unendo due account il giocatore restava iscritto **due volte** alla stessa gara, una con la categoria del direttore e una senza (produzione, gara 39, settembre 2026). Se una tabella ha un'unicità logica, si dichiara con un `UniqueConstraint`. E il vincolo da solo non basta: la dedup generica tiene la riga del **destinatario**, quindi dove i dati vanno conservati serve una fusione esplicita (`models/competition/inscription_dedup.py`) |
| `sess["_user_id"] = str(user.id)` in un test | `user.get_id()` (ADR-055): l'id di sessione porta un'impronta della credenziale, e l'id nudo produce un client **non autenticato** — i test falliscono con 302 verso il login senza dire perché |
| Verificare in un test che una sessione sia caduta, senza ripulire `g` | In questa suite `g` **non è per-richiesta**: Flask-Login trova l'utente già in cache e non richiama mai `load_user`, quindi il test passa sempre — anche col controllo rimosso (verificato sabotandolo). Cancella `g._login_user` prima della verifica, come fa `_simula_richiesta_nuova()` in `test_recupero_password.py` |
| Chiudere le righe di `user_session` per «buttare fuori» qualcuno | `user_session` è **analitica**: misura le permanenze, non autentica. Il cookie non la consulta, quindi chiuderne le righe cambia le statistiche e lascia l'intruso dov'è (ADR-055) |

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
