"""Regression rilievo test manuale 2026-07-28 (vista mobile: azionabile in cima).

Estende il principio "L'azionabile va prima" (docs/reference/UI_CONVENTIONS.md)
a due schermate:

1. /admin/match/<id>: a punteggio definitivo (rack massimi raggiunti o match
   gia' chiuso) la prossima azione probabile e' uscire dal match, quindi il
   pulsante di ritorno (alla gara per chi gestisce, alla dashboard per chi
   gioca) risale in cima su mobile.
2. /admin/gara/<id>: con strategie sequenziali (Amalfi) a turno finito
   l'azionabile e' avviare il turno successivo / lo spareggio SSR / terminare
   la gara, quindi la sezione Gestione risale in cima gia' aperta invece di
   restare collassata sotto le partite.

In entrambi i casi il desktop resta invariato e su mobile il blocco compare
UNA sola volta (le copie mobile/desktop sono mutuamente esclusive).
"""

import re
from datetime import date

import pytest

from models import Gara, Match
from models.status_enum import Discipline, GaraStatus, MatchStatus
from models.user.role_enum import UserRole


def _nav_class(html: str, nav_id: str):
    """Classi del blocco di ritorno, o None se quel blocco non c'e'.

    Non assume l'ordine degli attributi: il guscio 7c ha spostato `class`
    prima o dopo `id` a seconda del blocco, e asserire sulla stringa esatta
    ha lasciato questi test rossi per settimane senza che nulla fosse rotto.
    """
    tag = re.search(rf"<div[^>]*\bid=\"{nav_id}\"[^>]*>", html)
    if not tag:
        return None
    classes = re.search(r'class="([^"]*)"', tag.group(0))
    return classes.group(1) if classes else ""


@pytest.fixture
def admin_client(client, db_session):
    from models.user.services import UserService

    user = UserService.create_user("azion_admin", "azion_admin@test.local", "pw12345")
    user.role = UserRole.ADMIN.value
    db_session.commit()
    resp = client.post(
        "/auth/login", data={"username": "azion_admin", "password": "pw12345"}
    )
    assert resp.status_code in (200, 302)
    return client


def _make_gara(db_session, strategy="amalfi", rounds_count=3, current_round=1):
    gara = Gara(
        number=1,
        name="Gara Azionabile",
        date=date.today(),
        discipline=Discipline.EIGHT_BALL.value,
        distance=5,
        is_race_to=True,
        matchmaking_strategy=strategy,
        status=GaraStatus.PLAYING.value,
        current_round=current_round,
        rounds_count=rounds_count,
        min_participants=4,
    )
    db_session.add(gara)
    db_session.commit()
    return gara


def _make_match(db_session, gara, p1_score, p2_score, status, suffix=""):
    from models.user.services import UserService

    p1 = UserService.create_user(
        f"azion_p1{suffix}", f"azion_p1{suffix}@test.local", "pw12345"
    )
    p2 = UserService.create_user(
        f"azion_p2{suffix}", f"azion_p2{suffix}@test.local", "pw12345"
    )
    match = Match(
        gara_id=gara.id,
        round_number=gara.current_round,
        player1_id=p1.id,
        player2_id=p2.id,
        player1_score=p1_score,
        player2_score=p2_score,
        status=status,
    )
    if status == MatchStatus.CLOSED_UNILATERALLY.value:
        match.winner_id = p1.id if p1_score > p2_score else p2.id
    db_session.add(match)
    db_session.commit()
    return match


# ──────────────────────────────────────────────────────────────────────────────
# 1. /admin/match/<id> — pulsante di ritorno in cima a punteggio definitivo
# ──────────────────────────────────────────────────────────────────────────────


def test_match_a_distanza_mostra_ritorno_in_cima_su_mobile(admin_client, db_session):
    """Race to 5 con 5-2: rack massimi raggiunti -> ritorno in cima su mobile."""
    gara = _make_gara(db_session)
    match = _make_match(db_session, gara, 5, 2, MatchStatus.PLAYING.value)

    resp = admin_client.get(f"/admin/match/{match.id}")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    # Un solo ritorno per viewport: su mobile e' quello in cima, su desktop
    # vive nella testata (`page_actions`), quindi la copia in fondo non c'e'.
    assert _nav_class(html, "matchNavTop") == "d-lg-none"
    assert _nav_class(html, "matchNavSidebar") is None


def test_match_in_corso_non_anticipa_il_ritorno(admin_client, db_session):
    """Race to 5 con 3-2: si gioca ancora, il ritorno resta a fondo pagina."""
    gara = _make_gara(db_session)
    match = _make_match(db_session, gara, 3, 2, MatchStatus.PLAYING.value)

    resp = admin_client.get(f"/admin/match/{match.id}")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    # Solo la copia in fondo, e solo su mobile: sul desktop il ritorno e' in
    # testata e una seconda copia in pagina lo ripeterebbe.
    assert _nav_class(html, "matchNavTop") is None
    assert _nav_class(html, "matchNavSidebar") == "d-lg-none"


