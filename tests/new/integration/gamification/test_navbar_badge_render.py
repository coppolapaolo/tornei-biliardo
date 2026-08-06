"""Badge navbar "vivo" — wiring server-side (§11-quater).

Il badge in `templates/base.html` deve esporre l'anello di progresso e i
data-attribute che alimentano l'animazione lato JS (count-up XP, anello,
pulse/glow). Qui verifichiamo il *render* del template: che per un player
autenticato il badge contenga la struttura attesa con i valori da
`get_level_progress`, e che per un admin il badge sia assente.

Renderizziamo `base.html` direttamente in un request context (con i context
processor attivi) invece di colpire `/dashboard`: il route reale passa da
DashboardService ed è sensibile al leak di sessione di `@transactional` tra
test (cfr. i numerosi test skipped per lo stesso motivo). Qui ci interessa solo
il contratto del markup che il JS consuma.

Il comportamento JS (pulse/glow/cap toast) non è coperto — non esiste
infrastruttura di test JS.
"""

from __future__ import annotations

from flask import render_template
from flask_login import login_user, logout_user


def _render_base_as(app, user) -> str:
    with app.test_request_context("/"):
        login_user(user)
        try:
            return render_template("base.html")
        finally:
            logout_user()


class TestNavbarBadgeRender:
    def test_badge_exposes_progress_ring_and_data_attrs(self, app, logged_in_client):
        # get_level_progress restituisce i default (livello 1, 0 XP) anche senza
        # UserLevel: non serve award_xp (che inquinerebbe la sessione).
        _client, user = logged_in_client(role="player")

        html = _render_base_as(app, user)

        # Struttura del badge vivo.
        assert 'id="gami-badge"' in html
        assert "gami-badge-ring" in html
        assert 'id="gami-badge-level"' in html
        assert 'id="gami-badge-xp"' in html

        # Data-attribute che il JS consuma (count-up + anello).
        assert "data-current-xp=" in html
        assert "data-xp-next=" in html
        assert "data-progress=" in html
        # La variabile CSS dell'anello è impostata server-side.
        assert "--gami-progress:" in html

    def test_badge_absent_for_admin(self, app, logged_in_client):
        """Gli admin sono esclusi dalla gamification → niente badge."""
        _client, admin = logged_in_client(role="admin")
        html = _render_base_as(app, admin)
        assert 'id="gami-badge"' not in html
