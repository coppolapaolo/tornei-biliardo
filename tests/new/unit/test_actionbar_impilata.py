"""La barra azioni in colonna non schiaccia i suoi pulsanti.

`.c7-actionbar .btn { flex: 1 }` fa allargare i pulsanti su una barra in
riga. Con `flex-direction: column` scritto a mano sulla barra, lo stesso
`flex: 1` (base 0%) lavora sull'asse verticale e vince sull'altezza di 56px
di `.btn`, che non ha padding verticale: sul telefono «Inizia a segnare»
dell'avvio rapido era alto una riga di testo. Da `lg` in su la regola
diventa `flex: 0 0 auto`, quindi sul desktop non si vedeva.

La colonna si chiede con `.c7-actionbar--stack`, che rimette `flex: 0 0 auto`.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_nessuna_actionbar_mette_la_colonna_a_mano():
    colpevoli = []
    for path in (ROOT / "templates").rglob("*.html"):
        for n, riga in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "c7-actionbar" in riga and "flex-direction:column" in riga.replace(
                " ", ""
            ):
                colpevoli.append(f"{path.relative_to(ROOT)}:{n}")
    assert colpevoli == [], (
        "Barra azioni in colonna scritta a mano: usa `c7-actionbar--stack`, "
        "altrimenti `flex: 1` schiaccia i pulsanti sul telefono: "
        + ", ".join(colpevoli)
    )


def test_la_barra_in_colonna_non_allarga_i_pulsanti_in_altezza():
    css = (ROOT / "static/css/theme-7c.css").read_text(encoding="utf-8")
    regola = re.search(r"\.c7-actionbar--stack \.btn\s*\{([^}]*)\}", css)
    assert regola is not None
    assert "flex: 0 0 auto" in regola.group(1)


def test_l_avvio_rapido_usa_la_barra_in_colonna():
    html = (ROOT / "templates/individual_match/quick_match.html").read_text(
        encoding="utf-8"
    )
    assert "c7-actionbar c7-actionbar--stack" in html
