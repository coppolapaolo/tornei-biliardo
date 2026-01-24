# ADR-003 Sistema Privacy Profilo Utente

**Data**: 2025-12-28
**Stato**: Accepted
**Decisori**: Sviluppo assistito da Claude

## Contesto

I directors e players che cliccavano sugli utenti iscritti alle gare venivano reindirizzati a `/admin/user/<id>`, causando errore "Forbidden" per i non-admin. Era necessario:

1. Un profilo pubblico accessibile a tutti gli utenti autenticati
2. Controllo granulare su quali dati rendere visibili
3. Possibilità di nascondere singoli elementi (match, gare, campionati)
4. Mantenere la trasparenza sugli iscritti alle gare

**Requisiti raccolti dall'utente:**
- Toggle ON/OFF per categorie (email, telefono, statistiche, partite recenti, classifiche, challenge stats)
- Possibilità di nascondere singoli match, gare o campionati
- Gli iscritti alle gare devono sempre essere visibili (trasparenza tornei)
- UI per nascondere elementi sia dal profilo che dalla pagina storico

## Decisione

Implementazione con **tabelle separate per elementi nascosti** e **un modello per privacy settings generali**:

```
user_privacy_setting    → Toggle generali ON/OFF (1:1 con user)
hidden_match            → Match nascosti (M:N junction table)
hidden_inscription      → Iscrizioni/gare nascoste
hidden_campionato       → Campionati nascosti
```

Pattern architetturale:
- **Service Layer** (`PrivacyService`) con decorator `@transactional`
- **Lazy initialization** delle settings (create al primo accesso)
- **Filtering a livello route** (non model) per separare responsabilità
- **Admin bypass** per tutte le restrizioni privacy

## Alternative Considerate

### Alternativa 1: Flag sui modelli esistenti

**Descrizione**: Aggiungere campo `is_hidden_by_user_id` su Match, Inscription, Campionato

- **Pro**:
  - Query più semplici (JOIN non necessari)
  - Meno tabelle nel database
- **Contro**:
  - Inquina i modelli di dominio con logica privacy
  - Difficile gestire "nascosto per chi" (multi-utente)
  - Viola Single Responsibility Principle
  - Richiede migration su tabelle esistenti

### Alternativa 2: JSON field per hidden IDs

**Descrizione**: Campo JSON `hidden_elements` su UserPrivacySetting

- **Pro**:
  - Una sola tabella
  - Flessibile per nuovi tipi di elementi
- **Contro**:
  - Query inefficienti (no indici su JSON)
  - Integrità referenziale non garantita
  - Difficile fare JOIN con elementi nascosti

### Alternativa 3: Tabelle separate (SCELTA)

**Descrizione**: Tabelle junction dedicate per ogni tipo di elemento nascosto

- **Pro**:
  - Separazione netta tra domini
  - Indici efficienti per query
  - Integrità referenziale con FK
  - CASCADE delete quando elemento viene rimosso
  - Facile aggiungere metadata (hidden_at, reason)
- **Contro**:
  - Più tabelle da gestire
  - JOIN necessari per filtering

## Conseguenze

### Positive

- **Separazione delle responsabilità**: Privacy è un dominio isolato in `models/user/`
- **Backward compatibility**: Default tutto visibile, utenti esistenti non impattati
- **Estensibilità**: Facile aggiungere nuovi tipi di elementi nascondibili
- **Performance**: Indici su FK permettono query efficienti
- **Integrità**: CASCADE delete elimina automaticamente hidden records orfani
- **Sicurezza**: Validazione ownership prima di nascondere (solo propri elementi)

### Negative

- **4 nuove tabelle**: Aumenta complessità schema database
- **JOIN aggiuntivi**: Filtering richiede query su tabelle hidden_*
- **Context passing**: Templates devono ricevere `is_own_profile`, `is_admin`, `privacy`

### Rischi

- **Performance su profili con molti elementi**: Mitigato con indici e lazy loading
- **UI complexity**: Hide/show richiede AJAX calls - implementato con feedback immediato

## Note Implementative

### Struttura File

```
models/user/
├── privacy_models.py      # UserPrivacySetting, Hidden* models
├── privacy_service.py     # PrivacyService con @transactional
└── __init__.py           # Export aggiornati

routes/player.py          # Nuove rotte privacy + view_profile modificata

templates/
├── player/privacy_settings.html    # Form toggle settings
└── player/profile.html            # Template context-aware
```

### Pattern di Filtering

```python
# routes/player.py - view_profile()
matches = PrivacyService.filter_visible_matches(
    user_id=target_user.id,
    viewer_id=current_user.id,
    matches=all_matches,
    is_admin=current_user.is_admin,
)
```

### Validazione Ownership

```python
# Solo partecipanti possono nascondere un match
if match.player1_id != user_id and match.player2_id != user_id:
    raise ValueError("Only match participants can hide a match")
```

### Template Conditionals

```jinja2
{% if is_own_profile or is_admin or privacy.show_statistics %}
    {% include "components/_player_statistics.html" %}
{% endif %}
```

## Bug Fix Correlati

### 2025-12-28: Inscriptions non visibili per player/guest

**Problema**: La sezione iscritti in `gara_detail.html` mostrava il conteggio "(8)" nell'header ma "Nessun iscritto" nel body per player e guest.

**Causa**: Durante l'implementazione del sistema privacy, la variabile `inscriptions` in `routes/admin/competition.py` veniva caricata solo dentro il blocco `if user_can_manage:`, quindi era `None` per utenti non-admin.

**Fix**: Spostato il caricamento di `inscriptions` fuori dal blocco condizionale (linee 702-710) così tutti gli utenti ricevono la lista completa degli iscritti.

**Regression Test**: `tests/new/integration/test_gara_inscriptions_visibility_regression.py`

## GDPR Data Export (2026-01-24)

### Contesto

Per conformità al GDPR Art. 20 (Diritto alla portabilità dei dati), è stato implementato l'export completo dei dati personali dell'utente.

### Implementazione

**Flusso:**
1. Utente richiede export da `/player/privacy-settings`
2. Background thread genera JSON zippato
3. Notifica + SSE event quando pronto
4. Link di download valido 24 ore

**Dati esportati:**
- Account (username, email, phone, role, ratings)
- Privacy settings
- Iscrizioni a gare
- Partite giocate (con risultati)
- Classifiche campionati
- Challenge completate
- Gamification (livello, XP, achievement, streak, transazioni)

**Sicurezza:**
- Validazione ownership del file (filename inizia con user_id)
- Path traversal prevention (reject slashes in filename)
- Auto-cleanup file dopo 24 ore
- Rate limiting (max 1 export ogni 5 minuti)

**File:**
- `routes/player/profile.py` - Endpoints `request_gdpr_export`, `download_gdpr_export`
- `instance/gdpr_exports/` - Directory temporanea per file ZIP

## Riferimenti

- File correlati:
  - `models/user/privacy_models.py`
  - `models/user/privacy_service.py`
  - `routes/player/profile.py`
  - `routes/admin/competition.py` (linee 702-710, fix inscriptions)
  - `templates/player/profile.html`
  - `templates/player/privacy_settings.html`
- Migration: `migrations/add_user_privacy_settings.py`
- Tests: `tests/new/unit/test_privacy_service.py` (23 tests)
- Regression Tests: `tests/new/integration/test_gara_inscriptions_visibility_regression.py` (5 tests)
- GDPR Export Tests: `tests/new/integration/test_gdpr_export.py` (9 tests)
