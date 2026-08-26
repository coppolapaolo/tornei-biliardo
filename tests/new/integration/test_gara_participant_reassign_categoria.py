# tests/new/integration/test_gara_participant_reassign_categoria.py
"""La categoria nello spostamento della partecipazione a una gara.

Riproduce il caso reale della «Garetta Esordienti Palla 7 "Sudden Death"»: una
gara **con handicap** in cui il direttore, rimasto in cinque, si è messo dentro
lui — categoria A, mentre gli esordienti erano tutti E. A gara iniziata è
arrivato il giocatore che mancava, ha giocato al posto suo, e la partecipazione
va spostata.

Il punto che questi test presidiano è che *spostare non basta*: l'iscrizione si
sposta intera, categoria compresa, quindi senza dirlo il nuovo arrivato eredita
la A del direttore. In una gara con handicap è la categoria a decidere quali
partite entrano nell'ELO (ADR-049), e con la categoria sbagliata la sua partita
resta esclusa esattamente come prima — riparazione fatta, difetto intatto.
"""

import uuid
from datetime import date, time, timedelta

import pytest

from models import db
from models.base import utc_now
from models.categoria.models import Categoria
from models.categoria.service import CategoriaService
from models.classification.gara_classification import (
    StrategyBasedClassificationService,
)
from models.competition.models import Gara, Inscription
from models.competition.participant_reassign_service import (
    GaraParticipantReassignService,
)
from models.match.models import Match
from models.rating.eligibility import RatingEligibility, RatingExclusion
from models.status_enum import Discipline, GaraStatus, MatchStatus
from models.user.models import User
from models.user.role_enum import UserRole


def _user(role="player", name=None):
    suffix = uuid.uuid4().hex[:8]
    user = User(
        username=name or f"{role}_{suffix}",
        email=f"{role}_{suffix}@example.com",
        role=UserRole.ADMIN.value if role == "admin" else role,
    )
    user.set_password("secret123")
    db.session.add(user)
    db.session.flush()
    return user


@pytest.fixture
def garetta(app, db_session):
    """Gara standalone con handicap: il direttore-giocatore è A, gli altri E."""
    admin = _user("admin")
    direttore = _user(role=UserRole.DIRECTOR.value, name=f"MAX_{uuid.uuid4().hex[:6]}")
    esordiente = _user(name=f"ROSA_{uuid.uuid4().hex[:6]}")
    arrivato_tardi = _user(name=f"LEO_{uuid.uuid4().hex[:6]}")

    gara = Gara(
        name='Garetta Esordienti "Sudden Death"',
        number=1,
        campionato_id=None,
        date=date.today() - timedelta(days=1),
        time=time(20, 0),
        discipline=Discipline.NINE_BALL.value,
        distance=5,
        is_race_to=False,  # esattamente 5 triangoli
        rounds_count=1,
        min_participants=2,
        max_participants=10,
        matchmaking_strategy="amalfi",
        director_id=direttore.id,
        has_handicap=True,
        status=GaraStatus.COMPLETED.value,
        current_round=1,
        inscription_start=utc_now() - timedelta(days=5),
        inscription_end=utc_now() - timedelta(days=2),
    )
    db.session.add(gara)
    db.session.flush()

    iscrizioni = {}
    for order, (user, categoria) in enumerate(
        ((direttore, "A"), (esordiente, "E")), start=1
    ):
        inscription = Inscription(gara_id=gara.id, user_id=user.id, initial_order=order)
        db.session.add(inscription)
        db.session.flush()
        CategoriaService.set_inscription_categoria_by_name(
            gara, inscription, categoria, force=True
        )
        iscrizioni[user.id] = inscription

    match = Match(
        gara_id=gara.id,
        round_number=1,
        player1_id=esordiente.id,
        player2_id=direttore.id,
        player1_score=3,
        player2_score=2,
        winner_id=esordiente.id,
        status=MatchStatus.CONFIRMED_BY_BOTH.value,
        ended_at=utc_now() - timedelta(days=1),
    )
    db.session.add(match)
    db.session.flush()

    classification = StrategyBasedClassificationService()
    classification.calculate_round_classification(gara.id, 1)
    classification.calculate_gara_classification(gara.id)
    db.session.commit()

    return {
        "admin": admin,
        "direttore": direttore,
        "esordiente": esordiente,
        "arrivato_tardi": arrivato_tardi,
        "gara": gara,
        "match": match,
    }


def _reassign(garetta, categoria=None):
    return GaraParticipantReassignService.reassign(
        gara_id=garetta["gara"].id,
        source_id=garetta["direttore"].id,
        target_id=garetta["arrivato_tardi"].id,
        performed_by_id=garetta["admin"].id,
        categoria=categoria,
    )


def _plan(garetta, categoria=None):
    return GaraParticipantReassignService.plan(
        gara_id=garetta["gara"].id,
        source_id=garetta["direttore"].id,
        target_id=garetta["arrivato_tardi"].id,
        performed_by_id=garetta["admin"].id,
        categoria=categoria,
    )


def _categoria_di(gara_id, user_id):
    inscription = Inscription.query.filter_by(gara_id=gara_id, user_id=user_id).first()
    return inscription.categoria.name if inscription.categoria else None


