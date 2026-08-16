#!/usr/bin/env python3
"""Popola un database dimostrativo per le schermate del mini-sito di aiuto.

Le immagini di `docs/help/` non sono mockup: sono catturate dall'app vera
(`capture_screenshots.py`) su questo dataset. Averlo in uno script, e non in un
dump binario, e' cio' che rende le schermate rigenerabili quando l'interfaccia
cambia: si rilancia il seed, si ricattura, e le immagini tornano allineate.

Il dataset e' **deterministico** perche' due catture successive senza modifiche
all'app devono produrre immagini identiche: altrimenti ogni rigenerazione
sporcherebbe il diff con rumore e nessuno saprebbe piu' quali schermate sono
davvero cambiate. Deterministico significa tre cose: nomi e date scritti qui,
punteggi decisi dalla parita' dell'id del match, e **il generatore casuale
fissato** (`SEED`) — il sorteggio del primo turno e le strategie di
abbinamento pescano dal `random` globale, quindi senza fissarlo ogni
esecuzione produrrebbe accoppiamenti diversi e tutte le immagini cambierebbero.

Uso:
    python scripts/help_docs/seed_demo.py            # ricrea da zero
    python scripts/help_docs/seed_demo.py --keep     # non azzera il DB esistente

ATTENZIONE: senza `--keep` cancella il database di sviluppo indicato dalla
configurazione corrente. Non lanciarlo mai con `FLASK_ENV=production`.
"""

from __future__ import annotations

import argparse
import os
import random
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Il progetto si importa dalla radice del repo, non da scripts/.
sys.path.insert(0, str(REPO_ROOT))

# La lingua delle catture la imposta `capture_screenshots.py` sessione per
# sessione: qui serve solo un valore di partenza per i testi generati dal seed.
os.environ.setdefault("BABEL_DEFAULT_LOCALE", "it")


DEMO_PASSWORD = "demo1234"

# Seme del generatore casuale. Il valore non conta, conta che sia **fisso**:
# `RoundService.start_first_round` mescola gli iscritti con `random.shuffle` e
# le strategie di abbinamento pescano dallo stesso generatore. Senza questa
# riga ogni esecuzione del seed darebbe un tabellone diverso e la ricattura
# cambierebbe tutte le immagini anche a interfaccia identica.
SEED = 20260815

# Il direttore e i giocatori del dataset. L'ordine conta: `capture_screenshots`
# fa login per username, e i primi due giocatori sono quelli che compaiono nelle
# schermate del segnapunti.
DEMO_DIRECTOR = ("Luca Bianchi", "luca.bianchi@example.com")
DEMO_PLAYERS = [
    ("Marco Rossi", "marco.rossi@example.com", 1520),
    ("Giulia Conti", "giulia.conti@example.com", 1495),
    ("Andrea Ferri", "andrea.ferri@example.com", 1560),
    ("Sara Neri", "sara.neri@example.com", 1440),
    ("Paolo Greco", "paolo.greco@example.com", 1505),
    ("Elena Ricci", "elena.ricci@example.com", 1470),
    ("Davide Moro", "davide.moro@example.com", 1530),
    ("Chiara Fabbri", "chiara.fabbri@example.com", 1455),
]


def log(message: str) -> None:
    print(f"  · {message}")


def _reset_database(db) -> None:
    db.drop_all()
    db.create_all()


def _create_users(db):
    from models import User

    def make(username: str, email: str, role: str, elo: int | None = None) -> User:
        user = User.query.filter_by(username=username).first()
        if user:
            return user
        user = User(username=username, email=email, role=role)
        user.set_password(DEMO_PASSWORD)
        user.is_verified = True
        # L'onboarding e' obbligatorio al primo accesso (ADR-035): se non lo
        # segniamo fatto, ogni schermata catturata sarebbe la sua prima schermata.
        user.onboarding_completed = True
        if elo is not None:
            user.elo_rating = elo
        db.session.add(user)
        return user

    from models.user.role_enum import UserRole

    director = make(DEMO_DIRECTOR[0], DEMO_DIRECTOR[1], UserRole.DIRECTOR.value)
    players = [
        make(name, email, UserRole.PLAYER.value, elo)
        for name, email, elo in DEMO_PLAYERS
    ]
    db.session.commit()
    log(f"utenti: 1 direttore + {len(players)} giocatori")
    return director, players


