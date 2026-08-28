"""Le statistiche nel profilo: forma 7c, e la riga dei runout.

Il componente era in markup Bootstrap con quattro numeri colorati
(`text-primary`, `text-info`, `text-success`, `text-warning`): classi che
`theme-7c.css` **non sovrascrive**, quindi erano l'unico punto della pagina
dove si vedevano colori fuori dalla palette. Qui si fissa che non tornino.

Niente DB: il componente legge solo il dizionario `stats`.
"""

from __future__ import annotations

TEMPLATE = "components/_player_statistics.html"

#: Le quattro classi Bootstrap che nessuno ridefinisce. Se una ricompare, il
#: profilo torna ad avere il blu e il verde di Bootstrap in mezzo al 7c.
COLORI_BOOTSTRAP = ("text-primary", "text-info", "text-success", "text-warning")


def _stats(**overrides):
    base = {
        "tournaments_played": 6,
        "provas_played": 23,
        "won_matches": 68,
        "win_percentage": 61.0,
        "total_matches": 111,
        "lost_matches": 43,
    }
    base.update(overrides)
    return base


def _render(app, stats, is_own_profile=True):
    with app.test_request_context():
        return app.jinja_env.get_template(TEMPLATE).render(
            stats=stats, is_own_profile=is_own_profile
        )


class TestFormaSetteC:
    def test_niente_colori_bootstrap(self, app):
        html = _render(app, _stats())

        for classe in COLORI_BOOTSTRAP:
            assert classe not in html, f"{classe} è tornata nel profilo"

    def test_usa_le_classi_del_design_system(self, app):
        """Le stesse del componente accanto (`_player_challenge_statistics`)."""
        html = _render(app, _stats())

        assert "c7-sechead" in html
        assert "c7-card" in html
        assert "c7-num-lg" in html
        assert "c7-rows__row" in html

    def test_i_quattro_numeri_ci_sono_ancora(self, app):
        html = _render(app, _stats())

        for valore in ("6", "23", "68", "61.0%"):
            assert valore in html


class TestRigaRunout:
    def test_compare_col_totale_e_il_sottoinsieme(self, app):
        """«Runout: 26, di cui 9 break and run»: insieme e sottoinsieme."""
        html = _render(app, _stats(runouts={"total": 26, "break_and_runs": 9}))

        assert "Runout" in html
        assert "26" in html
        assert "9 break and run" in html

    def test_senza_break_and_run_niente_sottoriga(self, app):
        """«di cui 0» non è un'informazione, è rumore."""
        html = _render(app, _stats(runouts={"total": 4, "break_and_runs": 0}))

        assert "Runout" in html
        assert "break and run" not in html

    def test_chi_non_ne_ha_non_vede_la_riga(self, app):
        """Una voce a zero suggerisce che ci sia qualcosa da fare. Non c'è."""
        html = _render(app, _stats(runouts={"total": 0, "break_and_runs": 0}))

        assert "Runout" not in html

    def test_senza_la_chiave_il_componente_non_si_rompe(self, app):
        """Il profilo altrui e quello proprio la passano entrambi, ma il
        componente è incluso anche da chi potrebbe non farlo."""
        html = _render(app, _stats())

        assert "Runout" not in html

    def test_a_zero_partite_non_si_mostra_nessuna_riga(self, app):
        html = _render(
            app,
            _stats(total_matches=0, runouts={"total": 3, "break_and_runs": 1}),
        )

        assert "Sconfitte" not in html
        assert "Runout" not in html
