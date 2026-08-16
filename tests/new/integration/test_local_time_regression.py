"""Regressione: l'ora digitata è l'ora salvata, su ogni superficie.

Il bug era sistematico e silenzioso — un `<input type="datetime-local">` manda
l'ora **locale**, il DB tiene i naive come **UTC**, e in lettura
``|datetime_local`` risomma il fuso. Chi fissava un appuntamento per le 21:00 se
lo vedeva rimandare indietro come le 23:00.

Il test guarda le *superfici*, non l'helper: quello ha già i suoi test unitari.
Qui interessa che ogni punto che legge un orario dall'utente ci passi davvero.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]

#: I punti che leggono un orario da un ``datetime-local``. Aggiungerne uno qui
#: quando nasce una superficie nuova è il modo per non ripetere il bug.
SURFACES = (
    "routes/exam/requests.py",
    "routes/individual_match/proposals.py",
    "routes/admin/competition/inscriptions.py",
    "routes/gamification/admin.py",
    "routes/individual_match/matches.py",
)

#: I campi ripopolati in un form di modifica. Il verso di lettura ha lo stesso
#: bug del verso di scrittura, e nessuno dei due si vede: chi riapre il form,
#: non tocca l'orario e salva, arretra l'appuntamento di un'ora — ogni volta.
#: Qui si guarda che il valore passi dal filtro, non da uno ``strftime`` crudo.
REPOPULATED_FIELDS = (
    ("templates/components/_modify_dates_modal.html", "inscription_start"),
    ("templates/components/_modify_dates_modal.html", "inscription_end"),
    ("templates/gamification/admin/quest_form.html", "start_date"),
    ("templates/gamification/admin/quest_form.html", "end_date"),
    ("templates/individual_match/match_detail.html", "started_at"),
    ("templates/individual_match/match_detail.html", "ended_at"),
)


def _source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


@pytest.mark.parametrize("relative", SURFACES)
def test_the_surface_converts_instead_of_storing_raw(relative):
    """Deve passare da ``parse_local_datetime``, non da ``fromisoformat``."""
    source = _source(relative)
    assert "parse_local_datetime" in source, relative


@pytest.mark.parametrize("relative", SURFACES)
def test_the_surface_does_not_parse_by_hand(relative):
    """Un ``fromisoformat``/``strptime`` su ``scheduled_at`` sarebbe il bug di prima.

    Si guarda l'AST e non il testo: un'occorrenza dentro un commento o una
    docstring non deve far fallire il test, e una vera non deve sfuggirgli.
    """
    tree = ast.parse(_source(relative))
    hand_parsers = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"fromisoformat", "strptime"}
    }
    assert not hand_parsers, f"{relative} parsa a mano: {hand_parsers}"


def test_a_proposal_keeps_the_hour_the_player_typed(app):
    """Il giro completo sulla proposta di match: 21:00 digitate, 21:00 lette."""
    from utils.jinja import format_datetime_local_text
    from utils.local_time import parse_local_datetime

    with app.app_context():
        stored = parse_local_datetime("2026-06-12T21:00")
        assert "21:00" in format_datetime_local_text(stored)


@pytest.mark.parametrize("relative,field", REPOPULATED_FIELDS)
def test_the_edit_form_is_repopulated_in_local_time(relative, field):
    """Il ``value`` del campo deve venire da ``|datetime_input``."""
    source = _source(relative)
    marker = f'name="{field}"'
    assert marker in source, f"{relative}: campo {field} sparito"

    # La riga del `value` puo' stare su una riga sua: si guarda la finestra
    # dell'elemento, dal `name=` al `>` che lo chiude.
    start = source.index(marker)
    element = source[start : source.index(">", start)]
    assert "datetime_input" in element, f"{relative}: {field} ripopolato a mano"


def test_the_form_survives_a_round_trip_without_drifting(app):
    """Digitato → salvato → ripopolato: la stessa ora, non una spostata.

    È il giro che il bug rompeva in silenzio, e l'unico modo di accorgersene
    era riaprire il form: ogni salvataggio confermato senza modifiche spostava
    l'orario di un fuso.
    """
    from utils.jinja import format_datetime_input
    from utils.local_time import parse_local_datetime

    with app.app_context():
        typed = "2026-06-12T21:00"
        assert format_datetime_input(parse_local_datetime(typed)) == typed

        # Anche d'inverno, quando lo scarto è di un'ora invece che di due.
        winter = "2026-01-12T21:00"
        assert format_datetime_input(parse_local_datetime(winter)) == winter


def test_opening_inscriptions_keeps_the_hour_that_was_typed(
    logged_in_client, db_session
):
    """Il giro vero, dal form al DB: 09:00 e 21:00 digitate restano tali.

    Prima il valore del ``datetime-local`` finiva sul DB così com'era, e la
    gara si apriva alle iscrizioni due ore dopo l'ora scritta sul modale.
    """
    from datetime import date, timedelta

    from models.competition.models import Gara
    from models.competition.services import GaraService
    from utils.jinja import format_datetime_input

    client, manager = logged_in_client(role="admin")
    gara = GaraService.create_gara(
        campionato_id=None,
        number=1,
        name="Fuso orario iscrizioni",
        date=date.today() + timedelta(days=30),
        director_id=manager.id,
        max_participants=8,
        discipline="8_ball",
        distance=5,
    )

    response = client.post(
        f"/admin/gara/{gara.id}/open_inscriptions",
        data={
            "inscription_start": "2026-08-20T09:00",
            "inscription_end": "2026-09-10T21:00",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200

    stored = db_session.get(Gara, gara.id)
    assert format_datetime_input(stored.inscription_start) == "2026-08-20T09:00"
    assert format_datetime_input(stored.inscription_end) == "2026-09-10T21:00"
    # Sul DB il naive è UTC: in agosto l'Italia è UTC+2.
    assert stored.inscription_start.hour == 7

    # Riaprire il modale di modifica e salvare senza toccare nulla: prima
    # questo era il giro che spostava l'orario, perché la lettura mostrava
    # l'UTC e la scrittura lo riprendeva per ora locale.
    unchanged = {
        "inscription_start": format_datetime_input(stored.inscription_start),
        "inscription_end": format_datetime_input(stored.inscription_end),
    }
    response = client.post(
        f"/admin/gara/{gara.id}/modify_inscription_dates",
        data=unchanged,
        follow_redirects=True,
    )
    assert response.status_code == 200

    stored = db_session.get(Gara, gara.id)
    assert format_datetime_input(stored.inscription_start) == "2026-08-20T09:00"
    assert format_datetime_input(stored.inscription_end) == "2026-09-10T21:00"
