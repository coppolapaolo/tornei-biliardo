# Archivio documentazione

Questa cartella contiene **documentazione storica congelata**: handoff post-sessione, piani di refactoring completati, audit chiusi, snapshot BMad precedenti. **Non è documentazione viva** e non viene aggiornata.

Conservata per due ragioni:

1. **Contesto retrospettivo**: capire *perché* certe scelte di processo furono prese (non solo *cosa*, che si ricostruisce dal codice).
2. **Riferimento da link esterni**: alcuni commenti nel codice (es. `models/competition/models.py`) puntano a vecchi ADR del file pre-folder `_archive/2025-12-architectural-decisions-pre-adr.md`.

## Indice

### 2025

- [`2025-09-refactoring-amalfi/`](./2025-09-refactoring-amalfi/) — refactoring algoritmo Amalfi e dei value object Distance/Score (Phase 1-6, completate)
- [`2025-10-refactoring-base-match.md`](./2025-10-refactoring-base-match.md) — unificazione UX rack tra `Match` e `IndividualMatch` via `BaseMatchMixin`
- [`2025-10-ux-individual-match-simplified.md`](./2025-10-ux-individual-match-simplified.md) — snapshot UX semplificata individual match
- [`2025-12-architectural-decisions-pre-adr.md`](./2025-12-architectural-decisions-pre-adr.md) — vecchio formato ADR pre-folder `docs/adr/` (ADR-001..005 storici, distinti dai nuovi)
- [`2025-12-audit-refactoring-plan.md`](./2025-12-audit-refactoring-plan.md) — piano audit chiuso 31-dic-2025 (0 FAIL / 0 WARNING)
- [`2025-12-todo-backlog.md`](./2025-12-todo-backlog.md) — backlog audit completato

### 2026

- [`2026-01-handoffs/`](./2026-01-handoffs/) — handoff sessioni gennaio (bug-fixes, individual match completion, confirm migration)
- [`2026-01-handoff-classification.md`](./2026-01-handoff-classification.md) — handoff redesign sistema classifiche
- [`2026-01-plans/`](./2026-01-plans/) — design doc di feature ormai implementate (mobile-first, match start/end times, bootstrap notifications, trio rack undo, wizard classification)
- [`2026-01-spareggio-ssr-spec.md`](./2026-01-spareggio-ssr-spec.md) — spec spareggio SSR (implementato in `models/competition/spareggio_service.py`)
- [`2026-02-handoff-technical-debt.md`](./2026-02-handoff-technical-debt.md) — handoff refactoring technical debt (round 1-6 completi)
- [`2026-04-bmad-project-overview.md`](./2026-04-bmad-project-overview.md) — snapshot project overview generato da BMad il 2026-04-04 (sostituito dalla rigenerazione corrente)

## Quando aggiungere qui

Quando un documento di processo è esplicitamente **completato/congelato** e non rappresenta più informazione utile per chi opera sul codice oggi, ma non si vuole perderne la traccia. Esempi: handoff post-sessione, progress tracker di sprint chiusi, audit conclusi.

Quando **non** aggiungere qui:

- Documentazione di riferimento ancora valida → `docs/reference/`
- Decisioni architetturali → `docs/adr/`
- Backlog/wishlist ancora attivi → `docs/wishlist*.md` o ADR proposed
