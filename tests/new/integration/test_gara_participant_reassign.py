# tests/new/integration/test_gara_participant_reassign.py
"""Integration test: spostare la partecipazione a una gara fra due giocatori.

Riproduce il guasto reale: in un campionato di due gare il direttore iscrive
alla seconda l'omonimo sbagliato, e in classifica generale compaiono due
giocatori dove doveva essercene uno.

Verifica che dopo lo spostamento (a) i fatti siano attribuiti a chi ha giocato,
(b) le classifiche di gara e di campionato tornino a una riga sola, (c) gli XP
della gara cambino proprietario e (d) la simulazione non salvi niente.
"""

import json
import uuid
from datetime import date, time, timedelta

import pytest

from models import db
from models.base import utc_now
from models.campionato.models import Campionato
from models.classification.models import (
    Classification,
    GaraClassification,
    PlayerEncounter,
)
from models.classification.gara_classification import (
    StrategyBasedClassificationService,
)
from models.competition.models import Gara, Inscription
from models.competition.participant_reassign_service import (
    GaraParticipantReassignService,
)
from models.exceptions import ConflictError, ValidationError
from models.gamification.models import UserLevel, XPTransaction, XPTransactionType
from models.match.models import Match
from models.status_enum import GaraStatus, MatchStatus
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


def _campionato():
    campionato = Campionato(
        name=f"Campionato {uuid.uuid4().hex[:6]}",
        planned_gare_count=2,
        default_rounds_count=1,
    )
    db.session.add(campionato)
    db.session.flush()
    return campionato


def _gara(director_id, campionato_id, number, days_ago):
    gara = Gara(
        name=f"Gara {number}",
        number=number,
        campionato_id=campionato_id,
        date=date.today() - timedelta(days=days_ago),
        time=time(18, 0),
        discipline="8_ball",
        distance=5,
        rounds_count=1,
        min_participants=2,
        max_participants=10,
        matchmaking_strategy="random",
        director_id=director_id,
        status=GaraStatus.COMPLETED.value,
        current_round=1,
        inscription_start=utc_now() - timedelta(days=40),
        inscription_end=utc_now() - timedelta(days=35),
    )
    db.session.add(gara)
    db.session.flush()
    return gara


def _inscribe(gara, *users):
    for order, user in enumerate(users, start=1):
        db.session.add(
            Inscription(gara_id=gara.id, user_id=user.id, initial_order=order)
        )
    db.session.flush()


def _played(gara, winner, loser, ended_offset_days):
    match = Match(
        gara_id=gara.id,
        round_number=1,
        player1_id=winner.id,
        player2_id=loser.id,
        player1_score=5,
        player2_score=2,
        winner_id=winner.id,
        status=MatchStatus.CONFIRMED_BY_BOTH.value,
        ended_at=utc_now() - timedelta(days=ended_offset_days),
    )
    db.session.add(match)
    db.session.flush()
    return match


def _xp(user_id, amount, related):
    txn = XPTransaction(
        user_id=user_id,
        transaction_type=XPTransactionType.MATCH_WIN,
        xp_amount=amount,
        reason="test",
        level_before=1,
        level_after=1,
    )
    txn.related_entities = json.dumps(related)
    db.session.add(txn)
    db.session.flush()
    return txn


@pytest.fixture
def scenario(app, db_session):
    """Campionato di 2 gare: nella seconda è iscritto l'omonimo sbagliato."""
    admin = _user("admin")
    sbagliato = _user(name=f"LUIGI_{uuid.uuid4().hex[:6]}")
    giusto = _user(name=f"LUIGI_R_{uuid.uuid4().hex[:6]}")
    avversario = _user()

    campionato = _campionato()
    gara1 = _gara(admin.id, campionato.id, 1, days_ago=20)
    gara2 = _gara(admin.id, campionato.id, 2, days_ago=10)

    # Gara 1: gioca chi doveva giocare.
    _inscribe(gara1, giusto, avversario)
    _played(gara1, giusto, avversario, ended_offset_days=20)

    # Gara 2: il direttore iscrive l'omonimo sbagliato.
    _inscribe(gara2, sbagliato, avversario)
    match2 = _played(gara2, sbagliato, avversario, ended_offset_days=10)

    # Le classifiche di gara vanno calcolate come le calcola l'applicazione:
    # è da lì che la classifica generale si aggrega al volo, ed è lì che
    # comparivano i due omonimi.
    classification = StrategyBasedClassificationService()
    for gara in (gara1, gara2):
        classification.calculate_round_classification(gara.id, 1)
        classification.calculate_gara_classification(gara.id)

    db.session.commit()
    return {
        "admin": admin,
        "sbagliato": sbagliato,
        "giusto": giusto,
        "avversario": avversario,
        "campionato": campionato,
        "gara1": gara1,
        "gara2": gara2,
        "match2": match2,
    }


