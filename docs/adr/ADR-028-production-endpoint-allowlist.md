# ADR-028 Production Endpoint Allowlist (deny-by-default, matrice ruoli)

**Data**: 2026-05-09
**Stato**: Accepted
**Decisori**: Paolo Coppola

## Contesto

L'app esposta in produzione ha ~150 endpoint HTTP raggiungibili in 30 aree funzionali (auth, dashboard, gestione campionati/gare, scoring, gamification, challenge, individual match, rating, admin, ecc.). Alcune di queste aree hanno copertura test ampia (gamification 80+ test, individual_match 50+ test, challenge 50 test); altre sono in stato parziale (rating: 0 unit test; KPI: 0 test, solo modelli; venue manager: 0 test). Vedi `docs/PRODUCTION_INVENTORY.md` per l'inventario completo.

Pur non essendoci feature "rotte" sul piano del codice, l'autore percepisce **incertezza sullo stato reale** delle combinazioni di feature in produzione. Il bug ADR-027 (override di configurazione per turno persi nel scoring) ne è la prova: una feature considerata "stabile" ha avuto per mesi un percorso non coperto da test, scoperto solo nell'uso reale.

Vincoli del problema:

1. **Confidenza per scope**: l'autore vuole garantire che gli utenti finali in produzione vedano solo ciò che è stato esplicitamente verificato. Il default deve essere "non visibile" — è più gestibile mantenere una piccola allowlist che una grande blocklist.
2. **Admin invariato**: l'autore (admin) deve poter operare in produzione come opera in dev, senza limitazioni. L'allowlist riguarda solo i ruoli non-admin (anonimo, player, director).
3. **Ruoli non gerarchici**: un director NON è "un player con poteri in più". Sono tipi di utente diversi. Alcune route servono solo player (es. iscrizione gara: un director non si iscrive alle proprie gare); altre servono solo director (es. avvio turno); molte sono polimorfiche (es. dettaglio gara, con UI che si adatta al ruolo).
4. **Ambiente-driven**: in `development` (`DEBUG_MODE=true`) tutto deve restare visibile, per dogfooding e debug.
5. **Sicurezza server-side**: l'allowlist non deve essere implementata via CSS/JS — gli endpoint protetti devono restituire 404 indistinguibile da path inesistente, non basta nascondere il bottone.
6. **Niente buchi by default**: con 150 endpoint, proteggere ognuno con un decoratore esplicito è error-prone — basta dimenticarne uno e si crea un buco. Serve un meccanismo centrale che intercetti ogni richiesta.

## Decisione

Introduciamo una **matrice di visibilità endpoint→ruoli**, valutata in produzione da un singolo middleware `@app.before_request`. La matrice è esplicita (niente ereditarietà fra ruoli); endpoint non listati sono visibili **solo agli admin**.

### Modello matriciale

Una struttura dati `ENDPOINT_ROLES: dict[str, set[str]]` in `config/features.py`. I ruoli sono `anonimo`, `player`, `director`. Admin è bypass globale, fuori matrice. Esempio:

```python
ENDPOINT_ROLES = {
    # Pubblica (polimorfica: tutti i ruoli vedono, ma il template si adatta)
    "main.public_garas_list":               {"anonimo", "player", "director"},
    "admin.competition.gara_detail":        {"anonimo", "player", "director"},

    # Solo non-loggati
    "auth.login":                           {"anonimo"},

    # Solo loggati non-admin
    "dashboard.dashboard":                  {"player", "director"},
    "player.notifications":                 {"player", "director"},

    # Solo player (un director non si iscrive alle proprie gare)
    "player.inscribe_competition":          {"player"},

    # Solo director (gestione tournament)
    "admin.competition.create_gara_standalone": {"director"},
    "admin.competition.start_first_round":  {"director"},

    # Endpoint NON listato → solo admin lo vede
    # (es. admin.user.director_requests, admin.kpi.index)
}
```

### Engine

