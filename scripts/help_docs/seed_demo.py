#!/usr/bin/env python3
"""Popola un database dimostrativo per le schermate del mini-sito di aiuto.

Le immagini di `docs/help/` non sono mockup: sono catturate dall'app vera
(`capture_screenshots.py`) su questo dataset. Averlo in uno script, e non in un
dump binario, e' cio' che rende le schermate rigenerabili quando l'interfaccia
cambia: si rilancia il seed, si ricattura, e le immagini tornano allineate.

Il dataset e' **deterministico** perche' due catture successive senza modifiche
all'app devono produrre immagini identiche: altrimenti ogni rigenerazione
sporcherebbe il diff con rumore e nessuno saprebbe piu' quali schermate sono
davvero cambiate. Deterministico significa quattro cose: nomi e date scritti
qui, punteggi decisi dalla parita' dell'id del match, **il generatore casuale
fissato** (`SEED`) — l'ordine di partenza e le strategie a turni pescano dal
`random` globale — e **il seme del sorteggio fissato** su ogni gara prima di
avviarla (`_avvia_primo_turno`): l'app lo sceglie con `secrets`, e il
tabellone ne ricava gli accoppiamenti.

Resta una cosa che il seed non puo' fissare: le date sono relative a oggi,
perche' l'app rifiuta gare nel passato e iscrizioni fuori finestra. Due
catture fatte in giorni diversi cambiano quindi le immagini che mostrano una
data; due catture nello stesso giorno danno le stesse immagini.

Uso:
    python scripts/help_docs/seed_demo.py            # ricrea da zero
    python scripts/help_docs/seed_demo.py --keep     # non azzera il DB esistente

ATTENZIONE: senza `--keep` cancella il database di sviluppo indicato dalla
configurazione corrente. Non lanciarlo mai con `FLASK_ENV=production`.
"""

from __future__ import annotations

import argparse
import json
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
# le strategie a turni pescano dallo stesso generatore. Non basta da solo: il
# seme del sorteggio della gara nasce da `secrets`, e lo fissa
# `_avvia_primo_turno`. Senza uno dei due ogni esecuzione darebbe abbinamenti
# diversi e la ricattura cambierebbe immagini a interfaccia identica
# (presidio: `tests/new/integration/test_help_seed_riproducibile.py`).
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
        # Con gli esercizi accesi l'esercizio agganciato alla gara in corso
        # compare davvero fra i turni: spento, la guida non aveva la schermata.
        challenge_mode=True,
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
            # Tutte create nel futuro: `create_gara` rifiuta le date passate e
            # le iscrizioni si aprono solo su una finestra viva. Le prime due
            # vengono retrodatate a fine seed da `_backdate_gare`.
            #
            # Perche' domani e non oggi: `open_inscriptions` taglia la fine
            # delle iscrizioni alla data della gara, e `inscribe_user` la
            # confronta con `utc_now()`. Con le gare a oggi la finestra si
            # chiudeva alle 17:00 UTC, e il seed lanciato di sera moriva su
            # «Iscrizioni chiuse» — cioe' le schermate della guida non erano
            # piu' rigenerabili fino al mattino dopo. Le date definitive le
            # riscrive comunque `_backdate_gare`, quindi il dataset visibile
            # non cambia.
            date=today + timedelta(days=1 if number < 3 else 14),
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

    # La gara con le iscrizioni aperte riceve un indirizzo leggibile fisso
    # (issue #235): la sua vetrina finisce nella guida, e il manifest delle
    # schermate ha bisogno di un percorso stabile — il token, generato con
    # `secrets`, cambia a ogni seed e non si potrebbe scrivere lì.
    gare[-1].slug = "terza-prova-palla-8"
    # La gara in corso ha lo schermo in sala nella guida (canvas 3.10), che
    # sta sullo stesso indirizzo della vetrina: stessa ragione, slug fisso.
    gare[1].slug = "seconda-prova-palla-9"
    # Stessa ragione per il campionato, che dal secondo lotto ha una vetrina
    # sua: anche il suo token nasce da `secrets` e cambierebbe a ogni seed.
    gare[-1].campionato.slug = "campionato-sociale"
    # La descrizione deve reggere il confronto con il calendario che le sta
    # sotto: una schermata della guida in cui il testo dice «cinque gare da
    # marzo» e l'elenco ne mostra quattro da agosto è una bugia stampata.
    gare[-1].campionato.description = (
        "Quattro gare fra agosto e settembre, aperte a tutti i soci della "
        "sala. La classifica somma le vittorie di ogni gara."
    )
    db.session.commit()

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
        nuova = today + timedelta(days=offset)
        # Le iscrizioni si spostano di quanto si sposta la gara, non di
        # `offset`: la gara viene creata in avanti di un giorno (vedi
        # `_create_gare`), quindi le due quantita' non coincidono e uno scarto
        # lascerebbe le iscrizioni chiuse *dopo* la gara giocata.
        scarto = nuova - gara.date
        gara.date = nuova
        if gara.inscription_start:
            gara.inscription_start += scarto
        if gara.inscription_end:
            gara.inscription_end += scarto
    db.session.commit()
    log("gare 1 e 2 retrodatate (storico del campionato)")


def _open_and_fill(db, gara, players):
    from models.base import utc_now
    from models.competition.inscription_service import InscriptionService

    # `utc_now()` e non `datetime.now()`: e' con l'ora UTC che il servizio
    # confronta la finestra (convenzione 1 del CLAUDE.md).
    now = utc_now()
    InscriptionService.open_inscriptions(
        gara_id=gara.id,
        inscription_start=now - timedelta(days=14),
        inscription_end=datetime.combine(gara.date, time(17, 0)),
    )
    for player in players:
        InscriptionService.inscribe_user(user_id=player.id, gara_id=gara.id)
    db.session.commit()
    log(f"«{gara.name}»: {len(players)} iscritti")


def _avvia_primo_turno(db, gara) -> None:
    """Avvia il primo turno con un seme del sorteggio fisso.

    Nell'app il seme lo sceglie `RoundService.start_first_round` con `secrets`,
    solo se la gara non ne ha gia' uno, e da quel seme il tabellone ricava gli
    accoppiamenti. Qui lo si scrive prima dell'avvio, derivato da `SEED` e
    dall'id della gara, che nel dataset e' sempre lo stesso: la casualita' vera
    dell'app resta com'e', il dataset dimostrativo diventa riproducibile.
    """
    from models.competition.round_service import RoundService

    gara.draw_seed = SEED + gara.id
    db.session.commit()
    RoundService.start_first_round(gara.id)
    db.session.commit()


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

    _avvia_primo_turno(db, gara)

    for round_number in range(1, rounds + 1):
        if round_number > 1:
            RoundService.create_round_with_strategy(
                gara_id=gara.id, round_number=round_number
            )
            # Come fa `start_next_round` nell'app: il turno avviato e' il
            # turno corrente. Senza, la gara restava a `current_round=1` con
            # il turno 2 in gioco, e la pagina del direttore proponeva di
            # avviare un turno gia' avviato.
            gara.current_round = round_number
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


#: Il bersaglio dell'esercizio colpo per colpo, nelle coordinate del
#: disegnatore (1 diamante = 100 unità, panno 800 × 400). Tre anelli da mezzo
#: diamante: 3 punti al centro, poi 2 e 1. Da qui discende anche il punteggio
#: massimo della prova — vedi `_create_challenges`.
BERSAGLIO = {
    "type": "target",
    "id": "t1",
    "x": 600,
    "y": 200,
    "step": 50,
    "values": [3, 2, 1],
}
SCENA_BERSAGLIO = {"v": 4, "orient": "h", "items": [BERSAGLIO]}

#: Le liste da cui l'app pesca la consegna, e la scala con cui si conta un
#: colpo (#452). E' lo stesso «Kicking Madness» da cui nasce la richiesta: a
#: ogni colpo servono un numero di sponde e una bilia.
ESTRAZIONE = {
    "v": 1,
    "sources": [
        {"label": "sponde", "options": ["1 sponda", "2 sponde", "3 o più sponde"]},
        {"label": "bilia", "options": ["bilia 3", "bilia 5", "bilia 7", "bilia 9"]},
    ],
    "outcomes": [
        {"label": "Mancata", "points": 0},
        {"label": "Toccata", "points": 1, "hint": "la battente arriva sulla bilia"},
        {"label": "Mossa verso la buca", "points": 2},
        {"label": "Imbucata", "points": 4},
    ],
}


