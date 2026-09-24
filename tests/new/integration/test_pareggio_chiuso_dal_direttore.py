"""Il pareggio segnato da chi dirige la gara chiude la partita, come la vittoria.

Rilievo della gara del 2026-09-23: in «esattamente N triangoli» con N pari la
partita può finire pari, e le firme d'ufficio scattavano solo quando c'era un
vincitore. Il direttore che giocava restava così davanti a «Conferma», e la
conferma lo mandava in dashboard invece che alla gara.

La regola: arrivati alla distanza, se segna chi dirige la gara il punteggio è
già quello ufficiale — con o senza vincitore. Se segna un giocatore qualsiasi
un pareggio chiede ancora le due conferme: nessuno dei due ha perso, quindi
non c'è una firma che si possa dare per implicita.
"""

from datetime import date
from pathlib import Path

import pytest

from models.competition.models import Gara
from models.match.models import Match
from models.status_enum import Discipline, GaraStatus, MatchStatus
from models.user.role_enum import UserRole

pytestmark = pytest.mark.integration


def _gara_con_partita(db_session, prefisso, dirige_il_primo):
    from models.user.models import DirectorAssignment
    from models.user.services import UserService

    primo = UserService.create_user(
        f"{prefisso}_a", f"{prefisso}_a@test.local", "pw12345"
    )
    secondo = UserService.create_user(
        f"{prefisso}_b", f"{prefisso}_b@test.local", "pw12345"
    )
    if dirige_il_primo:
        primo.role = UserRole.DIRECTOR.value
    gara = Gara(
        number=1,
        name=f"Gara {prefisso}",
        date=date.today(),
        discipline=Discipline.EIGHT_BALL.value,
        distance=4,
        is_race_to=False,  # esattamente 4 triangoli: il 2-2 esiste
        matchmaking_strategy="amalfi",
        status=GaraStatus.PLAYING.value,
        current_round=1,
        rounds_count=3,
        min_participants=2,
    )
    db_session.add(gara)
    db_session.commit()
    if dirige_il_primo:
        db_session.add(
            DirectorAssignment(
                user_id=primo.id,
                entity_type="gara",
                entity_id=gara.id,
                assigned_by_id=primo.id,
            )
        )
    partita = Match(
        gara_id=gara.id,
        round_number=1,
        player1_id=primo.id,
        player2_id=secondo.id,
        status=MatchStatus.PLAYING.value,
        player1_score=0,
        player2_score=0,
    )
    db_session.add(partita)
    db_session.commit()
    return primo, secondo, partita.id


def _segna_pari(client, match_id, primo, secondo):
    for vincitore in (primo, secondo, primo, secondo):
        r = client.post(
            f"/player/match/{match_id}/racks/add", data={"winner_id": vincitore.id}
        )
        assert r.status_code == 200, r.get_json()


def test_il_pareggio_segnato_dal_direttore_chiude_la_partita(client, db_session):
    primo, secondo, match_id = _gara_con_partita(db_session, "pari_dir", True)
    client.post("/auth/login", data={"username": primo.username, "password": "pw12345"})

    _segna_pari(client, match_id, primo, secondo)

    db_session.expire_all()
    partita = db_session.get(Match, match_id)
    assert (partita.player1_score, partita.player2_score) == (2, 2)
    assert MatchStatus.is_finished(partita.status)
    assert partita.winner_id is None


def test_il_pareggio_segnato_da_un_giocatore_aspetta_le_due_conferme(
    client, db_session
):
    primo, secondo, match_id = _gara_con_partita(db_session, "pari_gioc", False)
    client.post("/auth/login", data={"username": primo.username, "password": "pw12345"})

    _segna_pari(client, match_id, primo, secondo)

    db_session.expire_all()
    partita = db_session.get(Match, match_id)
    assert not MatchStatus.is_finished(partita.status)
    assert partita.is_ready_for_validation()
    assert not partita.player1_confirmed and not partita.player2_confirmed


def test_la_conferma_dal_segnapunti_torna_dove_porta_il_pulsante_indietro():
    """«Conferma» non manda fisso in dashboard: chi dirige torna alla gara."""
    sorgente = (
        Path(__file__).resolve().parents[3] / "templates" / "match_detail.html"
    ).read_text(encoding="utf-8")
    inizio = sorgente.index("function confirmResult(")
    corpo = sorgente[inizio : sorgente.index("function ", inizio + 10)]
    assert "'/dashboard'" not in corpo
    assert "match_head.back_url(match)" in corpo


def test_il_segnapunti_del_direttore_torna_alla_gara(client, db_session):
    primo, _secondo, match_id = _gara_con_partita(db_session, "pari_url", True)
    client.post("/auth/login", data={"username": primo.username, "password": "pw12345"})
    gara_id = db_session.get(Match, match_id).gara_id

    html = client.get(f"/admin/match/{match_id}").get_data(as_text=True)
    corpo = html[html.index("function confirmResult(") :]
    corpo = corpo[: corpo.index("function ", 10)]
    assert f'window.location.href = "/admin/gara/{gara_id}"' in corpo