`utils/feature_flags.py` espone `is_endpoint_visible(endpoint, user) -> bool`:

```python
def is_endpoint_visible(endpoint: str, user) -> bool:
    if not _is_production():
        return True
    if endpoint in INFRASTRUCTURE_ALLOWLIST:
        return True
    if user.is_authenticated and user.is_admin:
        return True

    role = "anonimo"
    if user.is_authenticated:
        role = "director" if user.is_director else "player"

    return role in ENDPOINT_ROLES.get(endpoint, set())
```

`INFRASTRUCTURE_ALLOWLIST` contiene endpoint tecnici sempre visibili a tutti i ruoli (statici Flask, healthcheck, polling SSE, set_language). Le route debug-only (`/debug/*`, `/reset*`) sono già protette da check `if not Config.DEBUG_MODE: abort(404)` e non rientrano nella matrice.

### Middleware centrale

Un singolo `@app.before_request` in `app.py`:

```python
@app.before_request
def enforce_endpoint_allowlist():
    endpoint = request.endpoint
    if endpoint is None:
        return None  # 404 already handled by Flask
    if not is_endpoint_visible(endpoint, current_user):
        abort(404)
```

In dev passa sempre senza eseguire il check. In prod intercetta ogni richiesta e fa 404 silenzioso se l'endpoint non è visibile per il ruolo.

### Context processor Jinja

`feature_visible(endpoint)` esposto come globale Jinja, usato nei template per condizionare voci di menu/link:

```jinja
{% if feature_visible('individual_match.dashboard') %}
  <a href="{{ url_for('individual_match.dashboard') }}">{{ _("Match individuali") }}</a>
{% endif %}
```

Stessa logica del middleware, perché un utente non deve vedere link che porterebbero a 404. Niente discrepanza tra "cosa è raggiungibile" e "cosa è linkato".

### Visibilità ≠ autorizzazione

L'allowlist controlla solo se un endpoint è raggiungibile in produzione (200 vs 404). I decoratori esistenti (`@login_required`, `@admin_required`, `@director_required`, `@gara_manager_required`, `@match_manager_required`) controllano cosa l'utente può fare una volta raggiunto. I due layer sono ortogonali — l'allowlist non sostituisce i decoratori, li precede.

## Alternative Considerate

### Alternativa 1: visible-by-default con flag `alpha/beta/stable`

**Descrizione**: ogni endpoint visibile per default, marcato esplicitamente come "alpha" se da nascondere in prod.

- **Pro**: nessuna migrazione delle route esistenti — tutto continua a funzionare uguale.
- **Contro**: con 150 endpoint, mantenere "tutto è marcato" significa mantenere una **blocklist** — modello che non scala. Ogni nuova feature WIP rischia di finire in prod per dimenticanza. La domanda chiave dell'autore — "non sappiamo cosa è davvero stable" — diventa "non sappiamo cosa marcare alpha". Era la prima proposta dell'ADR-028 originale (cancellato), scartata per questi motivi.

### Alternativa 2: gerarchia di ruoli con ereditarietà (anonimo ⊂ player ⊂ director ⊂ admin)

**Descrizione**: definire 3 set incrementali (`GUEST_ALLOWLIST`, `USER_INCREMENT`, `DIRECTOR_INCREMENT`), un director eredita user che eredita guest.

- **Pro**: meno righe nella configurazione. Concettualmente compatto.
- **Contro**: presume che tutti i ruoli "alti" possano fare ciò che fanno i "bassi". È falso in questa app: un director **non** si iscrive alle proprie gare (anti-conflict di interesse). Esprimere queste eccezioni in un modello gerarchico richiede flag negativi/override che complicano più di quanto semplifichino. Il modello matriciale è più leggibile per route polimorfiche o ruolo-specifiche.

### Alternativa 3: decoratore esplicito su ogni route

**Descrizione**: `@feature_required(roles={"player", "director"})` su ogni view function.