def _massimo_a_colpi(colonne: dict):
    """Il punteggio massimo di una prova a colpi, con la formula dell'app.

    È i colpi per il valore più alto — il centro del bersaglio, o l'esito che
    vale di più — e non si scrive a mano: scritto a mano diventa un numero che
    nessuno ricalcola quando il bersaglio cambia. Stessa derivazione di
    `ChallengeAuthoringService._recording`.
    """
    from models.challenge.draw_spec import parse_draw_spec
    from models.challenge.target import target_from_scene

    colpi = colonne.get("shots_count")
    if not colpi:
        return None
    bersaglio = target_from_scene(colonne.get("diagram_scene"))
    if bersaglio is not None:
        return colpi * bersaglio.max_points
    spec = parse_draw_spec(colonne.get("draw_spec"))
    return colpi * spec.max_points if spec else None


def _create_challenges(db, director):
    """Cinque prove di abilità, una per ogni modo di registrarle.

    Le prime due sono i modi di sempre — a punteggio e superata/non superata —
    e servono perche' la guida li spiega entrambi: un catalogo con un solo tipo
    non li mostrerebbe. La terza porta le varianti (destra e sinistra). Le
    ultime due sono i modi nati con la fase 5: **colpo per colpo**, che vuole un
    disegno con un bersaglio, e **con estrazione**, che vuole le liste da cui
    pescare. Le immagini sono quelle gia' presenti in
    `static/uploads/challenges/`: il seed non ne inventa di nuove.

    Le prove hanno un **titolo**, e non e' un dettaglio: la guida consiglia di
    darne uno, e delle schermate piene di «Esercizio 1» e «Esercizio 2»
    direbbero il contrario di quello che c'e' scritto accanto.
    """
    from models.challenge.models import Challenge
    from models.challenge.recording import RecordingMode

    disponibili = sorted((REPO_ROOT / "static" / "uploads" / "challenges").glob("*.*"))
    if not disponibili:
        log("challenge non create: nessuna immagine in static/uploads/challenges/")
        return []

    # Il quarto elemento è il profilo (ADR-065): senza, «Oggi» e il catalogo
    # mostrerebbero card senza etichette e filtri che non trovano niente, cioè
    # l'opposto di quello che la guida racconta. Il terzo esercizio sta in fondo
    # apposta: esami e gara pescano i primi due per posizione.
    specs = [
        (
            "Spot Shot Rally",
            "Dieci tiri dalla stessa posizione: la bilia bersaglio sul punto, "
            "la battente in mano. Un punto per ogni imbucata riuscita.",
            False,
            dict(
                max_score=10,
                abilita=["tiro", "posizione"],
                gesti=["stop"],
                declared_level=1,
            ),
        ),
        (
            "Serie da otto",
            "Imbuca otto bilie di fila senza sbagliare. Si passa o non si passa.",
            True,
            dict(abilita=["posizione"], gesti=["follow", "draw"], declared_level=3),
        ),
        (
            "Ferma nel cerchio",
            "Imbuca la bilia e ferma la battente dentro il cerchio. Dieci tiri "
            "da destra e dieci da sinistra: un punto per ogni battente nel cerchio.",
            False,
            dict(
                max_score=10,
                abilita=["battente", "posizione"],
                gesti=["draw", "stun"],
                declared_level=2,
                family="controllo della battente",
                family_step=1,
                cue_ball_reset=True,
                variants=[{"label": "destra"}, {"label": "sinistra"}],
            ),
        ),
        # Gli ultimi due stanno in fondo apposta: esami e gara pescano i primi
        # per posizione, e un esercizio con estrazione in un esame lo rifiuta
        # il servizio (`refuse_if_drawn`) — a ognuno uscirebbe un'altra
        # consegna.
        (
            "Stop nel bersaglio",
            "Imbuca la bilia e ferma la battente nel bersaglio disegnato a "
            "metà tavolo. Vale l'anello in cui si ferma: tre punti il centro, "
            "poi due e uno.",
            False,
            dict(
                abilita=["battente", "posizione"],
                gesti=["stop", "draw"],
                declared_level=2,
                family="controllo della battente",
                family_step=2,
                colonne=dict(
                    recording_mode=RecordingMode.SHOTS.value,
                    shots_count=8,
                    diagram_scene=json.dumps(SCENA_BERSAGLIO),
                ),
            ),
        ),
        (
            "Kicking Madness",
            "A ogni colpo l'app estrae quante sponde fare e su quale bilia "
            "andare. Dieci colpi: conta come è andato ciascuno.",
            False,
            dict(
                abilita=["sponde", "difesa"],
                gesti=["kick", "bank"],
                declared_level=4,
                colonne=dict(
                    recording_mode=RecordingMode.DRAW.value,
                    shots_count=10,
                    draw_spec=json.dumps(ESTRAZIONE),
                ),
            ),
        ),
    ]
    from models.challenge.profile_service import ChallengeProfileService

    create = []
    for index, (title, description, pass_fail, profilo) in enumerate(specs):
        existing = Challenge.query.filter_by(description=description).first()
        if existing:
            create.append(existing)
            continue
        image = disponibili[index % len(disponibili)]
        colonne = profilo.pop("colonne", {})
        challenge = Challenge(
            title=title,
            description=description,
            image_path=f"uploads/challenges/{image.name}",
            pass_fail_only=pass_fail,
            max_score=profilo.pop("max_score", None) or _massimo_a_colpi(colonne),
            created_by_id=director.id,
            is_active=True,
            **colonne,
        )
        db.session.add(challenge)
        db.session.flush()
        ChallengeProfileService.set_profile(challenge.id, **profilo)
        create.append(challenge)
    db.session.commit()
    log(f"challenge: {len(create)} prove nel catalogo")
    return create


def _allena_su_challenge(db, player, challenges) -> None:
    """Qualche prova gia' registrata, per la schermata di allenamento.

    Senza, la figura della guida mostrerebbe «Nessuna prova ancora» e un
    record vuoto: il lettore vedrebbe la schermata che si ha *prima* di usarla,
    proprio mentre il testo gli spiega l'elenco delle prove e il record. I
    punteggi sono scritti qui e non sorteggiati perche' due catture successive
    devono produrre immagini identiche (vedi il docstring del modulo).
    """
    from models.base import utc_now
    from models.challenge.services import ChallengeService

    numeriche = [c for c in challenges if not c.pass_fail_only]
    if not player or not numeriche:
        return

    drill = numeriche[0]
    # Le tre prove sono distanti qualche minuto l'una dall'altra: registrate
    # tutte nello stesso istante, «Le prove di oggi» mostrava tre volte lo
    # stesso orario, che è il modo in cui una figura dice «questi dati sono
    # finti». L'ora resta quella di oggi, perché è la finestra che la
    # schermata guarda.
    for punteggio, minuti_fa in ((6, 14), (4, 9), (8, 3)):
        prova = ChallengeService.record_attempt(
            user_id=player.id,
            challenge_id=drill.id,
            score=punteggio,
        )
        prova.attempted_at = utc_now() - timedelta(minutes=minuti_fa)
    db.session.commit()
    log(f"allenamento: 3 prove registrate su «{drill.get_display_name()}»")


#: Quante prove mettere su ogni esercizio «a totale», e in quale finestra.
#: Il mese di adesso e quello prima, perché il radar disegni **due** poligoni:
#: il secondo si disegna solo se ogni asse ha numeri anche nel periodo
#: precedente, e senza queste righe la guida mostrerebbe un radar a un
#: poligono proprio mentre il testo spiega il confronto.
ANDAMENTO = (
    # (giorni fa, punteggio come frazione del massimo)
    (4, 0.7),
    (11, 0.6),
    (19, 0.8),
    (26, 0.6),
    (38, 0.5),
    (47, 0.5),
    (54, 0.4),
)