def test_la_partita_del_direttore_non_contava_per_l_elo(garetta):
    """Punto di partenza: A contro E, con handicap, non muove i rating."""
    motivo = RatingEligibility.exclusion_reason(garetta["match"])
    assert motivo is RatingExclusion.HANDICAP_DIFFERENT_CATEGORY


def test_senza_categoria_il_destinatario_eredita_quella_del_sorgente(garetta):
    """È il comportamento, non un difetto — ma è quasi mai quello voluto.

    L'iscrizione si sposta intera: chi arriva si ritrova la categoria di chi era
    iscritto per errore, e la partita resta esclusa dall'ELO esattamente come
    prima. Il test lo fissa perché è la ragione per cui `categoria` esiste.
    """
    gara_id = garetta["gara"].id
    arrivato_id = garetta["arrivato_tardi"].id
    match_id = garetta["match"].id

    _reassign(garetta)

    assert _categoria_di(gara_id, arrivato_id) == "A"
    match = db.session.get(Match, match_id)
    assert (
        RatingEligibility.exclusion_reason(match)
        is RatingExclusion.HANDICAP_DIFFERENT_CATEGORY
    )


def test_con_la_categoria_giusta_la_partita_entra_nell_elo(garetta):
    gara_id = garetta["gara"].id
    arrivato_id = garetta["arrivato_tardi"].id
    match_id = garetta["match"].id

    report = _reassign(garetta, categoria="E")

    assert _categoria_di(gara_id, arrivato_id) == "E"
    assert report["categoria"]["applied"]["touched"] == 1
    match = db.session.get(Match, match_id)
    assert RatingEligibility.exclusion_reason(match) is None


def test_la_categoria_si_scrive_prima_del_ricalcolo_dell_elo(garetta):
    """L'ordine dentro l'operazione, non solo lo stato finale.

    Scrivere la categoria *dopo* il replay dei rating lascerebbe lo stato
    finale identico — categoria giusta, iscrizione giusta — e l'ELO fermo,
    perché al momento del replay la partita risultava ancora fra categorie
    diverse. Nessuna asserzione sullo stato lo vedrebbe: lo vede solo la prova
    che la partita **ha prodotto** rating.
    """
    from models.rating.models import MatchRatingHistory

    match_id = garetta["match"].id
    assert MatchRatingHistory.query.filter_by(match_id=match_id).count() == 0

    _reassign(garetta, categoria="E")

    assert MatchRatingHistory.query.filter_by(match_id=match_id).count() > 0
    assert db.session.get(User, garetta["esordiente"].id).elo_rating is not None


def test_senza_categoria_giusta_l_elo_resta_fermo(garetta):
    """Il contrappunto: senza la categoria la partita non entra nel replay."""
    from models.rating.models import MatchRatingHistory

    match_id = garetta["match"].id

    _reassign(garetta)

    assert MatchRatingHistory.query.filter_by(match_id=match_id).count() == 0


def test_una_categoria_nuova_entra_in_elenco(garetta):
    gara_id = garetta["gara"].id

    _reassign(garetta, categoria="Esordienti")

    assert _categoria_di(gara_id, garetta["arrivato_tardi"].id) == "Esordienti"
    assert (
        Categoria.query.filter_by(gara_id=gara_id, normalized_name="esordienti").first()
        is not None
    )


def test_stringa_vuota_toglie_l_assegnazione(garetta):
    gara_id = garetta["gara"].id
    match_id = garetta["match"].id

    _reassign(garetta, categoria="")

    assert _categoria_di(gara_id, garetta["arrivato_tardi"].id) is None
    match = db.session.get(Match, match_id)
    assert (
        RatingEligibility.exclusion_reason(match)
        is RatingExclusion.HANDICAP_CATEGORY_MISSING
    )


def test_l_inventario_prevede_l_effetto_sull_elo_senza_scrivere(garetta):
    """`plan` deve dire *prima* quali partite cambiano idoneità.

    È l'effetto più importante dello spostamento e il meno visibile: senza
    questa riga lo si scopre a rating già rigiocato, cioè quando non si può
    più confrontarlo con il prima.
    """
    gara_id = garetta["gara"].id
    match_id = garetta["match"].id

    report = _plan(garetta, categoria="E")

    assert report["categoria"]["current"]["name"] == "A"
    assert report["categoria"]["target"] == {
        "id": Categoria.query.filter_by(gara_id=gara_id, normalized_name="e")
        .first()
        .id,
        "name": "E",
        "exists": True,
    }
    assert report["categoria"]["elo_effect"] == [
        {
            "match_id": match_id,
            "round_number": 1,
            "opponent": garetta["esordiente"].username,
            "before": RatingExclusion.HANDICAP_DIFFERENT_CATEGORY.value,
            "after": None,
        }
    ]

    # Sola lettura: la categoria del sorgente non si è mossa.
    assert _categoria_di(gara_id, garetta["direttore"].id) == "A"


def test_l_inventario_senza_categoria_non_promette_nessun_cambiamento(garetta):
    report = _plan(garetta)

    assert report["categoria"]["requested"] is None
    assert report["categoria"]["target"] is None
    assert report["categoria"]["elo_effect"] == []
