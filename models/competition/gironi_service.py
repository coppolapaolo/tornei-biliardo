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
from flask_babel import ngettext

from models.base import db
from models.exceptions import ValidationError
from models.matchmaking.configuration import MatchmakingStrategy
from models.matchmaking.fase_finale import turni_del_tabellone, verifica_qualificati
from models.matchmaking.gironi import (
    MINIMO_PER_GIRONE,
    ComposizioneGironi,
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

    #: quanti passano al tabellone finale da ogni girone; 0 = nessun tabellone.
    #: Con un girone solo il tabellone non si gioca (`girone_unico_senza_tabellone`).
    qualificati_per_girone: int = 0

    @property
    def girone_unico_senza_tabellone(self) -> bool:
        """La gara prevede il tabellone, che con un girone solo non si gioca.

        Il foglio di avvio lo dice quando il direttore sceglie un girone.
        """
        return self.qualificati_per_girone > 0

    @property
    def turni(self) -> Dict[int, int]:
        """Numero di gironi → turni della gara.

        Quelli del girone più numeroso, più quelli del tabellone finale se la
        gara ne ha uno.
        """
        turni = {}
        for g, taglie in self.taglie.items():
            turni[g] = turni_dei_gironi(taglie)
            # Il tabellone si gioca solo con più gironi.
            if self.qualificati_per_girone and g >= 2:
                turni[g] += turni_del_tabellone(self.qualificati_per_girone * g)
        return turni


def voci_della_composizione() -> List[tuple]:
    """Le voci di «Composizione dei gironi»: (valore, nome, spiegazione).

    Una sola fonte per i moduli della gara, del campionato e per il foglio di
    avvio. Nell'interfaccia non si dice «serpentina» né «abbinamenti» (ADR-076).
    """
    return [
        (
            ComposizioneGironi.SORTEGGIO.value,
            _("Sorteggio"),
            _("La fila degli iscritti la decide il sorteggio della gara."),
        ),
        (
            ComposizioneGironi.ELO.value,
            _("Per ELO"),
            _("Dal più alto: i più forti finiscono in gironi diversi."),
        ),
        (
            ComposizioneGironi.CATEGORIA.value,
            _("Per categoria"),
            _(
                "Nell'ordine del listino, poi per ELO: le prime categorie si "
                "dividono fra i gironi."
            ),
        ),
    ]


def come_si_compongono(composizione: object) -> str:
    """«a sorteggio», «per ELO», «per categoria»: il pezzo della frase."""
    voce = ComposizioneGironi.resolve(getattr(composizione, "value", composizione))
    if voce is ComposizioneGironi.ELO:
        return _("per ELO")
    if voce is ComposizioneGironi.CATEGORIA:
        return _("per categoria")
    return _("a sorteggio")


def descrivi_gironi(
    taglie: Optional[Sequence[int]],
    tetto: int,
    composizione: object,
    separa_compagni: bool = False,
) -> str:
    """La frase della formula a gironi, per il regolamento e le pagine.

    Prima dell'avvio (``taglie`` None) dice il tetto: «Fino a 2 gironi
    all'italiana, composti per ELO: quanti, lo sceglie il direttore all'avvio».
    Dopo, i gironi veri: «2 gironi all'italiana da 6 e 5 giocatori, composti
    per ELO».
    """
    come = come_si_compongono(composizione)
    if taglie:
        numero = len(taglie)
        diverse = sorted(set(taglie), reverse=True)
        quanti = _(" e ").join(str(t) for t in diverse)
        frase = ngettext(
            "%(num)d girone all'italiana da %(taglie)s giocatori, composto %(come)s",
            "%(num)d gironi all'italiana da %(taglie)s giocatori, composti %(come)s",
            numero,
            taglie=quanti,
            come=come,
        )
    else:
        frase = _(
            "Fino a %(n)s gironi all'italiana, composti %(come)s: quanti, lo "
            "sceglie il direttore all'avvio, con almeno %(minimo)s giocatori "
            "per girone",
            n=tetto,
            come=come,
            minimo=MINIMO_PER_GIRONE,
        )
    if separa_compagni:
        frase += _("; i compagni di squadra in gironi diversi, quando si può")
    return frase + "."


def descrivi_fase_finale(
    qualificati: int, finalina: bool, minuti: Optional[int] = None
) -> str:
    """La frase del tabellone dopo i gironi (ADR-081), per regolamento e pagine.

    «Poi i primi 2 di ogni girone vanno al tabellone, con la finalina per il
    3° posto; nel tabellone 45 minuti a partita.» Il limite si dice solo se
    è diverso da quello dei gironi: ``minuti`` è il valore della gara, a tre
    stati (None come i gironi, 0 senza limite, N minuti).
    """
    frase = ngettext(
        "Poi il primo di ogni girone va al tabellone",
        "Poi i primi %(num)d di ogni girone vanno al tabellone",
        qualificati,
    )
    if finalina:
        frase += _(", con la finalina per il 3° posto")
    if minuti is not None:
        if minuti > 0:
            frase += _("; nel tabellone %(n)s minuti a partita", n=minuti)
        else:
            frase += _("; nel tabellone senza limite di tempo")
    return frase + "."


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
            qualificati_per_girone=(
                gara.effective_qualifiers_per_group if gara.ha_tabellone_finale else 0
            ),
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
            # Col girone solo il tabellone non si gioca, anche se la gara lo
            # prevede: la gara finisce col girone, e la sua classifica è
            # quella finale (SPECIFICHE.md, «Fase finale dopo i gironi»).
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
        GironiService._verifica_tabellone(gara, [len(g) for g in composti])
        girone_di = {
            pid: indice for indice, girone in enumerate(composti) for pid in girone
        }
        for iscrizione in iscrizioni:
            iscrizione.group_index = girone_di[iscrizione.user_id]
        gara.rounds_count = turni_dei_gironi(
            [len(g) for g in composti]
        ) + GironiService._turni_del_tabellone(gara, len(composti))
        return composti

    @staticmethod
    def _turni_del_tabellone(gara: Gara, gironi: int) -> int:
        """I turni del tabellone finale, se la gara ne ha uno; altrimenti zero."""
        if not gara.ha_tabellone_finale:
            return 0
        return turni_del_tabellone(gara.effective_qualifiers_per_group * gironi)

    @staticmethod
    def _verifica_tabellone(gara: Gara, taglie: Sequence[int]) -> None:
        """Il tabellone finale si fa con questi gironi? Se no, l'avvio si ferma."""
        if not gara.ha_tabellone_finale:
            return
        k = gara.effective_qualifiers_per_group
        motivo = verifica_qualificati(taglie, k)
        if motivo == "girone":
            raise ValidationError(
                _(
                    "Al tabellone passano i primi %(k)s di ogni girone, ma un "
                    "girone ne ha solo %(n)s: scegli meno gironi o meno "
                    "qualificati.",
                    k=k,
                    n=min(taglie),
                )
            )
        if motivo is not None:
            raise ValidationError(_("Il numero di qualificati non è valido."))

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
            db.session.query(Match.player1_id, Match.player2_id, Match.bracket_group)
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
    def frase(gara: Optional[Gara]) -> Optional[str]:
        """La frase della formula a gironi di una gara, o None col girone unico.

        Con il tabellone dopo i gironi segue la frase della fase finale
        (`descrivi_fase_finale`). Una gara partita con un girone solo non ha
        frase: è il girone di sempre, e il tabellone non si gioca.
        """
        if gara is None or not _a_gironi_possibili(gara):
            return None
        from .campi_modificabili import e_avviata

        composti = GironiService.gironi(gara)
        # Avviata con un girone solo, o senza tetto: è il girone di sempre.
        if not composti and (gara.effective_max_groups <= 1 or e_avviata(gara)):
            return None
        frase = descrivi_gironi(
            [len(g) for g in composti] or None,
            gara.effective_max_groups,
            gara.effective_group_seeding,
            bool(gara.separate_teammates),
        )
        if gara.ha_tabellone_finale:
            frase += " " + descrivi_fase_finale(
                gara.effective_qualifiers_per_group,
                bool(gara.third_place_match),
                gara.final_phase_time_limit_minutes,
            )
        return frase

    @staticmethod
    def azzera(gara_id: int) -> None:
        """Toglie i gironi: annullare l'avvio vuol dire ricomporli."""
        db.session.query(Inscription).filter(Inscription.gara_id == gara_id).update(
            {Inscription.group_index: None}, synchronize_session="fetch"
        )


__all__ = [
    "Anteprima",
    "GironiService",
    "come_si_compongono",
    "descrivi_fase_finale",
    "descrivi_gironi",
    "nome_del_girone",
    "voci_della_composizione",
]
