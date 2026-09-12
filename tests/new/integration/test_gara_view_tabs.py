"""Linguette di vista della pagina gara su mobile (prototipo 8a).

Sotto i 992px la pagina non e' piu' una pila unica: si divide in viste
(Turni / Classifica / Iscritti, piu' Gestione per chi dirige). Le sezioni non
si spostano nel DOM — dichiarano a quali viste appartengono con `data-c7-tab`
e il foglio di stile nasconde quelle fuori dalla vista attiva.

L'invariante che conta e' **nessuna sezione irraggiungibile**: se una sezione
dichiara una vista per cui non esiste il pill corrispondente, su mobile quel
contenuto non e' raggiungibile da nessuna parte — e non se ne accorge nessuno,
perche' la pagina resta valida e non da' errori.
"""

import re
from datetime import date

import pytest

from models import Gara, Inscription, Match
from models.status_enum import Discipline, GaraStatus, MatchStatus
from models.user.role_enum import UserRole


def _pills(html: str) -> list:
    """Viste per cui esiste una linguetta, nell'ordine in cui compaiono."""
    return re.findall(r'data-c7-tab-btn="([a-z]+)"', html)


def _tagged_views(html: str) -> set:
    """Viste dichiarate dalle sezioni (`data-c7-tab="turni gestione"`)."""
    views = set()
    for group in re.findall(r'data-c7-tab="([a-z ]+)"', html):
        views.update(group.split())
    return views


def _active(html: str):
    found = re.search(r'data-c7-view="([a-z]+)"', html)
    return found.group(1) if found else None


def _login(client, db_session, username, role):
    from models.user.services import UserService

    user = UserService.create_user(username, f"{username}@test.local", "pw12345")
    user.role = role
    db_session.commit()
    resp = client.post(
        "/auth/login", data={"username": username, "password": "pw12345"}
    )
    assert resp.status_code in (200, 302)
    return user


def _make_gara(db_session, status=GaraStatus.PLAYING.value):
    gara = Gara(
        number=1,
        name="Gara Linguette",
        date=date.today(),
        discipline=Discipline.NINE_BALL.value,
        distance=5,
        matchmaking_strategy="random",
        status=status,
        current_round=1,
        rounds_count=3,
        min_participants=4,
    )
    db_session.add(gara)
    db_session.commit()
    return gara


def _make_match(db_session, gara, p1, p2, status, scores=(0, 0), table=None):
    match = Match(
        gara_id=gara.id,
        round_number=gara.current_round,
        player1_id=p1.id,
        player2_id=p2.id,
        player1_score=scores[0],
        player2_score=scores[1],
        status=status,
        table_assignment=table,
    )
    if MatchStatus.is_finished(status):
        match.winner_id = p1.id if scores[0] > scores[1] else p2.id
    db_session.add(match)
    db_session.commit()
    return match


@pytest.fixture
def director_client(client, db_session):
    _login(client, db_session, "vtabs_dir", UserRole.ADMIN.value)
    return client


def test_il_direttore_non_ha_linguette_ma_la_striscia(director_client, db_session):
    """Dal 2026-09-12 chi dirige vede la pagina a fasi del canvas: la striscia
    al posto delle linguette (`test_pagina_gara_direttore.py`)."""
    from models.user.services import UserService

    gara = _make_gara(db_session)
    p1 = UserService.create_user("vtabs_p1", "vtabs_p1@test.local", "pw12345")
    p2 = UserService.create_user("vtabs_p2", "vtabs_p2@test.local", "pw12345")
    _make_match(db_session, gara, p1, p2, MatchStatus.CLOSED_UNILATERALLY.value, (5, 3))

    html = director_client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)

    assert _pills(html) == []
    assert 'class="c7-fasi"' in html


def test_nessuna_sezione_irraggiungibile(director_client, db_session):
    """Ogni vista dichiarata da una sezione deve avere la sua linguetta."""
    from models.user.services import UserService

    gara = _make_gara(db_session)
    p1 = UserService.create_user("vtabs_r1", "vtabs_r1@test.local", "pw12345")
    p2 = UserService.create_user("vtabs_r2", "vtabs_r2@test.local", "pw12345")
    _make_match(db_session, gara, p1, p2, MatchStatus.CLOSED_UNILATERALLY.value, (5, 3))

    html = director_client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)

    assert _tagged_views(html) <= set(_pills(html))


def test_una_sola_vista_niente_linguette(client, db_session):
    """Con una vista sola la barra non serve, e senza `data-c7-view` il filtro
    del foglio di stile non nasconde nulla: la pagina resta la pila di prima."""
    _login(client, db_session, "vtabs_guest", UserRole.PLAYER.value)
    gara = _make_gara(db_session, GaraStatus.INSCRIPTION.value)

    html = client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)

    assert _pills(html) == []
    assert _active(html) is None


def test_scorciatoia_al_proprio_match(client, db_session):
    """Chi gioca trova la sua partita in cima, non in fondo alla pila."""
    from models.user.services import UserService

    player = _login(client, db_session, "vtabs_me", UserRole.PLAYER.value)
    other = UserService.create_user("vtabs_alt", "vtabs_alt@test.local", "pw12345")
    gara = _make_gara(db_session)
    db_session.add(Inscription(gara_id=gara.id, user_id=player.id))
    db_session.add(Inscription(gara_id=gara.id, user_id=other.id))
    db_session.commit()
    match = _make_match(
        db_session, gara, player, other, MatchStatus.PLAYING.value, table="7"
    )

    html = client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)

    assert "c7-shortcut" in html
    assert f'href="/admin/match/{match.id}"' in html
    # Il tavolo e' l'informazione che serve per alzarsi e andare a giocare.
    assert "Tavolo 7" in re.sub(r"\s+", " ", html)


def test_niente_scorciatoia_a_partita_conclusa(client, db_session):
    """A partita chiusa non c'e' niente da aprire in fretta."""
    from models.user.services import UserService

    player = _login(client, db_session, "vtabs_done", UserRole.PLAYER.value)
    other = UserService.create_user("vtabs_done2", "vtabs_done2@test.local", "pw12345")
    gara = _make_gara(db_session)
    db_session.add(Inscription(gara_id=gara.id, user_id=player.id))
    db_session.commit()
    _make_match(
        db_session, gara, player, other, MatchStatus.CONFIRMED_BY_BOTH.value, (5, 2)
    )

    html = client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)

    assert "c7-shortcut" not in html


def test_iscritti_non_sono_piu_dentro_le_partite(client, db_session):
    """Compromesso della PR #36 chiuso: su mobile iscritti e informazioni
    stavano dentro la sezione Partite, e in fase di gioco risalivano con lei.
    Ora sono una vista a sé, fuori da `#sectionPartite`. Vale per chi guarda:
    il direttore ha la pagina a fasi."""
    from models.user.services import UserService

    _login(client, db_session, "vtabs_i0", UserRole.PLAYER.value)
    gara = _make_gara(db_session)
    p1 = UserService.create_user("vtabs_i1", "vtabs_i1@test.local", "pw12345")
    p2 = UserService.create_user("vtabs_i2", "vtabs_i2@test.local", "pw12345")
    _make_match(db_session, gara, p1, p2, MatchStatus.PLAYING.value)

    html = client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)

    partite = html.index('id="sectionPartite"')
    iscritti = html.index('data-c7-tab="iscritti"')
    assert iscritti > partite, "la vista Iscritti e' ancora dentro le Partite"
    # E la lista non e' piu' richiusa: nella sua vista e' il soggetto.
    assert "mobileInscriptionsCollapse" not in html
