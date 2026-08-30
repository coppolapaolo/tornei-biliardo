# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Routes Directory - Flask Route Handlers

Flask blueprints for the American Pool community platform with role-based access control.

---

## Blueprint Organization

| Blueprint | Prefix | Purpose |
|-----------|--------|---------|
| `auth` | `/auth` | Login, logout, registration |
| `main` | `/` | Public pages, guest access |
| `dashboard` | `/dashboard` | Role-based dashboards |
| `player` | `/player` | Player profile, history, proposals |
| `admin.campionato` | `/admin/campionato` | Tournament management |
| `admin.competition` | `/admin/gara` | Gara management |
| `admin.match` | `/admin/match` | Match administration |
| `admin.user` | `/admin/user` | User management |
| `admin.venue` | `/admin/venue` | Venue management |
| `challenge` | `/challenge` | Challenge system |
| `individual_match` | `/match` | Casual matches |
| `exam` | `/exam` | Esami: catalogo, sessioni, appuntamenti (ADR-042) |
| `roles` | `/roles` | Ruoli concedibili e delega (ADR-041) |
| `feedback` | `/segnalazioni` | Segnalazioni degli utenti → issue GitHub (#255) |

---

## Permission Decorators

### Usage

```python
from flask_login import login_required
from utils import admin_required, director_required, player_only

@player_bp.route("/profile")
@login_required          # Must be logged in
def profile():
    pass

@admin_bp.route("/users")
@login_required
@admin_required          # Must be admin
def user_list():
    pass

@competition_bp.route("/create")
@login_required
@director_required       # Admin OR director
def create_gara():
    pass

@player_bp.route("/history")
@login_required
@player_only             # Blocks admins, allows directors+players
def history():
    pass
```

### Permission Hierarchy

```
admin_required    → Only admin users
director_required → Admin OR director users
player_only       → Director OR player (blocks admin-only users)
login_required    → Any authenticated user
```

---

## Production Endpoint Visibility (ADR-028)

L'allowlist endpoint **non sostituisce** i decoratori di permesso sopra: agisce come layer ortogonale che controlla solo se un endpoint è **raggiungibile in produzione** (200 vs 404). I decoratori controllano cosa l'utente può fare una volta raggiunto. Vedi `docs/adr/ADR-028-production-endpoint-allowlist.md`.

### Modello matriciale

`utils/feature_flags.py::ENDPOINT_ROLES` mappa ogni endpoint Flask a un set di ruoli ammessi (`anonimo`, `player`, `director`). Admin è bypass globale (vede tutto, anche endpoint non listati). Endpoint non listato → solo admin lo vede in produzione.

```python
ENDPOINT_ROLES = {
    "auth.login":                              {"anonimo"},
    "main.public_garas_list":                  {"anonimo", "player", "director"},
    "admin.competition.gara_detail":           {"anonimo", "player", "director"},  # polimorfica
    "dashboard.dashboard":                     {"player", "director"},
    "player.inscribe_competition":             {"player"},
    "admin.competition.create_gara_standalone": {"director"},
    # NON listato → solo admin: admin.kpi.index, admin.user.director_requests, ecc.
}
```

### Quando aggiungi una nuova route

1. Decidi quali ruoli devono vederla in produzione.
2. Aggiungi l'entry in `ENDPOINT_ROLES` (`utils/feature_flags.py`; anche `set()` esplicito = "solo admin", per documentare la decisione).
3. Se la route compare in un menu/link condizionato, aggiungi `{% if feature_visible('endpoint.name') %}` nel template.

⚠️ **Nessun test impone la copertura.** `tests/new/unit/test_endpoint_coverage.py`
**non esiste** (lo citava questa pagina, per errore). Il test reale è
`tests/new/integration/test_endpoint_allowlist.py`, e:

- `test_endpoint_roles_names_are_real` fallisce sui **refusi** nei nomi;
- `test_report_unclassified_endpoints` emette solo un `warnings.warn`, non un
  assert — scelta esplicita durante il rollout MVP (ADR-028, Open Items §3).

Conseguenza pratica: **dimenticare un endpoint non rompe la CI, lo rende
silenziosamente admin-only in produzione.** Va fatto a mano, e verificato
percorrendo il flusso con `DEBUG_MODE=false`.

### In sviluppo

In `development` (`DEBUG_MODE=true`) il middleware passa-through e tutto è visibile come oggi. La matrice ha effetto solo in produzione.

---

## Request/Response Patterns

### AJAX vs Page Requests

```python
from flask import request, jsonify, render_template

@bp.route("/some-action", methods=["POST"])
@login_required
def some_action():
    # Check if AJAX request
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        try:
            # Do work
            return jsonify({"success": True, "message": "Done"})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 400
    else:
        # Regular form submission
        flash(_("Azione completata"), "success")
        return redirect(url_for("some.route"))
```

### Service Layer Integration

```python
from models.competition.services import GaraService

@bp.route("/gara/<int:gara_id>/start-round", methods=["POST"])
@login_required
@director_required
def start_round(gara_id):
    gara = db.session.get(Gara, gara_id)
    if not gara:
        abort(404)

    # Permission check
    if not current_user.can_manage_competition(gara_id):
        abort(403)

    # Use service layer (handles @transactional)
    service = GaraService()
    result = service.start_next_round(gara_id)

    if result.success:
        flash(_("Turno avviato"), "success")
    else:
        flash(result.error, "danger")

    return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))
```

---

## Common Patterns

### Entity Permission Check

```python
@bp.route("/gara/<int:gara_id>/edit")
@login_required
@director_required
def edit_gara(gara_id):
    gara = db.session.get(Gara, gara_id)
    if not gara:
        abort(404)

    # Check user can manage this specific entity
    if not current_user.can_manage_competition(gara_id):
        flash(_("Non hai i permessi"), "danger")
        return redirect(url_for("dashboard.index"))

    # ... rest of handler
```

### Form parsing: single source (Form Object)

Quando più route (create / wizard / edit) parsano lo **stesso** form, il mapping
form↔modello deve vivere in **un solo posto**, non copiato in ogni handler
(altrimenti drift silenzioso → campi persi, cfr. ADR/tech-debt F7.5/F9.2):

| Entità | Parser | Usato da |
|--------|--------|----------|
| Gara | `routes/admin/competition/form_parser.py::GaraFormParser` | `create_gara`, `create_gara_standalone`, `edit_gara` |
| Campionato | `routes/admin/campionato_form_parser.py::CampionatoFormParser` | `wizard_create`, `edit_campionato` (blocco default-gare) |

```python
parser = GaraFormParser(campionato=gara.campionato)  # o None per standalone
data = parser.parse()
GaraService.update_gara(gara_id, name=..., **data)
```

Aggiungere un test anti-drift quando una stessa entità ha >1 form (vedi
`tests/new/integration/test_edit_*_persistence.py`).

### Flash Messages with i18n

```python
from flask_babel import _

flash(_("Operazione completata con successo"), "success")
flash(_("Errore: %(error)s", error=str(e)), "danger")
flash(_("Attenzione: dati mancanti"), "warning")
```

### Pagination

```python
@bp.route("/matches")
@login_required
def match_list():
    page = request.args.get("page", 1, type=int)
    per_page = 20

    pagination = Match.query.filter_by(
        player1_id=current_user.id
    ).paginate(page=page, per_page=per_page, error_out=False)

    return render_template(
        "player/matches.html",
        pagination=pagination,
        matches=pagination.items
    )
```

---

## Admin Routes Structure

Admin routes are nested blueprints under `/admin`:

```python
# routes/admin/__init__.py
from flask import Blueprint

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

# Sub-blueprints
from .campionato import campionato_bp
from .competition import competition_bp
from .match import match_bp

admin_bp.register_blueprint(campionato_bp)
admin_bp.register_blueprint(competition_bp)
admin_bp.register_blueprint(match_bp)
```

### URL Generation

```python
# For nested admin routes
url_for("admin.competition.gara_detail", gara_id=1)
# → /admin/gara/1

url_for("admin.campionato.detail", campionato_id=1)
# → /admin/campionato/1
```

---

## Gotchas

### Always Use db.session.get() for Primary Keys

```python
# ✅ Correct - uses get() for PK lookup
gara = db.session.get(Gara, gara_id)

# ❌ Deprecated - filter_by for PK
gara = Gara.query.filter_by(id=gara_id).first()
```

### Check Soft-Deleted Users

```python
# User model has soft delete
user = db.session.get(User, user_id)
if user and user.is_deleted:
    abort(404)  # Treat as not found
```

### Handle Standalone Gara

```python
# Gara can be standalone (no campionato)
if gara.campionato_id:
    return redirect(url_for("admin.campionato.detail", campionato_id=gara.campionato_id))
else:
    return redirect(url_for("admin.competition.gara_detail", gara_id=gara.id))
```

---

## Do Not

- **Do not use `filter_by(id=...)` for PK lookup** - Use `db.session.get(Model, id)`
- **Do not skip permission checks** - Always verify `current_user.can_manage_*()` for entity operations
- **Do not call `db.session.commit()`** - Services handle transactions via `@transactional`
- **Do not forget soft-delete check** - Deleted users should be treated as not found
- **Do not assume gara has campionato** - Check `gara.campionato_id` before accessing
