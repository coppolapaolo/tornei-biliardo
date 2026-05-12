# ADR-030 — `Campionato.is_active` non implica "in corso" nelle viste pubbliche

**Data**: 2026-05-12
**Stato**: Accepted
**Decisori**: Paolo Coppola

## Contesto

Un utente guest segnala che nella homepage di produzione un campionato con
tutte le 11 gare in stato `COMPLETED` ("La Garetta del MerColedì 2026")
compare nella sezione **"Campionati Attivi"**, con il badge "Completato"
visibile a fianco del nome — incoerenza fra header di sezione e contenuto.

### Cause

Nel modello `Campionato` (`models/campionato/models.py`) coesistono due
nozioni di "attivo":

1. **Colonna `is_active: bool`** — flag di vita/morte del record. Viene
   messo a `False` solo da:
   - `soft_delete()` (cancellazione)
   - `terminate_campionato()` (chiusura manuale anticipata)

   Non viene mai aggiornato automaticamente quando le gare arrivano
   naturalmente al `COMPLETED` finale.

2. **Status derivato** calcolato da `compute_campionato_status()`
   (`models/campionato/statistics_service.py`) ispezionando lo stato
   delle gare correlate. Restituisce uno fra `SETUP`,
   `REGISTRATION_OPEN`, `IN_PROGRESS`, `COMPLETED`, `TERMINATED`.

`HomepageService.get_homepage_data()` e
`routes/main.py:public_campionatos_list` filtravano solo per
`is_active=True`, mescolando quindi campionati realmente in corso con
campionati completati naturalmente — questi ultimi finivano sotto un
header "Attivi" anche se nei singoli badge erano marcati "Completato".

## Decisione

1. **`is_active` resta un flag di "non-cancellato/non-terminato"**,
   distinto dallo status derivato. Non lo aggiorniamo
   automaticamente sul completamento naturale: cambierebbe semantica a
   molte query già esistenti (matchmaking, soft-delete restore,
   filtri admin).

2. **La presentazione delle viste pubbliche guest deve filtrare per
   status derivato**, non per `is_active`:

   - **Homepage `/`** — sezione unica "Campionati" che mostra tutti i
     campionati con status non terminale (in corso, registration_open,
     setup) e, in coda, al massimo `HOMEPAGE_COMPLETED_LIMIT = 2`
     completati per richiamare interesse. Un link "Vedi tutti" porta
     alla pagina archivio.

   - **`/campionatos`** — diventa il punto di ingresso per la lista
     completa, con filtri per status (`all` | `in_corso` | `completati`
     | `terminati`) e ricerca per nome. Lo status filter è applicato in
     Python perché lo status derivato non è una colonna SQL.

3. **L'ordinamento dei completati in homepage** è per
   `created_at DESC` (campo già indicizzato). Una future iteration
   potrebbe ordinarli per data dell'ultima gara giocata, ma non oggi.

## Alternative Considerate

### Alternativa A: aggiornare `is_active=False` al completamento

**Descrizione**: hook su `compute_campionato_status` (o sul transition
dell'ultima gara) che marca `is_active=False` non appena tutte le gare
sono in `COMPLETED`.

- **Pro**:
  - Query in homepage rimane una `WHERE is_active=True` pura, indicizzabile.
- **Contro**:
  - Cambia semantica di `is_active` in tutto il codebase. Ricerche in
    admin/director per "campionati attivi non terminati" si romperebbero.
  - `soft_delete` e questo nuovo path collassano in un'unica colonna
    perdendo l'informazione su *come* il campionato è uscito dal flusso.
  - Coupling fra cambio stato di una `Gara` e una colonna su `Campionato` —
    duplicazione del derived state ora ben isolato in
    `compute_campionato_status`.

### Alternativa B: nascondere completamente i COMPLETED dalla homepage

**Descrizione**: filtrare in Python e mostrare solo gli IN_PROGRESS/etc.

- **Pro**: implementazione triviale.
- **Contro**:
  - Subito dopo la chiusura del campionato sparirebbe dalla home senza
    transizione: poco scoprìbile per i guest, che potrebbero voler
    vedere la classifica finale appena uscita.

### Alternativa C: due sezioni separate "Attivi" / "Completati"

**Descrizione**: come fatto in `/garas` (B5 split active vs completed).

- **Pro**: simmetrico con la lista gare standalone.
- **Contro**:
  - L'utente ha esplicitamente preferito una sezione unica con i
    completati come "coda recente". Mantenere due heading separati
    aggiunge spazio verticale senza aumentare la chiarezza per il caso
    "1-2 campionati completati di recente".

## Conseguenze

### Positive

- Coerenza visiva: ciò che è marcato "Completato" non compare più sotto
  un header "Attivi".
- `is_active` mantiene una semantica stabile (vita/morte del record),
  rispettata da tutto il resto del codebase.
- La pagina `/campionatos` diventa un vero archivio con filtri/ricerca,
  non più un duplicato non filtrato della home.

### Negative

- Filtraggio dello status derivato avviene in Python, non in SQL. È
  accettabile dato il volume (poche decine di campionati per istanza).
  Se mai un giorno l'app dovesse scalare a migliaia di campionati, si
  potrà denormalizzare lo status in una colonna calcolata.

### Rischi

- Se `compute_campionato_status` cambia semantica in futuro,
  l'allowlist `terminal_statuses` in `HomepageService` va aggiornata.
  Mitigato dal test di regressione `test_homepage_completed_campionato.py`.

## Note Implementative

File toccati:

- `models/campionato/homepage_service.py` — partizionamento per status
  derivato, esposizione di `active_count`, `completed_total`,
  `completed_shown`.
- `templates/index.html` — rinomina sezione "Campionati Attivi" → "Campionati",
  pulsante "Vedi tutti", contatore "Mostrati N di M completati".
- `routes/main.py:public_campionatos_list` — filtri di status + search.
- `templates/public/campionatos_list.html` — form filtri, badge status
  derivato (`| status_text`).

Test:

- `tests/new/integration/test_homepage_completed_campionato.py`

```python
# Esempio della partizione (homepage_service.py)
terminal_statuses = {
    TournamentStatus.COMPLETED.value,
    TournamentStatus.TERMINATED.value,
}
for c in candidates:
    if c.get_status() in terminal_statuses:
        completed.append(c)
    else:
        active.append(c)
campionatos_to_show = active + completed[:HOMEPAGE_COMPLETED_LIMIT]
```

## Riferimenti

- File correlati:
  - `models/campionato/models.py` (Campionato.is_active, get_status)
  - `models/campionato/statistics_service.py::compute_campionato_status`
  - `models/campionato/homepage_service.py`
  - `routes/main.py::public_campionatos_list`
  - `templates/public/campionatos_list.html`
- Precedente analogo per gare standalone: `routes/main.py::public_garas_list`
  (split active/completed, citato come "B5" nel commento del file).
