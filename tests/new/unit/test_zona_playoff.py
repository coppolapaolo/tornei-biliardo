"""La zona playoff: chi verrebbe invitato, e chi lo e' davvero (canvas 7.1).

Si confrontano i due percorsi della classifica generale: le righe
`Classification` (da cui partono gli inviti) e `calculate_general_classification`
(la pagina). Una zona che segnasse i primi della pagina mentre gli inviti
partono dalle righe persistite direbbe al direttore una cosa falsa il giorno
in cui i due ordini divergono.
"""

from __future__ import annotations

import uuid
from datetime import date, time

from datetime import timedelta

from models.base import db, utc_now
from models.campionato.models import Campionato
from models.classification.models import Classification
from models.classification.campionato_classification import ClassificationService
from models.competition.models import Gara
from models.match.models import Match
from models.playoff.models import (
    PlayoffConfiguration,
    PlayoffQualification,
    PlayoffType,
    QualificationStatus,
)
from models.playoff.zona import zone_playoff
from models.status_enum import Discipline, GaraStatus, MatchStatus
from models.user.models import User


def _utente(db_session, prefisso):
    s = uuid.uuid4().hex[:8]
    u = User(
        username=f"{prefisso}_{s}", email=f"{prefisso}_{s}@test.com", role="player"
    )
    u.set_password("test1234")
    db_session.add(u)
    db_session.flush()
    return u


def _campionato_a_quattro(db_session, **cfg):
    """Due gare, quattro giocatori, ordine A > B > C > D."""
    from models.classification.gara_classification import RoundClassificationService

    camp = Campionato(
        name=f"Camp {uuid.uuid4().hex[:6]}",
        campionato_type="amalfi",
        is_active=True,
        planned_gare_count=2,
        default_rounds_count=1,
    )
    db_session.add(camp)
    db_session.flush()
    a, b, c, d = (_utente(db_session, n) for n in "abcd")
    for numero, giorno, coppie in (
        (1, 10, ((a, d), (b, c))),
        (2, 15, ((a, c), (b, d))),
    ):
        gara = Gara(
            campionato_id=camp.id,
            number=numero,
            name=f"Gara {numero}",
            date=date(2026, 1, giorno),
            time=time(18, 0),
            discipline=Discipline.NINE_BALL.value,
            distance=5,
            rounds_count=1,
            current_round=1,
            status=GaraStatus.COMPLETED.value,
        )
        db_session.add(gara)
        db_session.flush()
        for vince, perde in coppie:
            db_session.add(
                Match(
                    gara_id=gara.id,
                    round_number=1,
                    player1_id=vince.id,
                    player2_id=perde.id,
                    player1_score=5,
                    player2_score=0,
                    status=MatchStatus.CLOSED_UNILATERALLY.value,
                    winner_id=vince.id,
                )
            )
        db_session.flush()
        RoundClassificationService.calculate_and_save_round_classification(gara.id, 1)
    db_session.commit()
    ClassificationService.update_campionato_classification(camp.id)
    impostazioni = dict(
        max_participants=2, positions_from=1, positions_to=2, min_garas_played=0
    )
    impostazioni.update(cfg)
    cfg = PlayoffConfiguration(
        campionato_id=camp.id,
        name="Finale",
        playoff_type=PlayoffType.TOP_N,
        is_active=True,
        **impostazioni,
    )
    db_session.add(cfg)
    db_session.commit()
    return {"campionato": camp, "cfg": cfg, "a": a, "b": b, "c": c, "d": d}


def test_prima_degli_inviti_la_zona_e_chi_verrebbe_invitato(db_session):
    from models.campionato.tournament_service import TournamentService

    dati = _campionato_a_quattro(db_session)
    (zona,) = zone_playoff(dati["campionato"])

    assert not zona.inviti_partiti
    assert zona.posti == 2
    assert zona.user_ids == {dati["a"].id, dati["b"].id}

    # I due percorsi dicono la stessa cosa: i primi due della pagina sono
    # esattamente la zona calcolata dalle righe persistite.
    pagina = TournamentService().calculate_general_classification(dati["campionato"].id)
    primi_in_pagina = {riga["user_id"] for pos, riga in pagina[:2]}
    assert primi_in_pagina == zona.user_ids


