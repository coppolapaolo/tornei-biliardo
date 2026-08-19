"""Elenco categorie di una competizione e categoria dei suoi iscritti.

Decisione: docs/adr/ADR-049-same-category-restores-elo-in-handicap-events.md

L'elenco appartiene al **campionato** quando la gara ne fa parte, alla **gara**
quando è standalone: unica asimmetria del modulo, tutta dentro ``owner_of``.

Tre regole vivono qui e non nella schermata, perché una schermata non è un
vincolo:

- **la finestra di modifica**: dopo l'avvio del primo turno le partite sono
  estratte e l'ELO sta per essere deciso da queste categorie; cambiarle
  darebbe un rating che non corrisponde più a ciò che si vede. Il tentativo è
  rifiutato con ``ConflictError`` (→ 409). Lo scavalca solo ``force=True``,
  che è come lo script di riparazione tocca le gare già giocate — e che
  richiede un ricalcolo dell'ELO per avere senso.
- **chi può scrivere**: soltanto chi dirige la competizione. È lo scostamento
  voluto rispetto alle squadre, dove decide anche il giocatore: la squadra al
  più influenza il sorteggio, la categoria decide se le partite muovono
  l'ELO, e autoassegnarsela sarebbe un pulsante «fammi contare».
- **crea-assegnando**: il combo della schermata manda un *nome*, non un id.
  Definire l'elenco e assegnare sono lo stesso gesto — si scrive «B» sul primo
  iscritto e la categoria nasce lì, sul secondo la si trova già in tendina.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from models.base import db
from models.exceptions import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from models.shared.naming import clean_display_name, normalize_list_name
from models.status_enum import GaraStatus
from models.transaction.manager import transactional

from .models import MAX_NAME_LENGTH, Categoria

# Stati in cui le categorie sono ancora modificabili. Oltre, il primo turno è
# partito: le partite sono estratte e l'eleggibilità all'ELO è decisa.
_EDITABLE_STATUSES = (GaraStatus.SETUP.value, GaraStatus.INSCRIPTION.value)


class CategoriaService:
    """Elenco categorie di una competizione e categoria dei suoi iscritti."""

    # ── Risoluzione dell'elenco ──────────────────────────────────────────

    @staticmethod
    def owner_of(gara) -> Tuple[str, int]:
        """A chi appartiene l'elenco categorie di questa gara.

        ``("campionato", id)`` oppure ``("gara", id)``. Le gare di un
        campionato condividono un elenco solo: è il motivo per cui alla
        seconda prova le categorie sono già pronte.
        """
        if getattr(gara, "campionato_id", None):
            return ("campionato", gara.campionato_id)
        return ("gara", gara.id)

    @staticmethod
    def _owner_query(gara):
        kind, owner_id = CategoriaService.owner_of(gara)
        if kind == "campionato":
            return Categoria.query.filter_by(campionato_id=owner_id)
        return Categoria.query.filter_by(gara_id=owner_id)

    @staticmethod
    def list_for_gara(gara, *, include_inactive: bool = False) -> List[Categoria]:
        """L'elenco della competizione, in ordine alfabetico.

        Le disattivate restano fuori dalle scelte ma servono a chi gestisce
        l'elenco, che deve poterle riattivare.
        """
        query = CategoriaService._owner_query(gara)
        if not include_inactive:
            query = query.filter_by(is_active=True)
        return query.order_by(Categoria.normalized_name).all()

    @staticmethod
    def find_by_name(gara, name: str) -> Optional[Categoria]:
        """La voce dell'elenco con questo nome, a meno di maiuscole e spazi."""
        normalized = normalize_list_name(name)
        if not normalized:
            return None
        return (
            CategoriaService._owner_query(gara)
            .filter(Categoria.normalized_name == normalized)
            .first()
        )

    # ── Finestra di modifica e permessi ──────────────────────────────────

    @staticmethod
    def is_editable(gara) -> bool:
        """Le categorie di questa gara si possono ancora toccare?"""
        return gara.status in _EDITABLE_STATUSES and (gara.current_round or 0) == 0

    @staticmethod
    def assert_editable(gara, *, force: bool = False) -> None:
        if force:
            return
        if not CategoriaService.is_editable(gara):
            raise ConflictError(
                "Il primo turno è già partito: le categorie decidono quali "
                "partite contano per l'ELO e non sono più modificabili."
            )

    @staticmethod
    def _assert_can_manage(gara, actor) -> None:
        """Le categorie le governa chi dirige quella competizione."""
        if actor is None or not getattr(actor, "is_authenticated", False):
            raise PermissionDeniedError("Accesso richiesto")
        if not actor.can_manage_competition(gara.id):
            raise PermissionDeniedError("Non gestisci questa competizione")

    @staticmethod
    def can_edit_inscription(gara, actor) -> bool:
        """Chi può cambiare la categoria degli iscritti, e quando.

        Nessun ramo per il giocatore titolare, a differenza delle squadre:
        vedi la docstring del modulo.
        """
        if not CategoriaService.is_editable(gara):
            return False
        if actor is None or not getattr(actor, "is_authenticated", False):
            return False
        return bool(actor.can_manage_competition(gara.id))

    # ── Elenco: creazione, rinomina, disattivazione, eliminazione ────────

    @staticmethod
    def _clean_name(name: str) -> str:
        cleaned = clean_display_name(name)
        if not cleaned:
            raise ValidationError("Il nome della categoria non può essere vuoto")
        if len(cleaned) > MAX_NAME_LENGTH:
            raise ValidationError(
                f"Il nome della categoria supera i {MAX_NAME_LENGTH} caratteri"
            )
        return cleaned

    @staticmethod
    def get_or_404(categoria_id: int) -> Categoria:
        categoria = db.session.get(Categoria, categoria_id)
        if not categoria:
            raise NotFoundError("Categoria non trovata")
        return categoria

    @staticmethod
    def _owned(gara, categoria_id: int) -> Categoria:
        """La categoria, ma solo se appartiene a *questa* competizione.

        Senza questo controllo il direttore della gara X rinominerebbe le
        categorie della competizione Y passando un id altrui.
        """
        categoria = CategoriaService.get_or_404(categoria_id)
        kind, owner_id = CategoriaService.owner_of(gara)
        appartiene = (
            categoria.campionato_id == owner_id
            if kind == "campionato"
            else categoria.gara_id == owner_id
        )
        if not appartiene:
            raise NotFoundError("Categoria non trovata in questa competizione")
        return categoria

    @staticmethod
    def _build(gara, cleaned: str) -> Categoria:
        kind, owner_id = CategoriaService.owner_of(gara)
        categoria = Categoria(
            name=cleaned,
            campionato_id=owner_id if kind == "campionato" else None,
            gara_id=owner_id if kind == "gara" else None,
        )
        db.session.add(categoria)
        db.session.flush()
        return categoria

    @staticmethod
    @transactional(domain="categoria")
    def create(gara, name: str, actor=None) -> Categoria:
        """Aggiunge una voce all'elenco della competizione."""
        if actor is not None:
            CategoriaService._assert_can_manage(gara, actor)
        CategoriaService.assert_editable(gara)

        cleaned = CategoriaService._clean_name(name)
        existing = CategoriaService.find_by_name(gara, cleaned)
        if existing:
            raise ConflictError(f"La categoria «{existing.name}» è già in elenco")
        return CategoriaService._build(gara, cleaned)

    @staticmethod
    @transactional(domain="categoria")
    def rename(gara, categoria_id: int, new_name: str, actor=None) -> Categoria:
        CategoriaService._assert_can_manage(gara, actor)
        CategoriaService.assert_editable(gara)
        categoria = CategoriaService._owned(gara, categoria_id)

        cleaned = CategoriaService._clean_name(new_name)
        clash = CategoriaService.find_by_name(gara, cleaned)
        if clash and clash.id != categoria.id:
            raise ConflictError(f"La categoria «{clash.name}» è già in elenco")

        categoria.rename(cleaned)
        return categoria

    @staticmethod
    @transactional(domain="categoria")
    def set_active(gara, categoria_id: int, active: bool, actor=None) -> Categoria:
        """Toglie (o rimette) una categoria dalle scelte future.

        Non tocca le iscrizioni che la usano già: è il modo di ritirare una
        categoria senza riscrivere le gare giocate.
        """
        CategoriaService._assert_can_manage(gara, actor)
        categoria = CategoriaService._owned(gara, categoria_id)
        categoria.is_active = bool(active)
        return categoria

    @staticmethod
    def usage_count(categoria_id: int) -> int:
        """Quante iscrizioni referenziano questa categoria, ovunque."""
        from models.competition.models import Inscription

        return Inscription.query.filter_by(categoria_id=categoria_id).count()

    @staticmethod
    @transactional(domain="categoria")
    def elimina(gara, categoria_id: int, actor=None) -> None:
        """Cancella una voce, ma solo se non la usa nessuno.

        È il rimedio al refuso appena creato («BB» accanto a «B»). Su una
        categoria in uso si rifiuta e si indica la disattivazione: cancellarla
        svuoterebbe in silenzio l'assegnazione di chi ce l'ha.
        """
        CategoriaService._assert_can_manage(gara, actor)
        CategoriaService.assert_editable(gara)
        categoria = CategoriaService._owned(gara, categoria_id)

        in_uso = CategoriaService.usage_count(categoria.id)
        if in_uso:
            raise ConflictError(
                f"«{categoria.name}» è assegnata a {in_uso} iscritti: "
                "disattivala invece di eliminarla."
            )
        db.session.delete(categoria)

    # ── Categoria di un iscritto ─────────────────────────────────────────

    @staticmethod
    @transactional(domain="categoria")
    def set_inscription_categoria_by_name(
        gara, inscription, name: Optional[str], actor=None, force: bool = False
    ) -> Optional[Categoria]:
        """Assegna la categoria di un iscritto **dal nome**, creandola se manca.

        È il metodo che regge il combo della schermata: chi organizza scrive
        «B» e non deve prima andare a definire un elenco. Nome vuoto (o
        ``None``) toglie l'assegnazione.

        ``force`` scavalca la finestra di modifica ed esiste per lo script che
        recupera le gare già giocate: da lì in poi il chiamante è responsabile
        di ricalcolare l'ELO, altrimenti la categoria appena scritta non
        cambia nulla su partite già chiuse.
        """
        if actor is not None:
            CategoriaService._assert_can_manage(gara, actor)
        CategoriaService.assert_editable(gara, force=force)

        if inscription.gara_id != gara.id:
            raise NotFoundError("Iscrizione non trovata in questa gara")

        cleaned = clean_display_name(name or "")
        if not cleaned:
            inscription.categoria_id = None
            return None

        cleaned = CategoriaService._clean_name(cleaned)
        categoria = CategoriaService.find_by_name(gara, cleaned)
        if categoria is None:
            categoria = CategoriaService._build(gara, cleaned)
        elif not categoria.is_active:
            # Riassegnarla esplicitamente è una richiesta di riattivarla: la
            # alternativa sarebbe accettare la scelta e ignorarla.
            categoria.is_active = True

        inscription.categoria_id = categoria.id
        return categoria

    @staticmethod
    def suggest_for_user(gara, user) -> Optional[Categoria]:
        """La categoria che il giocatore aveva nella competizione, se c'è.

        Letta **una volta sola**, al momento dell'iscrizione, per precompilare.
        Dentro un campionato l'elenco è condiviso, quindi dalla seconda prova
        in poi la categoria si riporta da sé e il direttore corregge soltanto
        chi è cambiato di categoria.
        """
        from models.competition.models import Inscription

        if user is None:
            return None

        kind, owner_id = CategoriaService.owner_of(gara)
        if kind == "gara":
            return None  # standalone: non c'è un "prima" da cui riportare

        return (
            db.session.query(Categoria)
            .join(Inscription, Inscription.categoria_id == Categoria.id)
            .filter(
                Inscription.user_id == user.id,
                Inscription.gara_id != gara.id,
                Categoria.campionato_id == owner_id,
            )
            .order_by(Inscription.id.desc())
            .first()
        )

    # ── Conteggi per la schermata ────────────────────────────────────────

    @staticmethod
    def counts_by_categoria(gara_id: int) -> Dict[int, int]:
        """Quanti iscritti per categoria in questa gara.

        Non è decorativo: è il modo in cui un refuso si vede. «BB» con un solo
        giocatore accanto a «B» con otto si riconosce a colpo d'occhio, ed è
        l'unico presidio possibile contro il testo libero.
        """
        from models.competition.models import Inscription

        rows = (
            db.session.query(Inscription.categoria_id, db.func.count(Inscription.id))
            .filter(
                Inscription.gara_id == gara_id,
                Inscription.categoria_id.isnot(None),
                Inscription.is_withdrawn.is_(False),
            )
            .group_by(Inscription.categoria_id)
            .all()
        )
        return {categoria_id: count for categoria_id, count in rows}

    @staticmethod
    def count_senza_categoria(gara_id: int) -> int:
        """Iscritti attivi senza categoria in questa gara.

        Alimenta l'avviso all'avvio del primo turno: è l'ultimo istante in cui
        una dimenticanza è ancora rimediabile da schermata.
        """
        from models.competition.models import Inscription

        return Inscription.query.filter(
            Inscription.gara_id == gara_id,
            Inscription.categoria_id.is_(None),
            Inscription.is_withdrawn.is_(False),
            Inscription.is_waitlist.is_(False),
        ).count()
