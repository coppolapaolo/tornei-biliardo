"""Una partita alla distanza aspetta il direttore, anche se è pari.

Presidio unitario (la CI esegue solo questi) del bug corretto il 2026-10-06:
il pulsante «Valida Risultato» della pagina della partita chiedeva il
vincitore e `match.validated_by_admin`, campo che su `Match` non esiste.
Il percorso con la pagina vera è in
`tests/new/integration/test_valida_risultato_sui_pareggi.py`.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from models.match.models import awaiting_validation
from models.status_enum import MatchStatus

pytestmark = pytest.mark.unit

TEMPLATES = Path(__file__).resolve().parents[3] / "templates"


def _partita(status, at_distance=True, confirmed=False):
    return SimpleNamespace(
        status=status, is_at_distance=at_distance, is_player_validated=confirmed
    )


def test_pareggio_alla_distanza_aspetta_il_direttore():
    # Nessun vincitore: la regola non lo guarda.
    assert awaiting_validation(_partita(MatchStatus.PLAYING.value)) is True


@pytest.mark.parametrize(
    "partita",
    [
        _partita(MatchStatus.PLAYING.value, at_distance=False),
        _partita(MatchStatus.PLAYING.value, confirmed=True),
        _partita(MatchStatus.CLOSED_UNILATERALLY.value),
        _partita(MatchStatus.CONFIRMED_BY_BOTH.value),
    ],
)
def test_non_aspetta_il_direttore(partita):
    assert awaiting_validation(partita) is False


def test_nessun_template_legge_validated_by_admin_sulla_partita():
    """`validated_by_admin` vive su `Rack` e `Set`: su `Match` Jinja lo dà falso."""
    letture = [
        f"{path.relative_to(TEMPLATES)}:{n}"
        for path in TEMPLATES.rglob("*.html")
        for n, riga in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if re.search(r"\bmatch\.validated_by_admin\b", riga)
        and "{#" not in riga
        and "Fino al" not in riga
    ]
    assert letture == []