def test_dopo_gli_inviti_chi_rifiuta_esce_e_chi_subentra_entra(db_session):
    dati = _campionato_a_quattro(db_session)
    for utente, stato, posizione in (
        (dati["a"], QualificationStatus.CONFIRMED, 1),
        (dati["b"], QualificationStatus.DECLINED, 2),
        (dati["c"], QualificationStatus.PENDING, 3),
    ):
        db_session.add(
            PlayoffQualification(
                configuration_id=dati["cfg"].id,
                user_id=utente.id,
                qualifying_position=posizione,
                qualification_reason="test",
                status=stato,
                invited_at=utc_now(),
            )
        )
    db.session.commit()

    (zona,) = zone_playoff(dati["campionato"])

    assert zona.inviti_partiti
    assert zona.user_ids == {dati["a"].id, dati["c"].id}


def test_senza_configurazioni_non_ci_sono_zone(db_session):
    camp = Campionato(name="Senza playoff", campionato_type="amalfi", is_active=True)
    db_session.add(camp)
    db_session.commit()
    assert zone_playoff(camp) == []


def _invito(dati, utente, stato, posizione, **campi):
    q = PlayoffQualification(
        configuration_id=dati["cfg"].id,
        user_id=utente.id,
        qualifying_position=posizione,
        qualification_reason="test",
        status=stato,
        **campi,
    )
    db.session.add(q)
    return q


def test_la_fascia_academy_segna_le_sue_posizioni_non_i_primi(db_session):
    """Rilievo della revisione automatica sulla PR #358: la fascia 3–4 non
    e' «i primi due»."""
    dati = _campionato_a_quattro(db_session, positions_from=3, positions_to=4)
    (zona,) = zone_playoff(dati["campionato"])
    assert zona.user_ids == {dati["c"].id, dati["d"].id}


def test_chi_non_ha_le_gare_minime_lascia_il_posto_a_chi_viene_dopo(db_session):
    """Come `start_playoff`: il posto rimasto si copre dopo la fascia."""
    dati = _campionato_a_quattro(db_session, min_garas_played=2)
    riga_b = Classification.query.filter_by(
        campionato_id=dati["campionato"].id, user_id=dati["b"].id
    ).one()
    riga_b.gare_played = 1
    db.session.commit()

    (zona,) = zone_playoff(dati["campionato"])

    assert zona.user_ids == {dati["a"].id, dati["c"].id}


def test_la_zona_e_start_playoff_scelgono_gli_stessi_giocatori(db_session):
    from models.playoff.services import PlayoffService

    dati = _campionato_a_quattro(db_session, positions_from=2, positions_to=3)
    righe = (
        Classification.query.filter_by(campionato_id=dati["campionato"].id)
        .order_by(Classification.position)
        .all()
    )
    (zona,) = zone_playoff(dati["campionato"])
    scelti = {
        u for u, _p, _m in PlayoffService.candidati_per_posizione(dati["cfg"], righe)
    }
    assert zona.user_ids == scelti == {dati["b"].id, dati["c"].id}


def test_un_invito_scaduto_non_e_nella_zona(db_session):
    """Rilievo della revisione automatica: la pagina pubblica non fa scadere
    gli inviti, quindi la scadenza si guarda nella zona."""
    dati = _campionato_a_quattro(db_session)
    adesso = utc_now()
    _invito(
        dati,
        dati["a"],
        QualificationStatus.PENDING,
        1,
        invited_at=adesso,
        expires_at=adesso - timedelta(days=1),
    )
    _invito(
        dati,
        dati["b"],
        QualificationStatus.PENDING,
        2,
        invited_at=adesso,
        expires_at=adesso + timedelta(days=3),
    )
    db.session.commit()

    (zona,) = zone_playoff(dati["campionato"])

    assert zona.inviti_partiti
    assert zona.user_ids == {dati["b"].id}


def test_qualificazioni_non_ancora_inviate_non_sono_inviti_partiti(db_session):
    """Rilievo della revisione automatica: le righe possono esistere prima
    della notifica, e allora vale ancora la classifica."""
    dati = _campionato_a_quattro(db_session)
    _invito(dati, dati["c"], QualificationStatus.PENDING, 3, invited_at=None)
    db.session.commit()

    (zona,) = zone_playoff(dati["campionato"])

    assert not zona.inviti_partiti
    assert zona.user_ids == {dati["a"].id, dati["b"].id}