def test_match_completato_mostra_ritorno_in_cima(admin_client, db_session):
    """Match gia' chiuso: nulla da fare se non uscire."""
    gara = _make_gara(db_session)
    match = _make_match(db_session, gara, 5, 3, MatchStatus.CLOSED_UNILATERALLY.value)

    resp = admin_client.get(f"/admin/match/{match.id}")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert 'id="matchNavTop"' in html


# ──────────────────────────────────────────────────────────────────────────────
# 2. /admin/gara/<id> — la fascia in cima dice l'unica cosa da fare
#
# Dal 2026-09-12 la pagina del direttore e' quella a fasi del canvas: niente
# Gestione collassata, la fascia scura in cima porta il comando che la gara
# aspetta (`models/dashboard/comandi.py`), e a turno in corso la card della
# console al suo posto. E' lo stesso principio di prima — l'azionabile va
# prima — con una forma sola per mobile e desktop.
# ──────────────────────────────────────────────────────────────────────────────


def test_amalfi_turno_finito_avvia_il_turno_dopo_dalla_fascia(admin_client, db_session):
    """Turno 1/3 completato: 'Avvia il turno 2' deve essere a portata di tap."""
    gara = _make_gara(db_session, strategy="amalfi", rounds_count=3, current_round=1)
    _make_match(db_session, gara, 5, 3, MatchStatus.CLOSED_UNILATERALLY.value)

    resp = admin_client.get(f"/admin/gara/{gara.id}")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "c7-fascia" in html
    assert "Avvia il turno 2" in html
    assert 'data-help="gara-avvia-turno"' in html
    # Un solo comando: quello della fascia, per mobile e desktop insieme.
    assert html.count("Avvia il turno 2") == 1
    # La card della console e' del turno in corso, non del turno chiuso.
    assert "c7-console" not in html


def test_amalfi_turno_in_corso_mostra_la_console_senza_comandi(
    admin_client, db_session
):
    """Turno ancora in gioco: l'azionabile sono le partite, non un comando."""
    gara = _make_gara(db_session, strategy="amalfi", rounds_count=3, current_round=1)
    _make_match(db_session, gara, 2, 1, MatchStatus.PLAYING.value)

    resp = admin_client.get(f"/admin/gara/{gara.id}")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "c7-console" in html
    assert "Avvia il turno 2" not in html
    assert "Termina la gara" not in html


def test_random_turno_finito_non_avvia_nessun_turno(admin_client, db_session):
    """Random: i giocatori avanzano da soli, non c'e' un turno da avviare."""
    gara = _make_gara(db_session, strategy="random", rounds_count=3, current_round=1)
    _make_match(db_session, gara, 5, 3, MatchStatus.CLOSED_UNILATERALLY.value)

    resp = admin_client.get(f"/admin/gara/{gara.id}")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "Avvia il turno" not in html


def test_amalfi_gara_finita_termina_dalla_fascia(admin_client, db_session):
    """Tutti i turni completati, nessun parimerito: 'Termina la gara' in cima."""
    gara = _make_gara(db_session, strategy="amalfi", rounds_count=1, current_round=1)
    _make_match(db_session, gara, 5, 3, MatchStatus.CLOSED_UNILATERALLY.value)

    resp = admin_client.get(f"/admin/gara/{gara.id}")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert gara.get_real_status() == "campionato_completed"
    assert html.count("Termina la gara") == 1
    assert "Avvia lo spareggio" not in html


def test_amalfi_parimerito_avvia_lo_spareggio_dalla_fascia(admin_client, db_session):
    """Turni finiti con parimerito nel podio: 'Avvia lo spareggio' in cima.

    Il parimerito deve nascere dai risultati veri (la classifica viene
    ricalcolata a ogni vista): due vincitori con lo stesso 5-3 finiscono
    entrambi a (1 vittoria, +2 rack) e vanno spareggiati. La striscia
    guadagna la tacca dello spareggio.
    """
    gara = _make_gara(db_session, strategy="amalfi", rounds_count=1, current_round=1)
    _make_match(
        db_session, gara, 5, 3, MatchStatus.CLOSED_UNILATERALLY.value, suffix="a"
    )
    _make_match(
        db_session, gara, 5, 3, MatchStatus.CLOSED_UNILATERALLY.value, suffix="b"
    )

    resp = admin_client.get(f"/admin/gara/{gara.id}")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "Avvia lo spareggio" in html
    assert "Termina la gara" not in html
    assert 'title="Spareggio"' in html
