---
title: 'UNIQUE constraints per TOCTOU su proposte individual_match'
type: 'bugfix'
created: '2026-04-05'
status: 'done'
baseline_commit: '6c751e8'
context: ['CLAUDE.md', 'models/CLAUDE.md', 'models/individual_match/CLAUDE.md']
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Due race condition TOCTOU identificate da Edge Case Hunter permettono duplicati a livello applicativo:
(1) due utenti accettano la stessa `MatchProposal` OPEN concorrentemente → 2 `IndividualMatch` creati puntanti allo stesso `proposal_id`; (2) `invite_player_to_match` non ha duplicate-check → inviti ripetuti allo stesso utente per la stessa proposta. Il single-writer di SQLite mitiga ma non elimina: mantenere il guard solo a livello applicativo è fragile.

**Approach:** Aggiungere vincoli UNIQUE a livello DB come rete di sicurezza definitiva, e gestire `IntegrityError` nei service come fallback user-friendly. Migrazione via `CREATE UNIQUE INDEX IF NOT EXISTS` (no table rebuild, idempotente), con pre-check di duplicati esistenti che fallisce loud.

## Boundaries & Constraints

**Always:**
- `individual_match.proposal_id` UNIQUE ma nullable (NULL multipli consentiti per match senza proposta).
- `proposal_invitation(proposal_id, invited_user_id)` UNIQUE composito.
- Migrazione idempotente con nome `20260405_unique_constraints_toctou` e funzione `upgrade_sqlite(db_path)`.
- Servizi che possono violare il vincolo devono fare `db.session.flush()` dentro try e tradurre `IntegrityError` in `ValueError` con messaggio i18n-ready.
- Modelli aggiornati con `__table_args__ = (db.UniqueConstraint(...),)` per coerenza ORM/DB.

**Ask First:**
- Se il pre-check trova duplicati esistenti in produzione: HALT, non deduplicare automaticamente, chiedere all'utente come procedere.

**Never:**
- Non ricostruire le tabelle (pattern CREATE TABLE AS SELECT) — usare solo CREATE UNIQUE INDEX.
- Non silenziare `IntegrityError` come `except: pass` — deve tradursi in errore di dominio.
- Non modificare la logica di `proposal.accept()` / `invite_player_to_match` oltre la gestione errori.
- Non aggiungere lock applicativi o SELECT FOR UPDATE (scope creep, SQLite non li supporta).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Happy accept | Proposta OPEN pending, utente eligible | `IndividualMatch` creato, proposta ACCEPTED | N/A |
| Race double-accept | 2 utenti accettano la stessa proposta | 1 match creato, 2° chiamata → `ValueError("Proposta già accettata")` | `IntegrityError` su proposal_id → ValueError |
| Match senza proposta | `proposal_id = NULL` (match diretto) | Insert OK, nessun conflitto UNIQUE | N/A (NULL non collide) |
| Happy invite | Nuovo invito utente X alla proposta P | `ProposalInvitation` creata | N/A |
| Duplicate invite | Invito utente X già esistente su P | `ValueError("Giocatore già invitato")` | `IntegrityError` su (proposal_id, invited_user_id) → ValueError |
| Migrazione con duplicati | DB contiene già righe duplicate | HALT migrazione con errore esplicito e count duplicati | Raise con messaggio, nessun auto-fix |
| Migrazione idempotente | Indice già esistente | No-op, log "already exists" | IF NOT EXISTS |

</frozen-after-approval>

## Code Map

- `models/individual_match/match_models.py` -- `IndividualMatch` — aggiungere `__table_args__` con UniqueConstraint su `proposal_id`
- `models/individual_match/proposal_models.py` -- `ProposalInvitation` — aggiungere `__table_args__` con UniqueConstraint su `(proposal_id, invited_user_id)`
- `models/individual_match/proposal_service.py` -- `accept_proposal` (L402), `invite_player_to_match` (L255) — gestione IntegrityError
- `migrations/20260405_unique_constraints_toctou.py` -- NEW — migrazione con pre-check e CREATE UNIQUE INDEX
- `models/user/privacy_models.py` -- L60-74 — pattern di riferimento per `begin_nested()` + `IntegrityError`
- `tests/new/integration/test_unique_constraints_toctou.py` -- NEW — test delle due race condition

## Tasks & Acceptance