def _create_venue(db, director):
    from models.location.models import BilliardHall

    venue = BilliardHall.query.filter_by(name="Biliardo Centrale").first()
    if venue:
        return venue
    venue = BilliardHall(
        name="Biliardo Centrale",
        address="Via Mercatovecchio 12",
        city="Udine",
        province="UD",
        postal_code="33100",
        phone="0432 123456",
        number_of_tables=4,
        is_active=True,
        verified=True,
        added_by_id=director.id,
    )
    venue.set_table_names(["1", "2", "3", "4"])
    venue.set_table_types(["9 piedi", "9 piedi", "8 piedi", "8 piedi"])
    db.session.add(venue)
    db.session.commit()
    log(f"sala: {venue.name} ({venue.number_of_tables} tavoli)")
    return venue


def _create_campionato(db, director, venue):
    from models.campionato.tournament_service import TournamentService

    service = TournamentService()
    campionato = service.create_campionato_with_director(
        name="Campionato Sociale 2026",
        creator_user_id=director.id,
        campionato_type="amalfi",
        planned_gare_count=6,
        default_venue_id=venue.id,
        default_entry_fee=10.0,
        default_rounds_count=3,
        default_classification_system="WINS",
    )
    db.session.commit()
    log(f"campionato: {campionato.name}")
    return campionato


def _create_gare(db, campionato, director, venue):
    """Tre gare in tre stati diversi: conclusa, in corso, iscrizioni aperte.

    Servono tutte e tre perche' l'aiuto spiega il ciclo di vita di una gara, e
    una schermata per stato e' l'unico modo di mostrarlo senza disegnarlo.
    """
    from models.competition.services import GaraService
    from models.status_enum import Discipline

    today = date.today()
    gare = []
    specs = [
        # (numero, nome, ora, disciplina, distanza, turni)
        (1, "1ª prova - Palla 8", time(18, 0), Discipline.EIGHT_BALL.value, 4, 3),
        (2, "2ª prova - Palla 9", time(20, 30), Discipline.NINE_BALL.value, 5, 3),
        (3, "3ª prova - Palla 8", time(20, 30), Discipline.EIGHT_BALL.value, 4, 3),
    ]
    for number, name, ora, discipline, distance, rounds_count in specs:
        gara = GaraService.create_gara(
            number=number,
            name=name,
            # Tutte create a oggi: `create_gara` rifiuta le date passate e le
            # iscrizioni si aprono solo su una finestra viva. Le prime due
            # vengono retrodatate a fine seed da `_backdate_gare`.
            date=today if number < 3 else today + timedelta(days=14),
            discipline=discipline,
            distance=distance,
            campionato_id=campionato.id,
            director_id=director.id,
            creator_id=director.id,
            time=ora,
            rounds_count=rounds_count,
            min_participants=4,
            entry_fee=10.0,
            billiard_hall_id=venue.id,
            location=venue.name,
            is_race_to=True,
            classification_system="WINS",
        )
        db.session.commit()
        gare.append(gara)
    log(f"gare: {len(gare)} nel campionato")
    return gare


def _backdate_gare(db, gare) -> None:
    """Sposta nel passato le gare gia' giocate.

    Si scrive sul modello, non tramite `GaraService.update_gara`: il servizio
    rifiuta le date passate (giustamente — nessun direttore vero programma una
    gara per ieri), ma un calendario dimostrativo in cui tutto accade oggi non
    mostrerebbe ne' lo storico ne' il prossimo appuntamento.
    """
    today = date.today()
    for gara, offset in zip(gare, (-21, -7)):
        gara.date = today + timedelta(days=offset)
        if gara.inscription_start:
            gara.inscription_start += timedelta(days=offset)
        if gara.inscription_end:
            gara.inscription_end += timedelta(days=offset)
    db.session.commit()
    log("gare 1 e 2 retrodatate (storico del campionato)")


def _open_and_fill(db, gara, players):
    from models.competition.inscription_service import InscriptionService

    now = datetime.now()
    InscriptionService.open_inscriptions(
        gara_id=gara.id,
        inscription_start=now - timedelta(days=14),
        inscription_end=datetime.combine(gara.date, time(17, 0)),
    )
    for player in players:
        InscriptionService.inscribe_user(user_id=player.id, gara_id=gara.id)
    db.session.commit()
    log(f"«{gara.name}»: {len(players)} iscritti")