- **Pro**: la regola di visibilità è co-locata con la route — leggibile localmente.
- **Contro**: con 150 endpoint, dimenticarne uno crea un buco silenzioso. Non c'è modo di vedere lo stato globale di chi vede cosa senza fare grep. La matrice centralizzata è una **single source of truth** che il decoratore distribuito non offre.

### Alternativa 4: matrice DB-backed con UI admin

**Descrizione**: persistere `ENDPOINT_ROLES` in una tabella DB, gestibile da admin UI senza redeploy.

- **Pro**: cambiabile a runtime, gradual rollout.
- **Contro**: overkill per il caso d'uso ("non esporre WIP", non A/B testing). Aggiunge query DB per ogni request o richiede caching. UI admin = altra feature da costruire e mantenere. Il file Python in `config/features.py` è già diff-tracciato in git, e ogni modifica passa per il normale flusso di review.

## Conseguenze

### Positive

- **Single source of truth**: aprire `config/features.py` mostra esattamente cosa è visibile in produzione, per ogni ruolo. La sensazione di "perdere il controllo" è risolta in modo strutturale.
- **Deny-by-default**: una feature WIP nuova non rischia di finire esposta — se non è in matrice, è invisibile.
- **Espressivo per route polimorfiche e ruolo-specifiche**: il modello matriciale gestisce in modo naturale "vista gara per chiunque ma con UI diversa" e "iscrizione solo per player".
- **Niente buchi**: il middleware centrale intercetta ogni richiesta. Impossibile dimenticare di proteggere un endpoint.
- **Admin invariato**: il workflow dell'autore (admin) in prod è identico a quello in dev. Nessuna friction.
- **Reversibile**: rimuovere `ENDPOINT_ROLES` e il middleware ripristina lo stato attuale dell'app.
- **Cresce con l'app**: ogni nuova feature deve essere esplicitamente aggiunta alla matrice prima di essere visibile in prod. Trasforma la "promozione a stable" in un atto deliberato, non automatico.

### Negative

- **Costo iniziale di mappatura**: stilare la matrice per ~140 endpoint richiede una sessione di lavoro mirata. Mitigazione: parte dell'inventario è già in `docs/PRODUCTION_INVENTORY.md`; possiamo procedere per area.
- **Accoppiamento template ↔ matrice**: ogni voce di menu condizionata richiede una chiamata `feature_visible(endpoint)`. Modificare la matrice senza aggiornare i template lascia link "morti" (che fanno 404). Mitigazione: il middleware risolve il problema lato server (404 silente è meglio di un crash), e un test E2E può verificare che ogni link nel template renderizzato sia in matrice.
- **404 timing leak**: un endpoint nascosto restituisce 404 sia perché non esiste sia perché è fuori allowlist. Un attaccante sofisticato potrebbe distinguere via timing analysis. Considerato accettabile: stiamo nascondendo UI WIP, non dati sensibili.

### Rischi

- **Dimenticanza in matrice**: aggiungo una nuova route ma dimentico di metterla in `ENDPOINT_ROLES`. Default = solo admin la vede → l'utente normale prende 404. Rischio basso (è la modalità "fail closed", che è il comportamento desiderato), ma può sorprendere lo sviluppatore in dev — perché in dev tutto è visibile, e il problema emerge solo a deploy. Mitigazione: un test che verifica che ogni endpoint registrato in Flask abbia un'entry esplicita in matrice (anche `set()` esplicito = "solo admin"). Trasforma l'omissione silenziosa in errore di test.
- **Drift template/matrice**: come sopra, link "morti". Mitigazione test e2e.
- **Override accidentale in env**: nessun env var di override è previsto in questa versione. Se in futuro lo aggiungiamo per dogfooding/test in prod, deve essere ignorato quando `FLASK_ENV=production`.

## Note Implementative

### Struttura dei file

