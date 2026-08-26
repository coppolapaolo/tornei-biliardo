# Architecture Decision Records (ADR)

Questa directory contiene le decisioni architetturali significative del progetto.

## Cos'e un ADR?

Un Architecture Decision Record (ADR) cattura una decisione architetturale importante insieme al suo contesto e alle conseguenze. E un documento che spiega **perche** abbiamo fatto una scelta, non solo **cosa** abbiamo scelto.

## Quando Creare un ADR

Crea un ADR quando:
- Scegli un pattern architetturale
- Introduci una nuova libreria/dipendenza
- Definisci una convenzione di codice significativa
- Prendi una decisione con trade-off importanti
- Modifichi un comportamento fondamentale del sistema

## Indice Decisioni

| # | Titolo | Stato | Data |
|---|--------|-------|------|
| ADR-001 | [Amalfi Strategy Pattern Unification](ADR-001-Amalfi-Strategy-Pattern-Unification.md) | Accepted | 2025-09 |
| ADR-002 | [Fix Anti-Rematch Encounter Cleanup](ADR-002-fix-anti-rematch-encounter-cleanup.md) | Accepted | 2025-12-28 |
| ADR-003 | [User Privacy System](ADR-003-user-privacy-system.md) | Accepted | 2025-12-28 |
| ADR-004 | [Challenge/Gara Decoupling](ADR-004-challenge-gara-decoupling.md) | Accepted | 2025-12-29 |
| ADR-005 | [Regole Distanza, Classifica e Trio](ADR-005-distance-classification-trio-rules.md) | Accepted | 2025-12 |
| ADR-006 | [SSE Event Bridge Architecture](ADR-006-sse-event-bridge.md) | Superseded | 2025-12 |
| ADR-007 | [Revisione Gestione SSR](ADR-007-ssr-management-revision.md) | Accepted | 2025-12 |
| ADR-012 | [Fix Circular Import in @transactional](ADR-012-transactional-circular-import-fix.md) | Accepted | 2025-12 |
| ADR-013 | [Redesign Sistema di Classificazione](ADR-013-classification-system-redesign.md) | Accepted | 2025-12 |
| ADR-014 | [Mobile-First Card Layout per Vista Gara](ADR-014-mobile-first-card-layout.md) | Accepted | 2025-12 |
| ADR-015 | [Table Assignment - PLAYING Status Fix](ADR-015-table-assignment-playing-status-fix.md) | Accepted | 2026-01 |
| ADR-016 | [Validazione Sequenziale Date Gare](ADR-016-gara-sequential-date-validation.md) | Accepted | 2026-01 |
| ADR-017 | [Campo Mancante racks_won nel Modello Classification](ADR-017-classification-model-missing-racks-won.md) | Accepted | 2026-01 |
| ADR-018 | [Separazione Jinja2 e JavaScript](ADR-018-jinja2-js-separation.md) | Accepted | 2026-01-25 |
| ADR-019 | [Gamification ABAC Migration](ADR-019-gamification-abac-migration.md) | Accepted | 2026-01 |
| ADR-020 | [Gamification System v2](ADR-020-gamification-system-v2.md) | Accepted | 2026-01 |
| ADR-021 | [SSE to Polling Migration](ADR-021-sse-to-polling-migration.md) | Accepted | 2026-01 |
| ADR-023 | [Match Status and Polling Fixes](ADR-023-match-status-and-polling-fixes.md) | Accepted | 2026-01 |
| ADR-024 | [Wizard Campionato e Sistema Playoff](ADR-024-wizard-campionato-e-sistema-playoff.md) | Accepted | 2026-01-07 |
| ADR-025 | [Savepoint + Flush per tradurre IntegrityError in ValueError](ADR-025-savepoint-integrity-error-translation.md) | Accepted | 2026-04-05 |
| ADR-026 | [Reset Match Preserves Pair Semantics](ADR-026-reset-match-preserves-pair-semantics.md) | Accepted | 2026-04 |
| ADR-027 | [Round-level Configuration Enforcement](ADR-027-round-level-configuration-enforcement.md) | Accepted | 2026-05 |
| ADR-028 | [Production Endpoint Allowlist](ADR-028-production-endpoint-allowlist.md) | Accepted | 2026-05-09 |
| ADR-029 | [Amalfi: garanzia zero-rematch nel caso pari](ADR-029-amalfi-zero-rematch-guarantee.md) | Accepted | 2026-05-10 |
| ADR-030 | [`Campionato.is_active` non implica "in corso"](ADR-030-campionato-is-active-vs-derived-status.md) | Accepted | 2026-05-12 |
| ADR-031 | [Modello di gating della gamification](ADR-031-gamification-gating-model.md) | Proposed | 2026-06-05 |
| ADR-032 | [Consolidamento della superficie di disponibilità](ADR-032-availability-surface-consolidation.md) | Accepted | 2026-06-06 |
| ADR-033 | [Rimozione della disponibilità "località" a testo libero](ADR-033-remove-free-text-locality-availability.md) | Accepted | 2026-06 |
| ADR-034 | [Modello geografico / di prossimità](ADR-034-geo-proximity-model.md) | Accepted | 2026-06 |
| ADR-035 | [Onboarding obbligatorio + backfill](ADR-035-mandatory-onboarding.md) | Accepted | 2026-06 |
| ADR-036 | [Segnale-domanda → director](ADR-036-demand-signal-to-director.md) | Accepted | 2026-06 |
| ADR-037 | [Leaderboard locale + contributo](ADR-037-local-contribution-leaderboard.md) | Accepted | 2026-06 |
| ADR-038 | [Il tabellone è un dato, non una ricostruzione](ADR-038-bracket-persistence.md) | Accepted | 2026-08-15 |
| ADR-039 | [Squadre: due livelli, e un sorteggio che rinvia i derby](ADR-039-team-separation-in-the-draw.md) | Accepted | 2026-08-15 |
| ADR-040 | [Classifica per posizione: pari merito voluti](ADR-040-position-classification-ties.md) | Accepted | 2026-08-15 |
| ADR-041 | [Ruoli concedibili: ortogonali a `user.role`, e delegabili a catena](ADR-041-grantable-roles-and-delegation.md) | Accepted | 2026-08-15 |
| ADR-042 | [L'esame e' un evento di persona, e l'esito e' un si' o un no](ADR-042-certified-exam.md) | Accepted | 2026-08-15 |
| ADR-043 | [L'orario e' quello di chi legge, e il fuso si deduce senza chiederlo](ADR-043-reader-timezone.md) | Accepted | 2026-08-15 |
| ADR-044 | [Il referto TPA: si annota il gioco, non il punteggio](ADR-044-tpa-scoresheet.md) | Accepted | 2026-08-16 |
| ADR-045 | [Niente WAL: SQLite sta su storage di rete](ADR-045-no-wal-on-network-storage.md) | Accepted | 2026-08-17 |
| ADR-046 | [Il beta tester vede in anticipo, non vede di più](ADR-046-beta-tester-visibility.md) | Accepted | 2026-08-18 |
| ADR-047 | [La classifica la decide il sistema di classifica, non il tipo di campionato](ADR-047-classification-system-drives-the-standings.md) | Accepted | 2026-08-18 |
| ADR-048 | [Spostare la partecipazione a una gara: fatti riassegnati, derivati ricalcolati](ADR-048-gara-scoped-participant-reassignment.md) | Accepted | 2026-08-19 |
| ADR-049 | [L'handicap non spegne l'Elo: lo spegne la differenza di categoria](ADR-049-same-category-restores-elo-in-handicap-events.md) | Accepted | 2026-08-19 |
| ADR-050 | [Il CSRF si difende con l'Origin, non con il referrer](ADR-050-csrf-origin-instead-of-referrer.md) | Accepted | 2026-08-19 |
| ADR-051 | [L'avvio rapido non toglie l'accettazione: la sposta alla fine](ADR-051-quick-start-moves-the-acceptance-to-the-end.md) | Accepted | 2026-08-20 |
| ADR-052 | [Fra Elo iterativo a rack e rifit globale si decide misurando](ADR-052-rating-model-decided-by-measurement.md) | Accepted | 2026-08-21 |
| ADR-053 | [Il peso della prova, e chi decide la classifica finale](ADR-053-playoff-weight-and-final-ranking-mode.md) | Accepted | 2026-08-23 |
| ADR-054 | [La versione la decidono i titoli delle PR](ADR-054-version-from-pull-request-titles.md) | Accepted | 2026-08-26 |
| ADR-055 | [La sessione è legata alla credenziale](ADR-055-session-bound-to-credential.md) | Accepted | 2026-08-26 |

## Come Creare un Nuovo ADR

1. Copia `TEMPLATE.md`
2. Rinomina in `ADR-NNN-titolo-kebab-case.md` (es. `ADR-004-use-transactional-decorator.md`)
3. Compila tutte le sezioni
4. Aggiorna questo README con il nuovo ADR

## Stati

| Stato | Significato |
|-------|-------------|
| **Proposed** | In discussione |
| **Accepted** | Approvato e in uso |
| **Deprecated** | Non piu raccomandato |
| **Superseded** | Sostituito (link al nuovo) |

## Riferimenti

- [ADR GitHub](https://adr.github.io/)
- [Michael Nygard - Documenting Architecture Decisions](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions)
