"""Il blocco «Come stai andando» disegnato davvero, non solo calcolato.

I test unitari coprono il servizio; questi coprono il pezzo che i test
unitari non vedono mai — il template. Una `.items` letta come attributo su un
dict, un `conic-gradient` che non arriva, un pannello senza `aria-controls`:
tutte cose che non falliscono da nessuna parte se non si rende la pagina.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from models import db
from models.base import utc_now
from models.individual_match.match_models import IndividualMatch
from models.rating.models import MatchRatingHistory, RatingSystem
from models.status_enum import MatchStatus
from models.user.models import User


def _opponent() -> User:
    tag = uuid.uuid4().hex[:8]
    user = User(username=f"opp_{tag}", email=f"{tag}@example.test", role="player")
    user.set_password("x")
    db.session.add(user)
    db.session.commit()
    return user


def _played(player: User, opponent: User, mine: int, theirs: int, days_ago: int):
    when = utc_now() - timedelta(days=days_ago)
    match = IndividualMatch(
        player1_id=player.id,
        player2_id=opponent.id,
        scheduled_at=when,
        ended_at=when,
        status=MatchStatus.CONFIRMED_BY_BOTH,
        discipline="palla_9",
        distance=5,
        player1_score=mine,
        player2_score=theirs,
        winner_id=player.id if mine > theirs else opponent.id,
    )
    db.session.add(match)
    db.session.commit()
    return match


def _elo(user: User, match: IndividualMatch, old: int, new: int):
    db.session.add(
        MatchRatingHistory(
            individual_match_id=match.id,
            user_id=user.id,
            rating_system=RatingSystem.ELO_GLOBAL,
            old_rating=old,
            new_rating=new,
            delta=new - old,
        )
    )
    db.session.commit()


def test_la_home_del_giocatore_attivo_disegna_il_blocco(logged_in_client):
    client, user = logged_in_client(role="player")
    other = _opponent()
    for i, (old, new) in enumerate([(1200, 1194), (1194, 1206), (1206, 1218)]):
        up = new > old
        match = _played(user, other, 5 if up else 2, 2 if up else 5, 5 - i)
        _elo(user, match, old, new)

    response = client.get("/dashboard")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "c7-feedback" in html
    assert "Come stai andando" in html
    assert "1218" in html

    # La sparkline esiste e il tratto e' protetto dallo stiramento del viewBox.
    assert 'viewBox="0 0 130 34"' in html
    assert 'vector-effect="non-scaling-stroke"' in html

    # L'espansione e' un vero bottone, con il pannello collegato e chiuso.
    assert 'aria-controls="activity-feedback-panel"' in html
    assert 'aria-expanded="false"' in html

    # Nessuna CTA dentro il blocco: il feedback non porta da nessuna parte.
    blocco = html.split('class="c7-feedback', 1)[1].split("</section>", 1)[0]
    assert "<a " not in blocco
    assert "url_for" not in blocco


def test_la_home_del_giocatore_nuovo_disegna_il_setup_e_non_il_blocco(logged_in_client):
    client, _user = logged_in_client(role="player")

    response = client.get("/dashboard")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    # Nessun numero inventato: al posto del blocco, i tre passi.
    assert "Come stai andando" not in html
    assert "c7-setup" in html
    assert "Il tuo Elo parte da 1200" in html


def test_le_tessere_portano_il_dato_anche_nel_markup(logged_in_client):
    client, user = logged_in_client(role="player")
    other = _opponent()
    _played(user, other, 5, 3, 3)
    _played(user, other, 2, 5, 2)

    html = client.get("/dashboard").get_data(as_text=True)

    assert "c7-feedback__tile--win" in html
    assert "c7-feedback__tile--loss" in html
    assert "5–3" in html  # il punteggio, non solo il colore
    assert 'title="' in html