**Execution:**
- [x] `migrations/20260405_unique_constraints_toctou.py` -- NEW: pre-check duplicati + CREATE UNIQUE INDEX su `individual_match(proposal_id) WHERE proposal_id IS NOT NULL` e `proposal_invitation(proposal_id, invited_user_id)` -- crea il vincolo DB-level idempotente
- [x] `models/individual_match/match_models.py` -- aggiungere `__table_args__ = (db.UniqueConstraint("proposal_id", name="uq_individual_match_proposal"),)` a `IndividualMatch` -- allinea ORM al DB
- [x] `models/individual_match/proposal_models.py` -- aggiungere `__table_args__ = (db.UniqueConstraint("proposal_id", "invited_user_id", name="uq_proposal_invitation_user"),)` a `ProposalInvitation` -- allinea ORM al DB
- [x] `models/individual_match/proposal_service.py` -- in `invite_player_to_match` wrappare l'`add()` con `db.session.begin_nested()` + `try/except IntegrityError` → `ValueError(_("Giocatore già invitato a questa proposta"))` -- gestisce dup lato servizio
- [x] `models/individual_match/proposal_service.py` -- in `accept_proposal` dopo `proposal.accept(user_id)` chiamare `db.session.flush()` in try; su `IntegrityError` → `ValueError(_("Proposta già accettata"))` -- gestisce race double-accept
- [x] `tests/new/integration/test_unique_constraints_toctou.py` -- NEW: (a) creare due IndividualMatch con stesso `proposal_id` → IntegrityError; (b) due ProposalInvitation con stessa coppia → IntegrityError; (c) due proposal_id NULL consecutivi → OK; (d) `invite_player_to_match` duplicato → ValueError; (e) accept concorrente simulato con flush manuale → ValueError sul secondo -- copre l'I/O matrix
- [x] eseguire `python migrations/runner.py` su DB dev per applicare la migrazione

**Acceptance Criteria:**
- Given un `IndividualMatch` esistente con `proposal_id=42`, when si tenta di inserire un altro match con `proposal_id=42`, then la DB solleva `IntegrityError` sul vincolo `uq_individual_match_proposal`.
- Given una `ProposalInvitation(proposal_id=5, invited_user_id=10)` esistente, when si chiama `invite_player_to_match(5, inviter, 10)`, then il service solleva `ValueError` con messaggio "Giocatore già invitato".
- Given una proposta PENDING già accettata in una transazione concorrente, when un secondo utente chiama `accept_proposal`, then il service solleva `ValueError` con messaggio "Proposta già accettata" (no doppio match creato).
- Given un `IndividualMatch` con `proposal_id=NULL`, when se ne crea un altro con `proposal_id=NULL`, then entrambi persistono senza errori.
- Given il DB di dev senza duplicati, when si esegue `python migrations/runner.py`, then la migrazione completa con successo e risulta idempotente su run successivo.
- Given un DB con duplicati preesistenti, when si esegue la migrazione, then fallisce con messaggio esplicito contenente il conteggio dei duplicati (no auto-fix).

## Verification

**Commands:**
- `pyright` -- expected: 0 errors
- `python migrations/runner.py` -- expected: migrazione applicata; secondo run = skipped
- `pytest tests/new/integration/test_unique_constraints_toctou.py -v -n 4 2>&1 | tail -1` -- expected: all passed
- `pytest tests/new/ -n 4 2>&1 | tail -1` -- expected: nessuna regressione
- `black . && flake8` -- expected: clean

## Suggested Review Order

**DB schema — the actual constraints**

- Pre-check + partial UNIQUE index, idempotent via IF NOT EXISTS.
  [`20260405_unique_constraints_toctou.py:67`](../../migrations/20260405_unique_constraints_toctou.py#L67)

- Entry point: UC on `proposal_id` with nullable-friendly semantics.
  [`match_models.py:105`](../../models/individual_match/match_models.py#L105)

- Composite UC `(proposal_id, invited_user_id)` for invitations.
  [`proposal_models.py:308`](../../models/individual_match/proposal_models.py#L308)

**Service-level error translation**

- Savepoint forces flush-time IntegrityError → user-friendly ValueError.
  [`proposal_service.py:432`](../../models/individual_match/proposal_service.py#L432)

- Same pattern for duplicate-invite guard.
  [`proposal_service.py:273`](../../models/individual_match/proposal_service.py#L273)

**Tests**

- DB-level constraints + service-level error translation + NULL multiplicity.
  [`test_unique_constraints_toctou.py:79`](../../tests/new/integration/test_unique_constraints_toctou.py#L79)
