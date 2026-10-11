"""Le pagine di una gara col tabellone dopo i gironi (ADR-081).

Otto giocatori in due gironi da quattro, composti per ELO, due qualificati
per girone, con la finalina. Nel girone del più forte gli altri tre si
battono in cerchio (A batte B, B batte C, C batte A): finiscono pari, e ne
passa uno solo — lo decide la catena di turno, col sorteggio in fondo.

* Durante i gironi: classifiche per girone, nessun tabellone.
* A gironi finiti: «al tabellone» e «fuori», con la riga del taglio; il
  comando dice «Avvia le semifinali».
* Durante il tabellone: il tabellone (direttore, pagina del tabellone,
  schermo in sala) con sotto le classifiche dei gironi.
* A gara conclusa: la classifica finale della serata.
* Girone unico: niente del tabellone. Tabellone puro: come sempre.
"""

from __future__ import annotations

import re
import uuid
from datetime import date, timedelta
from typing import Callable, Dict, List, Tuple

import pytest

from models import User
from models.base import db, utc_now
from models.competition.fase_finale_service import chi_va_al_tabellone
from models.competition.inscription_service import InscriptionService
from models.competition.models import Gara, Inscription
from models.competition.round_service import RoundService
from models.competition.services import GaraService
from models.match.models import Match
from models.match.services import RackService
from models.matchmaking.bracket import BRACKET_WINNERS
from models.status_enum import GaraStatus, MatchStatus
from models.user.role_enum import UserRole

pytestmark = pytest.mark.integration

# I segni del taglio (`components/_taglio.html`).
TAGLIO = 'class="c7-taglio"'
SEGNO = "data-taglio="
AL_TABELLONE = 'data-taglio="dentro"'
FUORI = 'data-taglio="fuori"'


def _utente(role: str, elo=None) -> User:
    uid = uuid.uuid4().hex[:8]
    user = User(username=f"tdg_{role}_{uid}", email=f"tdg_{role}_{uid}@test.com")
    user.role = role
    user.set_password("x")
    user.elo_rating = elo
    db.session.add(user)
    return user


def _gara(
    n: int = 8, *, strategia: str = "round_robin"
) -> Tuple[Gara, User, List[User]]:
    director = _utente(UserRole.DIRECTOR.value)
    players = [_utente(UserRole.PLAYER.value, elo=2000 - 10 * i) for i in range(n)]
    db.session.commit()
    valori = dict(
        campionato_id=None,
        number=1,
        name="Lunedì al 74",
        date=date.today() + timedelta(days=7),
        location="Sala",
        description="",
        rounds_count=3,
        min_participants=3,
        max_participants=16,
        entry_fee=0.0,
        discipline="8_ball",
        distance=3,
        is_race_to=True,
        director_id=director.id,
        matchmaking_strategy=strategia,
        first_round_policy="random",
        odd_number_policy="bye",
        anti_rematch_enabled=False,
        third_place_match=True,
    )
    if strategia == "round_robin":
        valori.update(
            max_groups=2,
            group_seeding="elo",
            final_phase_mode="tabellone",
            qualifiers_per_group=2,
        )
    gara = GaraService.create_gara(**valori)
    gara.public_token = uuid.uuid4().hex[:10]
    db.session.commit()
    InscriptionService.open_inscriptions(
        gara.id, utc_now() - timedelta(hours=1), utc_now() + timedelta(hours=1)
    )
    for player in players:
        InscriptionService.inscribe_user(player.id, gara.id)
    return gara, director, players


def _vincitore(players: List[User], gara: Gara) -> Callable[[Match], int]:
    """Vince il più forte, salvo il cerchio nel girone del primo."""
    elo = {p.id: p.elo_rating for p in players}
    girone_di = {
        i.user_id: i.group_index
        for i in Inscription.query.filter_by(gara_id=gara.id).all()
    }
    testa = players[0].id
    altri = sorted(
        (p for p in girone_di if girone_di[p] == girone_di.get(testa) and p != testa),
        key=lambda p: -elo[p],
    )
    cerchio: Dict[frozenset, int] = {}
    if len(altri) == 3:
        a, b, c = altri
        cerchio = {frozenset((a, b)): a, frozenset((b, c)): b, frozenset((c, a)): c}

    def chi(m: Match) -> int:
        coppia = frozenset((m.player1_id, m.player2_id))
        if coppia in cerchio:
            return cerchio[coppia]
        return max((m.player1_id, m.player2_id), key=lambda p: elo[p])

    return chi


