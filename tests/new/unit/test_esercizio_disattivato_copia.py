"""Disattivare un esercizio non deve svuotare la X di una gara in corso (#267).

Un esercizio si disattiva dal catalogo per dire «non proponetelo più»: è una
decisione sul catalogo, non sulle gare che l'hanno già scelto. Ma una gara che
deve ancora giocarsi resta con un esercizio che nessuno mantiene più, e il
direttore non se ne accorge finché qualcuno non riposa.

La risposta è una **copia attiva**: la gara continua a proporre esattamente la
stessa prova, e da quel momento dipende da una voce che vive nel catalogo dei
direttori invece che nel ricordo di una disattivata.

Due scelte che questo file fissa, perché nessuna delle due è ovvia:

**Una copia sola**, condivisa da tutte le gare interessate: è la stessa prova, e
moltiplicarla riempirebbe il catalogo di voci identiche e indistinguibili. Il
creatore è il direttore della prima gara in ordine di id — serve un proprietario
perché la voce sia manutenibile da qualcuno, e con gare di direttori diversi la
scelta è arbitraria per forza, ma dichiarata.

**Solo le gare non concluse.** Una gara finita non deve più proporre niente a
nessuno, e ripuntarla altrove riscriverebbe la configurazione con cui è stata
giocata — cioè un pezzo della sua storia.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest

from models.base import db
from models.challenge.models import Challenge
from models.challenge.services import ChallengeService
from models.competition.models import Gara
from models.status_enum import GaraStatus
from models.user.models import User
from models.user.role_enum import UserRole


def _direttore(db_session, prefisso="dir"):
    u = User(
        username=f"{prefisso}_{uuid.uuid4().hex[:8]}",
        email=f"{prefisso}_{uuid.uuid4().hex[:8]}@test.com",
        role=UserRole.DIRECTOR.value,
    )
    u.set_password("test1234")
    db_session.add(u)
    db_session.flush()
    return u


def _esercizio(db_session, creatore_id=None):
    c = Challenge(
        title=f"Spot Shot {uuid.uuid4().hex[:6]}",
        description="Descrizione della prova",
        image_path="test.jpg",
        pass_fail_only=False,
        is_active=True,
        created_by_id=creatore_id,
    )
    db_session.add(c)
    db_session.flush()
    return c


def _gara(db_session, direttore_id, esercizio_id, stato=GaraStatus.PLAYING.value):
    g = Gara(
        campionato_id=None,
        number=1,
        name=f"Gara {uuid.uuid4().hex[:6]}",
        date=date.today() + timedelta(days=7),
        discipline="9_ball",
        distance=5,
        rounds_count=3,
        min_participants=3,
        max_participants=8,
        matchmaking_strategy="amalfi",
        odd_number_policy="bye_with_challenge",
        status=stato,
        director_id=direttore_id,
        x_challenge_id=esercizio_id,
    )
    db_session.add(g)
    db_session.flush()
    return g


@pytest.mark.unit
def test_la_gara_in_corso_passa_a_una_copia_attiva(app, db_session):
    direttore = _direttore(db_session)
    originale = _esercizio(db_session)
    gara = _gara(db_session, direttore.id, originale.id)
    db_session.commit()

    ChallengeService.update_challenge(originale.id, is_active=False)
    db_session.commit()

    copia = db.session.get(Challenge, db.session.get(Gara, gara.id).x_challenge_id)
    assert copia.id != originale.id
    assert copia.is_active is True
    assert copia.created_by_id == direttore.id
    assert copia.description == originale.description


@pytest.mark.unit
def test_la_prova_resta_la_stessa(app, db_session):
    """La copia serve a non cambiare la prova, non a cambiarla."""
    direttore = _direttore(db_session)
    originale = _esercizio(db_session)
    originale.max_score = 9
    gara = _gara(db_session, direttore.id, originale.id)
    db_session.commit()

    ChallengeService.update_challenge(originale.id, is_active=False)
    db_session.commit()

    copia = db.session.get(Challenge, db.session.get(Gara, gara.id).x_challenge_id)
    assert copia.image_path == originale.image_path
    assert copia.pass_fail_only == originale.pass_fail_only
    assert copia.max_score == originale.max_score


@pytest.mark.unit
def test_una_copia_sola_per_tutte_le_gare(app, db_session):
    """Tre gare che usano lo stesso esercizio non fanno tre voci uguali."""
    direttore = _direttore(db_session)
    originale = _esercizio(db_session)
    gare = [_gara(db_session, direttore.id, originale.id) for _ in range(3)]
    db_session.commit()

    ChallengeService.update_challenge(originale.id, is_active=False)
    db_session.commit()

    puntano_a = {db.session.get(Gara, g.id).x_challenge_id for g in gare}
    assert len(puntano_a) == 1
    assert originale.id not in puntano_a


@pytest.mark.unit
def test_due_direttori_condividono_la_stessa_copia(app, db_session):
    """Una copia sola anche fra direttori diversi: è la stessa prova."""
    uno, due = _direttore(db_session, "a"), _direttore(db_session, "b")
    originale = _esercizio(db_session)
    gara_uno = _gara(db_session, uno.id, originale.id)
    gara_due = _gara(db_session, due.id, originale.id)
    db_session.commit()

    ChallengeService.update_challenge(originale.id, is_active=False)
    db_session.commit()

    copia_uno = db.session.get(Gara, gara_uno.id).x_challenge_id
    copia_due = db.session.get(Gara, gara_due.id).x_challenge_id
    assert copia_uno == copia_due
    # Il proprietario è il direttore della prima gara in ordine di id: serve un
    # proprietario, e con più direttori la scelta è arbitraria ma riproducibile.
    assert db.session.get(Challenge, copia_uno).created_by_id == uno.id


@pytest.mark.unit
def test_una_gara_conclusa_resta_sull_originale(app, db_session):
    """Ripuntarla riscriverebbe la configurazione con cui è stata giocata."""
    direttore = _direttore(db_session)
    originale = _esercizio(db_session)
    gara = _gara(
        db_session, direttore.id, originale.id, stato=GaraStatus.COMPLETED.value
    )
    db_session.commit()

    ChallengeService.update_challenge(originale.id, is_active=False)
    db_session.commit()

    assert db.session.get(Gara, gara.id).x_challenge_id == originale.id


@pytest.mark.unit
def test_riattivare_non_crea_niente(app, db_session):
    """Solo la disattivazione fa scattare la copia, non ogni salvataggio."""
    direttore = _direttore(db_session)
    originale = _esercizio(db_session)
    gara = _gara(db_session, direttore.id, originale.id)
    db_session.commit()
    quanti_prima = db.session.query(Challenge).count()

    ChallengeService.update_challenge(originale.id, description="Testo ritoccato")
    db_session.commit()

    assert db.session.query(Challenge).count() == quanti_prima
    assert db.session.get(Gara, gara.id).x_challenge_id == originale.id
