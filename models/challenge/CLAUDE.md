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
nessuno chiude più — invisibile, ma capace di falsare il conteggio dei drill
completati che apre i gate di gamification.

Il drill giocato **al posto del bye in gara** non passa di qui: ha un contesto
(gara, turno) e conseguenze in classifica, e resta su `challenge.start_attempt`.

---

## Challenge Types

| Type | `pass_fail_only` | Scoring | X-Substitution |
|------|------------------|---------|----------------|
| Numeric | `False` | Punteggio libero (il massimo lo fissa l'esame) | ✅ Yes |
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
**Fields:** `description`, `image_path`, `pass_fail_only`, `is_active`

> ⚠️ `Challenge` **non ha** `max_score`, né `name`. Il punteggio massimo è
> *per-esame* e sta su `ExamChallenge` (ADR-042): lo stesso drill può valere 10
> in un esame e 15 in un altro. Leggere `challenge.max_score` solleva
> `AttributeError` — è il bug che ha tenuto vuoto lo storico drill del profilo
> per mesi, perché finiva dentro un `except Exception: pass`. Per il nome
> mostrato si usa `get_display_name()`, che è la descrizione troncata: il vero
> nome è un debito noto, annotato in ADR-042.

### ChallengeAttempt
**Fields:** `challenge_id`, `user_id`, `score`, `passed`, `attempted_at`

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
