# ADR-0003: Sistema Permessi e Decoratori di Route

Data: 2025-08-01

## Stato
Accettato

## Contesto
Il dominio tornei richiede ACL fini (Admin, Director, Player). Flask-Login copre solo l'autenticazione. Opzioni valutate:
* Flask-Principal,
* estensione ACL di Flask-User,
* soluzione custom leggera.

## Decisione
* Implementare `PermissionChecker` (mappa ruoli-permessi in memoria) + decoratore `@requires(permission)` in `models/user/permissions.py`.
* Il checker legge il ruolo dall'oggetto utente in sessione; se mancante abort 403.
* Helpers `any_of`, `all_of` per permessi composti.
* Nessuna dipendenza esterna, per restare compatibili con account gratuito PythonAnywhere.

## Conseguenze
+ Zero query runtime per ACL.
+ Facile da testare (funzioni pure).
− Manutenzione a carico del team.

## Alternative
**Flask-Principal** – obsoleto, dipendenza extra.
**Casbin** – potente, ma troppo pesante per lo scope.