def _play_rounds(db, gara, rounds: int, leave_open_for=None):
    """Gioca `rounds` turni assegnando punteggi deterministici.

    `leave_open_for` e' il giocatore la cui partita dell'ultimo turno resta a
    meta': serve alla schermata del segnapunti, che ha senso solo su una
    partita viva. Deve essere il giocatore dimostrativo principale, altrimenti
    le immagini "come segnare un rack" mostrerebbero una partita di qualcun
    altro, che l'app — giustamente — non lascerebbe toccare.
    """
    from models.competition.round_service import RoundService
    from models.match.models import Match
    from models.status_enum import MatchStatus

    RoundService.start_first_round(gara.id)
    db.session.commit()

    for round_number in range(1, rounds + 1):
        if round_number > 1:
            RoundService.create_round_with_strategy(
                gara_id=gara.id, round_number=round_number
            )
            db.session.commit()

        matches = (
            Match.query.filter_by(gara_id=gara.id, round_number=round_number)
            .order_by(Match.id)
            .all()
        )
        playable = [m for m in matches if not m.is_bye and not m.is_trio]
        for match in playable:
            in_last_round = round_number == rounds
            hosts_player = leave_open_for is not None and leave_open_for.id in (
                match.player1_id,
                match.player2_id,
            )
            _score_match(db, match, partial=in_last_round and hosts_player)
        db.session.commit()
        RoundService.update_round_progression(gara.id)
        db.session.commit()

    finished = sum(
        1
        for m in Match.query.filter_by(gara_id=gara.id).all()
        if MatchStatus.is_finished(m.status)
    )
    log(f"«{gara.name}»: {rounds} turni, {finished} partite concluse")


def _score_match(db, match, partial: bool = False) -> None:
    """Assegna rack alternando i vincitori, in modo riproducibile.

    Il vincitore lo decide la parita' dell'id del match, non un sorteggio: due
    esecuzioni del seed devono produrre lo stesso tabellone e le stesse
    classifiche, altrimenti ogni ricattura cambierebbe tutte le immagini.
    """
    from models.match.rack_service import RackService

    distance = match.distance_config
    target = (
        distance.get_winning_racks() if distance.is_race_to_racks else distance.racks
    )
    winner_first = match.id % 2 == 0
    winner_id = match.player1_id if winner_first else match.player2_id
    loser_id = match.player2_id if winner_first else match.player1_id
    if not winner_id or not loser_id:
        return

    loser_racks = max(0, target - 2)
    if partial:
        # Partita "in corso": si ferma un rack prima del traguardo, cosi' il
        # segnapunti in aiuto mostra una partita viva e non un risultato finale.
        winner_racks = max(1, target - 1)
        loser_racks = max(0, target - 2)
    else:
        winner_racks = target

    # Alternati, non "prima tutti quelli del vincitore": il tabellino della
    # partita compare nelle schermate e una fila di rack tutti uguali si
    # leggerebbe come un errore dell'app.
    sequence: list[int] = []
    for i in range(max(winner_racks, loser_racks)):
        if i < winner_racks:
            sequence.append(winner_id)
        if i < loser_racks:
            sequence.append(loser_id)
    for rack_winner in sequence:
        RackService.add_rack_with_score_update(
            match_id=match.id,
            winner_id=rack_winner,
            reported_by_id=rack_winner,
            validated_by_admin=True,
        )


def _create_challenges(db, director):
    """Due prove di abilita', una a punteggio e una superata/non superata.

    Servono entrambe perche' la guida spiega che le challenge si contano in due
    modi diversi, e un catalogo con un solo tipo non lo mostrerebbe. Le immagini
    sono quelle gia' presenti in `static/uploads/challenges/`: il seed non ne
    inventa di nuove.
    """
    from models.challenge.models import Challenge

    disponibili = sorted((REPO_ROOT / "static" / "uploads" / "challenges").glob("*.*"))
    if not disponibili:
        log("challenge non create: nessuna immagine in static/uploads/challenges/")
        return []

    specs = [
        (
            "Spot Shot Rally — dieci tiri dalla stessa posizione: la bilia "
            "bersaglio sul punto, la battente in mano. Un punto per ogni "
            "imbucata riuscita.",
            False,
        ),
        (
            "Serie da otto — imbuca otto bilie di fila senza sbagliare. "
            "Si passa o non si passa.",
            True,
        ),
    ]
    create = []
    for index, (description, pass_fail) in enumerate(specs):
        existing = Challenge.query.filter_by(description=description).first()
        if existing:
            create.append(existing)
            continue
        image = disponibili[index % len(disponibili)]
        challenge = Challenge(
            description=description,
            image_path=f"uploads/challenges/{image.name}",
            pass_fail_only=pass_fail,
            created_by_id=director.id,
            is_active=True,
        )
        db.session.add(challenge)
        create.append(challenge)
    db.session.commit()
    log(f"challenge: {len(create)} prove nel catalogo")
    return create


