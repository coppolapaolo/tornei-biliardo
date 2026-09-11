"""Lo storico delle gare: la pagina `/storico` e la spia su `/campionatos`.

Regola 2 del 2026-09-10: la dashboard tiene l'ultima conclusa e quelle
dell'ultimo mese; il resto sta nello storico, di tutti, con «Hai giocato»
e «Hai diretto» per riconoscere le proprie. Qui si prova quello che decide
il database — cosa è concluso, cosa è mio, chi ha vinto — e che i filtri
arrivino dall'indirizzo alla pagina.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest

from models.base import utc_now
from models.classification.models import GaraClassification
from models.competition.models import Gara, Inscription
from models.status_enum import Discipline, GaraStatus


def _uid() -> str:
    return str(uuid.uuid4())[:8]


def _login(client, user, password) -> None:
    client.post(
        "/auth/login",
        data={"username": user.username, "password": password},
        follow_redirects=True,
    )


def _gara(
    nome, giorno, status=GaraStatus.COMPLETED.value, director_id=None, sala="Sala"
):
    return Gara(
        name=nome,
        number=1,
        date=giorno,
        location=sala,
        discipline=Discipline.NINE_BALL.value,
        status=status,
        distance=5,
        is_race_to=True,
        max_participants=8,
        min_participants=2,
        director_id=director_id,
        inscription_start=utc_now() - timedelta(days=30),
        inscription_end=utc_now() - timedelta(days=20),
    )


@pytest.fixture
def scenario(db_session, isolated_director_user, isolated_players):
    """Tre gare: una recente diretta dal direttore e vinta dal primo
    giocatore, una dell'anno scorso vinta dal secondo, una con le
    iscrizioni ancora aperte che nello storico non deve stare."""
    p0, p1 = isolated_players[0], isolated_players[1]
    recente = _gara(
        f"Coppa Recente {_uid()}",
        date.today() - timedelta(days=3),
        director_id=isolated_director_user.id,
        sala="Sala Centrale",
    )
    vecchia = _gara(f"Notturna Vecchia {_uid()}", date(date.today().year - 1, 5, 5))
    aperta = _gara(
        f"Aperta {_uid()}",
        date.today() + timedelta(days=5),
        status=GaraStatus.INSCRIPTION.value,
    )
    db_session.add_all([recente, vecchia, aperta])
    db_session.flush()
    db_session.add_all(
        [
            Inscription(user_id=p0.id, gara_id=recente.id),
            Inscription(user_id=p1.id, gara_id=recente.id),
            Inscription(user_id=p1.id, gara_id=vecchia.id),
            GaraClassification(gara_id=recente.id, user_id=p0.id, position=1),
            GaraClassification(gara_id=recente.id, user_id=p1.id, position=2),
            GaraClassification(gara_id=vecchia.id, user_id=p1.id, position=1),
        ]
    )
    db_session.commit()
    return {
        "recente": recente,
        "vecchia": vecchia,
        "aperta": aperta,
        "p0": p0,
        "p1": p1,
    }


@pytest.mark.integration
def test_l_ospite_vede_le_concluse_col_vincitore_e_nessun_filtro_sui_fatti(
    client, scenario
):
    html = client.get("/storico").get_data(as_text=True)

    assert scenario["recente"].name in html
    assert scenario["vecchia"].name in html
    assert scenario["aperta"].name not in html, "le iscrizioni aperte non sono storia"
    # il vincitore, dalla classifica finale
    assert scenario["p0"].username in html
    # i chip sui fatti non ci sono: l'ospite non ha fatti
    assert "Che ho giocato" not in html
    assert "Hai giocato" not in html
    # i due segmenti: le gare qui, i campionati sulla loro pagina
    assert "/campionatos?status=completati" in html


@pytest.mark.integration
def test_una_gara_in_gioco_senza_partite_non_e_conclusa(client, db_session, scenario):
    """Lo stato reale, come in dashboard: `playing` con i turni ancora da
    giocare non è concluso, anche se la colonna non dice `completed`."""
    in_gioco = _gara(
        f"In gioco {_uid()}", date.today(), status=GaraStatus.PLAYING.value
    )
    db_session.add(in_gioco)
    db_session.commit()

    html = client.get("/storico").get_data(as_text=True)
    assert in_gioco.name not in html


@pytest.mark.integration
def test_il_giocatore_riconosce_le_sue_e_le_filtra(client, scenario):
    p0 = scenario["p0"]
    _login(client, p0, "player123")

    html = client.get("/storico").get_data(as_text=True)
    riga = html.split(scenario["recente"].name, 1)[1].split("</a>", 1)[0]
    assert "Hai giocato" in riga
    assert "1°" in riga, "il piazzamento sta sulla pastiglia"
    assert "Che ho giocato" in html

    solo_mie = client.get("/storico?chi=giocate").get_data(as_text=True)
    assert scenario["recente"].name in solo_mie
    assert scenario["vecchia"].name not in solo_mie

    primi = client.get("/storico?primi=1").get_data(as_text=True)
    assert scenario["recente"].name in primi
    assert scenario["vecchia"].name not in primi


@pytest.mark.integration
def test_il_direttore_riconosce_quelle_che_ha_diretto(
    client, scenario, isolated_director_user
):
    _login(client, isolated_director_user, "director123")

    html = client.get("/storico?chi=dirette").get_data(as_text=True)
    assert scenario["recente"].name in html
    assert scenario["vecchia"].name not in html
    riga = html.split(scenario["recente"].name, 1)[1].split("</a>", 1)[0]
    assert "Hai diretto" in riga


@pytest.mark.integration
def test_anno_e_ricerca_arrivano_dall_indirizzo(client, scenario):
    anno_scorso = date.today().year - 1
    html = client.get(f"/storico?anno={anno_scorso}").get_data(as_text=True)
    assert scenario["vecchia"].name in html
    assert scenario["recente"].name not in html
    assert f"nel {anno_scorso}" in html

    html = client.get("/storico?q=centrale").get_data(as_text=True)
    assert scenario["recente"].name in html
    assert scenario["vecchia"].name not in html

    html = client.get("/storico?q=nessuna-gara-si-chiama-cosi").get_data(as_text=True)
    assert "Nessuna gara corrisponde ai filtri" in html


@pytest.mark.integration
def test_la_dashboard_manda_allo_storico(client, scenario, isolated_director_user):
    """Il link «Storico» delle concluse punta qui, non all'elenco delle sole
    standalone; e i vecchi «Vedi tutte» / «Vedi tutti» accanto ai titoli non
    ci sono più, né per chi gioca né per chi dirige (#332)."""
    for utente, password in (
        (scenario["p0"], "player123"),
        (isolated_director_user, "director123"),
    ):
        _login(client, utente, password)
        html = client.get("/dashboard").get_data(as_text=True)
        assert 'href="/storico"' in html
        assert 'href="/garas">Storico' not in html
        assert "Vedi tutt" not in html, utente.username
        client.get("/auth/logout")


@pytest.mark.integration
def test_due_primi_a_pari_merito_non_hanno_un_vincitore(client, db_session, scenario):
    """`StateService.complete` non designa un vincitore quando il primo posto
    è conteso: lo storico non deve sceglierne uno a caso (rilievo #333)."""
    vecchia, p0, p1 = scenario["vecchia"], scenario["p0"], scenario["p1"]
    db_session.add(GaraClassification(gara_id=vecchia.id, user_id=p0.id, position=1))
    db_session.commit()

    html = client.get("/storico").get_data(as_text=True)
    riga = html.split(vecchia.name, 1)[1].split("</a>", 1)[0]
    assert p0.username not in riga
    assert p1.username not in riga


@pytest.mark.integration
def test_conclusa_per_derivazione_prende_il_vincitore_dall_ultimo_turno(
    client, db_session, scenario
):
    """Una gara `playing` coi turni finiti è conclusa (stato derivato) ma
    nessuno ha premuto «Termina»: `GaraClassification` non c'è ancora. Il
    vincitore si legge dalla classifica dell'ultimo turno (rilievo #333)."""
    from models.classification.models import RoundClassification
    from models.match.models import Match
    from models.status_enum import MatchStatus

    p0, p1 = scenario["p0"], scenario["p1"]
    derivata = _gara(
        f"Derivata {_uid()}",
        date.today() - timedelta(days=1),
        status=GaraStatus.PLAYING.value,
    )
    derivata.rounds_count = 1
    db_session.add(derivata)
    db_session.flush()
    db_session.add_all(
        [
            Match(
                gara_id=derivata.id,
                round_number=1,
                player1_id=p0.id,
                player2_id=p1.id,
                player1_score=5,
                player2_score=1,
                status=MatchStatus.CLOSED_UNILATERALLY.value,
                winner_id=p0.id,
            ),
            RoundClassification(
                gara_id=derivata.id, round_number=1, user_id=p0.id, position=1
            ),
        ]
    )
    db_session.commit()

    html = client.get("/storico").get_data(as_text=True)
    assert derivata.name in html
    riga = html.split(derivata.name, 1)[1].split("</a>", 1)[0]
    assert p0.username in riga


@pytest.mark.integration
def test_il_turno_finale_e_quello_con_le_partite_non_il_programma(
    client, db_session, scenario
):
    """Uno spareggio aggiunge un turno oltre `rounds_count`: il vincitore
    si legge da lì, come fa `StateService.complete` con
    `effective_final_round` (rilievo di Copilot sulla #336)."""
    from models.classification.models import RoundClassification
    from models.match.models import Match
    from models.status_enum import MatchStatus

    p0, p1 = scenario["p0"], scenario["p1"]
    gara = _gara(
        f"Con spareggio {_uid()}",
        date.today() - timedelta(days=1),
        status=GaraStatus.PLAYING.value,
    )
    gara.rounds_count = 1
    gara.current_round = 2
    db_session.add(gara)
    db_session.flush()

    def partita(turno, vincitore, perdente):
        return Match(
            gara_id=gara.id,
            round_number=turno,
            player1_id=vincitore.id,
            player2_id=perdente.id,
            player1_score=5,
            player2_score=3,
            status=MatchStatus.CLOSED_UNILATERALLY.value,
            winner_id=vincitore.id,
        )

    db_session.add_all(
        [
            partita(1, p1, p0),
            partita(2, p0, p1),
            RoundClassification(
                gara_id=gara.id, round_number=1, user_id=p1.id, position=1
            ),
            RoundClassification(
                gara_id=gara.id, round_number=2, user_id=p0.id, position=1
            ),
        ]
    )
    db_session.commit()

    html = client.get("/storico").get_data(as_text=True)
    riga = html.split(gara.name, 1)[1].split("</a>", 1)[0]
    assert p0.username in riga, "il turno di spareggio decide"
    assert p1.username not in riga


@pytest.mark.integration
def test_l_elenco_dei_campionati_ha_la_spia_della_partecipazione(
    client, db_session, isolated_director_user, isolated_players
):
    from models.campionato.services import TournamentService
    from models.competition.services import GaraService

    campionato = TournamentService().create_campionato_with_director(
        name=f"Storico {_uid()}",
        creator_user_id=isolated_director_user.id,
        campionato_type="Amalfi",
        is_active=True,
        planned_gare_count=1,
    )
    gara = GaraService.create_gara(
        campionato_id=campionato.id,
        number=1,
        name="Gara 1",
        date=date.today() + timedelta(days=1),
        location="Sala",
        description="",
        rounds_count=1,
        min_participants=2,
        max_participants=4,
        entry_fee=0.0,
        discipline="9_ball",
        distance=5,
        is_race_to=True,
        director_id=isolated_director_user.id,
        matchmaking_strategy="amalfi",
    )
    p0 = isolated_players[0]
    db_session.add(Inscription(user_id=p0.id, gara_id=gara.id))
    db_session.commit()

    def scheda(html):
        return html.split(campionato.name, 1)[1].split("</article>", 1)[0]

    # l'ospite non ha fatti
    assert "Iscritto" not in scheda(client.get("/campionatos").get_data(as_text=True))

    _login(client, p0, "player123")
    assert "Iscritto" in scheda(client.get("/campionatos").get_data(as_text=True))
    client.get("/auth/logout", follow_redirects=True)

    _login(client, isolated_director_user, "director123")
    assert "Dirigi" in scheda(client.get("/campionatos").get_data(as_text=True))
    client.get("/auth/logout", follow_redirects=True)

    # concluso: le parole cambiano
    gara.status = GaraStatus.COMPLETED.value
    campionato.terminated_at = utc_now()
    db_session.commit()
    _login(client, p0, "player123")
    testo = scheda(client.get("/campionatos?status=completati").get_data(as_text=True))
    assert "Hai giocato" in testo
    assert "Iscritto" not in testo
