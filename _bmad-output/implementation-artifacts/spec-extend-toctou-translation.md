---
title: 'Estendere traduzione TOCTOU ValueError a report_result'
type: 'bugfix'
created: '2026-04-05'
status: 'done'
baseline_commit: '36bca1e'
context: ['CLAUDE.md', 'docs/adr/ADR-025-savepoint-integrity-error-translation.md']
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Il fix TOCTOU su `proposal.accept()` (commit `1d0a486`, ADR-025) ha wrappato solo `ProposalService.accept_proposal`. Un secondo caller attivo — `MatchLifecycleService.report_result` (match_lifecycle_service.py:122) — chiama ancora `proposal.accept(reporter_id)` senza savepoint: se il constraint UNIQUE su `individual_match.proposal_id` scatta per una race, l'utente vede un `IntegrityError` grezzo invece di un `ValueError` di dominio. Il terzo caller, `ProposalInvitation.accept` (proposal_models.py:323), è dead code (nessun route lo raggiunge, un solo test lo bypassa) ma è un'API del modello esposta e il suo contratto non è documentato.

**Approach:** Applicare il pattern savepoint+flush+traduzione (ADR-025) al sito attivo `report_result`. Per `ProposalInvitation.accept`, che è model-layer, NON applicare savepoint (violerebbe la rule 1 di ADR-025 "pattern in service methods") ma aggiungere docstring esplicito che documenta il contratto IntegrityError per future chiamate dirette.

## Boundaries & Constraints

**Always:**
- `report_result` mantiene `@transactional(domain="individual_match")`; il savepoint è aggiunto DENTRO al metodo, non sostituisce la transazione esterna.
- Il messaggio `ValueError` in `report_result` deve essere consistente con quello usato in `accept_proposal`: `_("Proposta già accettata")`.
- Usare `from flask_babel import _` (non `lazy_gettext`) come da ADR-025.
- Il docstring di `ProposalInvitation.accept` deve citare ADR-025 e chiarire che i caller sono responsabili del wrapping savepoint.

**Ask First:**
- Nessuna — scope chiuso.

**Never:**
- Non aggiungere savepoint/i18n strings dentro `ProposalInvitation.accept` (model method, viola ADR-025).
- Non modificare `MatchProposal.accept()` stesso (resta raw, per design).
- Non rimuovere `ProposalInvitation.accept` anche se dead code (fuori scope).
- Non introdurre nuovi `@transactional` o cambiare la decorazione esistente di `report_result`.
- Non toccare il flow `accept_proposal` già corretto.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Happy report_result su proposal PENDING | Proposta pending senza match esistente | accept() crea match, poi complete_match procede | N/A |
| TOCTOU race su report_result | Proposta pending ma match con stesso proposal_id già esiste (concurrent accept) | `ValueError("Proposta già accettata")` | `IntegrityError` su savepoint flush → ValueError |
| report_result su proposal non-PENDING | Proposta già ACCEPTED con match esistente | Branch esistente `IndividualMatch.query.filter_by` → complete_match | N/A (percorso attuale) |
| report_result senza match (non-PENDING) | Proposta CLOSED senza individual_match | `ValueError("No individual match found for this proposal")` | già gestito |
| Direct call ProposalInvitation.accept | Test/codice che chiama il modello direttamente | Comportamento invariato, docstring avvisa del contratto | Caller responsabile |

</frozen-after-approval>

## Code Map

- `models/individual_match/match_lifecycle_service.py` -- `report_result` (L107-134) — sito principale: wrappare `proposal.accept(reporter_id)` con savepoint
- `models/individual_match/proposal_models.py` -- `ProposalInvitation.accept` (L314-323) — aggiungere docstring contract
- `models/individual_match/proposal_service.py` -- `accept_proposal` (L432-441) — pattern di riferimento da imitare (read-only)
- `docs/adr/ADR-025-savepoint-integrity-error-translation.md` -- riferimento pattern (read-only)
- `tests/new/integration/test_unique_constraints_toctou.py` -- pattern di test TOCTOU esistente (helpers `_make_open_proposal`, `_make_match`, `_make_user`)

## Tasks & Acceptance

**Execution:**
- [x] `models/individual_match/match_lifecycle_service.py` -- importare `IntegrityError` da `sqlalchemy.exc` e `_` da `flask_babel`; wrappare la chiamata `proposal.accept(reporter_id)` in `db.session.begin_nested()` + `db.session.flush()`, traducendo `IntegrityError` in `ValueError(_("Proposta già accettata"))` -- chiude il gap TOCTOU sul percorso attivo
- [x] `models/individual_match/proposal_models.py` -- aggiornare docstring di `ProposalInvitation.accept` per documentare che può sollevare `IntegrityError` in scenari TOCTOU e che i caller sono responsabili del wrapping savepoint/traduzione per ADR-025 -- contratto API chiaro
- [x] `tests/new/integration/test_unique_constraints_toctou.py` -- aggiungere `test_report_result_race_raises_value_error`: precreare `IndividualMatch` con `proposal_id=X` (simula concurrent accept) lasciando proposal.status=PENDING, chiamare `MatchLifecycleService.report_result(X, ...)`, assertare `ValueError` con messaggio "già accettata" (no doppio match creato) -- copre la race condition end-to-end
- [x] `tests/new/integration/test_unique_constraints_toctou.py` -- aggiungere `test_report_result_happy_path_unaffected`: proposal pending senza match esistente, `report_result` completa senza errori e il match è creato + completato -- regressione happy path

**Acceptance Criteria:**
- Given una proposta PENDING e un `IndividualMatch` già esistente con lo stesso `proposal_id` (simulazione race), when si chiama `MatchLifecycleService.report_result`, then viene sollevato `ValueError` con messaggio "Proposta già accettata" e nessun secondo match viene creato.
- Given una proposta PENDING senza match, when si chiama `report_result` con dati validi, then il match viene creato e completato senza errori (happy path invariato).
- Given chiunque legga il codice di `ProposalInvitation.accept`, when consulta il docstring, then trova documentato il contratto IntegrityError con riferimento esplicito ad ADR-025.
- Given `accept_proposal` decorato con `@transactional`, when si esamina `report_result`, then il pattern savepoint applicato è identico (stessa sintassi `begin_nested()` + `flush()` + `except IntegrityError`).

## Verification

**Commands:**
- `pyright` -- expected: 0 errors
- `pytest tests/new/integration/test_unique_constraints_toctou.py -v -n 4 2>&1 | tail -1` -- expected: all passed (2 nuovi + esistenti)
- `pytest tests/new/ -n 4 2>&1 | tail -1` -- expected: nessuna regressione
- `black . && flake8` -- expected: clean
