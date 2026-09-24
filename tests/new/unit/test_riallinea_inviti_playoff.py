"""Riallineare gli inviti ai playoff partiti da una classifica sbagliata.

Il caso è quello del campionato 5 (24/09/2026): la pagina diceva A > B > C > D,
gli inviti per due posti sono andati ad A e C. Dopo il riallineamento C ha un
invito ritirato con B al suo posto, B ha un invito normale, e ognuno dei due
ha ricevuto l'avviso giusto.
"""

from __future__ import annotations

import uuid
from datetime import date, time, timedelta

import pytest

from models.base import utc_now
from models.campionato.models import Campionato
from models.competition.models import Gara
from models.exceptions import ConflictError
from models.match.models import Match
from models.notification.models import Notification, NotificationType
from models.playoff import riallineamento
from models.playoff.models import (
    PlayoffConfiguration,
    PlayoffQualification,
    PlayoffType,
    QualificationStatus,
)
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


@pytest.fixture
def dati(db_session):
    """Due gare, A > B > C > D in pagina, due posti; invitati A e C."""
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

    scadenza = utc_now() + timedelta(days=7)
    cfg = PlayoffConfiguration(
        campionato_id=camp.id,
        name="Finale",
        playoff_type=PlayoffType.TOP_N,
        is_active=True,
        max_participants=2,
        positions_from=1,
        positions_to=2,
        min_garas_played=0,
        response_deadline=scadenza,
    )
    db_session.add(cfg)
    db_session.flush()
    quals = {}
    for utente, posizione in ((a, 1), (c, 2)):
        q = PlayoffQualification(
            configuration_id=cfg.id,
            user_id=utente.id,
            qualifying_position=posizione,
            qualification_reason=f"Posizione {posizione} in classifica",
            invited_at=utc_now(),
            expires_at=scadenza,
        )
        db_session.add(q)
        db_session.flush()
        quals[utente.id] = q
        avviso = Notification(
            user_id=utente.id,
            notification_type=NotificationType.PLAYOFF_INVITATION,
            title="Invito Playoff — Finale",
            message="Sei stato qualificato",
        )
        avviso.set_related_entities({"qualification_id": q.id})
        db_session.add(avviso)
    db_session.commit()
    return {"cfg": cfg, "a": a, "b": b, "c": c, "d": d, "quals": quals}


def _qualifica(cfg, utente):
    return PlayoffQualification.query.filter_by(
        configuration_id=cfg.id, user_id=utente.id
    ).one_or_none()


def test_il_piano_dice_chi_esce_e_chi_entra_senza_scrivere(dati, db_session):
    piano = riallineamento.pianifica(dati["cfg"].id)

    assert [r.user_id for r in piano.da_ritirare] == [dati["c"].id]
    assert [i.user_id for i in piano.da_invitare] == [dati["b"].id]
    assert piano.da_ritirare[0].al_suo_posto == dati["b"].username
    assert _qualifica(dati["cfg"], dati["b"]) is None
    assert _qualifica(dati["cfg"], dati["c"]).status == QualificationStatus.PENDING


def test_eseguito_ritira_c_e_invita_b(dati, db_session):
    riallineamento.esegui(dati["cfg"].id)

    ritirata = _qualifica(dati["cfg"], dati["c"])
    assert ritirata.status == QualificationStatus.REPLACED
    assert ritirata.replaced_by_id == dati["b"].id

    nuova = _qualifica(dati["cfg"], dati["b"])
    assert nuova.status == QualificationStatus.PENDING
    assert nuova.qualifying_position == 2
    assert nuova.invited_at is not None
    assert nuova.expires_at == dati["cfg"].response_deadline

    assert _qualifica(dati["cfg"], dati["a"]).status == QualificationStatus.PENDING


def test_gli_avvisi_arrivano_a_chi_entra_e_a_chi_esce(dati, db_session):
    vecchio_di_c = Notification.query.filter_by(user_id=dati["c"].id).one()

    riallineamento.esegui(dati["cfg"].id)

    ritirata = _qualifica(dati["cfg"], dati["c"])
    avvisi_c = Notification.query.filter_by(user_id=dati["c"].id).all()
    assert len(avvisi_c) == 2
    assert db_session.get(Notification, vecchio_di_c.id).expires_at is not None
    nuovo_di_c = next(n for n in avvisi_c if n.id != vecchio_di_c.id)
    assert nuovo_di_c.action_url.endswith(f"/{ritirata.id}")

    nuova = _qualifica(dati["cfg"], dati["b"])
    (invito_b,) = Notification.query.filter_by(user_id=dati["b"].id).all()
    assert invito_b.get_related_entities()["qualification_id"] == nuova.id


def test_rieseguito_non_fa_niente(dati, db_session):
    riallineamento.esegui(dati["cfg"].id)

    assert riallineamento.pianifica(dati["cfg"].id).niente_da_fare


def test_chi_ha_rifiutato_resta_fuori_e_il_posto_va_al_primo_degli_esclusi(
    dati, db_session
):
    """B aveva l'invito e ha rifiutato: il suo posto era già di C."""
    db_session.add(
        PlayoffQualification(
            configuration_id=dati["cfg"].id,
            user_id=dati["b"].id,
            qualifying_position=2,
            qualification_reason="Posizione 2 in classifica",
            invited_at=utc_now(),
            status=QualificationStatus.DECLINED,
        )
    )
    db_session.commit()

    assert riallineamento.pianifica(dati["cfg"].id).niente_da_fare


def test_chi_e_stato_aggiunto_a_mano_resta(dati, db_session):
    db_session.add(
        PlayoffQualification(
            configuration_id=dati["cfg"].id,
            user_id=dati["d"].id,
            qualifying_position=4,
            qualification_reason="Aggiunto manualmente da admin",
            status=QualificationStatus.CONFIRMED,
            invited_at=utc_now(),
        )
    )
    db_session.commit()

    piano = riallineamento.pianifica(dati["cfg"].id)

    assert dati["d"].id not in {r.user_id for r in piano.da_ritirare}


def test_a_gara_di_playoff_cominciata_non_si_tocca_niente(dati, db_session):
    gara = Gara(
        name="Finale",
        number=3,
        date=date(2026, 1, 20),
        time=time(18, 0),
        campionato_id=dati["cfg"].campionato_id,
        playoff_config_id=dati["cfg"].id,
        discipline=Discipline.NINE_BALL.value,
        distance=5,
        rounds_count=1,
        current_round=1,
        status=GaraStatus.PLAYING.value,
    )
    db_session.add(gara)
    db_session.commit()

    with pytest.raises(ConflictError):
        riallineamento.pianifica(dati["cfg"].id)


def test_prima_dell_avvio_non_c_e_niente_da_riallineare(dati, db_session):
    for q in dati["quals"].values():
        q.invited_at = None
    db_session.commit()

    with pytest.raises(ConflictError):
        riallineamento.pianifica(dati["cfg"].id)