def _gioca(gara_id: int, r: int, chi_vince: Callable[[Match], int]) -> None:
    for match in Match.query.filter_by(gara_id=gara_id, round_number=r).all():
        if match.is_bye or MatchStatus.is_finished(match.status):
            continue
        vince = chi_vince(match)
        for _ in range(match.match_distance):
            RackService.add_rack_with_score_update(
                match_id=match.id,
                winner_id=vince,
                reported_by_id=vince,
                validated_by_admin=True,
            )
    db.session.commit()
    RoundService.update_round_progression(gara_id)
    db.session.commit()


def _fino_al_turno(
    gara: Gara, players: List[User], ultimo: int, groups: int = 2
) -> Gara:
    RoundService.start_first_round(gara.id, groups_count=groups)
    gara = db.session.get(Gara, gara.id)
    chi = _vincitore(players, gara)
    for r in range(1, ultimo + 1):
        if r > 1:
            RoundService.start_next_round(gara.id, r)
        _gioca(gara.id, r, chi)
    return db.session.get(Gara, gara.id)


def _come(client, user: User) -> None:
    risposta = client.post(
        "/auth/login", data={"username": user.username, "password": "x"}
    )
    assert risposta.status_code in (200, 302)


def _html(client, url: str, atteso: int = 200) -> str:
    risposta = client.get(url)
    assert risposta.status_code == atteso, url
    return risposta.get_data(as_text=True)


def _sezione_direttore(html: str) -> str:
    sezione = html[html.index('id="classificaDirettore"') :]
    return sezione[: sezione.index("</section>")]


class TestDuranteIGironi:
    def test_classifiche_per_girone_e_nessun_tabellone(self, client):
        gara, director, players = _gara()
        gara = _fino_al_turno(gara, players, 2)
        _come(client, director)
        html = _html(client, f"/admin/gara/{gara.id}")
        sezione = _sezione_direttore(html)
        assert 'data-girone="A"' in sezione and 'data-girone="B"' in sezione
        assert "c7-tabellino" not in html
        assert SEGNO not in html and TAGLIO not in html
        assert f"/admin/gara/{gara.id}/tabellone" not in html
        _html(client, f"/admin/gara/{gara.id}/tabellone", 404)


class TestAGironiFiniti:
    def test_il_taglio_con_tre_pari_ne_passa_uno(self, client):
        gara, director, players = _gara()
        gara = _fino_al_turno(gara, players, 3)
        qualificati = chi_va_al_tabellone(gara)
        assert qualificati is not None and len(qualificati) == 4
        girone_di = {
            i.user_id: i.group_index
            for i in Inscription.query.filter_by(gara_id=gara.id).all()
        }
        testa = players[0].id
        pari = [p for p in girone_di if girone_di[p] == girone_di[testa] and p != testa]
        passa = [p for p in pari if p in qualificati]
        assert len(passa) == 1  # tre pari, un solo posto
        nomi = {p.id: p.username for p in players}

        _come(client, director)
        html = _html(client, f"/admin/gara/{gara.id}")
        sezione = _sezione_direttore(html)
        nome_a = "A" if girone_di[testa] == 0 else "B"
        altro = "B" if nome_a == "A" else "A"
        a = sezione[sezione.index(f'data-girone="{nome_a}"') :]
        if f'data-girone="{altro}"' in a:
            a = a[: a.index(f'data-girone="{altro}"')]
        taglio = a.index(TAGLIO)
        # Chi passa sta sopra la riga del taglio, gli altri due sotto.
        assert a.index(nomi[passa[0]]) < taglio
        for p in pari:
            if p != passa[0]:
                assert a.index(nomi[p]) > taglio
        assert a.count(AL_TABELLONE) == 2 and a.count(FUORI) == 2
        # Il comando dice cosa sta per nascere.
        assert "Avvia le semifinali" in html

        guest = client.application.test_client()
        pubblica = _html(guest, f"/admin/gara/{gara.id}")
        assert AL_TABELLONE in pubblica and TAGLIO in pubblica
        sala = _html(guest, f"/g/{gara.public_token}/sala")
        assert AL_TABELLONE in sala and TAGLIO in sala


