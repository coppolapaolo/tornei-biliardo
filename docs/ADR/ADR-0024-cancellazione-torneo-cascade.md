# ADR-0024 — Cancellazione Torneo: cascade su associazione amministrativa

**Data:** 2025-08-15  
**Stato:** Accepted

## Contesto
La route `POST /admin/tournament/<id>/delete` falliva con:
> AssertionError: Dependency rule on column 'tournament.id' tried to blank-out primary key column 'tournament_director.tournament_id'

Motivo: la relazione ORM `TournamentDirector.tournament` usava `backref="directors_association"` **senza** `cascade`. Al delete del `Tournament` l’UnitOfWork tentava di “svuotare” la FK nella tabella di associazione, ma la colonna è parte della PK → errore.

## Decisione
Impostare sul backref del `Tournament` la cascade ORM:
- `cascade="all, delete-orphan"`

## Alternative valutate
- **Delete manuale** delle righe in `tournament_director` prima del `Tournament`: più codice, fragile e non scalabile.
- **Solo DB `ON DELETE CASCADE`**: robusto ma richiede migrazione; dato che siamo in dev con reset DB, si potrà aggiungere in un passo successivo insieme a `passive_deletes=True`.
- **Trigger DB**: eccessivo per il dominio, poco leggibile lato applicativo.

## Conseguenze
- La cancellazione del `Tournament` con direttori assegnati funziona senza 500.
- Aggiunto test di integrazione dedicato.
- Passo successivo consigliato (hardening): estendere le cascade a `classifications`, figli di `Prova` (`matches`, `inscriptions`, `racks`), e introdurre un `TournamentService.delete_tournament()` con gestione `IntegrityError`.