def _andamento_e_obiettivo(db, player, challenges) -> None:
    """Abbastanza prove perché l'andamento dica qualcosa, e un obiettivo aperto.

    Tre figure lo chiedono: il radar per abilità, quello per gesto e la card
    degli obiettivi. Nessuna delle tre direbbe niente con le tre prove su un
    esercizio solo che bastavano alla schermata di allenamento — il radar
    avrebbe due raggi e la pagina sarebbe una riga di scuse.

    Si allarga su **tutti** gli esercizi a totale, perché ogni abilità del
    vocabolario che compare nel catalogo abbia il suo raggio, e su **due
    finestre**, perché il confronto col mese prima si possa disegnare.
    """
    from models.base import utc_now
    from models.challenge.recording import RecordingMode
    from models.challenge.services import ChallengeService
    from models.obiettivo import GoalKind, GoalRule, TrainingGoalService

    if not player:
        return

    a_totale = [
        c
        for c in challenges
        if str(c.recording_mode or RecordingMode.TOTAL.value)
        == RecordingMode.TOTAL.value
    ]
    quante = 0
    for esercizio in a_totale:
        for giorni_fa, quota in ANDAMENTO:
            if esercizio.pass_fail_only:
                prova = ChallengeService.record_attempt(
                    user_id=player.id,
                    challenge_id=esercizio.id,
                    passed=quota >= 0.6,
                )
            else:
                massimo = esercizio.max_score or 10
                prova = ChallengeService.record_attempt(
                    user_id=player.id,
                    challenge_id=esercizio.id,
                    score=max(1, round(massimo * quota)),
                )
            prova.attempted_at = utc_now() - timedelta(days=giorni_fa)
            quante += 1
    db.session.commit()
    log(f"andamento: {quante} prove su {len(a_totale)} esercizi, su due mesi")

    # Un obiettivo aperto, e uno solo: la card ne mostra uno per riga, e tre
    # righe su un mockup sembrano un elenco di cose da fare invece di una
    # scelta. Il traguardo sta sopra la media di adesso — altrimenti il
    # servizio lo rifiuta, ed è giusto: un obiettivo già raggiunto non è un
    # obiettivo.
    if not a_totale:
        return
    bersaglio = next((c for c in a_totale if not c.pass_fail_only), None)
    if bersaglio is None:
        return
    massimo = bersaglio.max_score or 10
    TrainingGoalService.create(
        player.id,
        GoalKind.ESERCIZIO,
        challenge_id=bersaglio.id,
        rule=GoalRule.MEDIA,
        target=min(massimo, round(massimo * 0.9)),
    )
    db.session.commit()
    log(f"obiettivo: «{bersaglio.get_display_name()}» come traguardo")


def _crea_scheda(db, player, challenges) -> None:
    """Una scheda di allenamento come quella di carta, con tre sedute fatte.

    Serve a tre figure della guida — l'elenco, la seduta e il registro — e
    nessuna delle tre direbbe niente su una scheda vuota: il registro
    mostrerebbe «Nessuna seduta» proprio mentre il testo spiega come si legge
    l'andamento.

    I numeri sono scritti qui e non sorteggiati, come i punteggi di
    `_allena_su_challenge`: due catture successive devono dare immagini
    identiche. Sono quelli che raccontano qualcosa — un lato più debole
    dell'altro, e una voce in crescita — perché è quello che il registro deve
    saper dire.
    """
    from models.base import utc_now
    from models.challenge.models import ChallengeVariant
    from models.training_sheet import (
        SheetItemSpec,
        SheetMeasure,
        TrainingSheetService,
    )
    from models.training_sheet.measure import LevelUp
    from models.training_sheet.models import TrainingEntry, TrainingSession

    numeriche = [c for c in challenges if not c.pass_fail_only]
    if not player or len(numeriche) < 3:
        return

    a_lati, lungo, a_tempo = numeriche[0], numeriche[1], numeriche[2]
    if not a_lati.variants:
        for posizione, etichetta in enumerate(("destra", "sinistra"), start=1):
            db.session.add(
                ChallengeVariant(
                    challenge_id=a_lati.id, label=etichetta, position=posizione
                )
            )
        db.session.commit()

    sheet = TrainingSheetService.create_sheet(player, "Tecnica di base")
    TrainingSheetService.save_composition(
        sheet.id,
        player,
        name="Tecnica di base",
        level=3,
        threshold=30,
        # Il gradino lo sancisce una persona (D8, ADR-071): e' questa scheda a
        # far comparire «Valuta il passaggio di livello» fra gli allievi
        # dell'istruttore, e senza `instructor` quella sezione resterebbe vuota
        # proprio mentre la guida la spiega. Con `auto` non ci sarebbe nessuno
        # da chiamare, ed e' il motivo per cui il segnale non compare.
        level_up=LevelUp.INSTRUCTOR,
        items=[
            SheetItemSpec(
                challenge_id=a_lati.id,
                measure=SheetMeasure.MADE,
                amount=5,
                per_variant=True,
                section="Tecnica",
            ),
            SheetItemSpec(challenge_id=lungo.id, measure=SheetMeasure.MADE, amount=30),
            SheetItemSpec(
                challenge_id=a_tempo.id,
                measure=SheetMeasure.MINUTES,
                amount=10,
                section="Gioco",
            ),
        ],
    )
    db.session.commit()

    lati, voce_lunga, voce_tempo = sheet.active_items
    destra, sinistra = lati.variants

    # Tre sedute chiuse: il lato sinistro resta indietro, la voce lunga sale.
    for giorni_fa, (a_destra, a_sinistra), riusciti, minuti in (
        (6, (4, 2), 19, 10),
        (3, (5, 3), 22, 12),
        (1, (4, 3), 24, 10),
    ):
        quando = utc_now() - timedelta(days=giorni_fa)
        seduta = TrainingSession(
            sheet_id=sheet.id,
            user_id=player.id,
            sheet_version=sheet.version,
            started_at=quando,
            ended_at=quando + timedelta(minutes=52),
        )
        db.session.add(seduta)
        db.session.flush()
        caselle = (
            (voce_lunga.id, None, riusciti, voce_lunga.amount),
            (voce_tempo.id, None, minuti, voce_tempo.amount),
            (lati.id, destra.id, a_destra, lati.amount),
            (lati.id, sinistra.id, a_sinistra, lati.amount),
        )
        for item_id, variant_id, valore, tetto in caselle:
            voce = next(v for v in sheet.items if v.id == item_id)
            db.session.add(
                TrainingEntry(
                    session_id=seduta.id,
                    item_id=item_id,
                    variant_id=variant_id,
                    value=valore,
                    measure=voce.measure,
                    target_amount=tetto,
                )
            )
        db.session.commit()

    # E una seduta cominciata e lasciata a metà: è quella che la figura della
    # seduta mostra, e che «Oggi» propone di riprendere.
    aperta = TrainingSession(
        sheet_id=sheet.id,
        user_id=player.id,
        sheet_version=sheet.version,
        started_at=utc_now() - timedelta(minutes=18),
    )
    db.session.add(aperta)
    db.session.flush()
    db.session.add(
        TrainingEntry(
            session_id=aperta.id,
            item_id=lati.id,
            variant_id=destra.id,
            value=4,
            measure=lati.measure,
            target_amount=lati.amount,
        )
    )
    db.session.commit()
    log(f"scheda «{sheet.name}»: 3 sedute chiuse e una in corso")


# ── L'istruttore, i suoi allievi, i corsi (fase 8) ──────────────────────────

#: Da quanti giorni e' cominciato il corso in corso. Trentotto e non
#: trentacinque di proposito: `TrainingGroup.week_of` conta `giorni // 7 + 1`,
#: quindi la settimana in corso e' cominciata **tre giorni fa**, e le sedute di
#: questi giorni cadono dentro la finestra che la pagina chiama «questa
#: settimana». Con un multiplo esatto di sette la settimana comincerebbe oggi e
#: il numero sarebbe quasi sempre zero: vero, e inutile da guardare.
GIORNI_CORSO_DA = 38

#: Quanto manca alla fine dichiarata: «settimana 6 di 13».
GIORNI_CORSO_A = 49

#: Il corso chiuso dello storico, in giorni da oggi. Il passaggio di livello di
#: Giulia sta **dentro** questa finestra, ed e' cio' che fa dire «1 al livello
#: dopo» alla riga dello storico.
GIORNI_CORSO_PASSATO = (210, 120)


