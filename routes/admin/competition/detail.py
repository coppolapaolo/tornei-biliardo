# routes/admin/competition/detail.py
"""Gara detail view - unified for all user roles."""

from typing import Optional

from flask import (
    render_template,
    request,
    url_for,
)
from flask_login import current_user

from models import (
    db,
    Gara,
    Inscription,
    Match,
)
from models.status_enum import (
    GaraStatus,
    MatchStatus,
    Discipline,
    ProvaDerivedStatus,
)
from models.matchmaking.configuration import MatchmakingStrategy
from models.classification.models import RoundClassification, GaraClassification
from models.competition.spareggio_service import SpareggioService

from . import competition_bp


def _plays_in(match, user_id: int) -> bool:
    """Vero se l'utente e' uno dei giocatori della partita (trio compreso)."""
    if match.player1_id == user_id or match.player2_id == user_id:
        return True
    return bool(
        match.is_trio and match.trio_match and match.trio_match.player3_id == user_id
    )


def _iscrizioni(gara_id: int):
    """Le iscrizioni della gara, in ordine di username (visibili a tutti)."""
    from models.user.models import User

    return (
        Inscription.query.filter_by(gara_id=gara_id)
        .join(User, Inscription.user_id == User.id)
        .order_by(User.username)
        .all()
    )


def contesto_direzione(gara: Gara, inscriptions=None) -> dict:
    """Il contesto di chi dirige: co-direttori, candidati, permessi, iscrivibili.

    Lo usano la pagina della gara e «Impostazioni gara», che mostrano le
    stesse sezioni (direzione di gara, squadre, categorie, tavoli): calcolarlo
    in un posto solo evita che le due pagine offrano candidati diversi.
    """
    from models.user.models import User, DirectorAssignment

    gara_id = gara.id
    if inscriptions is None:
        inscriptions = _iscrizioni(gara_id)

    # Utenti disponibili per iscrizione da parte di director/admin
    available_users = None
    if gara.status == GaraStatus.INSCRIPTION.value:
        active_count = gara.get_active_inscriptions_count()
        if gara.max_participants is None or active_count < gara.max_participants:
            inscribed_user_ids = [i.user_id for i in inscriptions if not i.is_withdrawn]
            from models.user.role_enum import UserRole

            available_users = (
                User.query.filter(User.deleted_at.is_(None))
                .filter(User.role != UserRole.ADMIN.value)
                .filter(
                    ~User.id.in_(inscribed_user_ids) if inscribed_user_ids else True
                )
                .order_by(User.username)
                .all()
            )

    inherited_directors = []
    inherited_director_ids = []
    if gara.campionato_id and gara.campionato:
        inherited_directors = list(gara.campionato.directors)
        inherited_director_ids = [d.id for d in inherited_directors]

    assigned_director_ids = (
        db.session.query(DirectorAssignment.user_id)
        .filter(
            DirectorAssignment.entity_type == "gara",
            DirectorAssignment.entity_id == gara.id,
        )
        .all()
    )
    assigned_director_ids = [d[0] for d in assigned_director_ids]
    if gara.is_standalone and gara.director_id:
        assigned_director_ids.append(gara.director_id)
    excluded_director_ids = set(assigned_director_ids) | set(inherited_director_ids)

    # Chi si può proporre come co-direttore: i direttori della zona della
    # gara, non tutti quelli della piattaforma (`director_candidates.py`).
    from models.competition.director_candidates import direttori_candidati

    users = direttori_candidati(
        gara,
        escludi_ids=excluded_director_ids,
        richiedente_id=current_user.id,
    )

    is_gara_director = (
        db.session.query(DirectorAssignment)
        .filter(
            DirectorAssignment.entity_type == "gara",
            DirectorAssignment.entity_id == gara.id,
            DirectorAssignment.user_id == current_user.id,
        )
        .first()
        is not None
    )
    is_campionato_director = False
    if not gara.is_standalone and gara.campionato_id:
        is_campionato_director = (
            db.session.query(DirectorAssignment)
            .filter(
                DirectorAssignment.entity_type == "campionato",
                DirectorAssignment.entity_id == gara.campionato_id,
                DirectorAssignment.user_id == current_user.id,
            )
            .first()
            is not None
        )
    can_manage_directors = current_user.is_admin or (
        current_user.is_director
        and (
            is_gara_director
            or is_campionato_director
            or (gara.is_standalone and gara.director_id == current_user.id)
        )
    )

    # Squadre (US-2/3/8/9) e categorie (ADR-049): esistono solo dove servono.
    from models.squadra.service import SquadraService
    from models.categoria.service import CategoriaService
    from .categorie import avviso_senza_categoria

    squadre, squadre_all, squadra_counts, squadre_editable = [], [], {}, False
    if gara.separate_teammates:
        squadre = SquadraService.list_for_gara(gara)
        squadre_editable = SquadraService.is_editable(gara)
        squadre_all = SquadraService.list_for_gara(gara, include_inactive=True)
        squadra_counts = SquadraService.counts_by_squadra(gara.id)

    categorie, categorie_all, categoria_counts = [], [], {}
    categorie_editable, iscritti_senza_categoria, avviso_categorie = False, 0, ""
    if gara.effective_has_handicap:
        categorie = CategoriaService.list_for_gara(gara)
        categorie_editable = CategoriaService.can_edit_inscription(gara, current_user)
        categorie_all = CategoriaService.list_for_gara(gara, include_inactive=True)
        categoria_counts = CategoriaService.counts_by_categoria(gara.id)
        iscritti_senza_categoria = CategoriaService.count_senza_categoria(gara.id)
        avviso_categorie = avviso_senza_categoria(gara)

    return {
        "inscriptions": inscriptions,
        "available_users": available_users,
        "users": users,
        "inherited_directors": inherited_directors,
        "can_manage_directors": can_manage_directors,
        "show_admin_management": current_user.is_admin,
        "show_director_management": current_user.is_director and can_manage_directors,
        "squadre": squadre,
        "squadre_all": squadre_all,
        "squadra_counts": squadra_counts,
        "squadre_editable": squadre_editable,
        "squadra_owner_is_campionato": bool(gara.campionato_id),
        "categorie": categorie,
        "categorie_all": categorie_all,
        "categoria_counts": categoria_counts,
        "categorie_editable": categorie_editable,
        "iscritti_senza_categoria": iscritti_senza_categoria,
        "avviso_categorie": avviso_categorie,
        "categoria_owner_is_campionato": bool(gara.campionato_id),
        "prova_iscrizioni": _prova_iscrizioni(gara),
    }


