---
title: 'Reset match bloccato in presenza di tiebreaker attivo sulla gara'
type: 'feature — precondition + UI gate'
created: '2026-04-19'
status: 'done'
baseline_commit: '35c646c'
parent_spec: 'ADR-026 §Operations Glossary (residuo #2)'
tracked_in: '_bmad-output/implementation-artifacts/deferred-work.md (residuo ADR-026)'
---

## Problem

`Match.tiebreakers` è `cascade="all, delete-orphan"` solo sul delete del Match,
**non** sul reset. Dopo `reset_match_complete`, il match persiste in stato
PENDING/PLAYING con `winner_id=None`, ma eventuali `Tiebreaker` in stato
`COMPLETED` con `winner_id` settato restano allegati. Se il match viene
ri-completato, il classification aggregator può leggere dati tiebreaker stale.

Durante interview (2026-04-19) con il product owner è emerso che **il framing
iniziale del problema era sbagliato**: non è una questione di "preservare vs
rigenerare tiebreaker al reset", ma un problema di **semantica del reset in
presenza di spareggio**.

## Discovery (interview 2026-04-19)

### Uso reale dello SSR in produzione

Gli spot-shot rally (SSR) sono **una feature usata frequentemente** nei
tornei. UI esposta a due livelli:

1. **Configurazione gara**: SSR abilitato fino a una determinata posizione
   in classifica
2. **Esecuzione**: interfaccia per director per inserire i risultati dello
   spareggio

### Intent del product owner

**"Quando si fa lo SSR si certifica implicitamente che tutti i risultati
sono corretti. Non si torna indietro."**

Lo SSR non è un "sottoprodotto" del match — è un atto di certificazione che
trasforma la gara in stato irreversibile. Resettare un match dopo uno SSR
invaliderebbe il ranking che ha portato allo spareggio, trasformando lo
SSR stesso in dati orfani semanticamente corrotti.

### Decisioni

- **Scope della certificazione**: la creazione di uno SSR su una gara blocca
  il reset di **TUTTI i match della gara** (non solo dei match dei giocatori
  in parità). Rationale: la parità di classifica dipende dallo score
  aggregato di tutti i match; modificare qualsiasi match invaliderebbe il
  ranking che ha generato lo SSR.

- **Override admin**: **nessuno**. Per procedere col reset, l'admin deve
  prima cancellare manualmente lo SSR (feature già esistente).

- **Stati del Tiebreaker che bloccano il reset**: `PENDING`, `IN_PROGRESS`,
  `COMPLETED`. Solo `CANCELLED` non blocca. Rationale: l'atto stesso di
  creare lo SSR è la certificazione.

- **UX**: l'interfaccia **non deve esporre il bottone di reset** quando
  c'è uno SSR attivo. Defense-in-depth backend come safety net, non come
  primo muro.

## User Story

**Come** director/admin,
**quando** una gara ha un tiebreaker (SSR, rally, playoff) in stato non
cancelled,
**voglio** che l'interfaccia non mi permetta di resettare alcun match di
quella gara,
**in modo da** non invalidare silenziosamente la certificazione implicita
dello spareggio.

## Criteri di Accettazione

- [ ] **AC1**: `AdvancedRoundManager.can_modify_match(match_id)` restituisce
  `(False, <reason>)` se la gara del match ha almeno un `Tiebreaker` in
  stato != `CANCELLED`.
- [ ] **AC2**: La precondition è saltata per match standalone
  (`gara_id IS NULL`), coerente con il check già esistente per individual
  match.
- [ ] **AC3**: Il check non tocca match già resettati o senza tiebreaker —
  nessuna regressione sui flussi esistenti.
- [ ] **AC4**: Il bottone/endpoint di reset nella UI (`gara_detail.html`,
  `match_detail.html`, `_match_admin_controls.html`) è nascosto/disabilitato
  quando `can_modify_match` restituisce False per motivo tiebreaker.
- [ ] **AC5**: Se l'admin aggira la UI (chiamata diretta all'endpoint POST),
  il backend rifiuta con `ValueError` (defense-in-depth).
- [ ] **AC6**: Nessuna migrazione schema. Nessun cascade o hook aggiunto.
- [ ] **AC7**: Regression test che coprono: PENDING/IN_PROGRESS/COMPLETED
  bloccano, CANCELLED non blocca, standalone match non check, gara senza
  tiebreaker no regressione.

## User Journey

### Scenario A: Gara con SSR completato

1. Gara "Torneo Pasqua" in stato COMPLETED, Alice 1°, Carol 2° (via SSR),
   Bob 3°