```
utils/feature_flags.py             ← ENDPOINT_ROLES, INFRASTRUCTURE_ALLOWLIST,
                                      is_endpoint_visible() (un solo file per
                                      single-source-of-truth)
app.py                             ← @before_request hook + context processor
tests/new/unit/test_feature_flags.py            ← test logica is_endpoint_visible
tests/new/integration/test_endpoint_allowlist.py ← test che ogni route Flask sia
                                                   coperta in matrice
```

### Esempio middleware completo

```python
# app.py
from utils.feature_flags import is_endpoint_visible

@app.before_request
def enforce_endpoint_allowlist():
    endpoint = request.endpoint
    if endpoint is None:
        return None
    if not is_endpoint_visible(endpoint, current_user):
        abort(404)


@app.context_processor
def inject_endpoint_visibility():
    from utils.feature_flags import is_endpoint_visible

    def feature_visible(endpoint: str) -> bool:
        return is_endpoint_visible(endpoint, current_user)

    return {"feature_visible": feature_visible}
```

### Test di coverage matrice

```python
# tests/new/unit/test_endpoint_coverage.py
def test_all_endpoints_have_explicit_visibility(app):
    """Ogni endpoint Flask registrato deve avere un'entry in ENDPOINT_ROLES
    o in INFRASTRUCTURE_ALLOWLIST. Default implicito (solo admin) è ammesso
    solo se DICHIARATO con set() vuoto."""
    from config.features import ENDPOINT_ROLES, INFRASTRUCTURE_ALLOWLIST

    flask_endpoints = {rule.endpoint for rule in app.url_map.iter_rules()}
    flask_endpoints.discard("static")  # Flask built-in

    declared = set(ENDPOINT_ROLES.keys()) | INFRASTRUCTURE_ALLOWLIST
    undeclared = flask_endpoints - declared
    assert not undeclared, (
        f"Endpoint Flask senza visibility dichiarata: {undeclared}. "
        "Aggiungili a ENDPOINT_ROLES (con set() vuoto se solo admin) "
        "o a INFRASTRUCTURE_ALLOWLIST."
    )
```

### Procedura di adozione

1. Implementare engine, middleware, context processor (zero impatto: matrice vuota = solo admin vede tutto in prod).
2. Aggiungere test di coverage matrice (fallisce con 150 endpoint mancanti).
3. Stilare la matrice iniziale (`ENDPOINT_ROLES`) basata su `docs/PRODUCTION_INVENTORY.md` — area per area.
4. Aggiungere `feature_visible(...)` ai template che hanno menu/link condizionati.
5. Test e2e: registrazione utente nuovo, navigazione delle pagine principali, verifica che non riceva 404 sul flusso happy path.
6. Deploy.

### Promozione di una feature

Quando una feature passa da "WIP solo per admin" a "pronta per utenti normali":

1. Aggiungere o estendere l'entry in `ENDPOINT_ROLES`.
2. Aggiungere `{% if feature_visible(...) %}` nei punti UI dove il link compare.
3. Verificare con `?_role=player` (non implementato in questa versione, eventuale future extension) o registrando un utente test.
4. Commit con messaggio che cita l'endpoint promosso.

## Appendice: snapshot della matrice iniziale (proposta)

La matrice completa sarà scritta in `config/features.py` come parte dell'implementazione. Esempio rappresentativo dei pattern attesi (~10 voci su ~140):

```python
ENDPOINT_ROLES = {
    # Auth (solo non-loggati)
    "auth.login":                              {"anonimo"},
    "auth.register":                           {"anonimo"},
    "auth.logout":                             {"player", "director"},

    # Public (polimorfiche)
    "main.index":                              {"anonimo", "player", "director"},
    "main.public_garas_list":                  {"anonimo", "player", "director"},
    "admin.competition.gara_detail":           {"anonimo", "player", "director"},

    # Loggati non-admin
    "dashboard.dashboard":                     {"player", "director"},
    "player.profile":                          {"player", "director"},

    # Player only (anti-conflict)
    "player.inscribe_competition":             {"player"},
    "player.add_rack":                         {"player"},

    # Director only (gestione tournament)
    "admin.competition.create_gara_standalone": {"director"},
    "admin.competition.start_first_round":     {"director"},

    # Implicito = solo admin (NON in matrice):
    # admin.user.director_requests, admin.kpi.index, admin.venue.manage_*, ecc.
}
```