def _istruttore_e_allievi(db, players, challenges) -> None:
    """Un istruttore vero, i suoi allievi, un corso aperto e uno chiuso.

    Il seed della fase 6 si fermava alla scheda di un giocatore che si allena
    da solo: nessun ruolo di istruttore, nessun gruppo, nessuna proposta.
    Le pagine della fase 8 su quel dataset sarebbero tutte vuote — e una guida
    illustrata da elenchi vuoti non spiega niente, mostra un'app spenta.

    Lo stato costruito qui e' quello che serve a **dire la verita' sui numeri
    del corso**, e ogni pezzo risponde a una frase della guida:

    * **Davide prende la scheda e non la fa leggere.** E' il caso che spiega il
      denominatore: «l'hanno presa in 4» ma la media e' «su 3 schede che
      leggi». Senza di lui i due numeri coinciderebbero sempre, e chi legge
      crederebbe che siano lo stesso numero scritto due volte;
    * **Paolo non ha ancora risposto** — la proposta in attesa;
    * **Chiara e' entrata dopo** e la scheda del corso non l'ha mai ricevuta:
      non e' un «no», e la pagina lo dice a parte, coi nomi;
    * **Sara ha superato il livello** e le arriva la scheda del gradino dopo:
      e' la proposta con le **due** caselle, lettura e passaggio;
    * **Marco e' arrivato alla soglia** di una scheda che aspetta una persona:
      e' «Valuta il passaggio di livello», con «Confermo» da premere;
    * **Giulia e' un'ex allieva** che oggi non gli fa piu' leggere niente, e il
      suo passaggio resta scritto nello storico del corso chiuso: e' la
      proprieta' per cui il conteggio guarda **quando** leggevi, non se leggi
      adesso (`esiti_dei_corsi`).

    I numeri delle sedute sono scritti qui e non sorteggiati, come ovunque in
    questo file: due catture successive devono dare immagini identiche.
    """
    from models import User
    from models.base import utc_now
    from models.istruttore import AssegnazioneService, GruppoService
    from models.training_sheet import (
        SheetItemSpec,
        SheetMeasure,
        TrainingSheetService,
    )
    from models.training_sheet.measure import LevelUp
    from models.user.role_enum import UserRole

    numeriche = [c for c in challenges if not c.pass_fail_only]
    if len(numeriche) < 3:
        log("istruttore non creato: servono almeno tre esercizi numerici")
        return
    admin = User.query.filter_by(role=UserRole.ADMIN.value).first()
    director = User.query.filter_by(username=DEMO_DIRECTOR[0]).first()
    if admin is None or director is None:
        log("istruttore non creato: manca chi concede il ruolo")
        return

    marco, giulia, andrea = players[0], players[1], players[2]
    sara, paolo, elena = players[3], players[4], players[5]
    davide, chiara = players[6], players[7]

    # La catena delle nomine, che la pagina dei titolari mostra (#526): admin
    # concede al primo, e il primo concede al secondo. Con un titolare solo la
    # colonna «Concesso da» direbbe «admin» e basta, e la propagazione — che e'
    # il motivo per cui quella pagina esiste — non si vedrebbe.
    _concedi_istruttore(db, admin, director)
    _concedi_istruttore(db, director, andrea)
    andrea.organization = "Scuola Biliardo Centrale"
    db.session.commit()

    # I due modelli dell'istruttore: una scala di due gradini. Il secondo serve
    # a «Dai il livello dopo», che senza una scheda a cui puntare non si puo'
    # nemmeno fotografare.
    modelli = []
    for livello, soglia in ((1, 14), (2, 17)):
        modello = TrainingSheetService.create_sheet(
            andrea, f"Corso base · livello {livello}"
        )
        TrainingSheetService.save_composition(
            modello.id,
            andrea,
            name=f"Corso base · livello {livello}",
            level=livello,
            threshold=soglia,
            # Il gradino lo sancisce lui: e' una scheda che si fa in sala, con
            # qualcuno che guarda. Si copia sulle schede che ne nascono.
            level_up=LevelUp.INSTRUCTOR,
            items=[
                SheetItemSpec(
                    challenge_id=numeriche[0].id, measure=SheetMeasure.MADE, amount=5
                ),
                SheetItemSpec(
                    challenge_id=numeriche[1].id, measure=SheetMeasure.MADE, amount=10
                ),
                SheetItemSpec(
                    challenge_id=numeriche[2].id, measure=SheetMeasure.MADE, amount=5
                ),
            ],
        )
        modelli.append(modello)
    db.session.commit()
    livello1, livello2 = modelli

    # La prima mossa e' sempre dell'allievo (ADR-069): finche' non ti apre una
    # scheda non sei nessuno per lui, e non gli puoi proporre niente. Marco ha
    # gia' la sua — «Tecnica di base» — e la apre; gli altri ne scrivono una.
    tecnica = TrainingSheetService.sheets_of(marco.id)[0]
    _apre_la_scheda(db, tecnica, andrea, marco, giorni_fa=40)
    personali = {
        allievo.id: _scheda_personale(db, allievo, andrea, numeriche, giorni_fa=giorni)
        for allievo, giorni in (
            (sara, 40),
            (elena, 40),
            (davide, 40),
            (paolo, 40),
            (chiara, 3),
        )
    }
    # Davide si allena, e quel che l'istruttore vede di lui e' questo: la
    # scheda del corso lui la tiene per se'. Senza questa seduta finirebbe
    # fra quelli «da guardare» — vero secondo il modello, e fuorviante da
    # leggere: non e' sparito, e' solo che di quella scheda non gli dice
    # niente. Paolo resta l'unico che non ha ancora cominciato.
    _sedute_di_scheda(db, personali[davide.id], davide, ((5, 11),))

    # Il corso in corso, e chi ne fa parte.
    oggi = date.today()
    corso = GruppoService.crea(
        andrea,
        "Corso del lunedì",
        oggi - timedelta(days=GIORNI_CORSO_DA),
        oggi + timedelta(days=GIORNI_CORSO_A),
    )
    db.session.commit()
    for allievo in (marco, sara, elena, davide, paolo):
        GruppoService.aggiungi(corso.id, andrea, allievo.id)
    db.session.commit()

    # La scheda del corso, proposta dal gruppo: quattro la prendono, uno non ha
    # ancora risposto. L'ordine conta — `proponi` salta chi ha gia' una
    # proposta tua in attesa, quindi le risposte vanno date prima di mandarne
    # un'altra a chi ha gia' risposto.
    proposte = AssegnazioneService.proponi(
        andrea,
        livello1.id,
        [marco.id, sara.id, elena.id, davide.id, paolo.id],
        messaggio="La scheda del corso. Due giri a settimana, senza fretta.",
        group_id=corso.id,
    )
    db.session.commit()
    per_allievo = {proposta.user_id: proposta for proposta in proposte}

    copie = {}
    for allievo, legge in ((marco, True), (sara, True), (elena, True), (davide, False)):
        copie[allievo.id] = AssegnazioneService.accetta(
            per_allievo[allievo.id].id, allievo, apri_lettura=legge
        )
    db.session.commit()

    # Chiara entra a corso cominciato: la scheda comune non le e' mai arrivata,
    # ed e' la riga «Sono entrati nel corso dopo» della pagina.
    GruppoService.aggiungi(corso.id, andrea, chiara.id)
    db.session.commit()

    # Le sedute delle copie. I totali sono scelti perche' la pagina dica cose
    # diverse su persone diverse: Sara tiene la soglia e passa, Marco ed Elena
    # restano sotto — con una sola seduta sopra la soglia scatterebbe anche per
    # loro «Valuta il passaggio», e le tre sezioni collasserebbero in una.
    _sedute_di_scheda(db, copie[marco.id], marco, ((9, 12), (5, 16), (1, 13)))
    _sedute_di_scheda(db, copie[sara.id], sara, ((10, 11), (6, 15), (2, 15)))
    _sedute_di_scheda(db, copie[elena.id], elena, ((8, 10), (4, 12), (2, 13)))

    # Sara ha superato il livello, e a timbrarlo e' stato lui.
    passata = copie[sara.id]
    passata.passed_at = utc_now() - timedelta(days=1)
    passata.passed_by_id = andrea.id
    db.session.commit()

    # Il secondo gesto del passaggio: la scheda del livello dopo, che aspetta
    # la sua risposta. E' la proposta con le **due** caselle.
    AssegnazioneService.proponi(
        andrea,
        livello2.id,
        [sara.id],
        messaggio="Bravissima. Da lunedì passiamo a questa.",
        promuove={sara.id: passata.id},
    )
    db.session.commit()

    _corso_chiuso(db, andrea, giulia, numeriche)
    log(
        "istruttore Andrea Ferri: 6 allievi, «Corso del lunedì» "
        "(4 schede prese su 5, 3 lette) e un corso chiuso nello storico"
    )