def _run(scenario):
    return GaraParticipantReassignService.reassign(
        gara_id=scenario["gara2"].id,
        source_id=scenario["sbagliato"].id,
        target_id=scenario["giusto"].id,
        performed_by_id=scenario["admin"].id,
    )


def _plan(scenario):
    return GaraParticipantReassignService.plan(
        gara_id=scenario["gara2"].id,
        source_id=scenario["sbagliato"].id,
        target_id=scenario["giusto"].id,
        performed_by_id=scenario["admin"].id,
    )


def test_sposta_iscrizione_e_partita(scenario, db_session):
    gara2_id = scenario["gara2"].id
    match2_id = scenario["match2"].id
    sbagliato_id = scenario["sbagliato"].id
    giusto_id = scenario["giusto"].id

    _run(scenario)

    assert (
        Inscription.query.filter_by(gara_id=gara2_id, user_id=sbagliato_id).first()
        is None
    )
    assert (
        Inscription.query.filter_by(gara_id=gara2_id, user_id=giusto_id).first()
        is not None
    )

    match = db_session.get(Match, match2_id)
    assert match.player1_id == giusto_id
    assert match.winner_id == giusto_id


def test_classifica_campionato_torna_a_una_riga(scenario, db_session):
    """Il sintomo che ha fatto scoprire il guasto: due omonimi in classifica.

    Si verifica sulla classifica **che l'utente guarda**, calcolata al volo da
    `calculate_general_classification` aggregando le classifiche di gara — non
    sulla tabella `classification`, che l'applicazione scrive solo alla chiusura
    del campionato o all'avvio dei playoff.
    """
    from models.campionato.statistics_service import TournamentStatisticsService

    campionato_id = scenario["campionato"].id
    # La vista identifica i giocatori per `username`: è la stessa chiave con cui
    # l'errore si è manifestato, «due Luigi in classifica».
    sbagliato = db_session.get(User, scenario["sbagliato"].id).username
    giusto = db_session.get(User, scenario["giusto"].id).username

    statistiche = TournamentStatisticsService()
    presenti_prima = {
        dati["username"]
        for _, dati in statistiche.calculate_general_classification(campionato_id)
    }
    assert {sbagliato, giusto} <= presenti_prima, (
        "lo scenario non riproduce il guasto: i due omonimi devono comparire "
        "entrambi prima della correzione"
    )

    _run(scenario)

    presenti_dopo = {
        dati["username"]: dati
        for _, dati in statistiche.calculate_general_classification(campionato_id)
    }
    assert sbagliato not in presenti_dopo, "l'omonimo sbagliato è ancora in classifica"
    assert presenti_dopo[giusto]["participations"] == 2


def test_classifica_di_gara_attribuita_al_giocatore_giusto(scenario, db_session):
    gara2_id = scenario["gara2"].id
    sbagliato_id = scenario["sbagliato"].id
    giusto_id = scenario["giusto"].id

    _run(scenario)

    utenti = {
        row.user_id
        for row in GaraClassification.query.filter_by(gara_id=gara2_id).all()
    }
    assert sbagliato_id not in utenti
    assert giusto_id in utenti


def test_xp_della_gara_cambiano_proprietario(scenario, db_session):
    """Il registro XP è la fonte del livello: i movimenti vanno riattribuiti."""
    sbagliato_id = scenario["sbagliato"].id
    giusto_id = scenario["giusto"].id
    gara2_id = scenario["gara2"].id
    match2_id = scenario["match2"].id

    # XP dell'omonimo sbagliato: uno legato alla gara, uno a una partita di
    # quella gara, uno estraneo che NON deve muoversi.
    legato_gara = _xp(sbagliato_id, 50, {"gara_id": gara2_id})
    legato_match = _xp(sbagliato_id, 30, {"match_id": match2_id})
    estraneo = _xp(sbagliato_id, 70, {"individual_match_id": 999})
    db.session.commit()

    _run(scenario)

    assert db_session.get(XPTransaction, legato_gara.id).user_id == giusto_id
    assert db_session.get(XPTransaction, legato_match.id).user_id == giusto_id
    assert db_session.get(XPTransaction, estraneo.id).user_id == sbagliato_id

    # Il livello si ricostruisce sommando il registro, non spostando il totale.
    assert db_session.get(UserLevel, sbagliato_id).total_xp == 70
    assert db_session.get(UserLevel, giusto_id).total_xp == 80


def test_incontri_anti_rivincita_rigenerati(scenario, db_session):
    """Gli incontri portano l'ordinamento p1<p2 nella riga: si rigenerano."""
    gara2_id = scenario["gara2"].id
    sbagliato_id = scenario["sbagliato"].id
    giusto_id = scenario["giusto"].id

    _run(scenario)

    incontri = PlayerEncounter.query.filter_by(gara_id=gara2_id).all()
    coinvolti = {p for e in incontri for p in (e.player1_id, e.player2_id)}
    assert sbagliato_id not in coinvolti
    assert giusto_id in coinvolti
    for encounter in incontri:
        assert encounter.player1_id < encounter.player2_id


