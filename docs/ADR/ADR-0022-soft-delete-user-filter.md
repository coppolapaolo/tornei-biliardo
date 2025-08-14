# ADR-0022 — Filtro globale Soft-Delete per User
**Data**: 2025-08-13 — **Stato**: Accettata

## Contesto
Introdotto soft-delete utenti tramite `SoftDeleteMixin.deleted_at`. Alcune view (`/admin/tournament/<id>`, `/admin/users`) mostravano ancora utenti cancellati.

## Decisione
Filtro ORM globale su `User` con `do_orm_execute` + `with_loader_criteria`, registrato su `sqlalchemy.orm.Session` per coprire tutte le sessioni (anche nei test). Opt-out con `execution_options(include_deleted=True)`.

## Alternative scartate
1. Filtro locale per view/service → duplicazione e rischio regressioni.
2. Repository obbligatorio `list_active_users()` → refactor diffuso ora non necessario.

## Conseguenze
- Coerenza cross-app; nessuna modifica alle view esistenti.
- “Magia” documentata; opt-out disponibile per audit/report.
