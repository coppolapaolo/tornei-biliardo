"""Il verso di scrittura della conversione di fuso.

Il progetto ha sempre avuto solo metà della conversione: in lettura
``utils/jinja.py`` interpreta il naive del DB come UTC e mostra in ora italiana,
in scrittura non c'era nessuno. Chi digitava ``21:00`` se lo vedeva rimandare
indietro come ``23:00``, senza un errore da nessuna parte.

Il test che conta davvero è il **giro completo**: quello che digito è quello che
mi viene mostrato. Gli altri servono a non farlo passare per caso.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from utils.local_time import DISPLAY_TIMEZONE, parse_local_datetime, to_utc_naive

pytestmark = pytest.mark.unit


class TestTheRoundTrip:
    """Quello che l'utente digita è quello che l'utente rilegge."""

    @pytest.mark.parametrize(
        "typed",
        [
            "2026-06-12T21:00",  # ora legale: +2
            "2026-01-15T21:00",  # ora solare: +1
            "2026-03-29T04:00",  # dopo il cambio di primavera
            "2026-10-25T04:00",  # dopo il cambio d'autunno
        ],
    )
    def test_what_you_type_is_what_you_read_back(self, app, typed):
        from utils.jinja import format_datetime_local_text

        with app.app_context():
            shown = format_datetime_local_text(parse_local_datetime(typed))
        assert typed.split("T")[1] in shown, f"{typed} → {shown}"

    def test_a_fixed_offset_would_not_survive_this(self, app):
        """Giugno e gennaio hanno offset diversi: +1 fisso romperebbe uno dei due."""
        summer = parse_local_datetime("2026-06-12T21:00")
        winter = parse_local_datetime("2026-01-15T21:00")
        assert summer is not None and winter is not None
        assert summer.hour == 19  # CEST, -2
        assert winter.hour == 20  # CET, -1


class TestWhatComesOut:
    def test_the_result_is_naive(self):
        """Il DB tiene naive: restituire un aware romperebbe i confronti."""
        parsed = parse_local_datetime("2026-06-12T21:00")
        assert parsed is not None
        assert parsed.tzinfo is None

    def test_seconds_are_accepted(self):
        """L'input li manda se dichiara uno ``step`` al secondo."""
        assert parse_local_datetime("2026-06-12T21:00:30") is not None

    def test_an_explicit_utc_marker_is_respected(self):
        """Se il valore porta già la Z, il fuso ce l'ha: non si sovrascrive."""
        parsed = parse_local_datetime("2026-06-12T19:00Z")
        assert parsed == datetime(2026, 6, 12, 19, 0)


class TestWhatIsRefused:
    @pytest.mark.parametrize("bad", ["", None, "   ", "non-una-data", "12/06/2026"])
    def test_garbage_is_none_not_an_exception(self, bad):
        """A valle c'è una validazione che sa parlare all'utente: meglio di un 500."""
        assert parse_local_datetime(bad) is None


class TestToUtcNaive:
    def test_an_aware_input_keeps_its_own_timezone(self):
        """Chi passa un fuso esplicito sa quello che fa: non glielo si riscrive."""
        aware = datetime(2026, 6, 12, 19, 0, tzinfo=timezone.utc)
        assert to_utc_naive(aware) == datetime(2026, 6, 12, 19, 0)

    def test_a_naive_input_is_read_as_italian_time(self):
        naive = datetime(2026, 6, 12, 21, 0)
        assert to_utc_naive(naive) == datetime(2026, 6, 12, 19, 0)

    def test_the_display_timezone_is_the_one_the_filters_use(self):
        """Se i due divergessero, il giro completo smetterebbe di tornare."""
        assert str(DISPLAY_TIMEZONE) == "Europe/Rome"
