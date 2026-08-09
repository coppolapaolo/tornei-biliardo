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

from datetime import date

import pytest

from models import Gara, Match
from models.status_enum import Discipline, GaraStatus, MatchStatus
from models.user.role_enum import UserRole

# Testata "Gestione" nel design 7c: h3 a tutta riga, senza l'icona a
# ingranaggio di prima. Conta le occorrenze per scoprire i duplicati.
GESTIONE_HEADING = 'flex-fill">Gestione</h3>'


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
    if status == MatchStatus.COMPLETED.value:
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

    # Copia mobile in cima + copia in sidebar nascosta su mobile: una sola
    # visibile per viewport.
    assert 'id="matchNavTop"' in html
    assert 'id="matchNavSidebar" class="d-none d-md-block"' in html


def test_match_in_corso_non_anticipa_il_ritorno(admin_client, db_session):
    """Race to 5 con 3-2: si gioca ancora, il ritorno resta a fondo pagina."""
    gara = _make_gara(db_session)
    match = _make_match(db_session, gara, 3, 2, MatchStatus.PLAYING.value)

    resp = admin_client.get(f"/admin/match/{match.id}")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    # Solo la copia in sidebar, visibile anche su mobile a fondo pagina.
    assert 'id="matchNavTop"' not in html
    assert 'id="matchNavSidebar" class=""' in html


def test_match_completato_mostra_ritorno_in_cima(admin_client, db_session):
    """Match gia' chiuso: nulla da fare se non uscire."""
    gara = _make_gara(db_session)
    match = _make_match(db_session, gara, 5, 3, MatchStatus.COMPLETED.value)

    resp = admin_client.get(f"/admin/match/{match.id}")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert 'id="matchNavTop"' in html


# ──────────────────────────────────────────────────────────────────────────────
# 2. /admin/gara/<id> — Gestione in cima e aperta a turno Amalfi finito
# ──────────────────────────────────────────────────────────────────────────────


def test_amalfi_turno_finito_gestione_in_cima_e_aperta(admin_client, db_session):
    """Turno 1/3 completato: 'Avvia Turno 2' deve essere a portata di tap."""
    gara = _make_gara(db_session, strategy="amalfi", rounds_count=3, current_round=1)
    _make_match(db_session, gara, 5, 3, MatchStatus.COMPLETED.value)

    resp = admin_client.get(f"/admin/gara/{gara.id}")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    # Gestione in cima, senza collapse
    assert 'id="sectionGestioneMobileAperta"' in html
    # ...e la copia collassata sotto le partite non viene ripetuta
    assert 'id="sectionGestioneMobile"' not in html
    # Il pulsante dell'azione probabile e' renderizzato (non dietro un collapse)
    assert "Avvia Turno 2" in html
    # Desktop invariato: la sidebar mantiene la sua copia
    assert html.count(GESTIONE_HEADING) == 2


def test_amalfi_turno_in_corso_mantiene_gestione_collassata(admin_client, db_session):
    """Turno ancora in gioco: l'azionabile sono le partite, non la Gestione."""
    gara = _make_gara(db_session, strategy="amalfi", rounds_count=3, current_round=1)
    _make_match(db_session, gara, 2, 1, MatchStatus.PLAYING.value)

    resp = admin_client.get(f"/admin/gara/{gara.id}")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert 'id="sectionGestioneMobileAperta"' not in html
    assert 'id="sectionGestioneMobile"' in html


def test_random_turno_finito_non_promuove_la_gestione(admin_client, db_session):
    """Random: i giocatori avanzano da soli, non c'e' un turno da avviare."""
    gara = _make_gara(db_session, strategy="random", rounds_count=3, current_round=1)
    _make_match(db_session, gara, 5, 3, MatchStatus.COMPLETED.value)

    resp = admin_client.get(f"/admin/gara/{gara.id}")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert 'id="sectionGestioneMobileAperta"' not in html


def test_amalfi_gara_finita_gestione_gia_in_cima_senza_duplicati(
    admin_client, db_session
):
    """Tutti i turni completati, nessun parimerito: 'Termina Gara' in cima.

    Qui la sidebar (order-1 su mobile) mostra gia' Gestione aperta in cima:
    il blocco dedicato non deve aggiungersene un secondo.
    """
    gara = _make_gara(db_session, strategy="amalfi", rounds_count=1, current_round=1)
    _make_match(db_session, gara, 5, 3, MatchStatus.COMPLETED.value)

    resp = admin_client.get(f"/admin/gara/{gara.id}")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert gara.get_real_status() == "campionato_completed"
    assert "Termina Gara" in html
    # Una sola Gestione in tutto il documento: quella della sidebar, che su
    # mobile e' gia' in cima (order-1) e aperta.
    assert html.count(GESTIONE_HEADING) == 1
    assert 'id="sectionGestioneMobileAperta"' not in html
    assert 'id="sectionGestioneMobile"' not in html


def test_amalfi_parimerito_promuove_avvia_spareggio_in_cima(admin_client, db_session):
    """Turni finiti con parimerito nel podio: 'Avvia Spareggio (SSR)' in cima.

    Il parimerito deve nascere dai risultati veri (la classifica viene
    ricalcolata a ogni vista): due vincitori con lo stesso 5-3 finiscono
    entrambi a (1 vittoria, +2 rack) e vanno spareggiati.
    """
    gara = _make_gara(db_session, strategy="amalfi", rounds_count=1, current_round=1)
    _make_match(db_session, gara, 5, 3, MatchStatus.COMPLETED.value, suffix="a")
    _make_match(db_session, gara, 5, 3, MatchStatus.COMPLETED.value, suffix="b")

    resp = admin_client.get(f"/admin/gara/{gara.id}")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert 'id="sectionGestioneMobileAperta"' in html
    assert "Avvia Spareggio (SSR)" in html
    assert 'id="sectionGestioneMobile"' not in html