def _add_challenge_to_gara(db, gara, challenges) -> None:
    """Una prova di abilita' agganciata a un turno della gara.

    Serve alla pagina che spiega le challenge dentro una gara: senza un caso
    reale, quella pagina resterebbe l'unica senza schermate.
    """
    from models.competition.gara_challenge_service import GaraChallengeService

    if not challenges:
        return
    try:
        GaraChallengeService.add_challenge_to_gara(
            gara_id=gara.id,
            challenge_id=challenges[0].id,
            round_number=1,
            max_attempts=2,
            added_by_id=gara.director_id,
        )
        db.session.commit()
        log(f"«{gara.name}»: challenge agganciata al turno 1")
    except Exception as exc:  # pragma: no cover - il seed non deve bloccarsi
        log(f"challenge in gara non agganciata ({exc.__class__.__name__}: {exc})")


def _create_squadre(db, gara, players) -> None:
    """Squadre attive su una gara, con i compagni gia' assegnati.

    Le squadre si possono decidere solo mentre la gara e' in bozza o in
    iscrizione (ADR-039), quindi vanno su quella con le iscrizioni aperte.
    """
    from models.competition.models import Inscription
    from models.squadra.service import SquadraService

    gara.separate_teammates = True
    db.session.commit()

    try:
        squadre = [
            SquadraService.create(gara, name)
            for name in ("Biliardo Centrale", "CSB Udine")
        ]
        db.session.commit()
        for index, player in enumerate(players):
            inscription = Inscription.query.filter_by(
                gara_id=gara.id, user_id=player.id
            ).first()
            if inscription:
                SquadraService.set_inscription_squadra(
                    gara, inscription, squadre[index % len(squadre)].id
                )
        db.session.commit()
        log(f"«{gara.name}»: {len(squadre)} squadre con i compagni assegnati")
    except Exception as exc:  # pragma: no cover
        log(f"squadre non create ({exc.__class__.__name__}: {exc})")


def _create_gara_bozza(db, campionato, director, venue):
    """Una gara ancora in bozza, con un turno configurato a parte.

    Serve per due schermate che nelle altre gare non esistono: la gara prima
    dell'apertura delle iscrizioni, e la configurazione per turno — che l'app
    consente solo in bozza (ADR-027), quindi su una gara gia' aperta il
    pannello e' vuoto e non ci sarebbe niente da mostrare.
    """
    from models.competition.round_configuration import RoundConfiguration
    from models.competition.services import GaraService
    from models.status_enum import Discipline

    gara = GaraService.create_gara(
        number=4,
        name="4ª prova - Palla 10",
        date=date.today() + timedelta(days=28),
        discipline=Discipline.TEN_BALL.value,
        distance=4,
        campionato_id=campionato.id,
        director_id=director.id,
        creator_id=director.id,
        time=time(20, 30),
        rounds_count=3,
        min_participants=4,
        entry_fee=10.0,
        billiard_hall_id=venue.id,
        location=venue.name,
        is_race_to=True,
        classification_system="WINS",
    )
    db.session.commit()

    db.session.add(
        RoundConfiguration(
            gara_id=gara.id,
            round_number=3,
            discipline=Discipline.NINE_BALL.value,
            distance=5,
            is_race_to=True,
        )
    )
    db.session.commit()
    log(f"«{gara.name}»: in bozza, turno 3 configurato a parte (palla 9, al 5)")
    return gara


def _create_gara_tabellone(db, director, venue, players):
    """Una gara a eliminazione diretta, con il primo turno giocato.

    Il tabellone e' una schermata a se' e non esiste per le strategie a turni:
    senza una gara di questo tipo nel dataset, la pagina che lo spiega non
    potrebbe mostrarlo.
    """
    from models.competition.services import GaraService
    from models.status_enum import Discipline

    gara = GaraService.create_gara(
        number=1,
        name="Torneo di Primavera",
        date=date.today() + timedelta(days=7),
        discipline=Discipline.EIGHT_BALL.value,
        distance=4,
        director_id=director.id,
        creator_id=director.id,
        time=time(20, 0),
        min_participants=4,
        entry_fee=15.0,
        billiard_hall_id=venue.id,
        location=venue.name,
        is_race_to=True,
        classification_system="POSITION",
        matchmaking_strategy="direct_elimination",
        max_participants=8,
        third_place_match=True,
    )
    db.session.commit()

    _open_and_fill(db, gara, players)
    _play_rounds(db, gara, rounds=1)
    log(f"«{gara.name}»: tabellone a eliminazione diretta, primo turno giocato")
    return gara


