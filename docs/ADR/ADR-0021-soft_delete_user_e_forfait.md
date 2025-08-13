# ADR-0021 — Cancellazione utente: Soft Delete + Anonimizzazione e Forfait

**Stato:** Proposto → Approvato (12/08/2025)
**Contesto:** La route `POST /player/delete_account` esegue un hard-delete parziale dell’utente causando inconsistenze nell’Unit of Work (SQLAlchemy) e potenziali violazioni di FK. Il dominio richiede conservazione dello storico competitivo (match, classifiche, tornei, prove) e impossibilità di login post-cancellazione.

**Decisione:**

1. **Soft delete + anonimizzazione** come comportamento di default: l’utente non viene fisicamente rimosso; i campi PII sono azzerati; il login è disabilitato; lo **username pubblico** viene mutato in un identificativo tecnico, mentre la UI rende un handle “accattivante”.
2. **Hard delete** consentito solo se l’utente **non** ha storico competitivo.
3. Introduzione marcatori di **withdraw/forfait** per iscrizioni già avviate; **default policy** per pairing successivi: \`\`.

**Alternative considerate:**

* Hard delete con normalizzazione massiva FK → fragile e costoso; alto rischio regressioni.
* ON DELETE CASCADE generalizzato → perdita di storico.
* Soft delete senza mutazione username → poco chiaro nei registri storici.

**Conseguenze:**

* Aggiunta di campi a `User` (SoftDeleteMixin, `previous_username`).
* Aggiunta di campi a `Inscription`: booleano `is_withdrawn`, `withdrawn_at`, e `withdraw_policy`.
* Service transazionale `UserDeletionService` per orchestrare tutto senza bulk ops.
* UI helper per render “username cancellato” con emoji/strikethrough/data.

---

## Note di rilascio

* **Breaking change controllato**: `User.email` e `User.phone` diventano nullable (giustificato da ADR-0021). Reset DB in sviluppo.
* Nessuna modifica ai FK verso `user.id` (storico preservato).
* La route utente ora effettua **soft delete** e non crea più inconsistenze UoW.

## Prossimo step (Sprint breve)

* **WithdrawnHandlingPolicy** integrata nel Matchmaking (`AmalfiStrategy.preview()`/`start_round`) con 3 varianti (`KeepForfeit`, `XPointsOnly` \[default], `XWithPairing`).
* Test d’integrazione su pairing in presenza di giocatori ritirati, comprensivi di casi con/ senza X e con/ senza trio.
