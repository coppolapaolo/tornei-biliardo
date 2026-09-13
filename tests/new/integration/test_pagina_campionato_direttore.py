"""La pagina del campionato per chi lo dirige (canvas 7.1–7.4).

In stagione: la fascia dice a che punto e' e offre «Nuova gara», le gare
sono righe, sul telefono tre linguette. In fase playoff: la fascia parla
degli inviti, gli invitati sono righe, su chi e' in attesa il direttore
risponde per conto del giocatore, chi ha rifiutato dice chi e' entrato al
suo posto e chi e' entrato dice al posto di chi.
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest

from models import Campionato
from models.base import utc_now
from models.classification.models import Classification
from models.competition.models import Gara, Inscription
from models.playoff.models import (
    PlayoffConfiguration,
    PlayoffQualification,
    PlayoffType,
    QualificationStatus,
)
from models.status_enum import Discipline, GaraStatus
from models.user.models import DirectorAssignment, User

pytestmark = pytest.mark.integration


def _uid():
    return uuid.uuid4().hex[:8]


def _utente(db_session, prefisso, role="player"):
    u = User(
        username=f"{prefisso}_{_uid()}", email=f"{prefisso}_{_uid()}@t.com", role=role
    )
    u.set_password("test1234")
    db_session.add(u)
    db_session.flush()
    return u


def _campionato(db_session, *, terminato):
    direttore = _utente(db_session, "dir", role="director")
    camp = Campionato(
        name=f"Camp {_uid()}",
        campionato_type="amalfi",
        is_active=True,
        planned_gare_count=6,
    )
    db_session.add(camp)
    db_session.flush()
    db_session.add(
        DirectorAssignment(
            entity_type="campionato",
            entity_id=camp.id,
            user_id=direttore.id,
            assigned_by_id=direttore.id,
        )
    )
    gara = Gara(
        campionato_id=camp.id,
        number=1,
        name="Gara 1",
        date=date(2026, 1, 15),
        discipline=Discipline.NINE_BALL.value,
        status=GaraStatus.COMPLETED.value,
        rounds_count=1,
        current_round=1,
        distance=5,
    )
    db_session.add(gara)
    db_session.flush()
    cfg = PlayoffConfiguration(
        campionato_id=camp.id,
        name="Finale",
        playoff_type=PlayoffType.TOP_N,
        max_participants=2,
        positions_from=1,
        positions_to=2,
        is_active=True,
    )
    db_session.add(cfg)
    db_session.flush()
    giocatori = []
    for i in range(3):
        p = _utente(db_session, f"g{i}")
        db_session.add(
            Classification(
                campionato_id=camp.id,
                user_id=p.id,
                position=i + 1,
                total_matches_won=10 - i,
                total_point_difference=20 - i,
                gare_played=5,
            )
        )
        db_session.add(Inscription(user_id=p.id, gara_id=gara.id))
        giocatori.append(p)
    if terminato:
        camp.terminated_at = utc_now()
    db_session.commit()
    return {
        "campionato": camp,
        "cfg": cfg,
        "direttore": direttore,
        "giocatori": giocatori,
    }


def _login(client, user):
    client.post(
        "/auth/login",
        data={"username": user.username, "password": "test1234"},
        follow_redirects=True,
    )


def test_in_stagione_la_fascia_offre_nuova_gara_e_le_gare_sono_righe(
    client, db_session
):
    dati = _campionato(db_session, terminato=False)
    _login(client, dati["direttore"])

    html = client.get(f"/admin/campionato/{dati['campionato'].id}").get_data(
        as_text=True
    )

    assert "Stagione in corso" in html
    assert "Gara 1 conclusa" in html
    assert 'data-help="campionato-nuova-gara"' in html
    assert "c7-cgara" in html
    # Tre linguette sul telefono: Classifica, Gare, Gestione.
    for vista in ("classifica", "gare", "gestione"):
        assert f'data-c7-tab-btn="{vista}"' in html
    assert 'aria-label="Viste del campionato"' in html


def test_in_fase_playoff_gli_invitati_dicono_chi_e_al_posto_di_chi(client, db_session):
    dati = _campionato(db_session, terminato=True)
    primo, secondo, terzo = dati["giocatori"]
    cfg = dati["cfg"]
    from models import db

    confermato = PlayoffQualification(
        configuration_id=cfg.id,
        user_id=primo.id,
        qualifying_position=1,
        qualification_reason="Posizione 1",
        status=QualificationStatus.CONFIRMED,
        invited_at=utc_now(),
    )
    rifiutato = PlayoffQualification(
        configuration_id=cfg.id,
        user_id=secondo.id,
        qualifying_position=2,
        qualification_reason="Posizione 2",
        status=QualificationStatus.DECLINED,
        invited_at=utc_now(),
        replaced_by_id=terzo.id,
        replacement_position=3,
    )
    sostituto = PlayoffQualification(
        configuration_id=cfg.id,
        user_id=terzo.id,
        qualifying_position=3,
        qualification_reason="Replacement - Top 2 position",
        status=QualificationStatus.PENDING,
        invited_at=utc_now(),
    )
    db.session.add_all([confermato, rifiutato, sostituto])
    db.session.commit()
    _login(client, dati["direttore"])

    html = client.get(f"/admin/campionato/{dati['campionato'].id}").get_data(
        as_text=True
    )

    assert "Fase playoff" in html and "Inviti in attesa" in html
    assert 'data-c7-tab-btn="playoff"' in html
    assert f"al suo posto {terzo.username}" in html
    assert f"invitato al posto di {secondo.username}" in html
    # Su chi e' in attesa si risponde per conto del giocatore.
    assert f'name="qualification_id" value="{sostituto.id}"' in html
    assert 'data-help="playoff-risposta-invito"' in html
    assert "Confermato" in html and "Rifiutato" in html
