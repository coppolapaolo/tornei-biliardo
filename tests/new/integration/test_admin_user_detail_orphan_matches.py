"""Regression: il dettaglio utente admin non deve andare in 500 sui match orfani.

Incidente GlitchTip TORNEI-BILIARDO-5G (2026-07-04, `GET /admin/user/46`):
`UndefinedError: 'None' has no attribute 'campionato'` sollevato da
`templates/components/_user_recent_matches_table.html:24`
(`{{ match.gara.campionato.name }}`).

`UserStatsService.get_user_matches` filtrava solo su player e status, senza
toccare `gara`: restituiva quindi anche match la cui gara non è raggiungibile.
`match.gara` risolve a None in due casi:

1. gara soft-deleted — `register_soft_delete_filters` installa un
   `with_loader_criteria(Gara, deleted_at IS NULL)` che smaterializza la
   relazione pur lasciando la riga in `match`;
2. `match.gara_id IS NULL` — lo schema ha ON DELETE SET NULL sul FK.

Il caso gara **standalone** (`campionato_id = None`) invece NON rompe, ed è
qui sotto a documentarlo: `{{ None.name }}` in Jinja produce `Undefined`, che
stampato dà stringa vuota. A sollevare è solo l'accesso a un attributo *su*
`Undefined`, cioè `match.gara` nullo → `.campionato` → `.name`.

Difesa doppia: il service esclude i match senza gara raggiungibile, il
template regge comunque gara/campionato nulli (il componente potrebbe essere
incluso altrove con una lista non filtrata).
"""

from datetime import date

from flask import render_template

from models.base import utc_now
from models.campionato.models import Campionato
from models.competition.models import Gara
from models.match.models import Match
from models.status_enum import GaraStatus, MatchStatus
from models.user.stats_service import UserStatsService


def _make_gara(db_session, director_id, campionato_id=None, number=1):
    gara = Gara(
        name=f"Gara orfana {number}",
        number=number,
        date=date.today(),
        distance=5,
        discipline="9_ball",
        matchmaking_strategy="random",
        status=GaraStatus.PLAYING.value,
        is_race_to=True,
        director_id=director_id,
        campionato_id=campionato_id,
    )
    db_session.add(gara)
    db_session.flush()
    return gara


def _make_completed_match(db_session, gara_id, p1, p2):
    match = Match(
        gara_id=gara_id,
        round_number=1,
        player1_id=p1,
        player2_id=p2,
        player1_score=5,
        player2_score=3,
        winner_id=p1,
        status=MatchStatus.CLOSED_UNILATERALLY.value,
        updated_at=utc_now(),
    )
    db_session.add(match)
    db_session.flush()
    return match


def test_get_user_matches_esclude_match_con_gara_soft_deleted(
    app, db_session, isolated_director_user, isolated_players
):
    p1, p2 = isolated_players[:2]
    gara = _make_gara(db_session, isolated_director_user.id)
    _make_completed_match(db_session, gara.id, p1.id, p2.id)
    db_session.commit()

    assert len(UserStatsService.get_user_matches(p1.id)) == 1

    gara.deleted_at = utc_now()
    db_session.commit()

    matches = UserStatsService.get_user_matches(p1.id)
    assert matches == [], "un match con gara soft-deleted romperebbe il template"


def test_get_user_matches_esclude_match_senza_gara(
    app, db_session, isolated_director_user, isolated_players
):
    p1, p2 = isolated_players[:2]
    gara = _make_gara(db_session, isolated_director_user.id)
    match = _make_completed_match(db_session, gara.id, p1.id, p2.id)
    db_session.commit()

    # ON DELETE SET NULL sul FK: il match sopravvive alla gara
    match.gara_id = None
    db_session.commit()

    matches = UserStatsService.get_user_matches(p1.id)
    assert matches == [], "un match senza gara romperebbe il template"


def test_componente_regge_match_con_gara_nulla(
    app, db_session, isolated_director_user, isolated_players
):
    p1, p2 = isolated_players[:2]
    gara = _make_gara(db_session, isolated_director_user.id)
    match = _make_completed_match(db_session, gara.id, p1.id, p2.id)
    db_session.commit()
    match.gara_id = None
    db_session.commit()

    html = render_template(
        "components/_user_recent_matches_table.html", matches=[match], user=p1
    )
    assert "Partite Recenti" in html


def test_componente_regge_gara_standalone_senza_campionato(
    app, db_session, isolated_director_user, isolated_players
):
    p1, p2 = isolated_players[:2]
    # Gara standalone: campionato_id resta None (caso di prima classe)
    gara = _make_gara(db_session, isolated_director_user.id)
    match = _make_completed_match(db_session, gara.id, p1.id, p2.id)
    db_session.commit()

    assert gara.campionato is None
    html = render_template(
        "components/_user_recent_matches_table.html", matches=[match], user=p1
    )
    assert "Partite Recenti" in html


def test_componente_mostra_campionato_quando_presente(
    app, db_session, isolated_director_user, isolated_players
):
    p1, p2 = isolated_players[:2]
    campionato = Campionato(name="Campionato Regge", planned_gare_count=1)
    db_session.add(campionato)
    db_session.flush()
    gara = _make_gara(
        db_session, isolated_director_user.id, campionato_id=campionato.id
    )
    match = _make_completed_match(db_session, gara.id, p1.id, p2.id)
    db_session.commit()

    # Il guard non deve nascondere i dati nel caso normale
    html = render_template(
        "components/_user_recent_matches_table.html", matches=[match], user=p1
    )
    assert "Campionato Regge" in html
