"""
Module: models/competition/round_cancellation.py
Purpose: Round cancellation logic (cancel_first_round_startup,
    cancel_current_round_startup)
"""

from __future__ import annotations

from models.base import db, transactional
from models.status_enum import GaraStatus
from .models import Gara


class RoundCancellationService:
    """Round cancellation operations."""

    @staticmethod
    @transactional(domain="competition")
    def cancel_first_round_startup(gara_id: int) -> Gara:
        """Cancella l'avvio del primo turno se non sono stati inseriti risultati.

        Riporta la gara allo stato 'inscription' e rimuove tutte le partite del
        primo turno.
        Utilizzabile solo se il primo turno è stato avviato ma nessun risultato
        è stato inserito.
        """
        from models.match.models import Match, TrioMatch

        gara = db.session.get(Gara, gara_id)
        if not gara:
            raise ValueError(f"Gara {gara_id} non trovata")

        # Per strategie che creano tutti i round all'avvio (es. Random),
        # permettiamo l'annullamento indipendentemente da current_round
        if not gara.creates_all_rounds_at_startup() and gara.current_round != 1:
            raise ValueError("Questa operazione è valida solo per il primo turno")

        # Verifica che non ci siano risultati inseriti in NESSUN round
        # (esclusi i bye che sono auto-completati)
        matches_with_results = (
            db.session.query(Match)
            .filter_by(gara_id=gara_id)
            .filter(Match.winner_id.isnot(None))
            .filter(Match.is_bye == False)  # noqa: E712 - Exclude bye matches
            .count()
        )

        if matches_with_results > 0:
            raise ValueError(
                "Impossibile cancellare l'avvio: ci sono già dei risultati inseriti"
            )

        # Cancella le classifiche della gara
        from models.classification.models import RoundClassification, GaraClassification
        from models.competition.gara_challenge import (
            GaraChallenge,
            GaraChallengeAttempt,
            GaraChallengeClassification,
        )

        # Il seeding va rimosso tramite il servizio, che azzera anche
        # `Inscription.initial_order` ("Ordine sorteggio" mostrato al
        # giocatore): la delete grezza qui sotto toglierebbe solo il turno 0
        # lasciando in pagina un ordine che non corrisponde più a nulla.
        from models.classification.seeding_service import SeedingService

        SeedingService.clear_seeding(gara_id)

        # Stessa logica per il seme del sorteggio: annullare l'avvio significa
        # voler risorteggiare, quindi al riavvio se ne genera uno nuovo e il
        # tabellone risulta diverso. (`cancel_current_round_startup` invece non
        # lo tocca: dai turni 2+ il tabellone e' deterministico e il seme e'
        # irrilevante.)
        gara.draw_seed = None

        RoundClassification.query.filter_by(gara_id=gara_id).delete()
        GaraClassification.query.filter_by(gara_id=gara_id).delete()

        # Cancella tentativi e classifiche challenge (se presenti)
        GaraChallengeClassification.query.filter_by(gara_id=gara_id).delete()

        # Cancella i tentativi challenge associati alle challenge di questa gara
        gara_challenge_ids = [
            gc.id for gc in GaraChallenge.query.filter_by(gara_id=gara_id).all()
        ]
        if gara_challenge_ids:
            GaraChallengeAttempt.query.filter(
                GaraChallengeAttempt.gara_challenge_id.in_(gara_challenge_ids)
            ).delete(synchronize_session=False)

        # Cancella TUTTI i match della gara
        # Necessario specialmente per la strategia 'random', che pre-genera tutto
        matches = db.session.query(Match).filter_by(gara_id=gara_id).all()

        # Prima cancella i TrioMatch associati
        for match in matches:
            trio_matches = (
                db.session.query(TrioMatch).filter_by(match_id=match.id).all()
            )
            for trio in trio_matches:
                db.session.delete(trio)

        # Poi cancella i match
        for match in matches:
            db.session.delete(match)

        # Riporta la gara allo stato inscription
        gara.current_round = 0

        if gara.status == GaraStatus.PLAYING.value:
            gara.status = GaraStatus.INSCRIPTION.value

        # Gara di playoff: gli inviti chiusi dall'avvio tornano in attesa.
        if gara.playoff_config_id:
            from models.playoff.services import PlayoffService

            PlayoffService.riapri_inviti_all_annullo(gara)

        # Niente `db.session.add(gara)`: `gara` è già persistente, quindi la
        # modifica viene salvata comunque dal flush. L'unico effetto di quella
        # riga era propagare il cascade *save-update* su `gara.matches` — la
        # stessa collezione i cui elementi sono stati appena cancellati qui
        # sopra — e SQLAlchemy si rifiuta di reinserire un oggetto cancellato:
        # «Instance '<Match>' has been deleted». L'annullamento del sorteggio
        # falliva così, con la gara che restava in `playing`.
        return gara

    @staticmethod
    @transactional(domain="competition")
    def cancel_current_round_startup(gara_id: int) -> Gara:
        """Cancella l'avvio del turno corrente se non sono stati inseriti risultati.

        Decrementa il current_round e rimuove tutte le partite del turno corrente.
        Utilizzabile solo se non sono stati inseriti risultati (anche parziali).
        """
        from models.match.models import Match, TrioMatch

        gara = db.session.get(Gara, gara_id)
        if not gara:
            raise ValueError(f"Gara {gara_id} non trovata")

        # Verifica che siamo in stato playing
        if gara.status != GaraStatus.PLAYING.value:
            raise ValueError("La gara deve essere in stato playing")

        current_round = gara.current_round
        if current_round <= 0:
            raise ValueError("Non c'è un turno corrente da cancellare")

        # Verifica che non ci siano risultati inseriti (neanche parziali)
        current_round_matches = Match.query.filter_by(
            gara_id=gara_id, round_number=current_round
        ).all()

        if not current_round_matches:
            raise ValueError("Non ci sono partite del turno corrente da cancellare")

        # Controlla che non ci siano risultati inseriti (neanche parziali)
        # Note: match.status == PLAYING just means a table was assigned,
        # not that results have been entered. Only check actual scores.
        for match in current_round_matches:
            if (
                match.player1_score > 0
                or match.player2_score > 0
                or match.winner_id is not None
            ):
                raise ValueError(
                    "Impossibile cancellare l'avvio: sono già stati inseriti "
                    "risultati (anche parziali)"
                )

        # Rimuovi tutte le partite del turno corrente e dati correlati
        from models.classification.models import (
            PlayerEncounter,
            RoundClassification,
        )

        # Rimuovi eventuali trii collegati
        for match in current_round_matches:
            trio = db.session.query(TrioMatch).filter_by(match_id=match.id).first()
            if trio:
                db.session.delete(trio)

        # Rimuovi i PlayerEncounter del turno corrente per ripristinare l'anti-rematch
        encounters_to_remove = (
            db.session.query(PlayerEncounter)
            .filter_by(gara_id=gara_id, round_number=current_round)
            .all()
        )
        for encounter in encounters_to_remove:
            db.session.delete(encounter)

        # Rimuovi le RoundClassification del turno corrente
        classifications_to_remove = (
            db.session.query(RoundClassification)
            .filter_by(gara_id=gara_id, round_number=current_round)
            .all()
        )
        for classification in classifications_to_remove:
            db.session.delete(classification)

        # Rimuovi tutte le partite
        for match in current_round_matches:
            db.session.delete(match)

        # Decrementa il current_round
        gara.current_round = current_round - 1

        # Se torniamo al turno 0, riporta allo stato inscription
        if gara.current_round == 0:
            gara.status = GaraStatus.INSCRIPTION.value

            # La classifica di partenza vale solo a gara avviata: se restasse,
            # un cambio di iscritti prima del riavvio lascerebbe un seeding
            # stantio (ritirati presenti, nuovi assenti) a pilotare il primo
            # accoppiamento. Al riavvio se ne genera uno nuovo.
            from models.classification.seeding_service import SeedingService

            SeedingService.clear_seeding(gara_id)

            # Gara di playoff: gli inviti chiusi dall'avvio tornano in attesa.
            if gara.playoff_config_id:
                from models.playoff.services import PlayoffService

                PlayoffService.riapri_inviti_all_annullo(gara)

        db.session.add(gara)
        return gara