def test_inventario_non_scrive_niente(scenario, db_session):
    """`plan` deve dire cosa si muoverebbe senza muovere niente.

    È l'unica prova a costo zero disponibile: la prova *generale* si fa su una
    copia del file .db, perché un `@transactional` annidato committa la
    transazione esterna e un rollback finale non annullerebbe i ricalcoli.
    """
    gara2_id = scenario["gara2"].id
    sbagliato_id = scenario["sbagliato"].id
    match2_id = scenario["match2"].id

    report = _plan(scenario)

    assert report["read_only"] is True
    assert report["moved_rows"]["inscription.user_id"] == 1
    assert report["moved_rows"]["match.player1_id"] == 1
    assert report["moved_rows"]["match.winner_id"] == 1

    db.session.expire_all()
    assert (
        Inscription.query.filter_by(gara_id=gara2_id, user_id=sbagliato_id).first()
        is not None
    ), "l'inventario ha scritto sul database"
    assert db_session.get(Match, match2_id).player1_id == sbagliato_id


def test_inventario_solleva_sugli_stessi_conflitti(scenario, db_session):
    """L'inventario non è un giro a vuoto: valida come l'esecuzione."""
    _inscribe(scenario["gara2"], scenario["giusto"])
    db.session.commit()

    with pytest.raises(ConflictError):
        _plan(scenario)


def test_rifiuta_destinatario_gia_nella_gara(scenario, db_session):
    """Chi ha già giocato la gara diventerebbe avversario di sé stesso."""
    _inscribe(scenario["gara2"], scenario["giusto"])
    db.session.commit()

    with pytest.raises(ConflictError):
        _run(scenario)


def test_rifiuta_sorgente_non_iscritto(scenario, db_session):
    estraneo = _user()
    db.session.commit()

    with pytest.raises(ValidationError):
        GaraParticipantReassignService.reassign(
            gara_id=scenario["gara2"].id,
            source_id=estraneo.id,
            target_id=scenario["giusto"].id,
            performed_by_id=scenario["admin"].id,
        )


def test_rifiuta_esecutore_non_admin(scenario, db_session):
    with pytest.raises(ValidationError):
        GaraParticipantReassignService.reassign(
            gara_id=scenario["gara2"].id,
            source_id=scenario["sbagliato"].id,
            target_id=scenario["giusto"].id,
            performed_by_id=scenario["avversario"].id,
        )


def test_traguardo_non_piu_meritato_viene_tolto(scenario, db_session):
    """Chi non ha più partecipato a nessuna gara non tiene il badge di debutto.

    Lo sblocco degli achievement è monotòno per scelta di dominio: la sola
    ricostruzione non toglie mai niente. Qui serve la revoca esplicita, e la
    revoca è a sua volta un *ricalcolo* — se il requisito regge per altre vie,
    il traguardo resta.
    """
    from models.gamification.models import (
        Achievement,
        AchievementCategory,
        AchievementDifficulty,
        UserAchievement,
    )

    sbagliato_id = scenario["sbagliato"].id
    giusto_id = scenario["giusto"].id

    debutto = Achievement(
        slug="tournament_debut",
        name="Debutto Torneo",
        description="Partecipa al tuo primo torneo",
        category=AchievementCategory.TOURNAMENT,
        difficulty=AchievementDifficulty.COMMON,
        requirements='{"type": "tournament_participation", "count": 1}',
        xp_reward=100,
        is_active=True,
    )
    db.session.add(debutto)
    db.session.flush()
    db.session.add(
        UserAchievement(
            user_id=sbagliato_id,
            achievement_id=debutto.id,
            current_progress=1,
            is_unlocked=True,
            unlocked_at=utc_now(),
        )
    )
    db.session.commit()

    report = _run(scenario)

    assert "tournament_debut" in report["gamification"]["source_revoked_achievements"]
    tolto = UserAchievement.query.filter_by(
        user_id=sbagliato_id, achievement_id=debutto.id
    ).first()
    assert tolto.is_unlocked is False

    # Chi ha davvero giocato lo ottiene al posto suo.
    assegnato = UserAchievement.query.filter_by(
        user_id=giusto_id, achievement_id=debutto.id
    ).first()
    assert assegnato is not None and assegnato.is_unlocked is True


