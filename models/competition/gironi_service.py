"""I gironi del girone all'italiana, sul database (ADR-076).

Le regole stanno in `models/matchmaking/gironi.py`, puro. Qui:

- **all'avvio** (`fissa_all_avvio`): quanti gironi, chi va dove, e il numero
  di turni; l'appartenenza si scrive su `Inscription.group_index`;
- **dopo** (`girone_dei_giocatori`): a quale girone appartiene ognuno. Si
  legge dalle partite del primo turno (`Match.bracket_group`), che restano
  anche quando la regola di ritiro EXCLUDE cancella l'iscrizione, e prima che
  esistano dalle iscrizioni;
- **annullando l'avvio** (`azzera`): i gironi si tolgono, e al riavvio si
  ricompongono;
- **il foglio di avvio** (`anteprima`): la proposta e le taglie dei gironi.

Nessun metodo è `@transactional`: si chiamano dentro l'avvio e
l'annullamento, che lo sono già (ADR-061).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from flask_babel import gettext as _

from models.base import db
from models.exceptions import ValidationError
from models.matchmaking.configuration import MatchmakingStrategy
from models.matchmaking.gironi import (
    MINIMO_PER_GIRONE,
    Iscritto,
    componi_gironi,
    gironi_possibili,
    nome_del_girone,
    proposta_di_gironi,
    taglie_dei_gironi,
    turni_dei_gironi,
    turni_del_girone,
    verifica_numero_di_gironi,
)

from .models import Gara, Inscription


def _a_gironi_possibili(gara: Gara) -> bool:
    return gara.matchmaking_strategy == MatchmakingStrategy.ROUND_ROBIN.value


@dataclass(frozen=True)
class Anteprima:
    """Ciò che il foglio di avvio mostra sui gironi."""

    iscritti: int
    tetto: int
    massimo: int
    proposta: int
    #: numero di gironi → taglie, per ogni scelta possibile
    taglie: Dict[int, List[int]]

    @property
    def scelte(self) -> List[int]:
        return list(range(1, self.massimo + 1))

    @property
    def tetto_ridotto(self) -> bool:
        """Il tetto della gara è più alto di quanti gironi ci stanno."""
        return self.massimo < self.tetto


class GironiService:
    """I gironi di una gara a girone all'italiana."""

    @staticmethod
    def anteprima(gara: Gara, iscritti: Optional[int] = None) -> Optional[Anteprima]:
        """La proposta per il foglio di avvio, o None se la gara non ha gironi."""
        if not _a_gironi_possibili(gara) or gara.effective_max_groups <= 1:
            return None
        n = gara.get_active_inscriptions_count() if iscritti is None else iscritti
        tetto = gara.effective_max_groups
        massimo = gironi_possibili(n, tetto)
        return Anteprima(
            iscritti=n,
            tetto=tetto,
            massimo=massimo,
            proposta=proposta_di_gironi(n, tetto),
            taglie={g: taglie_dei_gironi(n, g) for g in range(1, massimo + 1)},
        )

    @staticmethod
    def fissa_all_avvio(
        gara: Gara,
        iscrizioni: Sequence[Inscription],
        gironi: Optional[int] = None,
    ) -> List[List[int]]:
        """Compone i gironi e fissa i turni del girone all'italiana.

        Args:
            gara: la gara che si avvia.
            iscrizioni: gli iscritti attivi.
            gironi: il numero scelto dal direttore; None = la proposta.

        Returns:
            I gironi, una lista di id per girone; uno solo per il girone unico.

        Raises:
            ValidationError: se il numero di gironi non è ammesso.
        """
        n = len(iscrizioni)
        tetto = gara.effective_max_groups
        numero = proposta_di_gironi(n, tetto) if gironi is None else int(gironi)
        motivo = verifica_numero_di_gironi(n, numero, tetto)
        if motivo == "tetto":
            raise ValidationError(
                _(
                    "Questa gara si gioca al massimo in %(n)s gironi.",
                    n=tetto,
                )
            )
        if motivo == "giocatori":
            raise ValidationError(
                _(
                    "Con %(iscritti)s iscritti non si fanno %(gironi)s gironi: "
                    "ne servono almeno %(minimo)s per girone.",
                    iscritti=n,
                    gironi=numero,
                    minimo=MINIMO_PER_GIRONE,
                )
            )
        if motivo is not None:
            raise ValidationError(_("Il numero di gironi non è valido."))

        if numero <= 1:
            for iscrizione in iscrizioni:
                iscrizione.group_index = None
            gara.rounds_count = max(turni_del_girone(n), 1)
            return [[i.user_id for i in iscrizioni]]

        composti = componi_gironi(
            GironiService._iscritti(gara, iscrizioni),
            numero,
            gara.effective_group_seeding,
            gara.draw_seed,
            separa_compagni=bool(gara.separate_teammates),
        )
        girone_di = {
            pid: indice for indice, girone in enumerate(composti) for pid in girone
        }
        for iscrizione in iscrizioni:
            iscrizione.group_index = girone_di[iscrizione.user_id]
        gara.rounds_count = turni_dei_gironi([len(g) for g in composti])
        return composti

    @staticmethod
    def _iscritti(gara: Gara, iscrizioni: Sequence[Inscription]) -> List[Iscritto]:
        posto = GironiService._ordine_delle_categorie(gara)
        risultato = []
        for iscrizione in iscrizioni:
            utente = iscrizione.user
            risultato.append(
                Iscritto(
                    player_id=iscrizione.user_id,
                    elo=getattr(utente, "elo_rating", None) if utente else None,
                    categoria=(
                        posto.get(iscrizione.categoria_id)
                        if iscrizione.categoria_id is not None
                        else None
                    ),
                    squadra=iscrizione.squadra_id,
                )
            )
        return risultato

    @staticmethod
    def _ordine_delle_categorie(gara: Gara) -> Dict[int, int]:
        """Il posto di ogni categoria: prima il listino, poi le altre per nome.

        Il listino va dalla quota più alta (`listino.listino_di`): Serie A,
        Serie B, Amatori. Le categorie senza quota seguono, in ordine
        alfabetico come nell'elenco.
        """
        from models.categoria.listino import listino_di
        from models.categoria.service import CategoriaService

        ordine = [c.id for c in listino_di(gara)]
        for categoria in CategoriaService.list_for_gara(gara, include_inactive=True):
            if categoria.id not in ordine:
                ordine.append(categoria.id)
        return {cid: posto for posto, cid in enumerate(ordine)}

    @staticmethod
    def girone_dei_giocatori(gara: Optional[Gara]) -> Dict[int, int]:
        """Il girone di ogni giocatore, o vuoto se la gara ha un girone solo.

        Dalle partite del primo turno, quando ci sono: lì c'è anche chi si è
        ritirato con la regola EXCLUDE, la cui iscrizione non esiste più.
        Prima, dalle iscrizioni.
        """
        if gara is None or not _a_gironi_possibili(gara):
            return {}
        from models.match.models import Match

        girone: Dict[int, int] = {}
        partite = (
            db.session.query(
                Match.player1_id, Match.player2_id, Match.bracket_group
            )
            .filter(
                Match.gara_id == gara.id,
                Match.round_number == 1,
                Match.bracket_group.isnot(None),
            )
            .all()
        )
        for p1, p2, gruppo in partite:
            for pid in (p1, p2):
                if pid is not None:
                    girone[pid] = gruppo
        for user_id, gruppo in (
            db.session.query(Inscription.user_id, Inscription.group_index)
            .filter(
                Inscription.gara_id == gara.id,
                Inscription.group_index.isnot(None),
                Inscription.is_waitlist.is_(False),
            )
            .all()
        ):
            girone.setdefault(user_id, gruppo)
        if len(set(girone.values())) < 2:
            return {}
        return girone

    @staticmethod
    def gironi(gara: Optional[Gara]) -> List[List[int]]:
        """I gironi della gara, in ordine (A, B, …): liste di id."""
        girone = GironiService.girone_dei_giocatori(gara)
        if not girone:
            return []
        per: Dict[int, List[int]] = {}
        for pid, gruppo in girone.items():
            per.setdefault(gruppo, []).append(pid)
        return [sorted(per[g]) for g in sorted(per)]

    @staticmethod
    def azzera(gara_id: int) -> None:
        """Toglie i gironi: annullare l'avvio vuol dire ricomporli."""
        db.session.query(Inscription).filter(Inscription.gara_id == gara_id).update(
            {Inscription.group_index: None}, synchronize_session="fetch"
        )


__all__ = ["Anteprima", "GironiService", "nome_del_girone"]
