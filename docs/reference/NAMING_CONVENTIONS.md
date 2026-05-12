# Naming Conventions

Convenzioni di nomenclatura per tornei-biliardo. Le regole codificano
prassi già presente nei documenti di progetto (`SPECIFICHE.md`, ADR)
ma non finora resa esplicita per il codice.

Scopo: rendere prevedibile il naming nei nuovi PR e dare un riferimento
oggettivo nelle review. Le violazioni esistenti diventano debito da
ripulire **organicamente** quando si tocca un file per altri motivi
(vedi `CLAUDE.md` → principio "Fix pre-existing issues"); non è
richiesto un PR di rename retroattivo unico.

---

## 1. Lingua dei termini di dominio

I concetti di business del biliardo sono in **italiano**, perché:
- è la lingua dell'utente e dell'UI;
- è la lingua di `docs/reference/SPECIFICHE.md` (requisiti);
- è la lingua usata nei commit, ADR, commenti di codice.

Termini italiani canonici:

| Singolare | Plurale italiano | Significato |
|---|---|---|
| `campionato` | `campionati` | Tournament container con più gare |
| `gara` | `gare` | Singola competizione (standalone o di campionato) |
| `iscrizione` | `iscrizioni` | Registrazione di un giocatore a una gara |
| `partita` | `partite` | Singolo confronto fra giocatori (1v1 o trio) |
| `turno` | `turni` | Round di matchmaking dentro una gara |
| `tavolo` | `tavoli` | Sede fisica di una partita |

### Eccezione storica: `Match`

Il modello `models.match.models.Match` mantiene il nome inglese perché
è stato chiamato così dall'inizio e ha relazioni nominate in tutto il
codice. È l'unica eccezione **dichiarata** alla regola "termini italiani
in italiano".

**Convenzione duale**: quando ci si riferisce al concetto, usare
`partita` nei testi e nei commenti italiani; usare `Match` nel codice
Python solo come riferimento al modello SQLAlchemy.

---

## 2. Plurali italiani (non anglicizzare con `-s`)

**Regola tassativa**: il plurale di un termine italiano è il plurale
italiano. **Mai** aggiungere `-s` come se fosse inglese.

✅ Corretto:

```python
campionati = Campionato.query.all()
def gare_attive(): ...
url_for("main.public_campionati_list")
template = "campionati_list.html"
```

❌ Sbagliato (anti-pattern):

```python
campionatos = Campionato.query.all()       # NO
def garas_attive(): ...                    # NO
url_for("main.public_campionatos_list")    # NO
template = "campionatos_list.html"         # NO
```

### Perché succede

L'errore tipico è l'autocomplete dell'IDE che, vedendo un identifier
italiano, applica meccanicamente la regola inglese `singular + s →
plural`. Va corretto a vista.

### Violazioni note (debito tecnico)

Al momento della stesura ci sono ~100 occorrenze di `campionatos` nel
codebase, fra cui la route URL pubblica `/campionatos`. Vanno pulite
**organicamente** dai PR che già toccano quei file. Il rename della
route URL `/campionatos → /campionati` richiede redirect 301 e va
trattato in un PR dedicato quando si decide di farlo.

---

## 3. Nomi tecnici in inglese

I pattern e i suffissi tecnici restano in **inglese** perché parlano
al lettore del framework, non del dominio:

- Suffissi: `Service`, `Repository`, `Builder`, `Strategy`,
  `Handler`, `Factory`, `Bridge`, `Manager`.
- Pattern: `ViewModel`, `DataClass`, `Mixin`, `Adapter`.
- Layer/folder: `models/`, `routes/`, `templates/`, `tests/`.

Esempi corretti:

```python
class HomepageService:        # Service inglese, dominio Homepage
class MatchmakingStrategy:    # Strategy inglese, dominio Matchmaking
class GaraService:            # Service inglese, dominio Gara
class CampionatoService:      # NOTA: NON CampionatoesService né CampionatiService
```

Le **classi `Service`** sono sempre con il modello singolare (`Gara`,
`Campionato`, `Iscrizione`, ecc.) perché operano sul "tipo" non sulla
collezione. Il plurale italiano si applica a **variabili e funzioni
che restituiscono collezioni** (es. `def get_campionati_attivi()`).

---

## 4. URL pubbliche

Pattern: lowercase, separatore `_` (coerente col resto del codice
Python), in italiano per i concetti di dominio.

✅ Corretto:

```
/campionati
/gare
/profilo
/campionato/<id>/public
/gara/<id>
```

❌ Da evitare in URL nuove:

```
/campionatos       (anglicizzazione)
/championships     (inglese)
/competition-list  (dash + inglese)
```

URL **già esposte in produzione** che violano la regola vanno
considerate API contract: cambiarle richiede gestire redirect 301 e
non si fa "per pulizia" in un PR generico.

---

## 5. Codice Python — PEP-8 + dominio

Standard:

- **Funzioni / variabili**: `snake_case`.
- **Classi**: `PascalCase`.
- **Costanti modulo**: `UPPER_SNAKE_CASE`.
- **Privati**: prefisso `_` (es. `_compute_user_stats`).

Lingua degli identifier:

- Termini di dominio in **italiano** (regola §1): `campionato`,
  `iscrivi_utente`, `gare_attive`.
- Termini tecnici / framework in **inglese**: `service`, `query`,
  `handler`, `view_model`.

Mix accettabile (è la norma del codebase):

```python
def get_campionati_attivi(user_id: int) -> list[Campionato]: ...
class CampionatoService:
    def create_campionato_with_director(...): ...   # dominio italiano + tecnico inglese
campionati_q = campionatos_q   # legacy alias (debito) — preferire il nome corretto in nuovo codice
```

---

## 6. Test

I nomi dei test:

- File: `test_<area>_<aspetto>.py` (es.
  `test_homepage_completed_campionato.py`).
- Classe: `Test<CapabilitàTest>` (es. `TestHomepageCompletedCampionato`).
- Funzione: `test_<comportamento>_<condizione>` (es.
  `test_completed_campionato_does_not_count_as_active`).

Lingua: i nomi tendono a essere in inglese (sono "specifiche
eseguibili" e l'inglese è più stringato), ma i termini di dominio
italiani sono accettati (es. `test_avvio_playoff_route`).

---

## 7. Database column names

In **inglese** quando è un campo strutturale/tecnico (`created_at`,
`updated_at`, `is_active`, `is_deleted`, `user_id`).

In **italiano** quando è un attributo di business reso fedelmente
(`numero_gara`, `nome_campionato`).

Convenzione: `snake_case` SQL.

---

## 8. Eccezioni esplicite

Le eccezioni alle regole sopra vanno **dichiarate** qui in modo
duraturo, per non riaprire la discussione caso per caso. Aggiungere
una sotto-sezione con motivazione.

### 8.1 `Match` (vedi §1)

Mantenuto in inglese perché il modello SQLAlchemy ha quel nome dalla
prima versione del codebase. Conseguenze acettate:

- `Match.query`, `match_id`, `models/match/models.py`.
- Nei testi UI e nei commenti italiani si usa "partita".

### 8.2 URL `/campionatos` (legacy, da migrare)

Non è una eccezione *permanente*: è una violazione conosciuta che
richiede redirect 301 per essere chiusa. Tracciata come debito tecnico.

---

## Riferimenti

- `CLAUDE.md` → sezione 14 (rimando rapido)
- `docs/reference/SPECIFICHE.md` → termini di dominio
- Memory `feedback_italian_plurals.md` → enforcement automatico per
  Claude in nuovo codice
