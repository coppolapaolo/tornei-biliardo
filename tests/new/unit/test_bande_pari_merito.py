"""Le bande del tabellone si mostrano sulla posizione più alta: «5° pari merito».

Decisione dell'utente del 2026-10-11, dopo la #661: la regola generale del
pari merito — sulla posizione più alta, e lo si dice — vale anche per le bande
del tabellone, che fino ad allora mostravano l'intervallo «5°–8°» (issue #240,
ADR-040, emendamento). Cambia solo la presentazione: la posizione della banda
e i punti per piazzamento erano già quelli del posto più alto, e qui sono
presidiati perché nessuno li sposti credendo di seguire l'etichetta.

I componenti si rendono senza database, come `test_classifica_direttore.py`.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from models.classification.bracket_standings import positions_from_bands
from models.classification.position_points import points_for_position
from models.competition.tabellone_view import Banda, NomeRound, RigaBanda

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[3]


def _riga(nome: str, uid: int, posizione: int, uscita: str | None) -> RigaBanda:
    return RigaBanda(
        user=SimpleNamespace(username=nome, id=uid),
        user_id=uid,
        position=posizione,
        uscita=NomeRound(uscita) if uscita else None,
        vinta=posizione == 1,
    )


def _bande() -> list[Banda]:
    """Otto giocatori, senza finalina: 1°, 2°, due terzi, quattro quinti."""
    return [
        Banda(1, (_riga("bp_campione", 1, 1, "finale"),)),
        Banda(2, (_riga("bp_finalista", 2, 2, "finale"),)),
        Banda(
            3,
            (
                _riga("bp_semi_a", 3, 3, "semifinali"),
                _riga("bp_semi_b", 4, 3, "semifinali"),
            ),
        ),
        Banda(
            5,
            tuple(_riga(f"bp_quarti_{i}", 10 + i, 5, "quarti") for i in range(4)),
        ),
    ]


# ── La sostanza: posizione e punti non cambiano ─────────────────────────────


def test_la_banda_vale_la_posizione_piu_alta():
    posizioni = positions_from_bands([[1], [2], [3, 4], [5, 6, 7, 8]])
    assert sorted(posizioni.values()) == [1, 2, 3, 3, 5, 5, 5, 5]


def test_i_quartifinalisti_prendono_tutti_i_punti_del_quinto_posto():
    posizioni = positions_from_bands([[1], [2], [3, 4], [5, 6, 7, 8]])
    punti = {points_for_position(posizioni[uid]) for uid in (5, 6, 7, 8)}
    assert punti == {points_for_position(5)}
    terzi = {points_for_position(posizioni[uid]) for uid in (3, 4)}
    assert terzi == {points_for_position(3)}


def test_la_banda_non_porta_piu_l_ultima_posizione():
    """L'intervallo non si mostra più: la banda sa solo da dove parte."""
    banda = _bande()[3]
    assert banda.posizione == 5
    assert banda.condivisa
    assert not hasattr(banda, "ultima")


# ── La presentazione ────────────────────────────────────────────────────────


def _render(app, template: str, **contesto) -> str:
    with app.test_request_context():
        return app.jinja_env.get_template(template).render(**contesto)


def test_la_classifica_a_bande_dice_quinto_pari_merito(app):
    html = _render(app, "direttore/_classifica_bande.html", bande_finali=_bande())

    assert "°–" not in html
    pastiglie = re.findall(r'c7-banda__pos[^"]*">([^<]+)<', html)
    assert pastiglie == ["1°", "2°"] + ["3° pari merito"] * 2 + ["5° pari merito"] * 4


def test_una_definizione_sola_dell_etichetta(app):
    """Classifica, schermo in sala e podio usano la stessa macro."""
    sorgente = (
        '{% import "components/_tabellone_macros.html" as t with context %}'
        "[{{ t.posto_della_banda(5, true) }}][{{ t.posto_della_banda(2, false) }}]"
    )
    with app.test_request_context():
        html = app.jinja_env.from_string(sorgente).render()
    assert html == "[5° pari merito][2°]"
    for template in (
        "direttore/_classifica_bande.html",
        "direttore/_podio.html",
        "public/schermo_sala.html",
    ):
        assert "posto_della_banda(" in (ROOT / "templates" / template).read_text(
            encoding="utf-8"
        ), template


def test_il_podio_senza_finalina_dice_terzo_pari_merito(app):
    podio = [b.righe for b in _bande() if b.posizione <= 3]
    html = _render(app, "direttore/_podio.html", classification=None, bande_podio=podio)

    assert "°–" not in html
    assert "3° pari merito" in html
    assert "1°" in html and "2°" in html


def test_nessun_template_mostra_l_intervallo_della_banda():
    """Presidio statico: l'etichetta «N°–M°» non torna nei template."""
    colpevoli = [
        str(p.relative_to(ROOT))
        for p in (ROOT / "templates").rglob("*.html")
        if "°–' ~" in p.read_text(encoding="utf-8")
        or "°–{{" in p.read_text(encoding="utf-8")
    ]
    assert colpevoli == []