def _concedi_istruttore(db, chi, a_chi) -> None:
    """Concede il ruolo, se non ce l'ha gia'. Idempotente come il resto."""
    from models.user.role_enum import GrantableRole
    from models.user.role_grant_service import RoleGrantService

    if RoleGrantService.has_role(a_chi.id, GrantableRole.INSTRUCTOR):
        return
    RoleGrantService.grant(
        user_id=a_chi.id, role=GrantableRole.INSTRUCTOR, granted_by=chi
    )
    db.session.commit()


def _apre_la_scheda(db, scheda, istruttore, proprietario, *, giorni_fa: int):
    """Apre una scheda a un istruttore, retrodatando il permesso.

    La data conta: «Ti hanno appena aperto una scheda» guarda gli ultimi sette
    giorni, e senza retrodatare l'elenco direbbe che sono arrivati tutti oggi.
    """
    from models.base import utc_now
    from models.training_sheet import TrainingSheetService

    lettore = TrainingSheetService.add_reader(
        scheda.id, istruttore.id, proprietario, avvisa=False
    )
    lettore.granted_at = utc_now() - timedelta(days=giorni_fa)
    db.session.commit()
    return lettore


def _scheda_personale(db, allievo, istruttore, numeriche, *, giorni_fa: int):
    """La scheda che l'allievo si scrive da se', e che apre all'istruttore.

    Serve a far esistere il legame: senza, l'istruttore non potrebbe proporgli
    niente — la prima mossa e' sempre dell'altro (ADR-069). Resta senza sedute
    di proposito: i numeri di questi allievi stanno sulla scheda del corso, e
    aggiungerne altrove renderebbe illeggibile la media.
    """
    from models.training_sheet import (
        SheetItemSpec,
        SheetMeasure,
        TrainingSheetService,
    )

    scheda = TrainingSheetService.create_sheet(allievo, "Esercizi di casa")
    TrainingSheetService.save_composition(
        scheda.id,
        allievo,
        name="Esercizi di casa",
        items=[
            SheetItemSpec(
                challenge_id=numeriche[0].id, measure=SheetMeasure.MADE, amount=10
            ),
            SheetItemSpec(
                challenge_id=numeriche[1].id, measure=SheetMeasure.MADE, amount=5
            ),
        ],
    )
    db.session.commit()
    _apre_la_scheda(db, scheda, istruttore, allievo, giorni_fa=giorni_fa)
    return scheda


def _sedute_di_scheda(db, scheda, proprietario, sedute) -> None:
    """Sedute chiuse su una scheda a tre voci, dato il totale di ciascuna.

    Il totale si spalma sulle tre voci rispettando il tetto di ognuna: cosi'
    l'invariante che conta — `total` e `max_total` della seduta — resta quella
    voluta senza dover scrivere a mano nove numeri per allievo.
    """
    from models.base import utc_now
    from models.training_sheet.models import TrainingEntry, TrainingSession

    voci = scheda.active_items
    for giorni_fa, totale in sedute:
        quando = utc_now() - timedelta(days=giorni_fa)
        seduta = TrainingSession(
            sheet_id=scheda.id,
            user_id=proprietario.id,
            sheet_version=scheda.version,
            started_at=quando,
            ended_at=quando + timedelta(minutes=45),
        )
        db.session.add(seduta)
        db.session.flush()
        resto = totale
        for voce in voci:
            valore = min(voce.amount, resto)
            resto -= valore
            db.session.add(
                TrainingEntry(
                    session_id=seduta.id,
                    item_id=voce.id,
                    value=valore,
                    measure=voce.measure,
                    target_amount=voce.amount,
                )
            )
        db.session.commit()


def _corso_chiuso(db, istruttore, allieva, numeriche) -> None:
    """Un corso finito, con dentro un passaggio di livello. E un'ex allieva.

    Il permesso di lettura viene **revocato** dopo il passaggio, ed e' voluto:
    Giulia oggi non e' piu' un'allieva — non compare in «I miei allievi» — ma
    lo storico continua a dire «1 al livello dopo», perche' il conteggio guarda
    se leggevi la scheda **quando** il timbro e' stato messo. Lo storico dice
    quello che hai visto succedere, e non cambia dopo.
    """
    from models.base import utc_now
    from models.istruttore import GruppoService
    from models.training_sheet import (
        SheetItemSpec,
        SheetMeasure,
        TrainingSheetService,
    )
    from models.training_sheet.measure import LevelUp

    da_giorni, a_giorni = GIORNI_CORSO_PASSATO
    scheda = TrainingSheetService.create_sheet(allieva, "Corso base · livello 1")
    TrainingSheetService.save_composition(
        scheda.id,
        allieva,
        name="Corso base · livello 1",
        level=1,
        threshold=14,
        level_up=LevelUp.INSTRUCTOR,
        items=[
            SheetItemSpec(
                challenge_id=numeriche[0].id, measure=SheetMeasure.MADE, amount=5
            ),
            SheetItemSpec(
                challenge_id=numeriche[1].id, measure=SheetMeasure.MADE, amount=10
            ),
        ],
    )
    db.session.commit()
    lettore = _apre_la_scheda(db, scheda, istruttore, allieva, giorni_fa=da_giorni - 5)

    oggi = date.today()
    corso = GruppoService.crea(
        istruttore,
        "Corso di primavera",
        oggi - timedelta(days=da_giorni),
        oggi - timedelta(days=a_giorni),
    )
    db.session.commit()
    membro = GruppoService.aggiungi(corso.id, istruttore, allieva.id)
    db.session.commit()

    # Il calendario e' una previsione, lo stato e' un atto (ADR-070): il corso
    # si chiude, e poi le date si portano indietro perche' sia davvero passato.
    GruppoService.chiudi(corso.id, istruttore)
    db.session.commit()
    corso.started_on = oggi - timedelta(days=da_giorni)
    corso.ended_on = oggi - timedelta(days=a_giorni)
    corso.closed_at = utc_now() - timedelta(days=a_giorni)
    membro.joined_at = utc_now() - timedelta(days=da_giorni - 5)
    membro.left_at = utc_now() - timedelta(days=a_giorni)
    scheda.passed_at = utc_now() - timedelta(days=150)
    scheda.passed_by_id = istruttore.id
    lettore.revoked_at = utc_now() - timedelta(days=a_giorni)
    db.session.commit()


def _popola_esercizi(db, players, challenges) -> None:
    """Altri giocatori che hanno provato e votato: i numeri sociali delle card.

    «4,5 · 5 giocatori» non si può mostrare con un giocatore solo. Prove e voti
    sono scritti qui, non sorteggiati, per lo stesso motivo dei punteggi sopra:
    due catture devono dare la stessa immagine. Il primo giocatore — quello
    delle schermate — **non** vota: la figura della scheda deve mostrare le
    bilie ancora da toccare.
    """
    from models.challenge.rating_service import ChallengeRatingService
    from models.challenge.services import ChallengeService

    if len(players) < 6 or len(challenges) < 3:
        return
    piano = {
        0: [(1, 7, 5), (2, 5, 4), (3, 9, 5), (4, 6, 4)],
        2: [(1, 4, 5), (2, 6, 4)],
    }
    for indice, prove in piano.items():
        esercizio = challenges[indice]
        for chi, punteggio, voto in prove:
            giocatore = players[chi]
            ChallengeService.record_attempt(
                user_id=giocatore.id, challenge_id=esercizio.id, score=punteggio
            )
            ChallengeRatingService.rate(giocatore.id, esercizio.id, voto)
    db.session.commit()
    log("esercizi: prove e voti di altri giocatori")


#: Dove si è fermata la battente, colpo per colpo: prima la prova già chiusa —
#: quella che la guida mostra a fine sessione — poi quella ancora aperta, che è
#: la schermata «si tira». `None` è il colpo non imbucato, che un punto
#: d'arrivo non ce l'ha. Coordinate del disegnatore, come il bersaglio.
#:
#: Sono scelti perché la nuvola **dica qualcosa**: tutti gli arrivi oltre il
#: centro verso la sponda lunga, cioè «Arrivi lungo · è forza, non mira». Una
#: dispersione a caso avrebbe dato la frase «Sparse attorno al centro», e la
#: guida avrebbe spiegato una lettura che la sua stessa figura non mostra.
COLPI_CHIUSI = [
    (640, 210),
    (665, 190),
    (690, 215),
    (652, 175),
    (700, 205),
    (645, 230),
    None,
    (620, 195),
]
COLPI_APERTI = [(610, 205), None, (660, 220), (695, 185)]

