# Challenge Domain

## Purpose

Skill challenge system for individual player training and X-substitution in tournaments.

**Core Responsibilities:**
- Individual skill challenges (drills)
- Numeric scoring or pass/fail evaluation
- X-substitution for odd player handling in gare
- Player favorites and statistics

---

## Quick Reference

```python
from models.challenge.models import Challenge, ChallengeAttempt, ChallengeFavorite
from models.challenge.services import ChallengeService

# Create challenge (admin)
challenge = Challenge(
    description="Spot Shot Rally",
    image_path="/static/challenges/spot_shot.png",
    pass_fail_only=False  # Numeric scoring
)

# Registra una prova gia' conclusa (aprire e chiudere in un gesto solo)
attempt = ChallengeService.record_attempt(
    user_id=player.id,
    challenge_id=challenge.id,
    score=12,          # drill numerico
)
attempt = ChallengeService.record_attempt(
    user_id=player.id,
    challenge_id=challenge.id,
    passed=True,       # drill riuscita-o-no
)

# Get player stats
stats = ChallengeService.get_player_statistics(user_id=player.id)
# Returns: {attempts, avg_score, best_score, pass_rate}
```

---

## Allenarsi: una prova, una richiesta

Dal catalogo si passa da `challenge.training_session`
(`/challenges/<id>/train`): una schermata sola, dove si registra una prova
dopo l'altra. La POST chiama `ChallengeService.record_attempt`, che **apre e
chiude** il tentativo in un gesto solo e risponde in JSON — la pagina non si
ricarica. Prima ogni singola prova costava due pagine e quattro richieste, e
per la seconda si ricominciava da capo.

**La sessione di allenamento non è un'entità**: a DB restano i singoli
`ChallengeAttempt`, già completi. Il gruppo «le prove di stasera» non è un
fatto di dominio, e dargli una tabella avrebbe voluto dire aprirla, chiuderla
e poi ripulire quelle rimaste aperte da chi chiude il browser a metà.

`record_attempt` **valida prima di creare**: `start_challenge_attempt` e
`complete_challenge_attempt` sono due transazioni distinte, quindi un esito
mancante scoperto solo dalla seconda lascerebbe una riga `completed=False` che
nessuno chiude più — invisibile, ma capace di falsare il conteggio degli
esercizi completati che apre i gate di gamification.

**Un tocco, non due** (dal 2026-08-18). Su un esercizio superato/non superato il
tasto dell'esito **è** la registrazione: scegliere e poi confermare erano due
gesti per un'informazione sola, e fra i due si perde il segno di cosa si era
scelto. A proteggere dall'errore c'è l'`annulla`, che è l'unico posto dove la
protezione serve davvero — dopo. Sugli esercizi a punteggio il numero va
composto, quindi il tastierino resta e la conferma è un tasto a parte, ma il
giro di richiesta è identico.

**Il tabellone orizzontale.** Girando il telefono
(`templates/challenge/_training_board.html`) foto, regola e comandi stanno in una
schermata sola, come il tabellone della partita: chi si allena il telefono non ce
l'ha in mano, ce l'ha appoggiato alla sponda, e in verticale servivano tre
scorrimenti fra un tiro e l'altro. **Non è una seconda schermata**: gli stessi
`data-*`, lo stesso JavaScript, gli stessi contatori del formato verticale — il
codice lavora per selettore e non per `id` proprio perché i comandi esistono due
volte nello stesso documento.

Il drill giocato **al posto del bye in gara** non passa di qui: ha un contesto
(gara, turno) e conseguenze in classifica, e resta su `challenge.start_attempt`.

---

## Disegnare un drill invece di fotografarlo

Chi propone un drill non sempre ha una foto del tavolo preparato. Il **builder**
(`challenge.diagram_builder`, `/challenges/builder`) è l'altra strada: si
dispongono le bilie, si tracciano i tiri, si salva.

Salvare scrive **due cose insieme**, e servono a mestieri diversi:

