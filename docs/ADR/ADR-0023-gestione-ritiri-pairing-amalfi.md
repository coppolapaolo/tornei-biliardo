# ADR-0023 — Gestione ritiri/cancellazioni nel pairing Amalfi (policy a livello **Prova** + cleanup match)

**Stato**: Accepted
**Data**: 2025-08-14
**Relazionati**: ADR-0021 (Soft Delete utente), ADR-0022 (Filtro globale soft-delete), ADR-0019/0020 (Preview senza IO / deprecazione preview engine)

---

## Contesto / Problema

* Va stabilizzata la semantica dei **ritiri/cancellazioni** rispetto a **pairing** (Amalfi) e **match** già creati.
* Una precedente ipotesi introduceva una policy per-iscrizione (`Inscription.withdraw_policy`), ma:

  * complica la governance del torneo,
  * non riflette la realtà operativa: la gestione ritiri è scelta **della Prova**.
* Servono regole chiare per casi speciali:

  1. giocatore **cancellato/ritirato vs X** (bye),
  2. **entrambi** i giocatori cancellati/ritirati in match **non concluso**,
  3. **forfeit** corretto quando uno solo è ritirato/cancellato.

---

## Decisione

1. **Policy unica a livello `Prova`** (`Prova.withdraw_policy`):

   * `WithdrawPolicy.EXCLUDE` *(default)*: i ritirati **non** vengono abbinati; disparità gestita da **X/Trio** secondo settaggi Prova.
   * `WithdrawPolicy.FORFEIT`: i ritirati **restano** abbinabili; se accoppiati contro un attivo, l’avversario vince **a tavolino** con **punteggio massimo**.

2. **Cleanup (sempre applicato, indipendente dalla policy):**

   * **Ritirato/cancellato vs X (bye)** → **il match viene eliminato** (nessun forfait).
   * **Entrambi** i giocatori cancellati/ritirati e match **non concluso** → **il match viene eliminato**.

3. **Finalizzazione forfait** *(solo se `Prova.withdraw_policy == FORFEIT`)*:

   * Se **esattamente uno** dei due è cancellato/ritirato e l’altro è **attivo**, il match è chiuso `COMPLETED` assegnando all’attivo il **winning score** della Prova (`Prova.get_winning_score()`).

4. **Centralizzazione**:

   * Cleanup + finalizzazione sono applicati **in `AmalfiEngine.create_round_matches()`** per **tutti** i turni (non solo il primo).

5. **Classifiche**:

   * Con `EXCLUDE`, ritirati/soft-deleted **non compaiono** nelle classifiche correnti/finali di Prova/Torneo (storico invariato). Il filtro è nello **strato service/presenter**.

---

## Dettagli di implementazione

### Modello / Dati

* `Prova.withdraw_policy: String(10), NOT NULL, default = WithdrawPolicy.EXCLUDE`.
* `Inscription`: **solo** `is_withdrawn: bool`, `withdrawn_at: datetime` (campo per-iscrizione `withdraw_policy` rimosso).
* `Match`: usare sempre `player1_score` / `player2_score`.
* Punteggio massimo: **`Prova.get_winning_score()`** (non letterali).

### Engine Amalfi

* **Filtro partecipanti**:

  * `EXCLUDE` → escludi iscrizioni `is_withdrawn=True` dai candidati.
  * `FORFEIT` → includi tutti.
* **Cleanup (nuovo)**:

  * Elimina match **vs X** se l’altro è cancellato/ritirato (sempre, anche se marcato completed dall’engine).
  * Elimina match **non conclusi** tra **due** cancellati/ritirati.
* **Finalizzazione forfait (solo FORFEIT)**:

  * Per match non conclusi con **un solo** cancellato/ritirato, assegna all’attivo `player*_score = prova.get_winning_score()` e `status = COMPLETED`.
* **Punto di applicazione**: alla fine di `create_round_matches()` (vale per 1º turno e successivi).

### Cancellazione utente (service)

* In `_forfeit_playing_matches(user)`:

  * **vs X** → elimina match.
  * **entrambi cancellati/ritirati** → elimina match (se non concluso).
  * **opposto attivo** → chiudi per forfeit assegnando winning score all’avversario.
  * *(Questa regola “durante il match” non dipende da `Prova.withdraw_policy`: è dominio operativo.)*

### Soft-delete filter (ADR-0022)

* Le routine seguenti devono poter “vedere” anche gli utenti soft-deleted (opt-out `include_deleted=True`):

  * `amalfi/engine.py`: cleanup + finalizzazione,
  * `models/user/services.py`: `_forfeit_playing_matches`.

### Classifiche

* Filtro di presentazione: `visible_user_ids = iscritti attivi (is_withdrawn=False) − soft_deleted`.
* Applicare nello **strato service/presenter**, non nelle query di repository.

---

## Alternative considerate

* **Policy per-iscrizione**: scartata (governance confusa, più casi limite, UX peggiore).
* **Riassegnare i bye a posteriori** (invece di eliminare match **vs X**): scartata; introdurrebbe side-effects non deterministici e rischio di drift rispetto all’anteprima.
* **Forfeit anche quando entrambi sono cancellati**: scartata; non c’è avversario attivo → nessun vincitore.

---

## Impatti e conseguenze

* **Chiarezza**: la scelta è in mano al Direttore **per Prova**.
* **Determinismo**: cleanup prima della finalizzazione; preview priva di IO.
* **Integrità storica**: match già `COMPLETED` non si toccano (eccetto caso **vs X**, dove il dominio impone eliminazione).
* **UI/UX**: la form di Prova espone la scelta **EXCLUDE/FORFEIT** (default EXCLUDE).

---

## Migrazione / Rollout

1. **Schema**

   * Aggiungi `Prova.withdraw_policy` (default EXCLUDE).
   * Rimuovi `Inscription.withdraw_policy` (se ancora presente).
2. **Codice**

   * Filtri EXCLUDE in engine/strategy.
   * Cleanup + finalizzazione in `create_round_matches()`.
   * Service `_forfeit_playing_matches` aggiornato.
   * Classifiche: filtro visibilità.
3. **Test**

   * Integrazione **preview EXCLUDE** (ritirati non presenti).
   * Integrazione **run FORFEIT** (chiusura a tavolino).
   * Test cleanup **vs X** e **entrambi cancellati**.
4. **Backout plan**

   * Forzare `withdraw_policy = EXCLUDE` su tutte le Prove (disabilita forfeit automatico) fino a rollback.

---

## Qualità / Gate

* Prestazioni: O(n) sui match del turno (<< 2s).
* Zero letterali: stati/ruoli/policy via Enum (`MatchStatus`, `UserRole`, `WithdrawPolicy`).
* Copertura test > 90% sui file toccati.

---

## Sicurezza & Privacy

* La soft-delete continua ad **anonimizzare PII** (ADR-0021).
* Le routine che leggono soft-deleted lo fanno solo per applicare regole dominio (non mostrate in UI).

---

## Open points / Futuro

* Eventuale scheduler per ripulire match obsoleti creati da editor manuali.
* UI: badge/tooltip sui match chiusi per forfeit (solo FORFEIT).

---

## Snippet di riferimento

```python
# Cleanup (sempre)
if p1 is None or p2 is None:            # vs X
    if other in cancelled_ids:
        db.session.delete(m)

if both_cancelled and not completed:     # entrambi cancellati/ritirati
    db.session.delete(m)

# Finalizzazione (solo FORFEIT)
if exactly_one_cancelled and policy == FORFEIT:
    win = prova.get_winning_score()
    award_to_active(...)
    m.status = MatchStatus.COMPLETED.value
```