## Open Items / Follow-up

Lista dei lavori residui collegati a questa decisione. Aggiornare man mano che si completano (rimuovere voci concluse, aggiungerne di nuove emerse dall'uso reale).

### 1. Espansione matrice da feedback empirico

La matrice oggi copre il flusso MVP (registrazione, login, iscrizione, gioco, profilo, gestione gare/campionati per director). Restano ~210 endpoint visibili solo all'admin per default. Procedere come segue:

- Monitorare i log di produzione per 404 inattesi (pattern: utente raggiunge endpoint dichiarato "admin-only" mentre stava facendo qualcosa di legittimo).
- Per ogni 404 evidenziato come falso positivo, identificare l'endpoint reale (`app.url_map`) e aggiungerlo a `ENDPOINT_ROLES` con i ruoli corretti.
- Quando una macro-area è giudicata pronta (es. gamification user-facing), promuovere tutti i suoi endpoint user-side in blocco.

### 2. Estensione `feature_visible(...)` ad altri template

Ad oggi il guard è applicato solo in `templates/base.html` (navbar + dropdown profilo). Altri template potrebbero contenere link a endpoint nascosti — cliccandoci portano a 404 corretto lato server, ma UX subottimale. Quando si individua un link "morto" durante l'uso reale:

- Trovare il template che lo emette (`grep -r "url_for('endpoint.name')" templates/`).
- Avvolgerlo con `{% if feature_visible('endpoint.name') %}…{% endif %}`.
- Bonus: per i link che hanno già una condizione ABAC (es. `{% if current_user.can_access('do_challenge') %}`), comporre con `and feature_visible(…)` (vedi `templates/base.html:211` per l'esempio).

### 3. Promozione default da "implicit admin-only" a "explicit declaration required"

Oggi un endpoint Flask non listato in `ENDPOINT_ROLES` è admin-only. Comodo durante la migrazione, ma a regime è preferibile **forzare la dichiarazione esplicita**: ogni endpoint registrato deve avere un'entry, anche se è `set()` vuoto (= "solo admin, scelta consapevole"). Questo evita che un endpoint nuovo finisca admin-only per inerzia.

Quando la matrice avrà ~120+ voci (oggi ~80) e sarà giudicata stabile:

- Modificare `tests/new/integration/test_endpoint_allowlist.py::test_report_unclassified_endpoints` da `warnings.warn(...)` a `assert not unclassified, ...`.
- Aggiungere nella matrice tutte le voci attualmente "implicit admin-only" con `set()` esplicito (~210 voci da popolare in blocco a quel punto).
- Aggiornare la sezione "Quando aggiungi una nuova route" in `routes/CLAUDE.md` per riflettere il nuovo regime obbligatorio.

## Riferimenti

- File correlati:
  - `config.py:16` — `DEBUG_MODE`, già usato per discriminare prod/dev.
  - `app.py:106-192` — context processors esistenti (modello per `inject_endpoint_visibility`).
  - `models/user/role_decorators.py` — decoratori esistenti `@login_required`, `@admin_required`, ecc. (livello autorizzazione, ortogonale all'allowlist).
- Documenti di lavoro:
  - `docs/PRODUCTION_INVENTORY.md` — inventario completo da cui derivare la matrice.
- ADR correlati:
  - ADR-019 (gamification ABAC), ADR-020 (gamification v2): sistemi di permessi ABAC esistenti per gamification — ortogonali all'allowlist (riguardano "chi può fare X" in feature specifiche, non "chi vede X" a livello di endpoint).
