"""Lo schermo in sala dal client HTTP (canvas 3.10).

La pagina `/g/<indirizzo>/sala` e il suo poll sono pubblici: li apre un
computer della sala senza login. Qui si difendono le cinque cose che non
devono cambiare in silenzio: l'anonimo la vede, una prova (ADR-058) no, una
gara a tabellone mostra tavoli, turno del tabellone e a gara conclusa podio e
bande (issue #352), un risultato appena arrivato resta in pagina invece di
sparire col tavolo che si libera (issue #443), e la pagina non scrive sul
database.
"""

from __future__ import annotations

import json
import uuid
from contextlib import contextmanager
from datetime import date, timedelta

import pytest
from flask import g
from sqlalchemy import event

from models import Gara, Match
from models.base import db, utc_now
from models.classification.models import RoundClassification
from models.competition.inscription_service import InscriptionService
from models.competition.round_service import RoundService
from models.competition.services import GaraService
from models.match.services import RackService
from models.prova.service import ProvaService
from models.status_enum import Discipline, GaraStatus, MatchStatus
from models.user.models import User
from models.user.role_enum import UserRole

pytestmark = pytest.mark.integration


def _utente(prefisso: str, role: str = UserRole.PLAYER.value) -> User:
    unico = uuid.uuid4().hex[:6]
    u = User(
        username=f"{prefisso}_{unico}",
        email=f"{prefisso}_{unico}@test.local",
        role=role,
    )
    u.set_password("secret123")
    db.session.add(u)
    db.session.commit()
    return u


def _gara(*, strategy="amalfi", status=GaraStatus.PLAYING.value, token=None) -> Gara:
    gara = Gara(
        number=1,
        name="Gara in sala",
        date=date.today(),
        location="Sala Test",
        discipline=Discipline.EIGHT_BALL.value,
        distance=5,
        is_race_to=True,
        matchmaking_strategy=strategy,
        status=status,
        current_round=1,
        rounds_count=3,
        min_participants=2,
        available_tables=json.dumps(["1", "2"]),
        public_token=token or uuid.uuid4().hex[:10],
    )
    db.session.add(gara)
    db.session.commit()
    return gara


def _partita(
    gara, p1, p2, s1, s2, *, status=MatchStatus.PLAYING.value, tavolo=None, turno=1
):
    m = Match(
        gara_id=gara.id,
        round_number=turno,
        player1_id=p1.id,
        player2_id=p2.id,
        player1_score=s1,
        player2_score=s2,
        status=status,
        table_assignment=tavolo,
    )
    db.session.add(m)
    db.session.commit()
    return m


def test_l_anonimo_vede_i_tavoli_senza_menu(client, db_session):
    gara = _gara()
    rossi, verdi = _utente("rossi"), _utente("verdi")
    _partita(gara, rossi, verdi, 4, 2, tavolo="1")

    r = client.get(f"/g/{gara.public_token}/sala")

    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert 'id="schermoSala"' in html
    assert rossi.username in html and verdi.username in html
    assert 'class="c7-sala__punti c7-num">4<' in html
    # Il tavolo 2 e' libero.
    assert "Libero" in html
    # Niente guscio dell'app: ne' colonna laterale ne' comando per richiuderla.
    assert "c7-sidetoggle" not in html
    assert 'name="robots" content="noindex"' in html
    assert f"/sse/poll/sala/{gara.public_token}" in html


def test_il_risultato_appena_arrivato_resta_sulla_pagina(client, db_session):
    """Issue #443: una partita che finisce non deve sparire dallo schermo.

    Le due strade, in una pagina sola. Il tavolo 1 si e' liberato e nessuno
    lo ha ripreso: il punteggio resta nella sua casella. Il tavolo 2 invece
    e' gia' tornato in uso, quindi quel risultato scende nell'elenco accanto
    alla classifica. In nessuno dei due casi si perde — che era il difetto:
    fuori dal tavolo, non ancora in classifica, e i risultati in basso
    mostrano solo i turni gia' chiusi.

    Il tavolo si legge da `played_on_table`, non da `table_assignment`: alla
    chiusura quest'ultima torna a NULL per rimettere il tavolo in circolo.
    """
    gara = _gara()
    marco, flavio = _utente("marco"), _utente("flavio")
    neri, conti = _utente("neri"), _utente("conti")
    galli, sala = _utente("galli"), _utente("sala")

    # Due partite chiuse: il listener di `Match` ricorda il tavolo, poi la
    # chiusura lo libera — esattamente come in produzione.
    for p1, p2, s1, s2, tavolo in (
        (marco, flavio, 5, 2, "1"),
        (neri, conti, 1, 5, "2"),
    ):
        m = _partita(gara, p1, p2, s1, s2, tavolo=tavolo)
        m.status = MatchStatus.CLOSED_UNILATERALLY.value
        m.table_assignment = None
        db.session.commit()
        assert m.played_on_table == tavolo

    # Il tavolo 2 se lo riprende un'altra partita, che tiene aperto il turno.
    _partita(gara, galli, sala, 2, 1, tavolo="2")

    html = client.get(f"/g/{gara.public_token}/sala").get_data(as_text=True)

    # Il tavolo 1 e' libero e mostra comunque il risultato.
    assert "c7-sala__lati--conclusa" in html
    assert "Partita conclusa" in html
    assert marco.username in html and flavio.username in html

    # Quello del tavolo 2 non ha piu' casella: sta nell'elenco a destra.
    assert "partite già concluse" in html
    assert "c7-sala__partita-chiusa" in html
    assert neri.username in html and conti.username in html