| Cosa | Colonna | A che serve |
|---|---|---|
| Immagine | `image_path` (NOT NULL) | **mostrare** il drill: catalogo, guida, notifiche |
| Scena JSON | `diagram_scene` (nullable) | **riaprirlo** e correggerlo |

Nessuna sa fare il mestiere dell'altra: da un PNG non si torna indietro alle
bilie, e una scena non entra in un `<img>`. `diagram_scene` a `NULL` non è un
dato mancante — dice «questo drill non è stato disegnato», ed è ciò che
distingue chi può riaprire il builder da chi può solo ri-fotografare.

**L'immagine la renderizza il browser**, non il server: il builder è l'unico
posto che sa come si disegna una scena, e riprodurne le regole lato server
significherebbe tenerne due copie destinate a divergere al primo ritocco
grafico. Il server non delega il resto: la scena passa da
`models/challenge/diagram.py::parse_scene` (JSON, oggetto, versione nota, lista
di elementi, tetto di 512 KB) e il file dall'ordinario `save_challenge_image`.

Le chiavi sconosciute della scena **si conservano**: il builder è un file che
cambia, e scartare ciò che oggi non riconosciamo farebbe perdere pezzi a un
drill riaperto domani, in silenzio.

**Due gate, non uno.** `@director_required` dice *chi* (è autorialità: il drill
lo eseguiranno tutti gli altri) e `@feature_required("use_drill_builder")` dice
*da quando* — soglia più severa di `create_challenge`, e su sola metrica come
vuole ADR-031.

⚠️ Il CSS e il JS vengono dal tool autonomo e stanno in
`static/css/drill-builder.css` e `static/js/drill-builder.js`. Il foglio è
**confinato sotto `.drill-builder`**: il tool stila `body`, `header` e
soprattutto `.btn`, che nell'app è di Bootstrap, quindi senza confine
ridisegnerebbe ogni pulsante di ogni schermata. Lo presidia
`tests/new/unit/test_drill_builder_css_scoped.py` — se arriva una versione
nuova del builder si **ri-prefissa**, non si incolla grezzo.

---

## Challenge Types

| Type | `pass_fail_only` | Scoring | X-Substitution |
|------|------------------|---------|----------------|
| Numeric | `False` | Punteggio libero, con tetto facoltativo (`max_score`) | ✅ Yes |
| Pass/Fail | `True` | Pass=1, Fail=0 | ❌ No |

**Numeric Challenges:**
- `passed` field remains `None` (not applicable)
- Score determines X-substitution ranking
- Examples: spot shot rally, break shots

**Pass/Fail Challenges:**
- `passed` is explicitly `True` or `False`
- Cannot be used for X-substitution

---

## Models

### Challenge
**Fields:** `title`, `description`, `image_path`, `pass_fail_only`, `max_score`,
`diagram_scene`, `is_active`

> ⚠️ `Challenge` **non ha** `name`: il nome mostrato è `get_display_name()`, che
> restituisce il `title` scelto oppure il progressivo (`Esercizio 12`). Non è
> più la descrizione troncata — quella faceva sembrare identici esercizi diversi,
> perché le istruzioni cominciano quasi sempre allo stesso modo.

> ⚠️ **Due `max_score`, e non sono lo stesso** (ADR-042 + emendamento
> 2026-08-18). Entrambi facoltativi, entrambi legittimamente `NULL`:
>
> | colonna | risponde a | la decide |
> |---|---|---|
> | `Challenge.max_score` | quanto vale **al massimo questa prova** | chi crea l'esercizio |
> | `ExamChallenge.max_score` | quanto pesa **dentro quell'esame** | chi compone l'esame |
>
> `effective_max_score` **non** guarda il catalogo, e non deve iniziare a
> farlo: derivarlo renderebbe di nuovo impossibile far pesare lo stesso
> esercizio in due modi in due esami. Il primo serve dove l'esame non arriva —
> mostrare «12 / 15» a chi si allena, e rifiutare un 20 su una prova da 15.
>
> Storicamente `challenge.max_score` **non esisteva** e veniva letto lo stesso,
> dentro un `except Exception: pass`: è il bug che ha tenuto vuoto lo storico
> drill del profilo per mesi. Oggi la colonna c'è, quindi quel difetto non si
> riproduce più cercando un `AttributeError`.

