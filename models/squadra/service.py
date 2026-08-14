"""Operazioni di business sull'elenco squadre di una competizione (US-1/2/3/8/9/11).

L'elenco appartiene al **campionato** quando la gara ne fa parte, alla **gara**
quando e' standalone: e' l'unica asimmetria del modulo, e sta tutta in
``owner_of``. Tutto il resto lavora sull'elenco risolto da li'.

Due regole vivono qui e non nella schermata, perche' una schermata non e'
un vincolo:

- **la finestra di modifica** (US-11): dopo l'avvio del primo turno il
  tabellone e' gia' estratto e cambiare squadra non avrebbe alcun effetto
  retroattivo. Il tentativo viene rifiutato con un ``ConflictError``
  esplicito, non accettato e ignorato in silenzio;
- **chi puo' scrivere cosa** (US-1/US-3/US-9): il testo del profilo e' del
  giocatore e nessun altro ruolo lo tocca; l'iscrizione la scrivono il
  giocatore titolare e il direttore di quella gara; l'elenco lo governa il
  direttore della competizione.
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from models.base import db
from models.exceptions import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from models.status_enum import GaraStatus
from models.transaction.manager import transactional

from .models import Squadra, normalize_squadra_name

# Stati in cui le squadre sono ancora modificabili. Oltre, il primo turno e'
# partito e il tabellone e' estratto (US-11).
_EDITABLE_STATUSES = (GaraStatus.SETUP.value, GaraStatus.INSCRIPTION.value)

MAX_NAME_LENGTH = 100


class SquadraService:
    """Elenco squadre di una competizione e squadra dei suoi iscritti."""

    # ── Risoluzione dell'elenco ──────────────────────────────────────────

    @staticmethod
    def owner_of(gara) -> Tuple[str, int]:
        """A chi appartiene l'elenco squadre di questa gara.

        Restituisce ``("campionato", id)`` oppure ``("gara", id)``. Le gare di
        un campionato condividono un elenco solo: e' il motivo per cui alla
        seconda gara chi si iscrive trova le squadre gia' pronte (US-2).
        """
        if getattr(gara, "campionato_id", None):
            return ("campionato", gara.campionato_id)
        return ("gara", gara.id)

    @staticmethod
    def _owner_query(gara):
        kind, owner_id = SquadraService.owner_of(gara)
        if kind == "campionato":
            return Squadra.query.filter_by(campionato_id=owner_id)
        return Squadra.query.filter_by(gara_id=owner_id)

    @staticmethod
    def list_for_gara(gara, *, include_inactive: bool = False) -> List[Squadra]:
        """L'elenco della competizione, in ordine alfabetico.

        Le disattivate restano fuori dalle scelte ma servono a chi gestisce
        l'elenco, che deve poterle riattivare.
        """
        query = SquadraService._owner_query(gara)
        if not include_inactive:
            query = query.filter_by(is_active=True)
        return query.order_by(Squadra.name).all()

    @staticmethod
    def find_by_name(gara, name: str) -> Optional[Squadra]:
        """La voce dell'elenco con questo nome, a meno di maiuscole e spazi."""
        normalized = normalize_squadra_name(name)
        if not normalized:
            return None
        return (
            SquadraService._owner_query(gara)
            .filter(Squadra.normalized_name == normalized)
            .first()
        )

    @staticmethod
    def similar_names(gara, name: str, *, limit: int = 5) -> List[Squadra]:
        """Voci simili a un nome che sta per essere creato (US-2).

        Confronto per sottostringa sulla forma normalizzata: "Circolo Nord" e
        "Nord" si vedono a vicenda. Serve a far notare il doppione **prima**
        che nasca, invece di doverlo unire dopo.
        """
        normalized = normalize_squadra_name(name)
        if not normalized:
            return []
        candidates = SquadraService.list_for_gara(gara, include_inactive=True)
        return [
            squadra
            for squadra in candidates
            if normalized in squadra.normalized_name
            or squadra.normalized_name in normalized
        ][:limit]

    @staticmethod
    def suggest_for_user(gara, user) -> Optional[Squadra]:
        """La voce dell'elenco che corrisponde al testo scritto nel profilo.

        E' l'unico momento in cui ``user.squadra`` viene letto: da qui in poi
        l'unica fonte autorevole e' ``Inscription.squadra_id`` (US-1).
        """
        testo = getattr(user, "squadra", None)
        if not testo:
            return None
        squadra = SquadraService.find_by_name(gara, testo)
        return squadra if (squadra and squadra.is_active) else None

    # ── Finestra di modifica e permessi ──────────────────────────────────

    @staticmethod
    def is_editable(gara) -> bool:
        """Le squadre di questa gara si possono ancora toccare?"""
        return gara.status in _EDITABLE_STATUSES and (gara.current_round or 0) == 0

    @staticmethod
    def assert_editable(gara) -> None:
        if not SquadraService.is_editable(gara):
            raise ConflictError(
                "Il primo turno è già partito: il tabellone è estratto e la "
                "squadra non è più modificabile."
            )

    @staticmethod
    def _assert_can_manage_list(gara, actor) -> None:
        """L'elenco lo governa chi dirige quella competizione (US-3)."""
        if actor is None or not getattr(actor, "is_authenticated", False):
            raise PermissionDeniedError("Accesso richiesto")
        if not actor.can_manage_competition(gara.id):
            raise PermissionDeniedError("Non gestisci questa competizione")

    # ── Elenco: creazione, rinomina, unione, disattivazione ──────────────

    @staticmethod
    def _clean_name(name: str) -> str:
        cleaned = " ".join((name or "").split())
        if not cleaned:
            raise ValidationError("Il nome della squadra non può essere vuoto")
        if len(cleaned) > MAX_NAME_LENGTH:
            raise ValidationError(
                f"Il nome della squadra supera i {MAX_NAME_LENGTH} caratteri"
            )
        return cleaned

    @staticmethod
    @transactional(domain="squadra")
    def create(gara, name: str, actor=None) -> Squadra:
        """Aggiunge una voce all'elenco della competizione.

        ``actor`` assente = chiamata di servizio (l'iscrizione che crea la
        squadra del proprio profilo): il permesso lo ha gia' controllato chi
        chiama. Con un ``actor`` si pretende che diriga la competizione.
        """
        if actor is not None:
            SquadraService._assert_can_manage_list(gara, actor)

        cleaned = SquadraService._clean_name(name)
        existing = SquadraService.find_by_name(gara, cleaned)
        if existing:
            raise ConflictError(f"La squadra «{existing.name}» è già in elenco")

        kind, owner_id = SquadraService.owner_of(gara)
        squadra = Squadra(
            name=cleaned,
            campionato_id=owner_id if kind == "campionato" else None,
            gara_id=owner_id if kind == "gara" else None,
        )
        db.session.add(squadra)
        db.session.flush()
        return squadra

    @staticmethod
    def get_or_404(squadra_id: int) -> Squadra:
        squadra = db.session.get(Squadra, squadra_id)
        if not squadra:
            raise NotFoundError("Squadra non trovata")
        return squadra

    @staticmethod
    @transactional(domain="squadra")
    def rename(gara, squadra_id: int, new_name: str, actor=None) -> Squadra:
        SquadraService._assert_can_manage_list(gara, actor)
        squadra = SquadraService._owned(gara, squadra_id)

        cleaned = SquadraService._clean_name(new_name)
        clash = SquadraService.find_by_name(gara, cleaned)
        if clash and clash.id != squadra.id:
            raise ConflictError(f"La squadra «{clash.name}» è già in elenco")

        squadra.rename(cleaned)
        return squadra

    @staticmethod
    @transactional(domain="squadra")
    def merge(gara, source_id: int, target_id: int, actor=None) -> Squadra:
        """Unisce due voci: le iscrizioni della prima passano alla seconda.

        La voce assorbita viene **cancellata**, non disattivata: dopo il
        travaso non la referenzia piu' nessuno, e lasciarla spenta in elenco
        significherebbe riproporre il doppione a chi lo ha appena risolto.
        """
        SquadraService._assert_can_manage_list(gara, actor)
        if source_id == target_id:
            raise ValidationError("Le due squadre da unire devono essere diverse")

        source = SquadraService._owned(gara, source_id)
        target = SquadraService._owned(gara, target_id)

        from models.competition.models import Inscription

        # Le iscrizioni si spostano in *tutte* le gare che condividono
        # l'elenco, non solo in questa: l'elenco è del campionato, e una voce
        # unita a metà sarebbe peggio del doppione.
        Inscription.query.filter_by(squadra_id=source.id).update(
            {"squadra_id": target.id}, synchronize_session=False
        )
        db.session.delete(source)
        db.session.flush()
        return target

    @staticmethod
    @transactional(domain="squadra")
    def set_active(gara, squadra_id: int, active: bool, actor=None) -> Squadra:
        """Toglie (o rimette) una voce fra quelle scegliibili.

        Non tocca le iscrizioni che la usano gia': lo storico non si riscrive.
        """
        SquadraService._assert_can_manage_list(gara, actor)
        squadra = SquadraService._owned(gara, squadra_id)
        squadra.is_active = bool(active)
        return squadra

    @staticmethod
    def _owned(gara, squadra_id: int) -> Squadra:
        """La squadra, se appartiene davvero all'elenco di questa gara.

        Il controllo non e' formale: senza, il direttore di una gara potrebbe
        rinominare le squadre di un'altra competizione passando un id altrui.
        """
        squadra = SquadraService.get_or_404(squadra_id)
        kind, owner_id = SquadraService.owner_of(gara)
        appartiene = (
            squadra.campionato_id == owner_id
            if kind == "campionato"
            else squadra.gara_id == owner_id
        )
        if not appartiene:
            raise NotFoundError("Squadra non trovata in questa competizione")
        return squadra

    # ── Squadra di un iscritto ───────────────────────────────────────────

    @staticmethod
    def can_edit_inscription(gara, inscription, actor) -> bool:
        """Chi puo' cambiare la squadra di questa iscrizione, e quando."""
        if not gara.separate_teammates or not SquadraService.is_editable(gara):
            return False
        if actor is None or not getattr(actor, "is_authenticated", False):
            return False
        return actor.id == inscription.user_id or actor.can_manage_competition(gara.id)

    @staticmethod
    @transactional(domain="squadra")
    def set_inscription_squadra(
        gara, inscription, squadra_id: Optional[int], actor=None
    ):
        """Assegna (o toglie) la squadra di un iscritto per **questa** gara.

        ``squadra_id`` a ``None`` non e' un errore: e' "gioco senza squadra
        qui", uno stato legittimo e distinto dal non aver ancora scelto
        (US-8). La scelta non tocca il profilo del giocatore.
        """
        if not gara.separate_teammates:
            raise ValidationError(
                "Le squadre non sono attive su questa gara: il sorteggio non "
                "separa i compagni."
            )
        SquadraService.assert_editable(gara)

        if actor is not None:
            if not (
                actor.id == inscription.user_id or actor.can_manage_competition(gara.id)
            ):
                raise PermissionDeniedError(
                    "Puoi cambiare solo la squadra della tua iscrizione"
                )

        inscription.squadra_id = (
            SquadraService._owned(gara, squadra_id).id
            if squadra_id is not None
            else None
        )
        return inscription

    @staticmethod
    def counts_by_squadra(gara_id: int) -> dict:
        """Quanti iscritti per squadra in questa gara.

        Serve alla schermata di gestione: un'unione o una disattivazione va
        decisa sapendo quante iscrizioni tocca.
        """
        from models.competition.models import Inscription

        rows = (
            db.session.query(Inscription.squadra_id, db.func.count(Inscription.id))
            .filter(
                Inscription.gara_id == gara_id,
                Inscription.squadra_id.isnot(None),
                Inscription.is_withdrawn.is_(False),
            )
            .group_by(Inscription.squadra_id)
            .all()
        )
        return {squadra_id: count for squadra_id, count in rows}

    @staticmethod
    def sizes_for_draw(inscriptions: Sequence) -> dict:
        """Numerosita' delle squadre fra gli iscritti passati.

        Il sorteggio puo' solo **rinviare** il derby quando una squadra e'
        troppo numerosa (US-6): questo conto e' quel che serve a dirlo prima,
        invece di farlo scoprire a tabellone estratto.
        """
        sizes: dict = {}
        for inscription in inscriptions:
            if inscription.squadra_id:
                sizes[inscription.squadra_id] = sizes.get(inscription.squadra_id, 0) + 1
        return sizes