def _prova_iscrizioni(gara: Gara):
    """Quanti fittizi aggiungerebbe ciascun pulsante della prova (ADR-058)."""
    if not gara.is_prova:
        return None
    from models.prova.service import MODALITA_ISCRIZIONE, ProvaService

    return {
        modalita: ProvaService.quanti_da_iscrivere(gara, modalita)
        for modalita in MODALITA_ISCRIZIONE
    }


def _esercizi_turni(gara: Gara, all_matches) -> list:
    """Gli esercizi fra i turni da registrare dalla pagina, a gara in corso.

    Uno per `GaraChallenge` attivo; quelli il cui turno e' concluso portano
    una riga per iscritto attivo con tentativi e migliore
    (`direttore_view.esercizi_fra_i_turni`). Fuori dal gioco, o in una gara
    che non li ammette, niente.
    """
    if gara.status != GaraStatus.PLAYING.value or not gara.ammette_esercizi_fra_i_turni:
        return []
    from models.competition.direttore_view import (
        esercizi_fra_i_turni,
        turni_conclusi,
    )
    from models.competition.gara_challenge import GaraChallengeAttempt
    from models.competition.gara_challenge_service import GaraChallengeService

    esercizi = GaraChallengeService.get_gara_challenges(gara.id)
    if not esercizi:
        return []

    # Chi ha dato forfait non e' piu' al tavolo: non ha esercizi da registrare,
    # e non blocca il turno dopo (`pendenze_turno`).
    iscrizioni = (
        Inscription.query.filter_by(gara_id=gara.id, is_withdrawn=False)
        .filter(Inscription.is_waitlist.is_(False))
        .filter(Inscription.is_forfeit.isnot(True))
        .all()
    )
    giocatori = sorted(
        ((i.user_id, i.user.username) for i in iscrizioni if i.user),
        key=lambda g: g[1].lower(),
    )
    tentativi: dict = {}
    for t in GaraChallengeAttempt.query.filter(
        GaraChallengeAttempt.gara_challenge_id.in_([e.id for e in esercizi]),
        GaraChallengeAttempt.completed.is_(True),
    ).order_by(GaraChallengeAttempt.attempt_number):
        tentativi.setdefault((t.gara_challenge_id, t.user_id), []).append(
            (t.score, t.passed, t.id)
        )
    return esercizi_fra_i_turni(
        esercizi,
        turni_chiusi=turni_conclusi(all_matches),
        giocatori=giocatori,
        tentativi=tentativi,
        turno_avviato=max((m.round_number for m in all_matches or []), default=0),
        casuale=gara.creates_all_rounds_at_startup(),
    )


