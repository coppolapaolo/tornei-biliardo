# Roadmap multi-sessione (WBS) con ancoraggi chiari

## Sprint 0 — Fondazioni architetturali (senza cambiare comportamento)

**Obiettivi**

* ADR di baseline; introdurre interfacce `PairingStrategy`, `Pairing`, `EngineRegistry`; `MatchmakingService` vuoto (pass-through).

**Deliverable**

* ADR-0014 “Engine & Strategy Registry” (alternative valutate).
* Scheletro codice (interfacce + registry), nessuna route modificata.
* Test fumo: istanziare registry, caricare `AmalfiAdapter` (vedi Sprint 1).

**Rischi mitigati**

* Blocchiamo il design prima di toccare logica.

---

## Sprint 1 — Amalfi come Strategy (adapter sull’engine esistente)

**Obiettivi**

* `AmalfiStrategy` che adatta l’engine attuale.
* Fix contratto `record_encounter` (ordine argomenti).
* Route `start_round` usa `MatchmakingService` al posto dell’engine diretto (stesso output).

**Deliverable**

* Codice Strategy + Adapter.
* Test integrazione:

  * anti-reincontro (`PlayerEncounter` aggiornato correttamente);
  * gestione bye/trii coerente con `without_x`;
  * “salto” applicato (verifica pairing vs `RoundClassification`).
* ADR-0015 “Contratto Pairing & invarianti Amalfi”.

---

## Sprint 2 — Policy separata (Bye/Trio, Anti-Rematch, Tiebreaker)

**Obiettivi**

* Estrarre `ByePolicy`, `AntiRematchPolicy` (oggi hardcoded nell’engine e nelle util).
* Portare la logica di preview in `AmalfiStrategy.preview()` (no side-effects).

**Deliverable**

* Policy pluggable + test unitari di policy.
* ADR-0016 “Policy separabili & Preview senza IO”.

---

## Sprint 3 — Aggiungere Round-Robin e scheletro Single/Double Elim

**Obiettivi**

* `RoundRobinStrategy` (rotazioni/“circle method”).
* Scheletri `SingleElimStrategy`/`DoubleElimStrategy` + `ProgressionRule` (avanzamento tabellone).
* UI/Config: selezione strategia a livello di prova.

**Deliverable**

* Test e2e minimi per ogni strategy.
* ADR-0017 “Tassonomia strategie pairing vs bracket progression”.

---

## Sprint 4 — State machine + Enum (via migrazione soft)

**Obiettivi**

* Introdurre `ProvaStatus`, `TournamentStatus`, `MatchStatus` (Enum) e State pattern. Oggi gli status sono stringhe sparse e c’è anche logica di view nel dominio.
* Rimuovere `get_status_badge_*` dai model (Presenter/Template filter).

**Deliverable**

* Mapping retro-compatibile (migrazione senza downtime).
* Test transizioni di stato + contract test per Presenter.
* ADR-0018 “State pattern & rimozione presentational logic dal dominio”.

---

## Sprint 5 — Unit of Work + Repository (stop ai commit nei model)

**Obiettivi**

* Eliminare `commit()` da `BaseModel`, `UtilityMixin`, `SoftDeleteMixin`.
* Introdurre `UnitOfWork` (scopo per caso d’uso) e Repository per `Prova`, `Match`, `PlayerEncounter`.

**Deliverable**

* Refactor servizi (`MatchmakingService`, `MatchProgressService`).
* Test transazionali (rollback atomico su failure).
* ADR-0019 “Confini transazionali & UoW”.

---

## Sprint 6 — RBAC centralizzato + pulizia route

**Obiettivi**

* Unica sorgente per `can_manage_*` (oggi frammentata tra utils/decorator).
* Route “stupide”: solo orchestrazione dei servizi.

**Deliverable**

* Decorator che chiamano `RBACService`.
* Test autorizzativi (positivo/negativo).

---

## Sprint 7 — Debito tecnico & deprecazioni

**Obiettivi**

* Rimozione util duplicati (es. `create_round_matches_*`).
* Migrare `legacy_models.Playoff`.
* Sostituire stampe/emoji con logging DI (dove presenti).

**Deliverable**

* Report “dead code” + script linter mirati.
* Copertura >90% (line/branch) su domini matchmaking e state.

---

## Test strategy (cosa testiamo “davvero”)

* **Invarianti di pairing (per ogni Strategy):** niente self-match; rispetto `AntiRematchPolicy`; stabilità con pari/dispari; riproducibilità (seed).
* **Salto Amalfi:** pairing coerenti con `RoundClassification` round−1; aggiornamento `PlayerEncounter`.
* **Preview:** zero side-effects, identico shape dei pairing rispetto a `propose`.
* **Stati:** automi di `Prova`/`Tournament` con tabella transizioni.
* **Transazioni:** o tutto committa o niente (UoW).
* **RBAC:** matrix test ruolo×azione×stato.

---

## Definition of Done (globale)

1. build ok
2. test unit/integration verdi
3. coverage ≥90% su moduli nuovi
4. ADR aggiornate
5. nessuna logica di view nel dominio
6. zero commit nei model.

---

## Checklist di migrazione (per non perdere il filo)

* Creare le ADR prima del codice (template fisso).
* Commit per ogni micro-step con tag `[arch]`, `[service]`, `[policy]`.
* Ogni Strategy nuova → contract test condiviso (riusa le stesse spec).
* Una PR per sprint con “migration notes” e script di validazione.
* Dopo ogni sprint: ripulire i TODO rimasti (issue tracker).