def test_la_classifica_gia_calcolata_ha_le_medaglie(client, db_session):
    gara = _gara()
    rossi, verdi = _utente("rossi"), _utente("verdi")
    _partita(gara, rossi, verdi, 5, 2, status=MatchStatus.CLOSED_UNILATERALLY.value)
    for pos, u in ((1, rossi), (2, verdi)):
        db.session.add(
            RoundClassification(
                gara_id=gara.id,
                round_number=1,
                user_id=u.id,
                position=pos,
                matches_won=2 - pos,
                rack_difference=3 if pos == 1 else -3,
            )
        )
    db.session.commit()

    html = client.get(f"/g/{gara.public_token}/sala").get_data(as_text=True)

    assert "Classifica dopo il turno 1" in html
    assert "c7-pos--1" in html and "c7-pos--2" in html
    assert "+3" in html


def test_la_pagina_non_ricalcola_la_classifica(client, db_session, monkeypatch):
    """Anonima e ricaricata a ogni evento: non deve scrivere sul database."""
    gara = _gara()
    rossi, verdi = _utente("rossi"), _utente("verdi")
    _partita(gara, rossi, verdi, 5, 2, status=MatchStatus.CLOSED_UNILATERALLY.value)

    def vietato(*args, **kwargs):
        raise AssertionError("lo schermo in sala non ricalcola la classifica")

    monkeypatch.setattr(
        RoundClassification, "calculate_classification_after_round", vietato
    )

    assert client.get(f"/g/{gara.public_token}/sala").status_code == 200


def _tabellone(db_session, n: int = 8, *, strategy="direct_elimination") -> Gara:
    """Una gara a tabellone con `n` iscritti e il sorteggio fatto."""
    batch = uuid.uuid4().hex[:6]
    giocatori = []
    for i in range(n):
        u = User(
            username=f"sala{i}_{batch}",
            email=f"sala{i}_{batch}@test.local",
            role=UserRole.PLAYER.value,
        )
        u.set_password("secret123")
        giocatori.append(u)
    db_session.add_all(giocatori)
    gara = Gara(
        number=1,
        name=f"Tabellone in sala {batch}",
        date=date.today() + timedelta(days=7),
        discipline=Discipline.NINE_BALL.value,
        distance=2,
        is_race_to=True,
        rounds_count=3,
        min_participants=4,
        max_participants=16,
        matchmaking_strategy=strategy,
        classification_system="POSITION",
        first_round_policy="random",
        available_tables=json.dumps(["1", "2", "3", "4"]),
        public_token=uuid.uuid4().hex[:10],
    )
    db_session.add(gara)
    db_session.commit()
    InscriptionService.open_inscriptions(
        gara.id, utc_now() - timedelta(hours=1), utc_now() + timedelta(hours=1)
    )
    for u in giocatori:
        InscriptionService.inscribe_user(u.id, gara.id)
    db_session.commit()
    RoundService.start_first_round(gara.id)
    return db_session.get(Gara, gara.id)


def _gioca_turno(db_session, gara_id: int, turno: int) -> None:
    """Chiude il turno: vince sempre `player1`."""
    for match in Match.query.filter_by(gara_id=gara_id, round_number=turno):
        if match.is_bye or MatchStatus.is_finished(match.status):
            continue
        for _ in range(match.match_distance):
            RackService.add_rack_with_score_update(
                match_id=match.id,
                winner_id=match.player1_id,
                reported_by_id=match.player1_id,
                validated_by_admin=True,
            )
    db_session.commit()