def _vista_direttore(
    gara: Gara,
    all_matches,
    available_tables,
    occupied_tables,
    has_ssr_data: bool,
    has_unresolved_tiebreakers: bool,
    user_id: Optional[int] = None,
) -> dict:
    """Fase, striscia, comando, conteggi e partite per `direttore/gara.html`."""
    from models.competition.direttore_view import (
        conteggi_turno,
        contesto_campionato,
        fase_della_gara,
        partite_del_turno,
        prima_in_attesa,
        scheda_partita,
        spareggio_nella_striscia,
        stato_partita,
        striscia,
        tavoli_del_turno,
    )
    from models.dashboard.comandi import comando_per

    fase = fase_della_gara(gara.status, playoff=gara.is_playoff)
    reale = gara.get_real_status()
    turni_conclusi = reale == ProvaDerivedStatus.TOURNAMENT_COMPLETED.value
    con_spareggio = spareggio_nella_striscia(
        fase,
        ha_dati_ssr=has_ssr_data,
        parimerito_aperti=has_unresolved_tiebreakers,
        turni_conclusi=turni_conclusi,
    )
    comando = comando_per(gara)

    conteggi = None
    menu_turno = None
    partite_turno = []
    turno_concluso = False
    prossima_in_attesa = None
    tavoli_turno = []
    # Lo stato di ogni card (canvas 3.2–3.4), per ogni turno: i turni chiusi
    # restano in pagina come righe.
    stati_partite = {m.id: stato_partita(m).value for m in (all_matches or [])}
    if gara.status == GaraStatus.PLAYING.value:
        turno = gara.display_round or 1
        partite_turno = partite_del_turno(all_matches or [], turno, user_id)
        # Il turno che si vede e' concluso quando ogni sua partita lo e' (la X
        # compresa): con i turni pre-generati `comando` parla del turno di
        # `current_round`, che puo' essere quello prima.
        turno_concluso = bool(partite_turno) and all(
            stati_partite[m.id] in ("conclusa", "x") for m in partite_turno
        )
        prossima_in_attesa = prima_in_attesa(all_matches or [], turno)
        tavoli_turno = tavoli_del_turno(all_matches or [], available_tables)
        conteggi = conteggi_turno(
            all_matches or [],
            turno,
            gara.rounds_count or turno,
            available_tables,
            occupied_tables,
        )
        # Il menu del turno: annullarne l'avvio, finche' nessuna partita ha un
        # triangolo (`Gara.can_cancel_round`). Sta accanto al turno **che si
        # vede** (`display_round`): con i turni pre-generati `current_round`
        # resta indietro mentre il turno dopo e' gia' in gioco, e un menu
        # agganciato al turno chiuso non lo troverebbe nessuno. Nella formula
        # casuale l'unico annullamento e' quello dell'avvio della gara, che
        # cancella tutti i turni insieme: si puo' finche' nessuna partita di
        # nessun turno ha segnato.
        if gara.creates_all_rounds_at_startup():
            menu_turno = {
                "turno": turno,
                "tipo": "gara",
                "annullabile": all(
                    gara.can_cancel_round(n)
                    for n in range(1, (gara.rounds_count or turno) + 1)
                ),
            }
        elif turno == 1:
            menu_turno = {
                "turno": 1,
                "tipo": "primo",
                "annullabile": gara.can_cancel_round(1),
            }
        else:
            menu_turno = {
                "turno": turno,
                "tipo": "turno",
                "annullabile": gara.can_cancel_round(turno),
            }

    schede_partite = {m.id: scheda_partita(m) for m in partite_turno}
    # A turno concluso le partite sono righe, ma la prova della X ancora da
    # convalidare trattiene il turno dopo (`pendenze_turno`): resta card, con
    # «Convalida», altrimenti il direttore non avrebbe dove sbloccarlo.
    x_da_convalidare = [
        m.id
        for m in partite_turno
        if turno_concluso
        and schede_partite[m.id].prova is not None
        and schede_partite[m.id].prova.stato.value != "convalidata"
    ]

    return {
        **_vista_tabellone(gara, all_matches or []),
        "esercizi_turni": _esercizi_turni(gara, all_matches or []),
        "x_da_convalidare": x_da_convalidare,
        "fase": fase,
        "striscia": striscia(
            fase, con_spareggio=con_spareggio, con_iscrizioni=not gara.is_playoff
        ),
        "comando": comando,
        "conteggi": conteggi,
        "menu_turno": menu_turno,
        "partite_turno": partite_turno,
        "turno_concluso": turno_concluso,
        "prossima_in_attesa": prossima_in_attesa,
        "tavoli_turno": tavoli_turno,
        "tavoli_occupanti": {
            t.nome: " – ".join(t.giocatori) for t in tavoli_turno if not t.libero
        },
        "stati_partite": stati_partite,
        # La forma di ogni card del turno che si vede: trio, set, X con
        # esercizio (i turni chiusi sono righe e non ne hanno bisogno).
        "schede_partite": schede_partite,
        # La gara dentro un campionato: kicker, «Dal campionato», testi di
        # chiusura. `None` per una gara singola.
        "campionato_ctx": contesto_campionato(gara),
    }