2. Director scopre errore in un match di Bob
3. Director naviga a `match_detail` del match incriminato
4. **Il bottone "Reset match" non è presente**
5. Eventuale tooltip/messaggio informativo (opzionale): "Gara certificata
   da spareggio. Annulla prima lo spareggio per modificare i match."

### Scenario B: SSR creato ma non ancora giocato

1. Director crea SSR ma realizza subito di aver sbagliato dati → vuole
   modificare un match prima di rigiocarlo
2. Tiebreaker in stato PENDING → reset bloccato
3. Director deve cancellare lo SSR (stato → CANCELLED) **prima** di
   resettare il match
4. Dopo cancellazione SSR, bottone reset ricompare, flusso normale

### Scenario C: Match standalone (individual match)

1. User A e User B giocano match one-off senza gara
2. Match ha `gara_id = NULL` → non può avere tiebreaker di classifica
3. Reset sempre possibile (nessun check aggiunto)

### Scenario D: Gara senza mai tiebreaker

1. Flusso standard: gara conclusa senza parità → nessun tiebreaker creato
2. Reset funziona come prima (no regressione)

## Edge Cases Gestiti

| Scenario | Comportamento Atteso |
|----------|---------------------|
| Match ha `gara_id=NULL` (standalone) | Check skippato, reset ammesso |
| Gara ha 0 tiebreaker | Check passa, reset ammesso |
| Gara ha solo tiebreaker CANCELLED | Check passa, reset ammesso |
| Gara ha tiebreaker PENDING | Reset bloccato |
| Gara ha tiebreaker IN_PROGRESS | Reset bloccato |
| Gara ha tiebreaker COMPLETED | Reset bloccato |
| Gara ha mix (1 CANCELLED + 1 COMPLETED) | Reset bloccato (il COMPLETED conta) |
| UI mostra reset ma tiebreaker creato da altro admin nel frattempo (TOCTOU) | Backend rifiuta con ValueError, UI dovrebbe refreshare |
| Reset via endpoint diretto POST (aggiramento UI) | Backend rifiuta con ValueError (defense-in-depth) |

## Impatto Tecnico

### Files da modificare

**Backend**
- `models/competition/round_manager.py` — `can_modify_match()`: aggiungere
  check tiebreaker attivo sulla gara dopo i check esistenti (status gara +
  round lock), prima del return `(True, "")`
- `models/competition/CLAUDE.md` — aggiornare §Match Lifecycle Operations
  Glossary con la nuova precondition in "reset_match_complete"
- `docs/adr/ADR-026-reset-match-preserves-pair-semantics.md` — aggiungere
  nota nel §Operations Glossary che il reset è bloccato in presenza di
  SSR attivo (supersede del residuo ECH originale)

**Frontend**
- `templates/gara_detail.html` — hide bottone reset se gara ha
  tiebreaker attivo
- `templates/match_detail.html` — hide bottone reset idem
- `templates/components/_match_admin_controls.html` — hide bottone reset idem
- `templates/components/_match_result_row.html` — verificare se espone
  reset, hide se sì
- `templates/components/_match_card.html` — verificare se espone reset,
  hide se sì

Il bottone reset dovrebbe già essere condizionato a `can_modify_match`
(o a un flag derivato passato dalla route). Da verificare in fase di
implementazione.

### Nessuna modifica necessaria

- `models/match/rack_service.py` — `reset_match_complete` resta invariato
  (la precondition vive nel wrapper `can_modify_match`, come oggi per
  round lock). Non duplichiamo la logica.
- `models/tiebreaker/models.py` — nessun nuovo campo
- Nessuna migrazione DB

### Nuove entità

Nessuna. Nessun cascade, nessuna relationship, nessun campo.

### Query proposta

```python
# In can_modify_match, dopo il round lock check:
from models.tiebreaker.models import Tiebreaker, TiebreakerStatus

active_tiebreaker_exists = (
    db.session.query(Tiebreaker.id)
    .filter(
        Tiebreaker.gara_id == gara.id,
        Tiebreaker.status != TiebreakerStatus.CANCELLED.value,
    )
    .first()
    is not None
)
if active_tiebreaker_exists:
    return (
        False,
        "Gara certificata da spareggio: "
        "annulla prima lo spareggio per modificare i match",
    )
```

Nota: `Tiebreaker.gara_id` è FK nullable ma la precondition filtra sul
valore specifico di `gara.id`, che è già noto non-null (controllato sopra
nel metodo). Rows con `gara_id=NULL` (eventuali tiebreaker a livello
campionato non gara-specifici) non vengono toccate.

## Integrazione con Sistema Esistente

- **Notifiche**: nessuna nuova notifica. Il blocco è preventivo, non
  reattivo.
- **Gamification**: nessun impatto. Il reset non avvia mai → nessun
  reward/XP rollback.