#: Le consegne della prova con estrazione, e come è andata ciascuna (l'indice
#: nella scala di `ESTRAZIONE`). L'ultima riga è la consegna **in attesa**: il
#: colpo che il lettore vede sullo schermo, ancora da tirare.
COLPI_ESTRATTI = [
    ("2 sponde, bilia 5", 3),
    ("1 sponda, bilia 9", 1),
    ("3 o più sponde, bilia 3", 0),
]
CONSEGNA_IN_ATTESA = "2 sponde, bilia 7"


def _prove_a_colpi(db, player, challenges) -> None:
    """Le prove delle schermate della fase 5: colpo per colpo ed estrazione.

    Tre stati, perché la guida ne mostra tre schermate diverse:

    * una prova **chiusa** sul bersaglio — è la «fine sessione», con la nuvola
      dei punti d'arrivo e che cosa dice;
    * una prova **aperta** sullo stesso esercizio, a metà dei colpi: è la
      schermata che si ha in mano mentre si tira;
    * una prova aperta **con estrazione**, con la consegna già uscita e in
      attesa del colpo.

    L'estrazione è l'unico punto in cui il seed deve mettere le mani dentro
    l'app: `DrawSpec.draw` pesca da un `random.Random()` suo, che non risponde
    al seme globale, quindi la consegna cambierebbe a ogni esecuzione e ogni
    ricattura riscriverebbe immagini a interfaccia identica. Si fissa la
    consegna sulla prova prima di registrare il colpo — come `_avvia_primo_turno`
    fissa il seme del sorteggio — e tutto il resto passa dal servizio vero.
    """
    from models.challenge.recording import RecordingMode
    from models.challenge.shot_service import ShotRunService

    if not player:
        return

    def _del_modo(modo):
        for esercizio in challenges:
            if RecordingMode.parse(esercizio.recording_mode) is modo:
                return esercizio
        return None

    bersaglio = _del_modo(RecordingMode.SHOTS)
    if bersaglio is not None:
        for serie, chiudere in ((COLPI_CHIUSI, True), (COLPI_APERTI, False)):
            for punto in serie:
                ShotRunService.record_shot(
                    user_id=player.id,
                    challenge_id=bersaglio.id,
                    made=punto is not None,
                    x=punto[0] if punto else None,
                    y=punto[1] if punto else None,
                )
            if chiudere:
                ShotRunService.close(player.id, bersaglio.id)
        db.session.commit()
        chiusa = len(COLPI_CHIUSI)
        log(
            f"colpo per colpo: una prova di {chiusa} colpi chiusa e una da "
            f"{len(COLPI_APERTI)} ancora aperta su «{bersaglio.get_display_name()}»"
        )

    estrazione = _del_modo(RecordingMode.DRAW)
    if estrazione is not None:
        for consegna, esito in COLPI_ESTRATTI:
            run = ShotRunService.draw_next(player.id, estrazione.id)
            run.attempt.pending_prompt = consegna
            db.session.commit()
            ShotRunService.record_outcome(player.id, estrazione.id, outcome_index=esito)
        run = ShotRunService.current(player.id, estrazione.id)
        run.attempt.pending_prompt = CONSEGNA_IN_ATTESA
        db.session.commit()
        log(
            f"con estrazione: {len(COLPI_ESTRATTI)} colpi giocati e la consegna "
            f"«{CONSEGNA_IN_ATTESA}» in attesa"
        )


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


def _grant_examiner(db, admin, users) -> bool:
    """Concede il ruolo di esaminatore, che nessun `create_all()` produce.

    Il ruolo e' **concedibile e ortogonale** (ADR-041): non e' un valore di
    `user.role`, e' una riga in `role_grant`. Lo prende anche un giocatore e
    non solo il direttore, di proposito: le due cose sono indipendenti, e un
    dataset in cui coincidono lascerebbe credere il contrario a chi guarda le
    figure.
    """
    from models.user.role_enum import GrantableRole
    from models.user.role_grant_service import RoleGrantService

    if admin is None:
        log("esami non creati: manca l'utente admin che concede il ruolo")
        return False
    for user in users:
        if RoleGrantService.has_role(user.id, GrantableRole.EXAMINER):
            continue
        RoleGrantService.grant(
            user_id=user.id, role=GrantableRole.EXAMINER, granted_by=admin
        )
    db.session.commit()
    log(f"ruolo esaminatore: {', '.join(u.username for u in users)}")
    return True


def _create_esami(db, director, players, challenges, venue):
    """Un esame composto, piu' i tre stati che le sue schermate mostrano.

    Un esame appena creato non basta alla guida: le pagine dell'area esami
    cambiano faccia a seconda di dove sei arrivato, e senza gli stati
    intermedi resterebbero schermate identiche con un elenco vuoto. Servono
    quindi un allenamento gia' concluso, una trattativa aperta e una sessione
    certificata a meta'.

    E servono **candidati diversi**: la pagina di un esame mostra «Prova da
    solo» a chi non ha niente in corso e «Riprendi» a chi ha un tentativo
    aperto. Catturare i due stati con la stessa persona e' impossibile, quindi
    Marco Rossi resta pulito (catalogo, dettaglio, modulo di richiesta), Elena
    Ricci porta la trattativa e Sara Neri la sessione certificata.

    Il primo drill chiede **tre prove**: e' l'unico modo di far vedere nelle
    figure il «conta la migliore» introdotto con le prove multiple. Con una
    prova sola la schermata non lo direbbe, e la guida spiegherebbe qualcosa
    che nell'immagine non si vede.
    """
    from models.exam.request_service import ExamRequestService
    from models.exam.services import ExamService

    if len(challenges) < 2:
        log("esami non creati: servono almeno due drill nel catalogo")
        return

    marco, elena, sara = players[0], players[5], players[3]
    co_esaminatore = players[2]

    from models import User
    from models.user.role_enum import UserRole

    admin = User.query.filter_by(role=UserRole.ADMIN.value).first()
    if not _grant_examiner(db, admin, [director, co_esaminatore]):
        return

    esame = ExamService.create_exam(
        actor=director,
        name="Fondamentali — livello 1",
        description=(
            "Tre gesti di base, uno dopo l'altro: il tiro dal punto, la serie "
            "senza errori e il controllo della battente. Si sostiene da soli "
            "per allenarsi, oppure davanti a un esaminatore per farlo valere."
        ),
    )
    db.session.commit()

    drill_punteggio = ExamService.add_challenge_to_exam(
        exam_id=esame.id,
        challenge_id=challenges[0].id,
        actor=director,
        max_score=10,
        max_attempts=3,
    )
    drill_passa = ExamService.add_challenge_to_exam(
        exam_id=esame.id,
        challenge_id=challenges[1].id,
        actor=director,
        max_attempts=1,
    )
    ExamService.add_examiner(
        exam_id=esame.id, user_id=co_esaminatore.id, actor=director
    )
    db.session.commit()
    log(f"esame «{esame.name}»: 2 drill, 2 esaminatori")

    # ── Un secondo esame, che nessuno ha ancora toccato. Due ragioni: nel
    #    catalogo serve almeno una voce «mai provato» accanto a quelle con una
    #    storia, e «Componi» va fotografata su un esame **senza sessioni
    #    certificate aperte** — quella di Sara, più sotto, blocca la
    #    composizione del primo (emendamento ADR-042). Gli esercizi sono gli
    #    stessi due, in ordine inverso e con un altro peso: è proprio ciò che
    #    la guida racconta di `max_score`, che si decide esame per esame.
    secondo = ExamService.create_exam(
        actor=director,
        name="Controllo — livello 1",
        description=(
            "Prima la serie senza errori, poi il tiro dal punto: qui il tiro "
            "pesa il doppio, e le prove sono due."
        ),
    )
    db.session.commit()
    ExamService.add_challenge_to_exam(
        exam_id=secondo.id,
        challenge_id=challenges[1].id,
        actor=director,
        max_attempts=1,
    )
    ExamService.add_challenge_to_exam(
        exam_id=secondo.id,
        challenge_id=challenges[0].id,
        actor=director,
        max_score=20,
        max_attempts=2,
    )
    db.session.commit()
    log(f"esame «{secondo.name}»: 2 drill, mai sostenuto")

    # ── Allenamento gia' concluso: da' statistiche non vuote all'esame e uno
    #    storico al profilo. I tre punteggi sono 6, 9, 7 — vale 9, e si vede.
    allenamento = ExamService.start_self_practice(actor=marco, exam_id=esame.id)
    for numero, punteggio in enumerate([6, 9, 7], start=1):
        ExamService.record_challenge_result(
            attempt_id=allenamento.id,
            exam_challenge_id=drill_punteggio.id,
            actor=marco,
            score=punteggio,
            attempt_number=numero,
        )
    ExamService.record_challenge_result(
        attempt_id=allenamento.id,
        exam_challenge_id=drill_passa.id,
        actor=marco,
        passed=True,
    )
    ExamService.complete_attempt(attempt_id=allenamento.id, actor=marco)
    db.session.commit()
    log(f"allenamento in autonomia concluso da {marco.username}")

    # ── Trattativa aperta: proposta del candidato, controproposta
    #    dell'esaminatore. Serve alla figura «Come ci siete arrivati», che con
    #    una proposta sola non mostrerebbe nessuno scambio.
    # Gli orari sono naive **UTC**, e la pagina li mostra nel fuso di chi legge:
    # le 18 diventano le 20 italiane (le 19 d'inverno). Scritti come «20» si
    # leggevano «22:00» e «23:30», orari a cui nessuna sala dà un esame.
    quando = datetime.combine(date.today() + timedelta(days=4), time(18, 0))
    trattativa = ExamRequestService.create_request(
        actor=elena,
        exam_id=esame.id,
        scheduled_at=quando,
        billiard_hall_id=venue.id,
        expires_at=quando - timedelta(hours=6),
        notes="Se per te va bene mi porto avanti con i fondamentali.",
    )
    db.session.commit()
    ExamRequestService.counter_propose(
        request_id=trattativa.id,
        actor=director,
        scheduled_at=quando + timedelta(minutes=90),
    )
    db.session.commit()
    log(f"appuntamento in trattativa: {elena.username} ↔ {director.username}")

    # ── Sessione certificata a meta': l'appuntamento e' stato accettato, il
    #    candidato ha dato il via e due prove su tre sono registrate. E' lo
    #    stato in cui un esaminatore vede davvero la schermata mentre lavora.
    appuntamento = ExamRequestService.create_request(
        actor=sara,
        exam_id=esame.id,
        # Domani, non oggi: «oggi alle 21» e' gia' passato per chi lancia il
        # seed di sera, e `create_request` rifiuta un appuntamento nel passato.
        scheduled_at=datetime.combine(date.today() + timedelta(days=1), time(19, 0)),
        billiard_hall_id=venue.id,
        recipient_ids=[director.id],
    )
    db.session.commit()
    ExamRequestService.accept(request_id=appuntamento.id, actor=director)
    db.session.commit()
    sessione = ExamService.open_certified_session(
        actor=director, request_id=appuntamento.id
    )
    db.session.commit()
    ExamService.accept_session_start(attempt_id=sessione.id, actor=sara)
    for numero, punteggio in enumerate([7, 8], start=1):
        ExamService.record_challenge_result(
            attempt_id=sessione.id,
            exam_challenge_id=drill_punteggio.id,
            actor=director,
            score=punteggio,
            attempt_number=numero,
        )
    db.session.commit()
    log(f"sessione certificata in corso: {sara.username} davanti a {director.username}")


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

    _create_tpa_referto_chiuso(db, players)