def _vista_tabellone(gara: Gara, all_matches) -> dict:
    """Il tabellone al posto della classifica, nelle gare a eliminazione (#240).

    Prima del sorteggio la forma che il tabellone avra' con gli iscritti di
    adesso; dopo, l'albero intero con i nodi futuri, i nomi dei turni
    («Semifinali»), dove va chi vince ogni partita e il tabellone compatto dei
    turni vicini a quello che si vede; a gara conclusa la classifica a bande
    (ADR-040). Niente di tutto questo per le gare a turni, che restano come
    sono.
    """
    from models.competition.tabellone_view import (
        bande_finali,
        costruisci_tabellone,
        destinazioni,
        forma_tabellone,
    )
    from models.matchmaking.configuration import BRACKET_STRATEGIES

    vista: dict = {
        "is_tabellone": gara.matchmaking_strategy in BRACKET_STRATEGIES,
        "nomi_turni": {},
        "tabellino": [],
        "destinazioni": {},
        "forma": None,
        "forma_stima": False,
        "bande_finali": [],
        "righe_bande": [],
        "turni_giocati": max((m.round_number or 0 for m in all_matches), default=0),
    }
    if not vista["is_tabellone"]:
        return vista

    if gara.status in (GaraStatus.SETUP.value, GaraStatus.INSCRIPTION.value):
        forma = forma_tabellone(
            gara.get_active_inscriptions_count(),
            gara.matchmaking_strategy,
            double_ko_rounds=gara.double_ko_rounds,
        )
        # Senza abbastanza iscritti la forma si stima sulla capienza: e' cio'
        # che il direttore sta preparando, e la riga lo dice.
        if forma is None and gara.max_participants:
            forma = forma_tabellone(
                gara.max_participants,
                gara.matchmaking_strategy,
                double_ko_rounds=gara.double_ko_rounds,
            )
            vista["forma_stima"] = forma is not None
        vista["forma"] = forma

    tabellone = costruisci_tabellone(
        all_matches,
        strategy=gara.matchmaking_strategy,
        finalina=bool(gara.third_place_match),
    )
    if tabellone is None:
        return vista

    turno = (
        gara.display_round or 1
        if gara.status == GaraStatus.PLAYING.value
        else vista["turni_giocati"]
    )
    vista["nomi_turni"] = tabellone.nomi_turni()
    vista["tabellino"] = tabellone.compatto(turno)
    vista["destinazioni"] = destinazioni(
        tabellone, [m for m in all_matches if not MatchStatus.is_finished(m.status)]
    )
    if gara.status == GaraStatus.COMPLETED.value:
        from models.classification.bracket_standings import bracket_positions

        bande = bande_finali(bracket_positions(gara), tabellone)
        vista["bande_finali"] = bande
        vista["righe_bande"] = [riga for banda in bande for riga in banda.righe]
    return vista


