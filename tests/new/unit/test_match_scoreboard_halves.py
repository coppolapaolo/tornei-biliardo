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

from models.match.base_match import BaseMatchMixin
from models.match.break_rules import DEFAULT_BREAK_RULE, DEFAULT_START_RULE
from models.match.distance import Distance
from models.status_enum import MatchStatus

TEMPLATE = "components/_match_scoreboard.html"

# La classe compare anche nel selettore dello script che aggancia il lampo:
# per contare le metà toccabili serve l'attributo, non il nome della classe.
META_TOCCABILE = 'class="c7-board__side c7-board__side--tap"'


class _User:
    def __init__(self, user_id, username="Tizio", authenticated=True, elo=1350):
        self.id = user_id
        self.username = username
        self.is_authenticated = authenticated
        # I due pool: il tabellone ne mostra uno solo, e quale lo decide il
        # tipo di partita (`utils/elo_visibility.py`).
        self.elo_rating = elo
        self.elo_global_rating = elo


class _Rack:
    def __init__(self, rack_number, winner_id, *, run_out=False, break_player_id=None):
        self.id = 100 + rack_number
        self.rack_number = rack_number
        self.winner_id = winner_id
        self.is_deleted = False
        self.is_run_out = run_out
        self.break_player_id = break_player_id

    @property
    def is_break_and_run(self):
        """Stessa deduzione dei due modelli veri (ADR-056)."""
        return bool(
            self.is_run_out
            and self.break_player_id is not None
            and self.break_player_id == self.winner_id
        )


class _Match(BaseMatchMixin):
    """Il minimo che il tabellone legge di una partita.

    Estende `BaseMatchMixin` **davvero**, invece di reimplementarne i pezzi:
    `active_racks()`, `next_break_player_id` e `needs_lag` sono contratto
    condiviso fra `Match` e `IndividualMatch`, e una copia qui sarebbe la terza
    — cioè quella che resta indietro senza che nessun test se ne accorga.
    """

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
        start_rule=DEFAULT_START_RULE,
        break_rule=DEFAULT_BREAK_RULE,
        first_break_player_id=None,
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
        # Senza `gara_id` questa e' una sfida individuale, coerentemente con
        # `gara = None` qui sopra: il tabellone scrive «Sfida individuale» in
        # testata e accanto ai nomi mette l'Elo globale.
        self.gara_id = None
        self.round_number = 1
        self.racks = racks if racks is not None else []
        self.started_at = None
        self._start_rule = start_rule
        self._break_rule = break_rule
        self.lag_winner_id = None
        self.first_break_player_id = first_break_player_id

    @property
    def effective_start_rule(self):
        return self._start_rule

    @property
    def effective_break_rule(self):
        return self._break_rule


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

    def test_a_distanza_raggiunta_le_risposte_sono_due_non_tre(self, app):
        """«Rifiuta» **è** l'annulla: la route toglie l'ultimo triangolo.

        Tenere anche il ⟲ voleva dire tre pulsanti per due azioni, con quello
        muto schiacciato in mezzo. E in questo stato l'ultimo triangolo è
        proprio quello che ha chiuso la partita, quindi «Rifiuta» è anche il
        nome giusto per il gesto: non correggo un punto qualunque, dico che il
        risultato non mi torna.
        """
        html = _render(app, _Match(p1_score=5, p2_score=3, racks=[_Rack(1, 1)]))

        assert "Accetta" in html
        assert "Rifiuta" in html
        # Il ⟲ non c'è: il suo `aria-label` è l'unico modo di riconoscerlo,
        # perché il pulsante è una sola icona.
        assert "Annulla ultimo triangolo" not in html

    def test_dopo_aver_confermato_l_annulla_torna_perche_e_la_sola_via(self, app):
        """Qui non è un doppione: le risposte non ci sono più, e un triangolo
        segnato per sbaglio va pur tolto in qualche modo."""
        html = _render(
            app,
            _Match(
                p1_score=5,
                p2_score=3,
                p1_confirmed=True,
                racks=[_Rack(1, 1)],
            ),
        )

        assert "Rifiuta" not in html
        assert "Annulla ultimo triangolo" in html

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


class TestIlTelefonoCheSiSpegne:
    """Il tocco che tiene acceso lo schermo non deve segnare un triangolo.

    Nessuna API dice «lo schermo sta per spegnersi», quindi quel tocco non si
    riconosce: si toglie il motivo di farlo (il telefono resta acceso finché il
    tabellone è davanti) e si ignora il primo attimo dopo che la pagina torna
    in primo piano, cioè dopo uno sblocco.
    """

    def test_il_telefono_resta_acceso_col_tabellone_aperto(self, app):
        html = _render(app, _Match())

        assert "wakeLock" in html
        assert "navigator.wakeLock.request('screen')" in html

    def test_lo_schermo_si_libera_quando_il_tabellone_non_serve(self, app):
        """Tenere acceso un telefono su una pagina che non si guarda è scortese."""
        html = _render(app, _Match())

        assert "release()" in html
        assert "visibilitychange" in html

    def test_dopo_uno_sblocco_c_e_una_finestra_cieca(self, app):
        html = _render(app, _Match())

        assert "CIECA_MS" in html
        # In cattura sul contenitore: da lì ferma l'evento prima che arrivi
        # all'`onclick` della metà.
        assert "event.stopPropagation();" in html


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


class TestLEloAccantoAlNome:
    """Chi c'è dall'altra parte del tavolo, e quanto vale.

    Prima di cominciare i due si misurano, e il tabellone è la schermata che
    hanno davanti in quel momento. Il numero però non è sempre lo stesso: le
    gare muovono l'Elo competitivo, le sfide individuali il globale — scrivere
    l'uno al posto dell'altro non solleva niente, mostra solo un numero che
    quella partita non muoverà mai (`utils/elo_visibility.py`).
    """

    def test_i_due_elo_compaiono_sotto_i_nomi(self, app):
        html = _render(app, _Match())

        assert html.count("c7-board__elo") == 2
        assert "1350" in html

    def test_la_sfida_individuale_dichiara_il_pool_globale(self, app):
        """Il nome per esteso sta nel `title`: nella riga non ci sta."""
        html = _render(app, _Match())

        assert "Elo globale" in html
        assert "Elo competitivo" not in html

    def test_chi_lo_ha_spento_non_lo_mostra(self, app, db_session):
        """`show_elo` è opt-out: acceso di suo, e sparisce quando lo si toglie."""
        import uuid

        from models.user.models import User
        from models.user.privacy_models import UserPrivacySetting
        from models.user.role_enum import UserRole

        # Qui servono utenti veri: la preferenza vive su una riga con una
        # chiave esterna, e il tabellone la interroga per id.
        veri = []
        for _ in range(2):
            tag = uuid.uuid4().hex[:8]
            u = User(
                username=f"u_{tag}",
                email=f"{tag}@example.test",
                role=UserRole.PLAYER.value,
            )
            u.set_password("x")
            db_session.add(u)
            veri.append(u)
        db_session.commit()

        match = _Match()
        match.player1_id, match.player2_id = veri[0].id, veri[1].id
        match.player1 = _User(veri[0].id, "Rossi M.")
        match.player2 = _User(veri[1].id, "Bianchi L.")

        db_session.add(UserPrivacySetting(user_id=veri[1].id, show_elo=False))
        db_session.commit()

        html = _render(app, match, user=_User(veri[0].id, "Rossi M."))

        # Resta quello di chi non l'ha spento: la scelta è di ciascuno.
        assert html.count("c7-board__elo") == 1