#: Una partita intera «al 3», finita 3 a 1: uno spacca e chiude, una chiusura
#: in un turno, una difesa premeditata, un fallo, un primo tiro di calcio. E'
#: cio' che la pagina del referto chiuso deve far vedere: errori di tipi
#: diversi, e almeno un numero in ciascuna riga dei «triangoli migliori».
REFERTO_CHIUSO = (
    ["3", "9", "end"]  # 1-0: spacca e chiude
    + [
        "0",
        "end",
        "2",
        "S",
        "x",
        "end",
        "1",
        "K-in",
        "M",
        "n",
        "end",
        "6",
        "end",
    ]  # 2-0
    + ["1", "3", "M", "end", "2", "M", "P", "end", "4", "end"]  # 2-1
    + ["1", "2", "S", "end", "0", "K", "end", "7", "end"]  # 3-1
)


def _create_tpa_referto_chiuso(db, players):
    """Una seconda sfida, fra altri due giocatori, col referto gia' chiuso.

    Fra altri due perche' le pagine di Marco Rossi — profilo, statistiche,
    elenco delle sfide — sono gia' fotografate, e una sua partita in piu' le
    cambierebbe tutte senza che l'interfaccia si sia mossa.
    """
    from models.base import utc_now
    from models.individual_match.match_models import IndividualMatch
    from models.status_enum import Discipline, MatchStatus
    from models.tpa.services import TpaRefertoService

    compilatore, avversario = players[1], players[4]
    try:
        match = IndividualMatch(
            player1_id=compilatore.id,
            player2_id=avversario.id,
            location="Biliardo Centrale",
            scheduled_at=utc_now(),
            status=MatchStatus.IN_PROGRESS,
            discipline=Discipline.NINE_BALL.value,
            distance=3,
            is_race_to=True,
            started_at=utc_now(),
        )
        db.session.add(match)
        db.session.commit()

        referto = TpaRefertoService.open_referto(match.id, compilatore.id)
        for comando in REFERTO_CHIUSO:
            TpaRefertoService.press(referto.id, compilatore.id, comando)
        TpaRefertoService.close(referto.id, compilatore.id)
        db.session.commit()
        log(f"referto TPA chiuso: match #{match.id}, referto #{referto.id}")
    except Exception as exc:  # pragma: no cover - il seed non deve bloccarsi qui
        log(f"referto TPA chiuso non creato ({exc.__class__.__name__}: {exc})")


def _create_prove(db, director, venue):
    """Due competizioni di prova (ADR-058) per la pagina «Fare una prova».

    La prima resta a iscrizioni aperte con i fittizi al minimo: e' la
    schermata dei tre pulsanti e del banner con l'interruttore dei
    suggerimenti. La seconda e' avviata e ha un turno simulato: e' la
    schermata dei pulsanti di simulazione, con meta' partite chiuse dai
    giocatori e meta' in attesa del direttore — esattamente cio' che il
    direttore vede dopo «Simula il turno».

    Tutto passa dai servizi della prova, non da scorciatoie: i nomi dei
    fittizi vengono da `models/prova/nomi.py`, i risultati dal
    `SimulationService` col generatore gia' fissato da `SEED`. Le prove
    nascono per ultime perche' gli id delle gare precedenti stanno nel
    manifest delle schermate e non devono spostarsi.
    """
    from models.competition.inscription_service import InscriptionService
    from models.competition.services import GaraService
    from models.base import utc_now
    from models.prova.service import ProvaService
    from models.prova.simulation_service import SimulationService
    from models.prova.visibility import prova_visibili
    from models.status_enum import Discipline

    today = date.today()
    prove = []
    with prova_visibili():
        for name, discipline, giocata in (
            ("Prova - Palla 9", Discipline.NINE_BALL.value, False),
            ("Prova - Palla 8", Discipline.EIGHT_BALL.value, True),
        ):
            gara = GaraService.create_gara(
                number=1,
                name=name,
                date=today + timedelta(days=1),
                discipline=discipline,
                distance=4,
                campionato_id=None,
                director_id=director.id,
                creator_id=director.id,
                time=time(21, 0),
                rounds_count=3,
                min_participants=6,
                max_participants=8,
                billiard_hall_id=venue.id,
                location=venue.name,
                is_race_to=True,
                classification_system="WINS",
                **ProvaService.campi_di_creazione(),
            )
            db.session.commit()
            now = utc_now()
            InscriptionService.open_inscriptions(
                gara_id=gara.id,
                inscription_start=now - timedelta(days=1),
                inscription_end=datetime.combine(gara.date, time(17, 0)),
            )
            db.session.commit()
            iscritti = ProvaService.iscrivi_fittizi(gara.id, "minimo")
            db.session.commit()
            if giocata:
                _avvia_primo_turno(db, gara)
                esito = SimulationService.simula_turno(gara.id)
                db.session.commit()
                log(
                    f"«{gara.name}»: prova avviata, turno simulato "
                    f"({esito.partite_chiuse} partite chiuse)"
                )
            else:
                log(f"«{gara.name}»: prova a iscrizioni aperte, {iscritti} fittizi")
            prove.append(gara)
    return prove


