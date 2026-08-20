"""Il tabellone orizzontale: segnare toccando la metà del giocatore (issue #170).

Al tavolo si segna con una mano sola, spesso senza guardare: il bersaglio è
mezza schermata, non un pulsante `+1`. Qui si fissa il contratto del markup —
quando le due metà sono toccabili e quando cedono il posto — perché è
esattamente la parte che, cambiando il componente, si perde in silenzio: una
`<div>` muta al posto di un `<button>` non rompe niente, smette solo di
funzionare per chi usa la tastiera o il lettore di schermo.

Niente DB: il componente si rende con oggetti finti, come
`test_match_scoring_state.py`.
"""

from __future__ import annotations

import pytest

from models.match.distance import Distance
from models.status_enum import MatchStatus

TEMPLATE = "components/_match_scoreboard.html"

# La classe compare anche nel selettore dello script che aggancia il lampo:
# per contare le metà toccabili serve l'attributo, non il nome della classe.
META_TOCCABILE = 'class="c7-board__side c7-board__side--tap"'


class _User:
    def __init__(self, user_id, username="Tizio", authenticated=True):
        self.id = user_id
        self.username = username
        self.is_authenticated = authenticated


class _Rack:
    def __init__(self, rack_number, winner_id):
        self.rack_number = rack_number
        self.winner_id = winner_id
        self.is_deleted = False


class _Match:
    """Il minimo che il tabellone legge di una partita."""

    def __init__(
        self,
        *,
        status=MatchStatus.PLAYING.value,
        p1_score=0,
        p2_score=0,
        table_assignment=1,
        p1_confirmed=False,
        p2_confirmed=False,
        racks=None,
    ):
        self.status = status
        self.player1 = _User(1, "Rossi M.")
        self.player2 = _User(2, "Bianchi L.")
        self.player1_id = 1
        self.player2_id = 2
        self.player1_score = p1_score
        self.player2_score = p2_score
        self.distance_config = Distance(racks=5, is_race_to_racks=True)
        self.player1_confirmed = p1_confirmed
        self.player2_confirmed = p2_confirmed
        self.table_assignment = table_assignment
        self.is_multi_set = False
        self.match_distance = None
        self.is_race_to_sets = True
        self.gara = None
        self.round_number = 1
        self.racks = racks if racks is not None else []


def _render(app, match, user=None):
    with app.test_request_context():
        return app.jinja_env.get_template(TEMPLATE).render(
            match=match,
            current_user=user or _User(1, "Rossi M."),
        )


class TestMetaToccabili:
    def test_in_corso_le_meta_sono_pulsanti(self, app):
        html = _render(app, _Match(p1_score=2, p2_score=1))

        assert html.count(META_TOCCABILE) == 2
        # `<button>`, non una `<div>` con un `onclick`: tastiera e lettore di
        # schermo passano di qui.
        assert 'aria-label="Un triangolo a Rossi M."' in html
        assert 'aria-label="Un triangolo a Bianchi L."' in html

    def test_toccare_la_meta_segna_a_quel_giocatore(self, app):
        html = _render(app, _Match())

        assert "addRack(1, this)" in html
        assert "addRack(2, this)" in html

    def test_i_piu_uno_non_ci_sono_piu(self, app):
        html = _render(app, _Match())

        assert ">+1<" not in html

    def test_l_annulla_resta_un_pulsante_esplicito(self, app):
        """Con un bersaglio così grande i tocchi sbagliati aumentano."""
        html = _render(app, _Match(p1_score=1, racks=[_Rack(1, 1)]))

        assert "c7-board__undo--wide" in html
        assert "removeRack(1, this)" in html

    def test_la_meta_di_chi_guarda_si_riconosce(self, app):
        html = _render(app, _Match(), user=_User(2, "Bianchi L."))

        assert "c7-board__you" in html


class TestQuandoLeMetaSiSpengono:
    def test_distanza_raggiunta_niente_da_toccare(self, app):
        """A 5-0 su un «al 5» il triangolo non va segnato: le metà si spengono."""
        html = _render(app, _Match(p1_score=5, p2_score=0))

        assert META_TOCCABILE not in html

    def test_distanza_raggiunta_le_meta_cedono_il_posto(self, app):
        html = _render(app, _Match(p1_score=5, p2_score=0))

        assert "Accetta" in html
        assert "Rifiuta" in html

    def test_senza_tavolo_assegnato_le_meta_dicono_perche(self, app):
        """Un'area muta che non fa niente è peggio di un pulsante spento."""
        html = _render(app, _Match(table_assignment=None))

        assert META_TOCCABILE not in html
        assert "Serve un tavolo assegnato prima di iniziare." in html

    def test_partita_chiusa_niente_da_toccare(self, app):
        html = _render(
            app,
            _Match(
                status=MatchStatus.CONFIRMED_BY_BOTH.value,
                p1_score=5,
                p2_score=3,
                p1_confirmed=True,
                p2_confirmed=True,
            ),
        )

        assert META_TOCCABILE not in html


class TestRiscontroAlTocco:
    def test_il_lampo_e_la_vibrazione_sono_agganciati(self, app):
        """Chi segna sta guardando il tavolo: il numero che cambia non basta."""
        html = _render(app, _Match())

        assert "is-flash" in html
        assert "navigator.vibrate" in html


@pytest.mark.parametrize("nome_funzione", ["addRackWin", "segnaTriangolo"])
def test_le_funzioni_della_pagina_ospite_restano_le_sue(app, nome_funzione):
    """Il tabellone non ha endpoint suoi: chiama il segnapunti della pagina."""
    with app.test_request_context():
        html = app.jinja_env.get_template(TEMPLATE).render(
            match=_Match(),
            current_user=_User(1, "Rossi M."),
            add_rack_js_func=nome_funzione,
        )

    assert f"{nome_funzione}(1, this)" in html