class TestDuranteIlTabellone:
    def test_il_tabellone_con_sotto_i_gironi(self, client):
        gara, director, players = _gara()
        gara = _fino_al_turno(gara, players, 3)
        RoundService.start_next_round(gara.id, 4)
        db.session.commit()

        _come(client, director)
        html = _html(client, f"/admin/gara/{gara.id}")
        assert "c7-tabellino" in html
        assert "Semifinali" in html
        sezione = _sezione_direttore(html)
        assert "Classifiche dei gironi" in sezione
        assert 'data-girone="A"' in sezione and AL_TABELLONE in sezione

        tab = _html(client, f"/admin/gara/{gara.id}/tabellone")
        assert "Tabellone finale" in tab and "Classifiche dei gironi" in tab
        assert tab.count(AL_TABELLONE) == 4 and tab.count(FUORI) == 4

        guest = client.application.test_client()
        pubblica = _html(guest, f"/admin/gara/{gara.id}")
        assert f"/admin/gara/{gara.id}/tabellone" in pubblica
        sala = _html(guest, f"/g/{gara.public_token}/sala")
        assert 'data-fase="tabellone"' in sala
        assert "Classifiche dei gironi" in sala and 'data-girone="A"' in sala


class TestAGaraConclusa:
    def test_la_classifica_finale_della_serata(self, client):
        gara, director, players = _gara()
        gara = _fino_al_turno(gara, players, 5)
        finale = [
            m
            for m in Match.query.filter_by(gara_id=gara.id, round_number=5).all()
            if m.bracket_type == BRACKET_WINNERS
        ]
        assert len(finale) == 1
        GaraService.complete(gara.id)
        db.session.commit()
        gara = db.session.get(Gara, gara.id)
        assert gara.status == GaraStatus.COMPLETED.value
        campione = next(p for p in players if p.id == finale[0].winner_id)

        _come(client, director)
        html = _html(client, f"/admin/gara/{gara.id}")
        assert TAGLIO not in html
        guest = client.application.test_client()
        sala = _html(guest, f"/g/{gara.public_token}/sala")
        assert 'data-fase="conclusa"' in sala and "Classifica finale" in sala
        assert re.search(r"girone [AB]", sala)
        righe = sala[sala.index("Classifica finale") :]
        assert righe.index(campione.username) < min(
            righe.index(p.username) for p in players if p.id != campione.id
        )


class TestGironeUnico:
    def test_niente_del_tabellone(self, client):
        gara, director, players = _gara(5)
        gara = _fino_al_turno(gara, players, 1, groups=1)
        _come(client, director)
        html = _html(client, f"/admin/gara/{gara.id}")
        assert "c7-tabellino" not in html and TAGLIO not in html
        assert "Classifiche dei gironi" not in html
        _html(client, f"/admin/gara/{gara.id}/tabellone", 404)
        guest = client.application.test_client()
        sala = _html(guest, f"/g/{gara.public_token}/sala")
        assert 'data-fase="gioco"' in sala


class TestTabellonePuro:
    def test_eliminazione_diretta_come_sempre(self, client):
        gara, director, players = _gara(8, strategia="direct_elimination")
        RoundService.start_first_round(gara.id)
        db.session.commit()
        _come(client, director)
        html = _html(client, f"/admin/gara/{gara.id}")
        assert "c7-tabellino" in html and "Quarti" in html
        assert "Classifiche dei gironi" not in html and SEGNO not in html
        tab = _html(client, f"/admin/gara/{gara.id}/tabellone")
        assert "Classifiche dei gironi" not in tab
        sala = _html(client.application.test_client(), f"/g/{gara.public_token}/sala")
        assert 'data-fase="tabellone"' in sala