DEMO_DIRECTOR_PROVE = ("Franco Galli", "franco.galli@example.com")


def _create_prove_forme(db, venue, challenges):
    """Quattro prove per le card che il resto del dataset non produce.

    La guida spiega come il direttore segna un trio, una partita a set e la
    prova al posto della X, e come li corregge: senza queste gare quelle card
    non esistono da nessuna parte e le figure non si possono generare.

    Sono **prove** (ADR-058) per non toccare le schermate che c'erano gia':
    una gara vera in corso comparirebbe fra le gare «In diretta ora» della
    home e delle dashboard, e cambierebbe immagini che non c'entrano. Una
    prova e' invisibile fuori dalla sua pagina. Nascono per ultime, come le
    altre due, perche' gli id delle gare precedenti stanno nel manifest.

    Le dirige un **secondo direttore**, non Luca Bianchi: le prove aperte di un
    direttore compaiono nella sua dashboard e oltre la terza il modulo della
    gara nuova avvisa che non se ne possono aprire altre, quindi con Luca
    sarebbero cambiate la sua dashboard e le schermate della nuova gara.

    - gara 8, trio chiuso con l'altra partita del turno ancora aperta: la card
      del trio concluso ha «Correggi»;
    - gara 9, trio a meta': la card con i tre lati e gli stepper;
    - gara 10, partite a set: una chiusa, da correggere, e una al secondo set;
    - gara 11, X con esercizio: le partite del turno chiuse e la prova
      dichiarata dal giocatore ma non convalidata, quindi la fascia dice
      «Prima di avviare il turno 2».
    """
    from models.base import utc_now
    from models.challenge.services import ChallengeService
    from models.competition.inscription_service import InscriptionService
    from models.competition.round_service import RoundService
    from models.competition.services import GaraService
    from models.match.match_service import MatchService
    from models.match.models import Match
    from models.match.trio_scoring_service import TrioScoringService
    from models.prova.service import ProvaService
    from models.prova.visibility import prova_visibili
    from models.status_enum import Discipline

    from models import User
    from models.user.role_enum import UserRole

    numeriche = [c for c in challenges if not c.pass_fail_only]
    if not numeriche:
        log("prove con trio, set e X non create: nessun esercizio a punteggio")
        return []

    director = User(
        username=DEMO_DIRECTOR_PROVE[0],
        email=DEMO_DIRECTOR_PROVE[1],
        role=UserRole.DIRECTOR.value,
    )
    director.set_password(DEMO_PASSWORD)
    director.is_verified = True
    director.onboarding_completed = True
    db.session.add(director)
    db.session.commit()

    def nuova(name: str, iscritti: int, **opzioni):
        gara = GaraService.create_gara(
            number=1,
            name=name,
            date=date.today() + timedelta(days=1),
            discipline=Discipline.EIGHT_BALL.value,
            campionato_id=None,
            director_id=director.id,
            creator_id=director.id,
            time=time(21, 0),
            rounds_count=3,
            min_participants=iscritti,
            max_participants=iscritti,
            billiard_hall_id=venue.id,
            location=venue.name,
            is_race_to=True,
            classification_system="WINS",
            **ProvaService.campi_di_creazione(),
            **opzioni,
        )
        db.session.commit()
        now = utc_now()
        InscriptionService.open_inscriptions(
            gara_id=gara.id,
            inscription_start=now - timedelta(days=1),
            inscription_end=datetime.combine(gara.date, time(17, 0)),
        )
        db.session.commit()
        ProvaService.iscrivi_fittizi(gara.id, "minimo")
        db.session.commit()
        _avvia_primo_turno(db, gara)
        return gara

    def partite(gara):
        return (
            Match.query.filter_by(gara_id=gara.id, round_number=1)
            .order_by(Match.id)
            .all()
        )

    gare = []
    with prova_visibili():
        # Trio chiuso, con l'altra partita del turno ancora aperta.
        gara = nuova("Prova - Trio", 5, distance=4, odd_number_policy="trio")
        for match in partite(gara):
            if match.is_trio:
                TrioScoringService.set_racks_won(
                    match.trio_match.id, (3, 2, 1), director.id
                )
            elif not match.is_bye:
                _score_match(db, match, partial=True)
        db.session.commit()
        gare.append(gara)

        # Trio a meta' del primo girone.
        gara = nuova("Prova - Trio in corso", 5, distance=4, odd_number_policy="trio")
        for match in partite(gara):
            if match.is_trio:
                TrioScoringService.set_racks_won(
                    match.trio_match.id, (2, 1, 0), director.id
                )
            elif not match.is_bye:
                _score_match(db, match, partial=True)
        db.session.commit()
        gare.append(gara)

        # Partite a set: la prima chiusa, la seconda al secondo set.
        gara = nuova(
            "Prova - Set",
            4,
            distance=3,
            is_multi_set=True,
            match_distance=2,
            is_race_to_sets=True,
        )
        chiusa, aperta = partite(gara)[:2]
        for match, set_giocati in (
            (chiusa, ((3, 1), (3, 2))),
            (aperta, ((3, 2), (1, 1))),
        ):
            for p1, p2 in set_giocati:
                MatchService.start_next_set(match.id)
                db.session.commit()
                MatchService.set_current_set_racks(match.id, p1, p2)
                db.session.commit()
        gare.append(gara)

        # X con esercizio: partite chiuse, prova dichiarata e non convalidata.
        gara = nuova(
            "Prova - X con esercizio",
            5,
            distance=4,
            odd_number_policy="bye_with_challenge",
            x_challenge_id=numeriche[0].id,
        )
        for match in partite(gara):
            if match.is_bye:
                tentativo = ChallengeService.create_x_replacement_attempt(
                    user_id=match.player1_id, gara_id=gara.id, round_number=1
                )
                db.session.commit()
                ChallengeService.complete_x_replacement_attempt(tentativo.id, 3)
            else:
                _score_match(db, match)
        db.session.commit()
        RoundService.update_round_progression(gara.id)
        db.session.commit()
        gare.append(gara)

    log(
        "prove per trio, set e X: "
        + ", ".join(f"«{g.name}» (gara {g.id})" for g in gare)
    )
    return gare


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
        # Conclusa come nella realta': il direttore preme «Termina gara», e
        # da li' nasce la classifica finale — quella che il podio, il
        # piazzamento in dashboard e lo storico leggono. Senza, la gara
        # risultava conclusa solo per stato derivato: niente vincitore.
        from models.competition.services import GaraService

        GaraService.complete(gara_conclusa.id)
        db.session.commit()
        log(f"«{gara_conclusa.name}»: terminata, classifica finale scritta")

        _open_and_fill(db, gara_in_corso, players)
        _play_rounds(db, gara_in_corso, rounds=2, leave_open_for=players[0])

        _open_and_fill(db, gara_iscrizioni, players[:5])

        _backdate_gare(db, [gara_conclusa, gara_in_corso])
        challenges = _create_challenges(db, director)
        _add_challenge_to_gara(db, gara_in_corso, challenges)
        _allena_su_challenge(db, players[0], challenges)
        _popola_esercizi(db, players, challenges)
        _prove_a_colpi(db, players[0], challenges)
        _crea_scheda(db, players[0], challenges)
        # Dopo la scheda: l'istruttore apre la scheda di Marco, che deve gia'
        # esistere, e l'andamento legge **anche** le sedute (ADR-068) —
        # seminarlo prima darebbe un radar costruito su metà delle fonti.
        _istruttore_e_allievi(db, players, challenges)
        _andamento_e_obiettivo(db, players[0], challenges)
        _create_squadre(db, gara_iscrizioni, players[:5])
        _create_gara_bozza(db, campionato, director, venue)
        _create_gara_tabellone(db, director, venue, players)
        _create_individual_match(db, players)
        _create_esami(db, director, players, challenges, venue)
        _create_tpa_referto(db, players)
        _create_prove(db, director, venue)
        _create_prove_forme(db, venue, challenges)

        print("\nFatto. Credenziali dimostrative:")
        print(f"  direttore: {DEMO_DIRECTOR[0]} / {DEMO_PASSWORD}")
        print(f"  giocatore: {DEMO_PLAYERS[0][0]} / {DEMO_PASSWORD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