def _create_individual_match(db, players):
    """Una partita casual conclusa + una proposta in attesa di risposta."""
    from models.individual_match.services import MatchProposalService
    from models.individual_match.proposal_models import ProposalType
    from models.status_enum import Discipline

    proposer, opponent = players[0], players[2]
    scheduled = datetime.combine(date.today() + timedelta(days=3), time(21, 0))
    try:
        proposal = MatchProposalService.create_proposal(
            proposer_id=proposer.id,
            proposal_type=ProposalType.DIRECT,
            location="Biliardo Centrale",
            scheduled_at=scheduled,
            expires_at=scheduled - timedelta(hours=6),
            discipline=Discipline.NINE_BALL.value,
            distance=5,
            is_race_to=True,
            description="Ci vediamo al Centrale per due partite?",
            invited_user_ids=[opponent.id],
        )
        db.session.commit()
        log(f"match individuale: proposta #{proposal.id} in attesa di risposta")
    except Exception as exc:  # pragma: no cover - il seed non deve bloccarsi qui
        log(f"match individuale non creato ({exc.__class__.__name__}: {exc})")


def _create_tpa_referto(db, players):
    """Un match singolo in corso con il referto TPA gia' avviato.

    Serve alle figure della guida: la pagina del referto ha senso solo con
    dentro qualche turno annotato, altrimenti si fotografa un foglio bianco.
    La sequenza sotto e' un primo rack verosimile — spaccata con una bilia,
    serie interrotta da un errore, difesa dell'avversario — e produce due TPA
    diversi, che e' esattamente cio' che la pagina deve far vedere.
    """
    from models.base import utc_now
    from models.individual_match.match_models import IndividualMatch
    from models.status_enum import Discipline, MatchStatus
    from models.tpa.services import TpaRefertoService

    compilatore, avversario = players[0], players[3]
    try:
        match = IndividualMatch(
            player1_id=compilatore.id,
            player2_id=avversario.id,
            location="Biliardo Centrale",
            scheduled_at=utc_now(),
            status=MatchStatus.IN_PROGRESS,
            discipline=Discipline.NINE_BALL.value,
            distance=5,
            is_race_to=True,
            started_at=utc_now(),
        )
        db.session.add(match)
        db.session.commit()

        referto = TpaRefertoService.open_referto(match.id, compilatore.id)
        for comando in ["1", "3", "M", "end", "2", "S", "end", "2"]:
            TpaRefertoService.press(referto.id, compilatore.id, comando)
        db.session.commit()
        log(f"referto TPA: match #{match.id}, referto #{referto.id}")
    except Exception as exc:  # pragma: no cover - il seed non deve bloccarsi qui
        log(f"referto TPA non creato ({exc.__class__.__name__}: {exc})")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--keep",
        action="store_true",
        help="non azzerare il database esistente (aggiunge solo cio' che manca)",
    )
    args = parser.parse_args()

    if os.environ.get("FLASK_ENV") == "production":
        print("RIFIUTO: seed dimostrativo con FLASK_ENV=production", file=sys.stderr)
        return 2

    from app import create_app
    from models import db

    random.seed(SEED)

    app = create_app("development")
    with app.app_context():
        print("Seed dimostrativo per il mini-sito di aiuto")
        if not args.keep:
            _reset_database(db)
            log("database azzerato e ricreato")
            from utils import create_admin_if_not_exists

            create_admin_if_not_exists()

        director, players = _create_users(db)
        venue = _create_venue(db, director)
        campionato = _create_campionato(db, director, venue)
        gara_conclusa, gara_in_corso, gara_iscrizioni = _create_gare(
            db, campionato, director, venue
        )

        _open_and_fill(db, gara_conclusa, players)
        _play_rounds(db, gara_conclusa, rounds=3)

        _open_and_fill(db, gara_in_corso, players)
        _play_rounds(db, gara_in_corso, rounds=2, leave_open_for=players[0])

        _open_and_fill(db, gara_iscrizioni, players[:5])

        _backdate_gare(db, [gara_conclusa, gara_in_corso])
        challenges = _create_challenges(db, director)
        _add_challenge_to_gara(db, gara_in_corso, challenges)
        _create_squadre(db, gara_iscrizioni, players[:5])
        _create_gara_bozza(db, campionato, director, venue)
        _create_gara_tabellone(db, director, venue, players)
        _create_individual_match(db, players)
        _create_tpa_referto(db, players)

        print("\nFatto. Credenziali dimostrative:")
        print(f"  direttore: {DEMO_DIRECTOR[0]} / {DEMO_PASSWORD}")
        print(f"  giocatore: {DEMO_PLAYERS[0][0]} / {DEMO_PASSWORD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
