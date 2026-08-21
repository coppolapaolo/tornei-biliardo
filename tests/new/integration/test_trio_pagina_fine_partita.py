"""La pagina di un trio a fine partita dice le stesse cose di una a due.

Questi test renderizzano davvero `/admin/match/<id>` e leggono l'HTML, perche'
il difetto da cui nascono era invisibile a qualunque test di comportamento: il
template chiedeva `match.validated_by_admin`, Jinja valutava l'Undefined come
falso senza protestare, e il riquadro semplicemente non compariva. Nessuna
eccezione, nessun log, nessun assert rosso — solo una schermata monca.

Si asserisce sul **testo mostrato**, che e' l'unica cosa che l'utente vede.
"""

from datetime import date

import pytest

from models.base import db
from models.campionato.models import Campionato
from models.competition.models import Gara
from models.match.models import Match, TrioMatch
from models.match.trio_scoring_service import TrioScoringService
from models.status_enum import MatchStatus


@pytest.fixture
def trio_alla_distanza(db_session, isolated_players):
    """Un trio giocato fino in fondo, in attesa delle conferme."""
    campionato = Campionato(name="Campionato trio pagina")
    db_session.add(campionato)
    db_session.flush()

    gara = Gara(
        campionato_id=campionato.id,
        number=1,
        date=date.today(),
        distance=3,
        discipline="9_ball",
    )
    db_session.add(gara)
    db_session.flush()

    p1, p2, p3 = isolated_players[0], isolated_players[1], isolated_players[2]
    match = Match(
        gara_id=gara.id,
        round_number=1,
        player1_id=p1.id,
        player2_id=p2.id,
        is_trio=True,
        status=MatchStatus.PLAYING.value,
    )
    db_session.add(match)
    db_session.flush()

    trio = TrioMatch(
        match_id=match.id, player1_id=p1.id, player2_id=p2.id, player3_id=p3.id
    )
    db_session.add(trio)
    db_session.commit()

    # Tre triangoli: P0 ne vince due, P1 il terzo. Nessuno "inserisce".
    TrioScoringService.add_rack_win(trio.id, p1.id)
    db_session.commit()
    TrioScoringService.add_rack_win(trio.id, p1.id)
    db_session.commit()
    TrioScoringService.add_rack_win(trio.id, p2.id)
    db_session.commit()

    return {"match": match, "trio_id": trio.id, "players": [p1, p2, p3]}


def _entra(client, utente):
    client.post(
        "/auth/login",
        data={"username": utente.username, "password": "player123"},
        follow_redirects=True,
    )


def _pagina(client, match_id):
    risposta = client.get(f"/admin/match/{match_id}")
    assert risposta.status_code == 200, f"la pagina risponde {risposta.status_code}"
    return risposta.get_data(as_text=True)


def test_chi_deve_ancora_confermare_vede_accetta_e_rifiuta(
    client, db_session, trio_alla_distanza
):
    """Stato 1: distanza raggiunta, i due pulsanti ci sono."""
    dati = trio_alla_distanza
    # P2 non ha vinto il trio e non ha inserito nulla: deve esprimersi.
    _entra(client, dati["players"][2])
    html = _pagina(client, dati["match"].id)

    assert "Il risultato è pronto per la conferma." in html
    assert "Accetta" in html
    assert "Rifiuta" in html


def test_chi_ha_gia_confermato_vede_chi_manca_per_nome(
    client, db_session, trio_alla_distanza
):
    """Stato 2: l'attesa e' al plurale, e nomina le persone."""
    dati = trio_alla_distanza
    p1, _p2, p3 = dati["players"]

    # P0 e' il vincitore: la firma ce l'ha gia' implicita.
    _entra(client, p1)
    html = _pagina(client, dati["match"].id)

    assert "Hai confermato" in html
    assert "In attesa di" in html
    assert p3.username in html, "deve dire *chi* manca, non «gli altri giocatori»"


def test_a_partita_chiusa_dai_giocatori_resta_la_via_duscita(
    client, db_session, trio_alla_distanza
):
    """Stato 4a: chiusa dai giocatori — annullabile finche' il direttore tace."""
    dati = trio_alla_distanza
    trio = db_session.get(TrioMatch, dati["trio_id"])
    for p in dati["players"]:
        trio = db_session.get(TrioMatch, dati["trio_id"])
        if not trio.is_completed:
            trio.confirm_result_by_player(p.id)
            db_session.commit()

    match = db_session.get(Match, dati["match"].id)
    assert match.status == MatchStatus.CONFIRMED_BY_BOTH.value

    _entra(client, dati["players"][0])
    html = _pagina(client, dati["match"].id)

    assert "Partita conclusa" in html
    assert "puoi ancora annullarlo" in html
    assert (
        "Annulla ultimo triangolo" in html
    ), "la finestra di ripensamento si chiude col direttore, non con la terza firma"


def test_dopo_la_validazione_del_direttore_la_pagina_lo_dice_e_chiude(
    client, db_session, trio_alla_distanza
):
    """Stato 4b: agli atti. Il riquadro che non compariva mai, ora compare."""
    dati = trio_alla_distanza
    trio = db_session.get(TrioMatch, dati["trio_id"])
    trio.confirm_result_by_admin()
    db_session.commit()

    match = db_session.get(Match, dati["match"].id)
    assert match.status == MatchStatus.CLOSED_UNILATERALLY.value

    _entra(client, dati["players"][0])
    html = _pagina(client, dati["match"].id)

    assert "Risultato validato" in html
    assert "Annulla ultimo triangolo" not in html, "agli atti: non si torna indietro"


def test_lendpoint_di_annullamento_rifiuta_dopo_il_sigillo(
    client, db_session, trio_alla_distanza
):
    """Il pulsante nascosto non e' una difesa: la POST diretta deve fallire."""
    dati = trio_alla_distanza
    trio = db_session.get(TrioMatch, dati["trio_id"])
    trio.confirm_result_by_admin()
    db_session.commit()

    _entra(client, dati["players"][0])
    risposta = client.post(f"/player/match/{dati['match'].id}/trio/remove_rack")

    assert risposta.status_code == 400
    assert "validato" in risposta.get_json()["error"]

    # E soprattutto: la partita e' rimasta chiusa.
    match = db.session.get(Match, dati["match"].id)
    assert match.status == MatchStatus.CLOSED_UNILATERALLY.value
