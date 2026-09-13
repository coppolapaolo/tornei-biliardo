"""
WithdrawPolicyService - Handles forfait and withdrawal policies for competitions.

This service centralizes the logic for handling player forfeits based on
the competition's withdraw_policy setting.
"""

from flask_babel import gettext as _

from models.base import db, utc_now
from models.transaction.manager import transactional
from .models import Gara, Inscription, WithdrawPolicy
from .inscription_service import InscriptionService


class WithdrawPolicyService:
    """Service for handling forfait and withdrawal policies."""

    # ── I ritiri decisi dal direttore ───────────────────────────────────────
    #
    # Tre strade, un'operazione atomica ciascuna: il menu della partita, il
    # trio, la riga dell'iscritto. Ognuna chiude cio' che va chiuso, applica la
    # regola della gara e avvisa il giocatore con `_notifica_ritiro`, dentro un
    # solo `@transactional`. Tutto o niente: se la notifica fallisce il ritiro
    # non resta a meta', e un ritiro fallito non manda notifiche. Il forfait
    # dichiarato dal giocatore non passa di qui e non manda notifiche.
    #
    # L'annidamento dei `@transactional` interni e' sicuro da ADR-061: salva
    # solo il piu' esterno.

    @staticmethod
    @transactional(domain="competition")
    def ritira_dalla_partita(match_id: int, user_id: int, direttore_id: int):
        """Il ritiro deciso dal direttore dal menu della partita a due.

        Stessa strada del forfait del giocatore (`MatchService.forfeit_match`,
        che applica la regola della gara), piu' la notifica.
        """
        from models.match.services import MatchService

        match = MatchService.forfeit_match(match_id=match_id, user_id=user_id)
        gara = db.session.get(Gara, match.gara_id) if match.gara_id else None
        if gara is not None:
            WithdrawPolicyService._notifica_ritiro(gara, user_id, direttore_id)
        return match

    @staticmethod
    @transactional(domain="competition")
    def ritira_dal_trio(trio_id: int, user_id: int, direttore_id: int) -> dict:
        """Il ritiro nel trio registrato dal direttore.

        Stessa strada del ritiro dichiarato dal giocatore
        (`TrioMatchService.forfeit_trio`, che applica la regola della gara),
        piu' la notifica.
        """
        from models.match.models import TrioMatch

        from .trio_service import TrioMatchService

        risultato = TrioMatchService.forfeit_trio(trio_id, user_id, direttore_id)
        trio = db.session.get(TrioMatch, trio_id)
        match = trio.match if trio is not None else None
        if match is not None and match.gara_id:
            gara = db.session.get(Gara, match.gara_id)
            if gara is not None:
                WithdrawPolicyService._notifica_ritiro(gara, user_id, direttore_id)
        return risultato

    @staticmethod
    @transactional(domain="competition")
    def ritira_iscritto(gara_id: int, user_id: int, direttore_id: int) -> str:
        """Il direttore ritira un iscritto a gara in corso.

        Serve per chi se ne va senza dirlo all'app, quando nessuno puo'
        dichiarare il forfait al posto suo. A gara in corso questa
        cancellazione **e'** il forfait di quel giocatore, e passa dalla stessa
        strada: la sua partita aperta si chiude a tavolino tenendo i triangoli
        gia' vinti, le altre si chiudono come vuole la regola della gara, trio
        compresi, e la regola decide se resta negli abbinamenti o esce. Il
        giocatore riceve la notifica una volta sola: dalla strada della partita
        o del trio quando ce n'e' una aperta, altrimenti da qui.

        Prima dell'avvio la strada e' la disiscrizione
        (`InscriptionService.admin_uninscribe_user`); a gara conclusa o in
        spareggio non c'e' piu' niente da ritirare.

        Returns: l'azione della regola, ``"forfeit_marked"`` o ``"excluded"``.
        """
        from models.exceptions import ConflictError, NotFoundError
        from models.status_enum import GaraStatus
        from models.user.models import User

        gara = db.session.get(Gara, gara_id)
        if gara is None:
            raise NotFoundError(_("Gara non trovata"))
        utente = db.session.get(User, user_id)
        nome = utente.username if utente else str(user_id)

        if gara.status != GaraStatus.PLAYING.value:
            if gara.status in (GaraStatus.SETUP.value, GaraStatus.INSCRIPTION.value):
                raise ConflictError(
                    _(
                        "La gara non è ancora partita: %(nome)s si toglie "
                        "dagli iscritti.",
                        nome=nome,
                    )
                )
            raise ConflictError(
                _("A gara conclusa o in spareggio il ritiro non si registra più.")
            )

        iscrizione = (
            db.session.query(Inscription)
            .filter_by(gara_id=gara_id, user_id=user_id, is_withdrawn=False)
            .first()
        )
        if iscrizione is None:
            raise NotFoundError(_("%(nome)s non è iscritto a questa gara.", nome=nome))
        if iscrizione.is_waitlist:
            raise ConflictError(
                _(
                    "%(nome)s è in lista d'attesa: non gioca, e non c'è un "
                    "ritiro da registrare.",
                    nome=nome,
                )
            )
        if iscrizione.is_forfeit:
            raise ConflictError(
                _("%(nome)s si è già ritirato da questa gara.", nome=nome)
            )

        esclude = gara.withdraw_policy == WithdrawPolicy.EXCLUDE.value
        partita = WithdrawPolicyService._partita_da_chiudere(gara_id, user_id)
        if partita is not None and partita.is_trio:
            WithdrawPolicyService.ritira_dal_trio(
                partita.trio_match.id, user_id, direttore_id
            )
        elif partita is not None:
            WithdrawPolicyService.ritira_dalla_partita(
                partita.id, user_id, direttore_id
            )
        else:
            # Fra un turno e l'altro, o con la X: niente da chiudere a mano,
            # resta la regola per i turni dopo.
            WithdrawPolicyService.handle_forfeit(gara_id=gara_id, user_id=user_id)
            WithdrawPolicyService._notifica_ritiro(gara, user_id, direttore_id)
        return "excluded" if esclude else "forfeit_marked"

    @staticmethod
    def _partita_da_chiudere(gara_id: int, user_id: int):
        """La partita aperta da cui parte il ritiro, o `None`.

        La prima del turno piu' basso che si puo' ancora toccare. Da li' il
        forfait tiene i triangoli gia' vinti da chi si ritira, come quello dal
        menu della partita; le altre le chiude `handle_forfeit`, a zero.
        """
        from sqlalchemy import or_

        from models.competition.round_manager import AdvancedRoundManager
        from models.match.models import Match, TrioMatch
        from models.status_enum import MatchStatus

        aperte = (
            db.session.query(Match)
            .outerjoin(TrioMatch, TrioMatch.match_id == Match.id)
            .filter(
                Match.gara_id == gara_id,
                Match.status.in_(
                    [MatchStatus.PENDING.value, MatchStatus.PLAYING.value]
                ),
                Match.is_bye == False,  # noqa: E712
                or_(
                    Match.player1_id == user_id,
                    Match.player2_id == user_id,
                    TrioMatch.player3_id == user_id,
                ),
            )
            .order_by(Match.round_number, Match.id)
            .all()
        )
        for match in aperte:
            if match.is_trio:
                trio = match.trio_match
                if trio is None or trio.is_completed or trio.awaiting_confirmation:
                    continue
            if AdvancedRoundManager.motivo_turno_superato(match) is None:
                return match
        return None

    @staticmethod
    def _notifica_ritiro(gara: Gara, user_id: int, direttore_id: int) -> None:
        """Dice al giocatore chi l'ha ritirato e cosa comporta la regola.

        L'unico punto che compone la notifica di un ritiro deciso dal
        direttore, in tre varianti: resta negli abbinamenti, esce dalla gara,
        tabellone. Si chiama dentro l'operazione atomica e non cattura niente:
        una notifica che fallisce annulla il ritiro, invece di lasciarlo scritto
        senza avviso.
        """
        from models.matchmaking.configuration import BRACKET_STRATEGIES
        from models.user.models import User

        direttore = db.session.get(User, direttore_id)
        valori = {
            "direttore": direttore.username if direttore else "",
            "gara": InscriptionService.nome_gara(gara),
        }
        if gara.withdraw_policy == WithdrawPolicy.EXCLUDE.value:
            messaggio = _(
                "%(direttore)s ti ha ritirato dalla gara %(gara)s. Le tue "
                "partite aperte si chiudono a tavolino e la tua iscrizione è "
                "stata tolta: dal turno dopo non entri più negli abbinamenti.",
                **valori,
            )
        elif gara.matchmaking_strategy in BRACKET_STRATEGIES:
            messaggio = _(
                "%(direttore)s ti ha ritirato dalla gara %(gara)s. Le tue "
                "partite aperte si chiudono a tavolino e il tabellone resta "
                "com'è: chi ti avrebbe incontrato passa il turno a tavolino.",
                **valori,
            )
        else:
            messaggio = _(
                "%(direttore)s ti ha ritirato dalla gara %(gara)s. Le tue "
                "partite aperte si chiudono a tavolino: resti in classifica, e "
                "nei turni dopo perdi a tavolino ogni partita.",
                **valori,
            )
        InscriptionService.notifica_di_gara(user_id, gara, str(messaggio))

    @staticmethod
    @transactional(domain="competition")
    def handle_forfeit(gara_id: int, user_id: int) -> str:
        """
        Handle player forfeit according to gara's withdraw policy.

        When a player forfeits, ALL their remaining pending/playing matches
        in this gara are also completed with the opponent as winner.

        Args:
            gara_id: ID of the gara
            user_id: ID of player who forfeited

        Returns:
            Policy action taken ("forfeit_marked" or "excluded")

        Raises:
            ValueError: If gara not found or user not inscribed
        """
        from sqlalchemy import or_
        from models.match.models import Match
        from models.status_enum import MatchStatus

        gara = db.session.get(Gara, gara_id)
        if not gara:
            raise ValueError(f"Gara {gara_id} not found")

        inscription = (
            db.session.query(Inscription)
            .filter_by(user_id=user_id, gara_id=gara_id, is_withdrawn=False)
            .first()
        )
        if not inscription:
            raise ValueError(
                f"User {user_id} not inscribed or already withdrawn from gara {gara_id}"
            )

        # Complete ALL pending/playing matches for this player in this gara
        # (The match that triggered the forfeit is already completed)
        from models.match.models import TrioMatch

        # Query 1: Regular matches (player is player1 or player2)
        pending_regular_matches = (
            db.session.query(Match)
            .filter(
                Match.gara_id == gara_id,
                Match.status.in_(
                    [MatchStatus.PENDING.value, MatchStatus.PLAYING.value]
                ),
                or_(Match.player1_id == user_id, Match.player2_id == user_id),
                Match.is_bye == False,  # noqa: E712  Skip bye matches
                Match.is_trio == False,  # noqa: E712  Skip trio matches
            )
            .all()
        )

        # Query 2: Trio matches where player is player3 (not in Match table)
        # These won't be found by Query 1
        pending_trio_matches_as_player3 = (
            db.session.query(Match)
            .join(TrioMatch, Match.id == TrioMatch.match_id)
            .filter(
                Match.gara_id == gara_id,
                Match.status.in_(
                    [MatchStatus.PENDING.value, MatchStatus.PLAYING.value]
                ),
                Match.is_trio == True,  # noqa: E712
                TrioMatch.player3_id == user_id,
            )
            .all()
        )

        # Query 3: Trio matches where player is player1 or player2
        # (found by player1_id/player2_id but need special handling)
        pending_trio_matches_as_player12 = (
            db.session.query(Match)
            .filter(
                Match.gara_id == gara_id,
                Match.status.in_(
                    [MatchStatus.PENDING.value, MatchStatus.PLAYING.value]
                ),
                Match.is_trio == True,  # noqa: E712
                or_(Match.player1_id == user_id, Match.player2_id == user_id),
            )
            .all()
        )

        # Handle regular matches
        for match in pending_regular_matches:
            # Quanto vale il tavolino lo dice il value object `Distance`
            # (ADR-027, issue #260). Qui c'era `match.match_distance or
            # gara.distance`: il valore coincideva quasi sempre, ma il
            # ripiego era rotto — `match_distance == 1` è il sentinella di
            # «non popolato» per `effective_distance`, e con l'`or` non
            # scatta, quindi una partita mai configurata sarebbe stata
            # chiusa 1-0 invece che alla distanza vera.
            winning_score = match.distance_config.walkover_score()
            if match.player1_id == user_id:
                winner_id = match.player2_id
                match.player1_score = 0
                match.player2_score = winning_score
            else:
                winner_id = match.player1_id
                match.player1_score = winning_score
                match.player2_score = 0

            match.winner_id = winner_id
            match.status = MatchStatus.CLOSED_UNILATERALLY.value

        # Handle trio matches (all of them - player3, player1, or player2)
        # Combine unique trio matches from both queries
        all_trio_matches = set(
            pending_trio_matches_as_player3 + pending_trio_matches_as_player12
        )
        for match in all_trio_matches:
            trio = match.trio_match
            if trio and not trio.is_completed:
                # Use TrioMatch's forfeit handler for proper round-robin completion
                trio.handle_forfeit(user_id)

        if gara.withdraw_policy == WithdrawPolicy.FORFEIT.value:
            # Policy FORFEIT: Mark as forfeit but keep in inscriptions
            inscription.is_forfeit = True
            inscription.forfeit_at = utc_now()
            return "forfeit_marked"

        elif gara.withdraw_policy == WithdrawPolicy.EXCLUDE.value:
            # Policy EXCLUDE: Remove from inscriptions completely
            InscriptionService.uninscribe_user(user_id=user_id, gara_id=gara_id)
            return "excluded"

        else:
            raise ValueError(f"Unknown withdraw policy: {gara.withdraw_policy}")

    @staticmethod
    def get_active_inscriptions(gara_id: int) -> list[Inscription]:
        """
        Get active inscriptions (not withdrawn, not waitlist).

        Includes forfeit players as they still participate in matchmaking.
        """
        return Inscription.active_for_gara(gara_id)

    @staticmethod
    def get_forfeit_inscriptions(gara_id: int) -> list[Inscription]:
        """
        Get inscriptions marked as forfeit (for auto-completion logic).

        Excludes waitlist entries: a waitlisted player cannot have matches to
        forfeit, and promotion to active must clear `is_forfeit` — filtering
        here is defense-in-depth so a promoted-but-still-forfeit inscription
        never reaches matchmaking as a forfeit target.
        """
        return (
            db.session.query(Inscription)
            .filter_by(
                gara_id=gara_id, is_withdrawn=False, is_waitlist=False, is_forfeit=True
            )
            .all()
        )

    @staticmethod
    def get_forfeit_user_ids(gara_id: int) -> set[int]:
        """
        Return forfeit player user_ids as a set — canonical source for the
        `forfeit_user_ids` parameter consumed by `create_matches_from_pairings`.
        """
        return {
            ins.user_id
            for ins in WithdrawPolicyService.get_forfeit_inscriptions(gara_id)
        }

    @staticmethod
    def is_player_forfeit(gara_id: int, user_id: int) -> bool:
        """
        Check if a specific player is marked as forfeit in this gara.
        """
        inscription = (
            db.session.query(Inscription)
            .filter_by(
                user_id=user_id, gara_id=gara_id, is_withdrawn=False, is_forfeit=True
            )
            .first()
        )
        return inscription is not None