@competition_bp.route("/<int:gara_id>")
def gara_detail(gara_id):
    """
    Vista unificata per dettaglio gara.
    Si adatta automaticamente in base ai permessi dell'utente:
    - Admin/Director con permessi → Vista gestionale completa
    - Player iscritto → Vista personale con le sue partite
    - Guest/Player non iscritto → Vista pubblica read-only
    """
    gara = db.get_or_404(Gara, gara_id)

    # Forza un refresh per assicurarsi di avere i dati più aggiornati
    db.session.refresh(gara)

    # Determina permessi e contesto utente
    user_can_manage = False
    user_inscription = None

    if current_user.is_authenticated:
        # Check se può gestire questa gara
        user_can_manage = current_user.can_manage_competition(gara_id)

        # Check iscrizione (solo per non-admin)
        if not current_user.is_admin:
            user_inscription = Inscription.query.filter_by(
                gara_id=gara_id, user_id=current_user.id
            ).first()

    # Carica dati in base al contesto utente
    if user_can_manage:
        # ADMIN/DIRECTOR VIEW: Carica tutto per gestione
        matches = (
            Match.query.filter_by(gara_id=gara_id)
            .order_by(Match.round_number, Match.id)
            .all()
        )
        all_matches = (
            matches  # Needed for _round_management.html round completion check
        )

    elif user_inscription:
        # PLAYER VIEW: Solo le sue partite
        matches = (
            Match.query.filter_by(gara_id=gara_id)
            .filter(
                db.or_(
                    Match.player1_id == current_user.id,
                    Match.player2_id == current_user.id,
                )
            )
            .order_by(Match.round_number, Match.id)
            .all()
        )
        all_matches = (
            Match.query.filter_by(gara_id=gara_id)
            .order_by(Match.round_number, Match.id)
            .all()
        )
    else:
        # GUEST VIEW: Tutte le partite (read-only)
        matches = None
        all_matches = (
            Match.query.filter_by(gara_id=gara_id)
            .order_by(Match.round_number, Match.id)
            .all()
        )

    # Chi si puo' aggiungere alla direzione, chi puo' farlo, chi c'e' gia':
    # lo stesso contesto della pagina «Impostazioni gara». Le iscrizioni le
    # vedono tutti.
    inscriptions = _iscrizioni(gara_id)
    contesto = contesto_direzione(gara, inscriptions) if user_can_manage else {}
    users = contesto.get("users")
    can_manage_directors = contesto.get("can_manage_directors", False)
    show_admin_management = contesto.get("show_admin_management", False)
    show_director_management = contesto.get("show_director_management", False)
    inherited_directors = contesto.get("inherited_directors", [])
    available_users = contesto.get("available_users")

    match_can_modify = {}
    if user_can_manage:
        # Add match modification permissions
        from models.competition.round_manager import AdvancedRoundManager

        for match in matches:
            can_modify, _ = AdvancedRoundManager.can_modify_match(match.id)
            match_can_modify[match.id] = can_modify

    # Ottieni l'ultima classificazione disponibile per turni completati
    current_round_classification = None
    latest_round_with_classification = None

    # Check if SSR has been applied (positions adjusted for tiebreakers)
    # If so, skip recalculation to preserve SSR-corrected positions
    # Just check if any SSR score exists, regardless of gara status
    ssr_has_been_applied = (
        GaraClassification.query.filter(
            GaraClassification.gara_id == gara_id,
            GaraClassification.spot_shot_wins.isnot(None),
        ).first()
        is not None
    )

    if gara.current_round > 0:
        # For Random strategy: show overall classification if ANY matches are completed
        # For other strategies: show classification only for completed rounds
        if gara.matchmaking_strategy == MatchmakingStrategy.RANDOM.value:
            # Random: classifica complessiva da tutte le partite finite —
            # chiuse dal direttore o confermate dai due giocatori, che sono
            # finite quanto le altre (`finished_values`, CLAUDE.md).
            completed_count = (
                Match.query.filter_by(gara_id=gara_id)
                .filter(Match.status.in_(MatchStatus.finished_values()))
                .count()
            )

            if completed_count > 0:
                # Usa il numero massimo di turni (query dal database)
                # per la classifica complessiva
                from sqlalchemy import func

                max_round = (
                    db.session.query(func.max(Match.round_number))
                    .filter(Match.gara_id == gara_id)
                    .scalar()
                    or gara.current_round
                )

                # Skip recalculation if SSR has been applied (preserva
                # le posizioni corrette)
                if not ssr_has_been_applied:
                    RoundClassification.calculate_classification_after_round(
                        gara_id, max_round
                    )

                # `ordered_for_display`, non `order_by(position)`: i parimerito
                # condividono la posizione (#67) e vanno elencati in ordine di
                # estrazione.
                classification = RoundClassification.ordered_for_display(
                    gara_id, max_round
                )
                if classification:
                    current_round_classification = classification
                    # For Random, use 0 to indicate overall classification
                    latest_round_with_classification = 0
        else:
            # Amalfi/other strategies: classification per completed round
            def is_round_completed(round_number):
                round_matches = Match.query.filter_by(
                    gara_id=gara_id, round_number=round_number
                ).all()
                if not round_matches:
                    return False
                # Exclude bye matches; VALIDATED conta come finito (post-COMPLETED).
                finished = (
                    MatchStatus.CLOSED_UNILATERALLY.value,
                    MatchStatus.CONFIRMED_BY_BOTH.value,
                )
                return all(
                    match.status in finished or match.is_bye for match in round_matches
                )

            # Cerca la classificazione del turno completato più recente
            for round_num in range(gara.current_round, 0, -1):
                if is_round_completed(round_num):
                    # Skip recalculation if SSR has been applied (preserva
                    # le posizioni corrette)
                    if not ssr_has_been_applied:
                        # SEMPRE ricalcola la classificazione per garantire dati
                        # aggiornati. Necessario perché i risultati potrebbero essere
                        # stati modificati dopo il calcolo iniziale
                        RoundClassification.calculate_classification_after_round(
                            gara_id, round_num
                        )

                    # Carica la classificazione (parimerito in ordine di
                    # estrazione, vedi sopra)
                    classification = RoundClassification.ordered_for_display(
                        gara_id, round_num
                    )

                    if classification:
                        current_round_classification = classification
                        latest_round_with_classification = round_num
                        break

    # Get challenge data
    challenge_classification = None
    gara_challenges = None
    user_challenge_data = None

    if gara.ammette_esercizi_fra_i_turni:
        from models.competition.gara_challenge_service import GaraChallengeService

        if GaraChallengeService.has_active_challenges(gara_id):
            if user_can_manage:
                # Admin view: challenge classification
                challenge_classification = (
                    GaraChallengeService.update_gara_classification(gara_id)
                )
            gara_challenges = GaraChallengeService.get_gara_challenges(gara_id)

    # Per player iscritto: carica challenge personali
    if user_inscription and gara_challenges:
        user_challenge_data = []
        for gara_challenge in gara_challenges:
            user_attempts = gara_challenge.get_user_attempts(current_user.id)
            best_attempt = gara_challenge.get_user_best_attempt(current_user.id)
            can_attempt = gara_challenge.can_user_attempt(current_user.id)

            user_challenge_data.append(
                {
                    "gara_challenge": gara_challenge,
                    "challenge": gara_challenge.challenge,
                    "user_attempts": user_attempts,
                    "best_attempt": best_attempt,
                    "can_attempt": can_attempt,
                    "attempts_count": len(user_attempts),
                    "max_attempts": gara_challenge.max_attempts,
                }
            )

    # Get available tables for gara (for table assignment UI)
    available_tables = []
    occupied_tables = {}  # Maps table_name -> match_id
    if user_can_manage:
        from models.match.table_assignment_service import TableAssignmentService

        available_tables = TableAssignmentService.get_table_names_for_gara(gara.id)
        occupied_tables = TableAssignmentService.get_occupied_tables(gara.id)

    # Get forfeit user IDs for visual indication
    forfeit_user_ids = set(insc.user_id for insc in inscriptions if insc.is_forfeit)

    # Collegamento alla vista tabellone (US-13). Compare solo quando c'e'
    # davvero un tabellone da guardare: prima del sorteggio la pagina
    # esisterebbe ma sarebbe uno stato vuoto, e una gara a tabellone
    # antecedente allo Step 2 non ha coordinate da disegnare affatto.
    from models.matchmaking.bracket_view import has_bracket_coordinates
    from models.matchmaking.configuration import BRACKET_STRATEGIES

    has_bracket_view = gara.matchmaking_strategy in BRACKET_STRATEGIES and (
        has_bracket_coordinates(all_matches or [])
    )

    # Squadre (US-2/3/8/9) e categorie (ADR-049): per chi dirige stanno nel
    # contesto della direzione; chi guarda vede solo l'elenco attivo.
    from models.squadra.service import SquadraService
    from models.categoria.service import CategoriaService

    squadre = contesto.get("squadre", [])
    squadre_all = contesto.get("squadre_all", [])
    squadra_counts = contesto.get("squadra_counts", {})
    squadre_editable = contesto.get("squadre_editable", False)
    if gara.separate_teammates and not user_can_manage:
        squadre = SquadraService.list_for_gara(gara)
        squadre_editable = SquadraService.is_editable(gara)

    categorie = contesto.get("categorie", [])
    categorie_all = contesto.get("categorie_all", [])
    categoria_counts = contesto.get("categoria_counts", {})
    categorie_editable = contesto.get("categorie_editable", False)
    iscritti_senza_categoria = contesto.get("iscritti_senza_categoria", 0)
    avviso_categorie = contesto.get("avviso_categorie", "")
    if gara.effective_has_handicap and not user_can_manage:
        categorie = CategoriaService.list_for_gara(gara)
        categorie_editable = CategoriaService.can_edit_inscription(gara, current_user)

    # Si arriva da un'iscrizione appena conclusa (`?chiedi_squadra=1`): la
    # scelta della squadra si chiede subito, in un modale, invece di lasciarla
    # a una card dentro una linguetta che chi si iscrive non apre mai (US-8).
    # A sorteggio fatto non si chiede più: non c'è più niente da decidere.
    chiedi_squadra = bool(
        request.args.get("chiedi_squadra")
        and user_inscription
        and gara.separate_teammates
        and squadre_editable
    )

    # SSR (Spot Shot Rally) data for tiebreaker display
    ssr_groups = []
    has_ssr_data = False
    can_edit_ssr = False
    has_unresolved_tiebreakers = False

    # Only load SSR data if competition is in final stages or has SSR data
    if gara.status in [
        GaraStatus.PLAYING.value,
        GaraStatus.AWAITING_SSR.value,
        GaraStatus.COMPLETED.value,
    ]:
        # Get all SSR groups (resolved and unresolved)
        ssr_groups = SpareggioService.get_all_ssr_groups(gara_id)

        # Check if there's any SSR data to display (0 is a valid score)
        has_ssr_data = any(
            any(p["current_ssr_score"] is not None for p in group["players"])
            for group in ssr_groups
        )

        # Check for unresolved tiebreakers
        has_unresolved_tiebreakers = SpareggioService.has_unresolved_tiebreakers(
            gara_id
        )

        # Can edit SSR if user can manage and gara is in appropriate state
        can_edit_ssr = user_can_manage and gara.status in [
            GaraStatus.PLAYING.value,
            GaraStatus.AWAITING_SSR.value,
        ]

    # Build SSR scores map for classification display (0 is a valid score)
    ssr_scores_map = {}
    for group in ssr_groups:
        for player in group["players"]:
            if player["current_ssr_score"] is not None:
                ssr_scores_map[player["user_id"]] = player["current_ssr_score"]

    # Pre-compute template flags that were previously {% set %} in the template
    is_ssr_phase = gara.status == GaraStatus.AWAITING_SSR.value
    show_ssr_section = is_ssr_phase or (ssr_groups and has_ssr_data)
    is_gara_ending = (
        gara.get_real_status() == ProvaDerivedStatus.TOURNAMENT_COMPLETED.value
        and not has_unresolved_tiebreakers
    ) or (has_ssr_data and not has_unresolved_tiebreakers)
    has_scores = bool(
        current_round_classification
        and (
            any(c.rack_difference != 0 for c in current_round_classification)
            or any(c.matches_won > 0 for c in current_round_classification)
        )
    )
    ssr_needs_input = is_ssr_phase and has_unresolved_tiebreakers
    ssr_ready_to_terminate = is_ssr_phase and not has_unresolved_tiebreakers

    # "L'azionabile va prima" (UI_CONVENTIONS): con le strategie sequenziali
    # (Amalfi & co., non Random) a turno finito l'azione probabile e' avviare il
    # turno successivo / lo spareggio SSR / terminare la gara — tutti pulsanti
    # che vivono in Gestione. Su mobile Gestione risale quindi in cima e gia'
    # aperta, invece di restare collassata sotto le partite.
    # `is_gara_ending` e' escluso perche' in quel caso Gestione e' gia' in cima
    # e aperta nella sidebar (che su mobile e' order-1).
    round_action_ready = (
        user_can_manage
        and gara.status == GaraStatus.PLAYING.value
        and gara.matchmaking_strategy != MatchmakingStrategy.RANDOM.value
        and not is_gara_ending
        and gara.get_real_status()
        in (
            ProvaDerivedStatus.ROUND_COMPLETED.value,
            ProvaDerivedStatus.TOURNAMENT_COMPLETED.value,
        )
    )

    # Scorciatoia "il tuo match" (prototipo 8a): su mobile la propria partita
    # sta in cima alla vista Turni, non da cercare nella pila dei turni.
    # `all_matches` e' ordinato per turno, quindi il primo non finito e' quello
    # piu' basso — lo stesso che _match_cards_mobile mette in alto. L'admin non
    # gioca: per lui la scorciatoia non ha senso.
    my_active_match = None
    if current_user.is_authenticated and not current_user.is_admin:
        my_active_match = next(
            (
                match
                for match in (all_matches or [])
                if not MatchStatus.is_finished(match.status)
                and not match.is_bye
                and _plays_in(match, current_user.id)
            ),
            None,
        )

    # Iscrizione dalla pagina della gara (issue #61). Il pulsante mancava:
    # ci si poteva iscrivere solo dalle card di homepage e liste, quindi chi
    # arrivava qui da un link diretto non aveva alcun modo di iscriversi.
    from models.competition.invite_service import GaraInviteService

    inscription_open = GaraInviteService.inscription_open(gara)
    can_inscribe_now = (
        inscription_open
        and user_inscription is None
        and GaraInviteService.is_eligible(gara, current_user)
    )
    # Guest: non può iscriversi ora, ma deve sapere che potrebbe accedendo.
    show_login_to_inscribe = inscription_open and not current_user.is_authenticated

    # Link pubblico da condividere: solo per chi gestisce la gara — e mai per
    # una prova (ADR-058), che da fuori non deve esistere. Il template lo
    # spiega al posto del link.
    public_invite_url = None
    if user_can_manage and not gara.is_prova:
        from models.competition.services import GaraService

        token = gara.public_token or GaraService.ensure_public_token(gara_id)
        # Lo slug, quando il direttore ne ha scelto uno: e' quello che vuole
        # vedere sulla locandina, e il token continua comunque a funzionare
        # (issue #235). `public_slug_or_token` decide quale **pubblicare**.
        indirizzo = gara.slug or token
        if indirizzo:
            public_invite_url = url_for(
                "main.gara_invite", token=indirizzo, _external=True
            )

    # Chi riceve la X del primo turno. La domanda si pone solo per gare
    # amalfi/casuali col primo turno a sorteggio e i dispari gestiti dalla X,
    # e solo mentre la gara è ancora da avviare: dopo non c'è più niente da
    # decidere. Vedi models/matchmaking/bye_preference.py.
    x_choice_last_inscribed = None
    if user_can_manage and gara.current_round == 0:
        from models.matchmaking import bye_preference

        if bye_preference.choice_applies(gara):
            last_user_id = bye_preference.last_inscribed_user_id(gara)
            x_choice_last_inscribed = next(
                (
                    inscription.user
                    for inscription in inscriptions
                    if inscription.user_id == last_user_id
                ),
                None,
            )

    prova_iscrizioni = contesto.get("prova_iscrizioni")

    # La pagina del direttore e' un template a se' (canvas «Pagina gara del
    # direttore»): la striscia di fase al posto delle linguette, la fascia
    # con l'unica cosa da fare, il resto della gestione in «Impostazioni».
    vista = {}
    if user_can_manage:
        # In preparazione il desktop porta in linea il modulo della vetrina e
        # i passi (canvas 1.9): servono il contesto della vetrina e le tendine.
        if gara.status == GaraStatus.SETUP.value:
            from .preparazione import passi_della_preparazione
            from .vetrina import contesto_vetrina

            vista["passi"] = passi_della_preparazione(gara)
            if not gara.is_prova:
                vista.update(contesto_vetrina(gara))
        vista.update(
            _vista_direttore(
                gara,
                all_matches,
                available_tables,
                occupied_tables,
                has_ssr_data=has_ssr_data,
                has_unresolved_tiebreakers=has_unresolved_tiebreakers,
                user_id=current_user.id if current_user.is_authenticated else None,
            )
        )

    contesto_pagina = dict(
        gara=gara,
        **vista,
        prova_iscrizioni=prova_iscrizioni,
        x_choice_last_inscribed=x_choice_last_inscribed,
        can_inscribe_now=can_inscribe_now,
        show_login_to_inscribe=show_login_to_inscribe,
        public_invite_url=public_invite_url,
        user_can_manage=user_can_manage,
        user_inscription=user_inscription,
        inscriptions=inscriptions,
        matches=matches,
        all_matches=all_matches,
        my_active_match=my_active_match,
        users=users,
        inherited_directors=inherited_directors,
        can_manage_directors=can_manage_directors,
        show_admin_management=show_admin_management,
        show_director_management=show_director_management,
        current_round_classification=current_round_classification,
        latest_round_with_classification=latest_round_with_classification,
        challenge_classification=challenge_classification,
        gara_challenges=gara_challenges,
        user_challenge_data=user_challenge_data,
        match_can_modify=match_can_modify,
        discipline_choices=Discipline.get_choices(),
        available_tables=available_tables,
        occupied_tables=occupied_tables,
        forfeit_user_ids=forfeit_user_ids,
        has_bracket_view=has_bracket_view,
        squadre=squadre,
        squadre_all=squadre_all,
        squadra_counts=squadra_counts,
        squadre_editable=squadre_editable,
        chiedi_squadra=chiedi_squadra,
        squadra_owner_is_campionato=bool(gara.campionato_id),
        categorie=categorie,
        categorie_all=categorie_all,
        categoria_counts=categoria_counts,
        categorie_editable=categorie_editable,
        iscritti_senza_categoria=iscritti_senza_categoria,
        avviso_categorie=avviso_categorie,
        categoria_owner_is_campionato=bool(gara.campionato_id),
        available_users=available_users,
        # SSR (Spot Shot Rally) data
        ssr_groups=ssr_groups,
        has_ssr_data=has_ssr_data,
        can_edit_ssr=can_edit_ssr,
        has_unresolved_tiebreakers=has_unresolved_tiebreakers,
        ssr_scores_map=ssr_scores_map,
        # Pre-computed template flags (moved from template {% set %})
        is_ssr_phase=is_ssr_phase,
        show_ssr_section=show_ssr_section,
        is_gara_ending=is_gara_ending,
        has_scores=has_scores,
        ssr_needs_input=ssr_needs_input,
        ssr_ready_to_terminate=ssr_ready_to_terminate,
        round_action_ready=round_action_ready,
    )
    # Due chiamate letterali, non un nome in variabile: l'analisi di
    # raggiungibilita' dei template (`test_no_orphan_templates`) legge il
    # sorgente e non seguirebbe la variabile.
    if user_can_manage:
        return render_template("direttore/gara.html", **contesto_pagina)
    return render_template("gara_detail.html", **contesto_pagina)
