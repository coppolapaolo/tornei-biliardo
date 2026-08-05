"""Il parametro `next` del login non deve diventare un open redirect (#61).

Il link pubblico di iscrizione porta chi non è autenticato su
`/auth/login?next=/g/<token>`: da lì in poi `next` arriva dall'URL, quindi da
chiunque. Senza validazione, `?next=https://sito-falso/login` sposta l'utente
fuori dal sito nell'istante esatto in cui ha appena digitato le credenziali —
sulla pagina più adatta a chiederle di nuovo.
"""

from __future__ import annotations

import pytest

from utils.safe_redirect import safe_next_url


@pytest.mark.unit
class TestSafeNextUrl:
    @pytest.mark.parametrize(
        "value",
        [
            "/g/abc123",
            "/g/abc123?confirm=1",
            "/admin/gara/7",
            "/",
        ],
    )
    def test_internal_paths_pass(self, value):
        assert safe_next_url(value) == value

    @pytest.mark.parametrize(
        "value",
        [
            "https://sito-falso.example/login",
            "http://sito-falso.example/login",
            "//sito-falso.example/login",
            "///sito-falso.example",
            "\\\\sito-falso.example",
            "/\\sito-falso.example",
            "javascript:alert(1)",
            "gara",
        ],
    )
    def test_everything_else_is_rejected(self, value):
        assert safe_next_url(value) is None

    def test_missing_value_is_not_an_error(self):
        assert safe_next_url(None) is None
        assert safe_next_url("") is None
