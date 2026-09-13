"""Trio, partita a set e X con esercizio sulla card del direttore.

La card della partita (canvas 3C) segnava solo le partite a due: il trio e la
partita a set ricadevano sulla card di prima, con il risultato secco in un
modale, e la X con esercizio aveva un campo numerico e un `confirm()`. Qui si
verifica il passaggio interfaccia↔server delle tre forme nuove:

* gli endpoint degli stepper (`trio_punteggio`, `set_punteggio`) e le varianti
  JSON della prova al posto della X: stesse guardie del punteggio a due (partita
  chiusa o turno bloccato 409, punteggio impossibile 400) e l'evento live con
  `autore`;
* i tre difetti delle route del trio trovati strada facendo;
* la card che la pagina disegna per ciascuna forma;
* il rifiuto della correzione per la partita a set, che prima stava solo nel
  template.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest

from models import Gara, Match
from models.base import utc_now
from models.match.models import TrioMatch
from models.status_enum import Discipline, GaraStatus, MatchStatus
from models.user.role_enum import UserRole
from routes.sse import EventScope, _get_events_since

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _archivio_pulito(db_session):
    from models.live_event import LiveEvent

    LiveEvent.query.delete()
    db_session.commit()


@pytest.fixture
def admin(client, db_session):
    from models.user.services import UserService

    nome = f"card_admin_{uuid.uuid4().hex[:6]}"
    user = UserService.create_user(nome, f"{nome}@test.local", "pw12345")
    user.role = UserRole.ADMIN.value
    db_session.commit()
    client.post("/auth/login", data={"username": nome, "password": "pw12345"})
    return user


def _gara(db_session, distance=4):
    gara = Gara(
        number=1,
        name="Gara delle card",
        date=date.today(),
        discipline=Discipline.EIGHT_BALL.value,
        distance=distance,
        is_race_to=True,
        matchmaking_strategy="amalfi",
        status=GaraStatus.PLAYING.value,
        current_round=1,
        rounds_count=3,
        min_participants=3,
        available_tables='["1", "2"]',
    )
    db_session.add(gara)
    db_session.commit()
    return gara


def _blocca_il_turno_1(db_session, gara, giocatori):
    """Un turno 2 con partite: nella formula Amalfi il turno 1 si blocca."""
    db_session.add(
        Match(
            gara_id=gara.id,
            round_number=2,
            player1_id=giocatori[-1].id,
            player2_id=giocatori[-2].id,
            status=MatchStatus.PENDING.value,
        )
    )
    db_session.commit()


def _eventi(gara_id):
    return _get_events_since(EventScope.GARA, gara_id, 0)


def _card(html, match_id):
    return html.split(f'id="partita{match_id}"')[1].split("</article>")[0]


# ── Trio ──────────────────────────────────────────────────────────────────────


def _trio(db_session, gara, giocatori):
    p1, p2, p3 = giocatori[:3]
    match = Match(
        gara_id=gara.id,
        round_number=1,
        player1_id=p1.id,
        player2_id=p2.id,
        is_trio=True,
        status=MatchStatus.PLAYING.value,
        table_assignment="1",
    )
    db_session.add(match)
    db_session.flush()
    trio = TrioMatch(
        match_id=match.id, player1_id=p1.id, player2_id=p2.id, player3_id=p3.id
    )
    db_session.add(trio)
    db_session.commit()
    return match, trio


def _punti_trio(client, trio_id, a, b, c):
    return client.post(
        f"/admin/gara/trio/{trio_id}/punteggio",
        data={"player1_racks": a, "player2_racks": b, "player3_racks": c},
    )


def test_il_trio_si_segna_dalla_card_nell_ordine_del_girone(
    client, admin, db_session, isolated_players
):
    gara = _gara(db_session, distance=4)  # due gironi, sei triangoli
    match, trio = _trio(db_session, gara, isolated_players)

    # Il primo triangolo e' fra il primo e il secondo: il terzo non l'ha vinto.
    r = _punti_trio(client, trio.id, 0, 0, 1)
    assert r.status_code == 400
    assert r.get_json()["success"] is False

    r = _punti_trio(client, trio.id, 5, 0, 0)
    assert r.status_code == 400, "ognuno gioca quattro triangoli"

    r = _punti_trio(client, trio.id, 1, 0, 0)
    assert r.status_code == 200
    dati = r.get_json()
    assert dati["punti"] == [1, 0, 0]
    assert dati["finished"] is False
    assert dati["piu"] == [True, True, True]

    eventi = [e for e in _eventi(gara.id) if e["type"] == "match_updated"]
    assert eventi and eventi[-1]["data"]["autore"] == admin.id
    assert eventi[-1]["data"]["match_id"] == match.id


def test_al_totale_dei_triangoli_il_trio_si_chiude_e_poi_non_si_riscrive(
    client, admin, db_session, isolated_players
):
    gara = _gara(db_session, distance=4)
    match, trio = _trio(db_session, gara, isolated_players)

    r = _punti_trio(client, trio.id, 4, 2, 0)
    assert r.status_code == 200
    assert r.get_json()["finished"] is True
    riletto = db_session.get(Match, match.id)
    assert MatchStatus.is_finished(riletto.status)
    assert riletto.winner_id == isolated_players[0].id
    assert db_session.get(TrioMatch, trio.id).player_racks_list == [4, 2, 0]

    r = _punti_trio(client, trio.id, 3, 3, 0)
    assert r.status_code == 409
    assert db_session.get(TrioMatch, trio.id).player_racks_list == [4, 2, 0]


def test_un_triangolo_tolto_resta_nello_storico(
    client, admin, db_session, isolated_players
):
    gara = _gara(db_session, distance=4)
    _, trio = _trio(db_session, gara, isolated_players)
    assert _punti_trio(client, trio.id, 1, 1, 0).status_code == 200
    assert _punti_trio(client, trio.id, 1, 0, 0).status_code == 200
    riletto = db_session.get(TrioMatch, trio.id)
    assert riletto.player_racks_list == [1, 0, 0]
    assert len([r for r in riletto.racks.all() if r.is_deleted]) == 1


def test_il_trio_di_un_turno_bloccato_non_si_segna(
    client, admin, db_session, isolated_players
):
    gara = _gara(db_session, distance=4)
    _, trio = _trio(db_session, gara, isolated_players)
    _blocca_il_turno_1(db_session, gara, isolated_players)

    assert _punti_trio(client, trio.id, 1, 0, 0).status_code == 409
    r = client.post(
        f"/admin/gara/trio/{trio.id}/set_result",
        data={"player1_racks": 4, "player2_racks": 2, "player3_racks": 0},
    )
    assert r.status_code == 409, "il risultato secco guardava solo il permesso"
    assert db_session.get(TrioMatch, trio.id).player_racks_list == [0, 0, 0]


def test_il_risultato_secco_del_trio_non_riscrive_un_trio_chiuso_e_si_annuncia(
    client, admin, db_session, isolated_players
):
    gara = _gara(db_session, distance=2)  # un girone, tre triangoli
    match, trio = _trio(db_session, gara, isolated_players)
    url = f"/admin/gara/trio/{trio.id}/set_result"

    r = client.post(
        url, data={"player1_racks": 2, "player2_racks": 1, "player3_racks": 0}
    )
    assert r.status_code == 200
    chiusura = [e for e in _eventi(gara.id) if e["type"] == "match_completed"]
    assert any(e["data"].get("autore") == admin.id for e in chiusura)

    r = client.post(
        url, data={"player1_racks": 0, "player2_racks": 1, "player3_racks": 2}
    )
    assert r.status_code == 409
    assert db_session.get(Match, match.id).winner_id == isolated_players[0].id


def test_l_azzera_del_trio_risponde_400_a_un_rifiuto_del_dominio(
    client, admin, db_session, isolated_players, monkeypatch
):
    """Fino al 2026-09-13 un `ValueError` del servizio usciva come 500."""
    from models.competition.trio_service import TrioMatchService

    gara = _gara(db_session, distance=4)
    _, trio = _trio(db_session, gara, isolated_players)

    def rifiuta(_trio_id):
        raise ValueError("non si azzera")

    monkeypatch.setattr(TrioMatchService, "reset_trio", staticmethod(rifiuta))
    r = client.post(f"/admin/gara/trio/{trio.id}/reset")
    assert r.status_code == 400
    assert r.get_json()["error"] == "non si azzera"


def test_la_card_del_trio_ha_tre_stepper(client, admin, db_session, isolated_players):
    gara = _gara(db_session, distance=4)
    match, trio = _trio(db_session, gara, isolated_players)
    html = client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)
    card = _card(html, match.id)
    assert 'data-tipo="trio"' in card
    assert card.count("passoPunteggio(this, 1)") == 3
    assert 'data-piu="1,1,0"' in card
    assert "Trio · 2 gironi" in card
    assert f"/admin/gara/trio/{trio.id}/punteggio" in card
    assert 'data-correggibile="1"' in card
    assert "Inserisci risultato" not in html


def test_il_trio_giocato_dai_giocatori_e_da_validare(
    client, admin, db_session, isolated_players
):
    from models.match.trio_scoring_service import TrioScoringService

    gara = _gara(db_session, distance=2)
    match, trio = _trio(db_session, gara, isolated_players)
    p1, p2, _ = isolated_players[:3]
    for vincitore in (p1.id, p1.id, p2.id):
        TrioScoringService.add_rack_win(trio.id, vincitore)
        db_session.commit()

    html = client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)
    card = _card(html, match.id)
    assert 'data-stato="da_validare"' in card
    assert f"validaTrio({trio.id}, this)" in card
    assert "fa-crown" in card


def test_a_turno_concluso_il_trio_e_una_riga_con_tre_nomi_e_la_matita(
    client, admin, db_session, isolated_players
):
    gara = _gara(db_session, distance=4)
    match, trio = _trio(db_session, gara, isolated_players)
    assert _punti_trio(client, trio.id, 4, 2, 0).status_code == 200

    html = client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)
    riga = html.split(f'data-match-id="{match.id}"')[1].split("c7-rows__row")[0]
    for giocatore in isolated_players[:3]:
        assert giocatore.username in riga
    assert "4–2–0" in riga
    assert "apriCorrezione(this)" in riga
    assert 'data-correzione="trio"' in riga
    assert 'data-punti-trio="4,2,0"' in riga
    assert 'data-totale="6"' in riga
    assert 'data-massimo="4"' in riga


def test_il_trio_chiuso_a_turno_in_corso_ha_correggi_sulla_card(
    client, admin, db_session, isolated_players
):
    gara = _gara(db_session, distance=4)
    match, trio = _trio(db_session, gara, isolated_players)
    db_session.add(
        Match(
            gara_id=gara.id,
            round_number=1,
            player1_id=isolated_players[3].id,
            player2_id=isolated_players[4].id,
            status=MatchStatus.PENDING.value,
        )
    )
    db_session.commit()
    assert _punti_trio(client, trio.id, 4, 2, 0).status_code == 200

    card = _card(client.get(f"/admin/gara/{gara.id}").get_data(as_text=True), match.id)
    assert 'data-stato="conclusa"' in card
    assert "apriCorrezione(this)" in card
    assert 'data-correggibile="1"' in card
    assert 'data-correzione="trio"' in card


def test_la_correzione_del_trio_riscrive_triangoli_vincitore_e_classifica(
    client, admin, db_session, isolated_players
):
    from models.classification.score_aggregator import ScoreAggregator
    from models.match.models import MatchCorrection

    gara = _gara(db_session, distance=4)
    match, trio = _trio(db_session, gara, isolated_players)
    assert _punti_trio(client, trio.id, 4, 2, 0).status_code == 200
    p1, p2, p3 = isolated_players[:3]

    r = client.post(
        f"/admin/match/{match.id}/correct",
        data={
            "player1_score": 1,
            "player2_score": 3,
            "player3_score": 2,
            "note": "nomi scambiati",
            "next": f"/admin/gara/{gara.id}",
        },
    )
    assert r.status_code == 302
    assert r.headers["Location"].endswith(f"/admin/gara/{gara.id}")

    riletto = db_session.get(TrioMatch, trio.id)
    assert riletto.player_racks_list == [1, 3, 2]
    assert riletto.winner_id == p2.id
    traccia = MatchCorrection.query.filter_by(match_id=match.id).one()
    assert (traccia.previous_player3_score, traccia.new_player3_score) == (0, 2)

    voci = {
        v.player_id: v for v in ScoreAggregator().aggregate_round_scores(gara.id, 1)
    }
    assert [voci[g.id].matches_won for g in (p1, p2, p3)] == [0, 1, 0]

    pagina = client.get(f"/admin/match/{match.id}").get_data(as_text=True)
    assert "4–2–0" in pagina and "1–3–2" in pagina

    eventi = _eventi_della_correzione(gara.id, match.id)
    assert len(eventi) == 1
    dati = eventi[0]["data"]
    assert (dati["autore"], dati["trio_id"], dati["winner_id"]) == (
        admin.id,
        trio.id,
        p2.id,
    )


def test_il_trio_di_un_turno_bloccato_non_si_corregge(
    client, admin, db_session, isolated_players
):
    from models.match.models import MatchCorrection

    gara = _gara(db_session, distance=4)
    match, trio = _trio(db_session, gara, isolated_players)
    assert _punti_trio(client, trio.id, 4, 2, 0).status_code == 200
    _blocca_il_turno_1(db_session, gara, isolated_players)

    client.post(
        f"/admin/match/{match.id}/correct",
        data={"player1_score": 1, "player2_score": 3, "player3_score": 2},
    )
    assert db_session.get(TrioMatch, trio.id).player_racks_list == [4, 2, 0]
    assert MatchCorrection.query.filter_by(match_id=match.id).count() == 0
    assert not _eventi_della_correzione(gara.id, match.id)


def _eventi_della_correzione(gara_id, match_id):
    """Gli eventi live che annunciano la correzione di quella partita."""
    return [
        e
        for e in _eventi(gara_id)
        if e["type"] == "match_completed"
        and e["data"].get("corretto")
        and e["data"].get("match_id") == match_id
    ]


def test_la_correzione_della_partita_a_due_si_annuncia(
    client, admin, db_session, isolated_players
):
    """Fino al 2026-09-13 la correzione non emetteva niente: classifica e
    schermo in sala restavano sul risultato di prima fino a un ricaricamento."""
    gara = _gara(db_session, distance=4)
    primo, secondo = isolated_players[5], isolated_players[6]
    match = Match(
        gara_id=gara.id,
        round_number=1,
        player1_id=primo.id,
        player2_id=secondo.id,
        player1_score=4,
        player2_score=1,
        winner_id=primo.id,
        status=MatchStatus.CLOSED_UNILATERALLY.value,
    )
    db_session.add(match)
    db_session.commit()

    r = client.post(
        f"/admin/match/{match.id}/correct",
        data={"player1_score": 1, "player2_score": 4},
    )
    assert r.status_code == 302

    eventi = _eventi_della_correzione(gara.id, match.id)
    assert len(eventi) == 1
    dati = eventi[0]["data"]
    assert dati["autore"] == admin.id
    assert (dati["player1_score"], dati["player2_score"], dati["winner_id"]) == (
        1,
        4,
        secondo.id,
    )


def test_una_correzione_rifiutata_non_si_annuncia(
    client, admin, db_session, isolated_players
):
    gara = _gara(db_session, distance=4)
    match = Match(
        gara_id=gara.id,
        round_number=1,
        player1_id=isolated_players[5].id,
        player2_id=isolated_players[6].id,
        player1_score=4,
        player2_score=1,
        winner_id=isolated_players[5].id,
        status=MatchStatus.CLOSED_UNILATERALLY.value,
    )
    db_session.add(match)
    db_session.commit()

    client.post(
        f"/admin/match/{match.id}/correct",
        data={"player1_score": 4, "player2_score": 4},
    )
    assert db_session.get(Match, match.id).player1_score == 4
    assert not _eventi_della_correzione(gara.id, match.id)


# ── Partita a set ─────────────────────────────────────────────────────────────


def _a_set(db_session, gara, giocatori, *, sets=2):
    match = Match(
        gara_id=gara.id,
        round_number=1,
        player1_id=giocatori[3].id,
        player2_id=giocatori[4].id,
        is_multi_set=True,
        match_distance=sets,
        is_race_to_sets=True,
        status=MatchStatus.PLAYING.value,
        table_assignment="2",
    )
    db_session.add(match)
    db_session.commit()
    return match


def _punti_set(client, match_id, a, b):
    return client.post(
        f"/admin/match/{match_id}/set/punteggio",
        data={"player1_racks": a, "player2_racks": b},
    )


def test_il_set_in_corso_si_segna_dalla_card_e_si_chiude_alla_sua_distanza(
    client, admin, db_session, isolated_players
):
    gara = _gara(db_session, distance=4)  # set al 4
    match = _a_set(db_session, gara, isolated_players)

    assert _punti_set(client, match.id, 1, 0).status_code == 409, "nessun set"
    r = client.post(f"/admin/match/{match.id}/start-next-set")
    assert r.status_code == 200
    assert any(e["data"].get("autore") == admin.id for e in _eventi(gara.id))

    r = _punti_set(client, match.id, 3, 1)
    assert r.status_code == 200
    assert r.get_json()["punti"] == [3, 1]
    assert r.get_json()["set_chiuso"] is False

    assert _punti_set(client, match.id, 5, 1).status_code == 400

    r = _punti_set(client, match.id, 4, 1)
    assert r.get_json()["set_chiuso"] is True
    assert r.get_json()["set_vinti"] == [1, 0]
    assert _punti_set(client, match.id, 4, 2).status_code == 409, "set chiuso"

    assert client.post(f"/admin/match/{match.id}/start-next-set").status_code == 200
    r = _punti_set(client, match.id, 4, 0)
    assert r.get_json()["finished"] is True
    riletta = db_session.get(Match, match.id)
    assert MatchStatus.is_finished(riletta.status)
    assert riletta.winner_id == isolated_players[3].id
    assert _punti_set(client, match.id, 3, 0).status_code == 409


def test_un_triangolo_tolto_nel_set_e_l_ultimo_di_quel_giocatore(
    client, admin, db_session, isolated_players
):
    from models.match.set_models import SetRack

    gara = _gara(db_session, distance=4)
    match = _a_set(db_session, gara, isolated_players)
    client.post(f"/admin/match/{match.id}/start-next-set")
    assert _punti_set(client, match.id, 2, 1).status_code == 200
    assert _punti_set(client, match.id, 2, 2).status_code == 200
    # Da 2–2 a 1–2: se ne va un triangolo del primo, non l'ultimo del set.
    assert _punti_set(client, match.id, 1, 2).status_code == 200

    corrente = db_session.get(Match, match.id).get_current_set()
    racks = SetRack.query.filter_by(set_id=corrente.id).order_by(SetRack.rack_number)
    assert [r.rack_number for r in racks] == [1, 2, 3]
    vinti = [r.winner_id for r in racks]
    assert vinti.count(isolated_players[3].id) == 1
    assert vinti.count(isolated_players[4].id) == 2


def test_il_set_di_un_turno_bloccato_non_si_segna(
    client, admin, db_session, isolated_players
):
    gara = _gara(db_session, distance=4)
    match = _a_set(db_session, gara, isolated_players)
    client.post(f"/admin/match/{match.id}/start-next-set")
    _blocca_il_turno_1(db_session, gara, isolated_players)
    assert _punti_set(client, match.id, 1, 0).status_code == 409
    assert client.post(f"/admin/match/{match.id}/start-next-set").status_code == 409


def test_la_card_della_partita_a_set_mostra_il_set_in_corso(
    client, admin, db_session, isolated_players
):
    gara = _gara(db_session, distance=4)
    match = _a_set(db_session, gara, isolated_players)

    html = client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)
    assert f"iniziaSet({match.id}, this)" in _card(html, match.id)
    assert "Inizia il set 1" in _card(html, match.id)

    client.post(f"/admin/match/{match.id}/start-next-set")
    _punti_set(client, match.id, 1, 0)
    html = client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)
    card = _card(html, match.id)
    assert 'data-tipo="set"' in card
    assert 'data-punti="1,0"' in card
    assert 'data-max="4"' in card
    assert f"/admin/match/{match.id}/set/punteggio" in card
    assert card.count("passoPunteggio(this, 1)") == 2
    assert f"/admin/match/{match.id}/punteggio" not in card


def _gioca_a_set(client, match_id, *punteggi):
    for a, b in punteggi:
        assert client.post(f"/admin/match/{match_id}/start-next-set").status_code == 200
        assert _punti_set(client, match_id, a, b).status_code == 200


def _campi_set(sets, **altri):
    dati = dict(altri)
    for numero, (a, b) in enumerate(sets, start=1):
        dati[f"set_{numero}_player1"] = a
        dati[f"set_{numero}_player2"] = b
    return dati


def test_a_turno_concluso_la_partita_a_set_e_una_riga_che_si_corregge(
    client, admin, db_session, isolated_players
):
    gara = _gara(db_session, distance=4)
    match = _a_set(db_session, gara, isolated_players)
    _gioca_a_set(client, match.id, (4, 1), (4, 2))

    html = client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)
    riga = html.split(f'data-match-id="{match.id}"')[1].split("c7-rows__row")[0]
    assert "apriCorrezione(this)" in riga
    assert 'data-correzione="set"' in riga
    assert 'data-set-punti="4-1,4-2"' in riga
    assert 'data-set-distanza="4"' in riga
    assert 'data-set-da-vincere="2"' in riga


def test_la_partita_a_set_chiusa_a_turno_in_corso_ha_correggi_sulla_card(
    client, admin, db_session, isolated_players
):
    gara = _gara(db_session, distance=4)
    match = _a_set(db_session, gara, isolated_players)
    db_session.add(
        Match(
            gara_id=gara.id,
            round_number=1,
            player1_id=isolated_players[0].id,
            player2_id=isolated_players[1].id,
            status=MatchStatus.PENDING.value,
        )
    )
    db_session.commit()
    _gioca_a_set(client, match.id, (4, 1), (4, 2))

    card = _card(client.get(f"/admin/gara/{gara.id}").get_data(as_text=True), match.id)
    assert 'data-stato="conclusa"' in card
    assert "apriCorrezione(this)" in card
    assert 'data-correggibile="1"' in card
    assert 'data-correzione="set"' in card


def test_la_partita_a_set_si_corregge_set_per_set(
    client, admin, db_session, isolated_players
):
    """Un set in più e il vincitore che cambia: set, vincitore e classifica."""
    from models.classification.score_aggregator import ScoreAggregator
    from models.match.models import MatchCorrection
    from models.match.set_models import Set

    gara = _gara(db_session, distance=4)
    match = _a_set(db_session, gara, isolated_players)
    _gioca_a_set(client, match.id, (4, 1), (4, 2))
    primo, secondo = isolated_players[3], isolated_players[4]

    r = client.post(
        f"/admin/match/{match.id}/correct",
        data=_campi_set(
            [(4, 1), (2, 4), (1, 4)],
            player1_score=1,
            player2_score=2,
            next=f"/admin/gara/{gara.id}",
        ),
    )
    assert r.status_code == 302

    riletta = db_session.get(Match, match.id)
    assert (riletta.player1_score, riletta.player2_score) == (1, 2)
    assert riletta.winner_id == secondo.id
    sets = Set.query.filter_by(match_id=match.id).order_by(Set.set_number).all()
    assert [(s.player1_racks, s.player2_racks) for s in sets] == [
        (4, 1),
        (2, 4),
        (1, 4),
    ]
    traccia = MatchCorrection.query.filter_by(match_id=match.id).one()
    assert (traccia.previous_detail, traccia.new_detail) == (
        "4–1 · 4–2",
        "4–1 · 2–4 · 1–4",
    )

    voci = {
        v.player_id: v for v in ScoreAggregator().aggregate_round_scores(gara.id, 1)
    }
    assert (voci[primo.id].matches_won, voci[secondo.id].matches_won) == (0, 1)
    assert (voci[primo.id].racks_won, voci[secondo.id].racks_won) == (7, 9)

    pagina = client.get(f"/admin/match/{match.id}").get_data(as_text=True)
    assert "4–1 · 2–4 · 1–4" in pagina

    eventi = _eventi_della_correzione(gara.id, match.id)
    assert len(eventi) == 1
    dati = eventi[0]["data"]
    assert dati["autore"] == admin.id
    assert (dati["player1_score"], dati["player2_score"], dati["winner_id"]) == (
        1,
        2,
        secondo.id,
    )


def test_la_partita_a_set_si_corregge_con_un_set_in_meno(
    client, admin, db_session, isolated_players
):
    gara = _gara(db_session, distance=4)
    match = _a_set(db_session, gara, isolated_players)
    _gioca_a_set(client, match.id, (4, 1), (2, 4), (4, 3))

    client.post(
        f"/admin/match/{match.id}/correct",
        data=_campi_set([(4, 1), (4, 3)], player1_score=2, player2_score=0),
    )
    riletta = db_session.get(Match, match.id)
    assert (riletta.player1_score, riletta.player2_score) == (2, 0)
    assert riletta.winner_id == isolated_players[3].id


def test_una_partita_a_set_impossibile_non_si_scrive(
    client, admin, db_session, isolated_players
):
    from models.match.models import MatchCorrection

    gara = _gara(db_session, distance=4)
    match = _a_set(db_session, gara, isolated_players)
    _gioca_a_set(client, match.id, (4, 1), (4, 2))

    client.post(
        f"/admin/match/{match.id}/correct",
        data=_campi_set([(4, 1), (4, 2), (4, 0)], player1_score=3, player2_score=0),
    )
    riletta = db_session.get(Match, match.id)
    assert (riletta.player1_score, riletta.player2_score) == (2, 0)
    assert MatchCorrection.query.filter_by(match_id=match.id).count() == 0


def test_la_partita_a_set_di_un_turno_bloccato_non_si_corregge(
    client, admin, db_session, isolated_players
):
    from models.match.models import MatchCorrection

    gara = _gara(db_session, distance=4)
    match = _a_set(db_session, gara, isolated_players)
    _gioca_a_set(client, match.id, (4, 1), (4, 2))
    _blocca_il_turno_1(db_session, gara, isolated_players)

    client.post(
        f"/admin/match/{match.id}/correct",
        data=_campi_set([(4, 1), (2, 4), (1, 4)], player1_score=1, player2_score=2),
    )
    riletta = db_session.get(Match, match.id)
    assert (riletta.player1_score, riletta.player2_score) == (2, 0)
    assert MatchCorrection.query.filter_by(match_id=match.id).count() == 0
    assert not _eventi_della_correzione(gara.id, match.id)


def test_a_set_pari_con_i_triangoli_esatti_la_partita_non_e_alla_distanza(
    db_session, isolated_players
):
    """`is_at_distance` usava la modalita' dei triangoli anche per i set: a 1–1
    con i triangoli «esattamente» la partita al 2 set risultava finita."""
    from models.competition.direttore_view import StatoPartita, stato_partita

    gara = _gara(db_session, distance=4)
    match = _a_set(db_session, gara, isolated_players)
    match.is_race_to = False
    match.player1_score = 1
    match.player2_score = 1
    db_session.commit()
    assert match.is_at_distance is False
    assert stato_partita(match) == StatoPartita.IN_CORSO
    match.player1_score = 2
    assert match.is_at_distance is True


# ── X con esercizio ───────────────────────────────────────────────────────────


@pytest.fixture
def gara_con_x(db_session, admin):
    """Gara Amalfi a cinque con la X sostituita da un esercizio."""
    from models.challenge.models import Challenge
    from models.competition.inscription_service import InscriptionService
    from models.competition.round_service import RoundService
    from models.competition.services import GaraService
    from models.user.models import User

    giocatori = []
    for i in range(5):
        s = uuid.uuid4().hex[:8]
        u = User(username=f"x{i}_{s}", email=f"x{i}_{s}@t.com", role="player")
        u.set_password("test1234")
        db_session.add(u)
        giocatori.append(u)
    esercizio = Challenge(
        description="Spot Shot Rally",
        image_path="test.jpg",
        pass_fail_only=False,
        created_by_id=admin.id,
        is_active=True,
    )
    db_session.add(esercizio)
    db_session.commit()
    gara = GaraService.create_gara(
        campionato_id=None,
        number=1,
        name=f"Gara X {uuid.uuid4().hex[:6]}",
        date=date.today() + timedelta(days=7),
        location="Test",
        description="",
        rounds_count=3,
        min_participants=3,
        max_participants=8,
        entry_fee=0.0,
        discipline="9_ball",
        distance=5,
        is_race_to=True,
        director_id=admin.id,
        matchmaking_strategy="amalfi",
        first_round_policy="random",
        odd_number_policy="bye_with_challenge",
        anti_rematch_enabled=True,
        x_challenge_id=esercizio.id,
    )
    InscriptionService.open_inscriptions(
        gara.id, utc_now() - timedelta(hours=1), utc_now() + timedelta(days=5)
    )
    for g in giocatori:
        InscriptionService.inscribe_user(g.id, gara.id)
    db_session.commit()
    RoundService.start_first_round(gara.id)
    x = Match.query.filter_by(gara_id=gara.id, round_number=1, is_bye=True).one()
    # La distanza del turno (ADR-027): l'override porta il turno al 3.
    x.match_distance = 3
    db_session.commit()
    return gara, x


def _url_prova(x, azione):
    return f"/admin/gara/{x.gara_id}/round/1/prova-x/{x.player1_id}/{azione}"


def test_la_card_della_x_ha_lo_stepper_fino_alla_distanza_del_turno(client, gara_con_x):
    gara, x = gara_con_x
    html = client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)
    card = _card(html, x.id)
    assert 'data-tipo="x"' in card
    assert 'data-max="3"' in card, "la distanza del turno, non quella della gara"
    assert "Convalida" in card
    assert "convalidaProvaX(this)" in card
    assert "confirm(" not in card
    assert "form-control" not in card


def test_la_prova_si_convalida_in_json_col_limite_del_turno(
    client, admin, db_session, gara_con_x
):
    from models.competition.gara_bye_challenge import GaraByeChallenge

    gara, x = gara_con_x
    intestazioni = {"X-Requested-With": "XMLHttpRequest"}

    r = client.post(_url_prova(x, "valida"), data={"score": 4}, headers=intestazioni)
    assert r.status_code in (400, 422)
    assert r.get_json()["success"] is False

    r = client.post(_url_prova(x, "valida"), data={"score": 2}, headers=intestazioni)
    assert r.status_code == 200
    assert r.get_json() == {"success": True, "punteggio": 2}
    assert db_session.get(Match, x.id).player1_score == 2
    assert any(
        e["data"].get("autore") == admin.id and e["data"].get("match_id") == x.id
        for e in _eventi(gara.id)
    )

    html = client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)
    card = _card(html, x.id)
    assert "Convalidata" in card
    assert "data-prova-reset-url" in card

    r = client.post(_url_prova(x, "azzera"), headers=intestazioni)
    assert r.status_code == 200
    assert r.get_json()["success"] is True
    ponte = GaraByeChallenge.query.filter_by(
        gara_id=gara.id, round_number=1, user_id=x.player1_id
    ).one()
    assert not ponte.is_validated
    assert db_session.get(Match, x.id).player1_score == 0


def test_la_prova_dal_form_di_prima_risponde_ancora_col_redirect(client, gara_con_x):
    _, x = gara_con_x
    r = client.post(_url_prova(x, "valida"), data={"score": 1})
    assert r.status_code == 302