- **i18n**: il messaggio di errore va tradotto via `_()`.
- **Soft delete utenti**: nessun impatto.
- **Mobile app**: il messaggio di errore va tradotto. Frontend mobile
  (quando esisterà) dovrà consumare lo stesso `can_modify_match`.

## Test Plan

### Unit test in `tests/new/unit/test_reset_blocked_by_tiebreaker.py`

1. `test_can_modify_match_blocked_by_pending_tiebreaker` — gara con 1 TB
   PENDING → `(False, ...)`
2. `test_can_modify_match_blocked_by_in_progress_tiebreaker` — gara con 1
   TB IN_PROGRESS → `(False, ...)`
3. `test_can_modify_match_blocked_by_completed_tiebreaker` — gara con 1
   TB COMPLETED → `(False, ...)`
4. `test_can_modify_match_allowed_with_only_cancelled_tiebreakers` — gara
   con 1 TB CANCELLED → `(True, ...)`
5. `test_can_modify_match_allowed_without_tiebreakers` — gara senza TB
   → `(True, ...)` (no regressione)
6. `test_can_modify_match_allowed_for_standalone_match` — `gara_id=NULL`,
   anche con TB globali → `(True, ...)`
7. `test_can_modify_match_blocked_by_mixed_tiebreakers` — gara con 1
   CANCELLED + 1 COMPLETED → `(False, ...)`

### Integration test in `tests/new/integration/test_reset_with_tiebreaker.py`

1. `test_reset_match_with_validation_rejects_when_tiebreaker_active` —
   chiamata end-to-end a `AdvancedRoundManager.reset_match_with_validation`
   restituisce `(False, "Gara certificata...")`.
2. `test_reset_endpoint_returns_error_when_tiebreaker_active` — chiamata
   HTTP all'endpoint admin reset → 403 o 400 con payload errore appropriato.

### Frontend verification

- Test manuale post-implementazione: creare gara, creare TB PENDING,
  verificare che bottone reset scompaia da tutte le view che lo espongono.
- Cancellare TB, verificare che bottone ricompaia.

## Domande Aperte

Nessuna bloccante. Nota per l'implementazione:

- La UI potrebbe beneficiare di un **tooltip informativo** sul bottone
  reset disabilitato (es. "Annulla prima lo spareggio") per evitare
  confusione, ma il PO ha indicato che il bottone deve **non essere
  presente** (hide, non disable). Scelta: hide. Eventuale banner
  informativo nell'area gara ("Questa gara ha uno spareggio attivo —
  i match sono bloccati finché lo spareggio non è annullato") può essere
  aggiunto opzionalmente se utile per UX, ma non è parte del core scope.

## Note Architetturali

### Perché NON la soluzione (a) "reset cancella tiebreaker"

Inizialmente proposta nel deferred-work, ma incoerente con la semantica
confermata dal PO: lo SSR è certificazione, non un "appendice" al match.
Cancellarlo silenziosamente nel reset:
- Distrugge audit trail di uno spareggio già giocato (spot_shots registrati)
- Fa perdere la garanzia di integrità del ranking
- Crea pattern "magico" (il director non si aspetta che reset tocchi
  tiebreaker)

### Perché NON la soluzione (b) "to_completed rigenera tiebreaker"

Anche questa incoerente: un tiebreaker è **uno spareggio giocato**, non
un dato derivato. Rigenerarlo significherebbe rigiocare gli spot shots,
cosa che il sistema non può fare autonomamente.

### Perché NON la soluzione (c) "accetta come limitazione documentata"

Scartata perché lo SSR è feature **usata frequentemente** e il flusso
"admin resetta dopo SSR" ha probabilità non trascurabile. Lasciarlo come
limitazione documentata significherebbe accettare rischio latente di
classificazioni silenziosamente corrotte.

### Allineamento con ADR-026

ADR-026 stabilisce che "il reset preserva semantica pair, corregge solo
score". Questo spec è coerente: **quando il reset è ammesso**, preserva
pair e corregge score come da ADR-026. Il nuovo check aggiunge una
pre-condition di **ammissibilità**, non cambia il comportamento del reset
stesso.

## Checklist Pre-Implementazione

- [x] User story chiara con attore, azione, beneficio
- [x] 7 criteri di accettazione testabili
- [x] User journey completo (4 scenari)
- [x] Permessi: immutati (director/admin come oggi)
- [x] Comportamento errori specificato
- [x] Edge cases coperti (9 scenari)
- [x] Impatto notifiche: nessuno
- [x] Impatto gamification: nessuno
- [x] Necessità i18n: 1 nuova stringa
- [x] Nessuna domanda aperta bloccante