### ChallengeAttempt
**Fields:** `challenge_id`, `user_id`, `score`, `passed`, `attempted_at`

Una prova si **cancella**, con `ChallengeService.delete_attempt`. Non è una
concessione: si registra con un tocco solo, col telefono appoggiato alla sponda,
e il tasto sbagliato si preme. Senza via d'uscita l'unico rimedio sarebbe
compensare a mano, sbagliando due volte invece di una.

Cancellare **disfa quello che la prova aveva prodotto**, e lo fa
**ricalcolando, non sottraendo**. La differenza è tutto il punto: se altri
esercizi reggono comunque la serie o il traguardo, non cambia niente — chi si
allena tutti i giorni non deve perdere la serie per un tocco sbagliato.

| cosa | come torna indietro |
|---|---|
| **XP della prova** | movimento compensativo (negativo), non cancellazione di quello originale: il registro racconta cos'è successo |
| **serie `WEEKLY_DRILL` e `WEEKLY_ACTIVITY`** | ricostruite dalle settimane in cui l'attività c'è *davvero*. `WEEKLY_ACTIVITY` si nutre anche di partite e iscrizioni: se la settimana resta viva per quelle, resta viva |
| **traguardi legati agli esercizi** | rivalutati sulla fonte di verità; cadono solo se il conto non li regge più, e restituiscono il loro XP |
| **congelamenti e `milestone_*_reached`** | **non** si toccano: un congelamento speso non si rimette nel cassetto, e azzerare il flag aprirebbe un modo di guadagnarne uno nuovo |

Il ricalcolo è `GamificationRecalcService.recompute_after_drill_removed`, e
**non** è `_rebuild_streaks`: quello azzera i congelamenti perché ricostruisce
un account dopo una fusione, qui si sta correggendo un tocco sbagliato.

### ChallengeFavorite
**Fields:** `user_id`, `challenge_id` - Quick access to preferred challenges

---

## Eventi di dominio

`ChallengeAttemptCompletedEvent` (`models/challenge/events.py`) annuncia il drill
completato. Il dominio **non** chiama la gamification: pubblica il fatto, e chi
vuole ascolta — stessa regola dell'esame.

Lo pubblicano `ChallengeService.complete_challenge_attempt` (catalogo),
`ChallengeService.complete_x_replacement_attempt` (drill al posto del bye) e
`GaraChallengeService.record_challenge_attempt` (drill di turno). L'evento porta
`origin` e `attempt_number` perché in gara la stessa prova si ripete fino a
`max_attempts`: chi ascolta deve distinguere un allenamento nuovo da un secondo
tiro. Le conseguenze (XP, streak `WEEKLY_DRILL`) stanno in
`models/gamification/CLAUDE.md`.

---

## Gara Challenge Integration

For X-substitution in tournaments with odd players:

```python
from models.challenge.gara_challenge_service import GaraChallengeService

# Assign challenge to bye player
GaraChallengeService.assign_challenge_to_player(
    gara_id=gara.id,
    user_id=bye_player.id,
    challenge_id=challenge.id
)

# Record result (affects round classification)
GaraChallengeService.record_challenge_result(
    gara_id=gara.id,
    user_id=bye_player.id,
    score=12
)
```

---

## Do Not

- **Do not use pass/fail challenges for X-substitution** - Only numeric challenges allowed
- **Do not set `passed` for numeric challenges** - Leave as `None`
- **Do not assume 70% pass threshold** - Removed; pass/fail is explicit only
- **Do not call `db.session.commit()`** - Services use `@transactional`

---

## Cross-References

- **Competition**: [../competition/CLAUDE.md](../competition/CLAUDE.md) - X-substitution integration
- **Matchmaking**: [../matchmaking/CLAUDE.md](../matchmaking/CLAUDE.md) - OddNumberPolicy.CHALLENGE