def test_non_popola_una_classifica_di_campionato_mai_scritta(scenario, db_session):
    """Una tabella vuota di proposito resta vuota.

    L'applicazione persiste la classifica generale solo in momenti precisi
    (chiusura campionato, avvio playoff, correzione manuale di un risultato).
    Finché non arrivano, `AmalfiStrategy._seeding_order` accoppia a caso
    *perché* non trova righe: popolarle qui cambierebbe il sorteggio della
    prossima gara. La schermata dell'utente non le legge — aggrega al volo le
    classifiche di gara, che lo spostamento ha già corretto.
    """
    campionato_id = scenario["campionato"].id
    assert Classification.query.filter_by(campionato_id=campionato_id).count() == 0

    _run(scenario)

    assert (
        Classification.query.filter_by(campionato_id=campionato_id).count() == 0
    ), "lo spostamento ha popolato una classifica che non era mai stata scritta"


def test_rinfresca_una_classifica_di_campionato_esistente(scenario, db_session):
    """Una riga che c'è va aggiornata: stantia sarebbe peggio che assente."""
    campionato_id = scenario["campionato"].id
    sbagliato_id = scenario["sbagliato"].id
    giusto_id = scenario["giusto"].id

    # Lo stato che l'utente vedeva: due giocatori dove doveva essercene uno.
    for position, user_id in ((1, giusto_id), (2, sbagliato_id)):
        db.session.add(
            Classification(
                campionato_id=campionato_id,
                user_id=user_id,
                position=position,
                gare_played=1,
                total_matches_won=1,
            )
        )
    db.session.commit()

    _run(scenario)

    righe = {
        row.user_id: row
        for row in Classification.query.filter_by(campionato_id=campionato_id).all()
    }
    assert sbagliato_id not in righe, "la riga stantia è rimasta"
    assert righe[giusto_id].gare_played == 2


def test_sposta_anche_le_partite_a_trio(scenario, db_session):
    """Il triangolo non e' un caso di scuola: e' come la gara 35 ha giocato.

    Con un numero dispari di iscritti la politica crea una partita a tre, e
    quella partecipazione vive in `trio_match`/`trio_rack` — otto colonne utente
    fra le due, non solo `player1_id`. Restare indietro su una sola lascerebbe
    il triangolo con due identita' diverse per la stessa persona, e gli incontri
    anti-rivincita si rigenererebbero attorno a quella sbagliata.
    """
    from models.match.models import TrioMatch, TrioRack

    gara2 = scenario["gara2"]
    sbagliato_id = scenario["sbagliato"].id
    giusto_id = scenario["giusto"].id
    terzo = _user()
    quarto = _user()
    _inscribe(gara2, terzo, quarto)

    partita = Match(
        gara_id=gara2.id,
        round_number=1,
        player1_id=sbagliato_id,
        player2_id=terzo.id,
        is_trio=True,
        status=MatchStatus.CONFIRMED_BY_BOTH.value,
        ended_at=utc_now() - timedelta(days=10),
    )
    db.session.add(partita)
    db.session.flush()

    trio = TrioMatch(
        match_id=partita.id,
        player1_id=sbagliato_id,
        player2_id=terzo.id,
        player3_id=quarto.id,
        current_player1_id=sbagliato_id,
        current_player2_id=terzo.id,
        waiting_player_id=quarto.id,
        winner_id=terzo.id,
        is_completed=True,
    )
    db.session.add(trio)
    db.session.flush()
    db.session.add(
        TrioRack(
            trio_match_id=trio.id,
            rack_number=1,
            winner_id=terzo.id,
            player1_id=sbagliato_id,
            player2_id=terzo.id,
            waiting_player_id=quarto.id,
            added_by_id=sbagliato_id,
        )
    )
    db.session.commit()
    trio_id, rack_id, partita_id = trio.id, TrioRack.query.first().id, partita.id

    _run(scenario)

    trio = db_session.get(TrioMatch, trio_id)
    assert trio.player1_id == giusto_id
    assert trio.current_player1_id == giusto_id
    assert trio.player2_id == terzo.id, "gli altri due non si devono muovere"
    assert trio.player3_id == quarto.id

    rack = db_session.get(TrioRack, rack_id)
    assert rack.player1_id == giusto_id
    assert rack.added_by_id == giusto_id
    assert rack.waiting_player_id == quarto.id

    # La partita che fa da contenitore e il triangolo devono raccontare la
    # stessa persona: e' la coerenza che gli incontri anti-rivincita leggono.
    assert db_session.get(Match, partita_id).player1_id == trio.player1_id

    incontri = PlayerEncounter.query.filter_by(gara_id=gara2.id).all()
    coppie = {(e.player1_id, e.player2_id) for e in incontri}
    assert sbagliato_id not in {p for c in coppie for p in c}
    for atteso in (
        (giusto_id, terzo.id),
        (giusto_id, quarto.id),
        (terzo.id, quarto.id),
    ):
        ordinata = (min(atteso), max(atteso))
        assert ordinata in coppie, f"manca l'incontro {ordinata} del triangolo"