class TestGaraATabellone:
    """Issue #352: tavoli, turno del tabellone, podio e bande."""

    def test_in_gioco_i_tavoli_e_il_turno_del_tabellone(self, client, db_session):
        gara = _tabellone(db_session, 8)

        html = client.get(f"/g/{gara.public_token}/sala").get_data(as_text=True)

        assert "non è ancora disponibile" not in html
        assert 'class="c7-sala__tavoli' in html
        # Al posto della classifica il turno che si gioca e quello dopo.
        assert "c7-sala-tab" in html
        assert "c7-sala__classifica" not in html
        assert html.count('class="c7-sala-tab__col is-attuale"') == 1
        assert "Quarti" in html and "Semifinali" in html
        # Le due semifinali non sono ancora nate: nodi vuoti, con chi arrivera'.
        assert html.count("c7-sala-tab__nodo is-vuoto") == 2
        assert "chi vince" in html
        # La finale e' due turni avanti: a tre metri non serve.
        assert ">Finale<" not in html

    def test_fra_un_turno_e_l_altro_il_turno_dopo_ha_gia_i_nomi(
        self, client, db_session
    ):
        gara = _tabellone(db_session, 8)
        _gioca_turno(db_session, gara.id, 1)
        vincitori = [
            m.player1.username
            for m in Match.query.filter_by(gara_id=gara.id, round_number=1)
        ]

        html = client.get(f"/g/{gara.public_token}/sala").get_data(as_text=True)

        assert "concluso" in html
        assert html.count("c7-sala-tab__nodo is-vuoto") == 2
        assert all(nome in html for nome in vincitori)

    def test_doppio_ko_vincenti_sopra_e_ripescati_sotto(self, client, db_session):
        gara = _tabellone(db_session, 8, strategy="double_knockout")
        _gioca_turno(db_session, gara.id, 1)
        RoundService.start_next_round(gara.id, 2)

        html = client.get(f"/g/{gara.public_token}/sala").get_data(as_text=True)

        assert html.index(">Vincenti<") < html.index(">Ripescati<")
        assert "Turno 2 dei vincenti · Recupero 1" in html

    def test_a_gara_conclusa_podio_e_bande(self, client, db_session):
        gara = _tabellone(db_session, 8)
        for turno in (1, 2, 3):
            if turno > 1:
                RoundService.start_next_round(gara.id, turno)
            _gioca_turno(db_session, gara.id, turno)
        gara = db_session.get(Gara, gara.id)
        gara.status = GaraStatus.COMPLETED.value
        db_session.commit()

        html = client.get(f"/g/{gara.public_token}/sala").get_data(as_text=True)

        assert "c7-podio-finale" in html
        assert html.count("5°–8°") == 4
        assert html.count("esce ai quarti") == 4
        assert "c7-sala-tab" not in html
        # Conclusa: niente poll.
        assert "/sse/poll/sala/" not in html

    def test_la_pagina_non_scrive_sul_database(self, client, db_session):
        """Anonima e ricaricata a ogni evento: in gioco e a gara conclusa."""
        gara = _tabellone(db_session, 4)

        with _scritture() as in_gioco:
            assert client.get(f"/g/{gara.public_token}/sala").status_code == 200

        _gioca_turno(db_session, gara.id, 1)
        RoundService.start_next_round(gara.id, 2)
        _gioca_turno(db_session, gara.id, 2)
        conclusa = db_session.get(Gara, gara.id)
        conclusa.status = GaraStatus.COMPLETED.value
        db_session.commit()

        with _scritture() as a_gara_conclusa:
            html = client.get(f"/g/{gara.public_token}/sala").get_data(as_text=True)

        assert "c7-podio-finale" in html
        assert in_gioco == [] and a_gara_conclusa == []


@contextmanager
def _scritture():
    """Le istruzioni INSERT/UPDATE/DELETE eseguite dentro il blocco."""
    viste: list = []

    def spia(conn, cursor, statement, *args):
        if statement.lstrip().split(" ", 1)[0].upper() in (
            "INSERT",
            "UPDATE",
            "DELETE",
        ):
            viste.append(statement)

    event.listen(db.engine, "before_cursor_execute", spia)
    try:
        yield viste
    finally:
        event.remove(db.engine, "before_cursor_execute", spia)


def test_un_indirizzo_sconosciuto_e_404(client, db_session):
    assert client.get("/g/nessuna-gara-cosi/sala").status_code == 404
    assert client.get("/sse/poll/sala/nessuna-gara-cosi").status_code == 404


def test_il_poll_pubblico_risponde_all_anonimo(client, db_session):
    gara = _gara()

    r = client.get(f"/sse/poll/sala/{gara.public_token}")

    assert r.status_code == 200
    corpo = r.get_json()
    assert "cursor" in corpo and corpo["events"] == []


def test_una_prova_non_ha_schermo_in_sala(client, db_session):
    """ADR-058: da fuori una prova non esiste, e lo schermo passa dallo stesso
    indirizzo della vetrina."""
    direttore = _utente("dir", role=UserRole.DIRECTOR.value)
    prova = GaraService.create_gara(
        campionato_id=None,
        number=1,
        name=f"Prova segreta {uuid.uuid4().hex[:4]}",
        date=date.today() + timedelta(days=1),
        discipline=Discipline.NINE_BALL.value,
        distance=5,
        director_id=direttore.id,
        min_participants=4,
        max_participants=8,
        status=GaraStatus.INSCRIPTION.value,
        **ProvaService.campi_di_creazione(),
    )
    db.session.commit()
    token = prova.public_token
    # Come in `test_prova_visibilita`: la sessione del test non e' quella di
    # una richiesta vera, e l'identity map servirebbe la prova senza filtro.
    g.pop("_login_user", None)
    db.session.expunge_all()

    assert client.get(f"/g/{token}/sala").status_code == 404
    assert client.get(f"/sse/poll/sala/{token}").status_code == 404
