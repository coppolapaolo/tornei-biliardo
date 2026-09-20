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
`diagram_scene`, `is_active` — più il profilo (`declared_level`, `family`,
`family_step`, `cue_ball_reset`, vedi sotto)

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

### Il profilo: che cosa allena, quanto è difficile, in che varianti (ADR-065)

`Challenge` dice *come si valuta* la prova; il **profilo** dice *come si trova*.
Tutto facoltativo, e `NULL` vuol dire «l'autore non l'ha detto» — mai un default
inventato, nemmeno in migration.

| cosa | dove | note |
|---|---|---|
| **abilità** (al più 3) e **gesti** (senza tetto) | `challenge_category (axis, value)` → `challenge.abilita`, `challenge.gesti` | vocabolari **fissi**, enum in `vocabulary.py`; su disco va il *valore*, in colonne `String` |
| livello **dichiarato** 1–5 | `declared_level` | non «difficoltà»: quella misurata (#174) gli starà accanto |
| famiglia e passo | `family`, `family_step` | liberi dell'autore; un passo senza famiglia si rifiuta |
| la bianca | `cue_ball_reset` | `True` si rimette, `False` resta dove si ferma |
| varianti (dx/sx, A/B) | `challenge_variant` + `ChallengeAttempt.variant_id` | **mai un secondo esercizio**; con prove si rinomina, non si toglie |
| voto 1–5 | `challenge_rating` | uno per giocatore, unicità e `CHECK` nello schema |

```python
from models.challenge.profile_service import ChallengeProfileService, copy_profile
from models.challenge.popularity import popularity_for, has_tried

ChallengeProfileService.set_profile(
    challenge.id,
    abilita=["posizione", "tiro"],      # sostituisce l'elenco
    gesti=["draw"],
    declared_level=2,
    variants=[{"id": 7, "label": "destra"}, {"label": "sinistra"}],
)
numeri = popularity_for([c.id for c in esercizi])   # tre query, non tre per card
```

* **Non inviato ≠ vuoto**: ogni argomento di `set_profile` ha default `UNSET`;
  `None` o `[]` vuol dire «toglilo».
* Il profilo **non** passa da `update_challenge`: quello cambia il senso dei
  punteggi già registrati (e il modulo chiede se farne una copia), questo no.
* «Quanti l'hanno provato» **si conta**, non si salva: prove *completate* dal
  catalogo ∪ in gara, le stesse fonti dello storico. `has_tried` è anche la
  regola di chi può votare — una funzione sola perché non divergano.
* `copy_profile(originale, copia)` porta il profilo, non prove né voti.

### Il modulo unico: crea, modifica, duplica (#252, #253)

Le tre route (`create_challenge`, `edit_challenge`, `duplicate_challenge`)
rendono **lo stesso** `challenge/form.html`, leggono i campi con **un** parser
(`routes/challenge_form.py::parse_challenge_draft` → `ChallengeDraft`) e salvano
da **una** porta, `models/challenge/authoring.py::ChallengeAuthoringService`,
che scrive valutazione e profilo nella stessa transazione.

**«Ha già delle prove».** Se il salvataggio cambia il *senso* dei punteggi — tipo
di valutazione, massimo, istruzioni (`meaning_changes`) — e l'esercizio ha prove
(`evidence`: catalogo + gara + **esami**), `update` non salva e solleva
`EvidenceDecisionRequired`. La route risponde **409** con `needs_decision`; il
browser apre il foglio e rispedisce lo stesso modulo con `on_evidence=copy` o
`overwrite`. Titolo, profilo, foto e «nel catalogo» passano lisci. La decisione
sta nel servizio, non nel JavaScript: una POST scritta a mano non la salta.

* La **copia** è di chi la fa (`created_by_id`), nasce senza prove, voti e
  preferiti, e ha un **file immagine suo** (`ImagePathManager.copy_challenge_image`):
  risalvare un disegno cancella l'immagine di prima, quindi due esercizi sullo
  stesso file vuol dire che ritoccando l'uno si spegne l'altro.
* I file li gestisce la route, prima e dopo il servizio: se il servizio rifiuta,
  il file appena scritto si toglie.
* Una **foto nuova** al posto di un disegno azzera `diagram_scene`.
* Il **disegnatore** salva anche istruzioni e punteggio ma non ha il foglio:
  `_refuse_meaning_change_from_builder` gli fa salvare solo il disegno quando ci
  sono prove. Senza, sarebbe la porta sul retro della #252.

### «Oggi», il catalogo che si filtra, la scheda (fase 4c)

`/challenges/` è **«Oggi»** (`challenge.today`), la porta d'ingresso: riprendi
l'ultimo esercizio, i preferiti, i più provati. Il catalogo sta dietro, su
`/challenges/catalog` (`challenge.challenge_catalog`). L'admin non si allena:
«Oggi» lo manda al catalogo. «Oggi» crescerà da sola: scheda in corso (fase 6),
obiettivi e consigli (fase 7) — niente segnaposto vuoti nel frattempo.

Le due viste, e la card della scheda, vengono da
`models/challenge/catalog_view.py` (`build_today`, `build_catalog`,
`build_card`, `variant_lines`): stessa forma di `models/exam/overview.py`. Un
numero fisso di query qualunque sia la lunghezza del catalogo — la card di prima
chiamava `get_statistics()` a ogni giro, cioè caricava tutte le prove di ogni
esercizio per stampare due numeri.

* **I filtri sono collegamenti**, non JavaScript: `CatalogFilter.from_args`
  legge la query string (`abilita`, `gesto`, `livello`, `voto`, `ordine`,
  `vista`), `to_args(gesto=None)` dà l'indirizzo con una voce cambiata — è così
  che la pillola accesa, ritoccata, si spegne. Un valore ignoto vale «nessun
  filtro», mai un errore.
* La riga «Media 63% · ultime tre 89%» viene dalle **stesse due fonti** dello
  storico (`TrainingHistoryService.get_drill_attempts`): catalogo e gara.
* I pezzi con cui un esercizio si presenta — etichette, voto e giocatori, riga
  di chi guarda, card — stanno in `templates/challenge/_exercise_bits.html`.
* La **variante** si sceglie nella schermata di allenamento (pillole «Da che
  parte», con «senza dirlo» accesa) e viaggia con ogni prova; la scheda mostra
  una riga per variante.

### ChallengeAttempt
**Fields:** `challenge_id`, `user_id`, `score`, `passed`, `attempted_at`, `variant_id`

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
