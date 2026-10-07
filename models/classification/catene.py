"""Quale catena vale, e le partite dello scontro diretto (ADR-078).

Il motore (`ordinamento.py`) è puro; qui si leggono dal database le due cose
che gli servono e che solo la gara o il campionato sanno:

- **la catena** di ogni livello, normalizzata;
- **gli scontri**, cioè le partite a due chiuse, se la catena ha lo scontro
  diretto. Si caricano solo in quel caso: chi non usa il criterio non paga la
  query.

Un posto solo, così la classifica di turno, quella di gara, la ricerca dei pari
da spareggiare e la classifica generale leggono la stessa catena.
"""

from __future__ import annotations

from typing import Any, Iterable, List, Optional

from models.status_enum import ClassificationSystem, MatchStatus

from .ordinamento import (
    SSR_FINO_AL_DEFAULT,
    Catena,
    Criterio,
    Livello,
    Scontro,
    catena_dal_testo,
    catena_di_default,
    normalizza_catena,
    ssr_della_catena,
    testo_della_catena,
)


def sistema_della_gara(gara: Any) -> ClassificationSystem:
    """Il sistema della gara, ma per la catena: POSITION ripiega su WINS.

    Nel sistema POSITION la catena non si usa (ADR-040); ci si arriva solo
    per una gara a tabellone senza tabellone persistito, e lì l'ordine per
    vittorie è meglio di una classifica tutta a pari.
    """
    sistema = ClassificationSystem.resolve(getattr(gara, "classification_system", None))
    return sistema if ordina_con_la_catena(sistema) else ClassificationSystem.WINS


def sistema_dichiarato(gara: Any) -> ClassificationSystem:
    return ClassificationSystem.resolve(getattr(gara, "classification_system", None))


def ordina_con_la_catena(sistema: ClassificationSystem) -> bool:
    """Se quel sistema si ordina con la catena. POSITION no (ADR-040)."""
    return sistema in (
        ClassificationSystem.WINS,
        ClassificationSystem.RACK,
        ClassificationSystem.POINTS,
    )


#: Le colonne delle catene, per livello: sulla gara, e quella che il
#: campionato propone alle sue gare (ADR-075). La catena della classifica
#: generale sta solo sul campionato (`Campionato.catena_generale`).
COLONNA_DELLA_GARA = {Livello.TURNO: "catena_turno", Livello.GARA: "catena_gara"}
COLONNA_PROPOSTA = {
    Livello.TURNO: "default_catena_turno",
    Livello.GARA: "default_catena_gara",
}


def _sistema_del_campionato(campionato: Any) -> ClassificationSystem:
    sistema = ClassificationSystem.resolve(
        getattr(campionato, "default_classification_system", None)
    )
    return sistema if ordina_con_la_catena(sistema) else ClassificationSystem.WINS


def catena_proposta(campionato: Any, livello: Livello) -> Catena:
    """La catena che il campionato propone alle gare di quel livello.

    Senza una scelta del campionato, il default dell'app per il suo sistema.
    """
    sistema = _sistema_del_campionato(campionato)
    salvata = catena_dal_testo(getattr(campionato, COLONNA_PROPOSTA[livello], None))
    if salvata is None:
        salvata = catena_di_default(livello, sistema)
    return normalizza_catena(salvata, livello, sistema)


def _testo_al_turno(gara: Any, turno: int) -> Optional[str]:
    """Il testo della catena di turno in vigore al turno ``turno``.

    A gara avviata la catena di turno è una regola, e vale dal turno
    successivo (ADR-075): la classifica di un turno già nato si fa con la
    catena di allora, anche se la si ricalcola dopo una correzione. La storia
    dice cosa valeva: il primo cambio che vale da **dopo** quel turno ha in
    «prima» la catena di quel turno. Senza cambi così, vale quella di adesso.
    """
    attuale = getattr(gara, "catena_turno", None)
    gara_id = getattr(gara, "id", None)
    if not isinstance(gara_id, int):
        return attuale if isinstance(attuale, str) else None
    from models.base import db
    from models.storia.models import SettingsChange, SettingsChangeField

    riga = (
        db.session.query(SettingsChangeField.old_value)
        .join(SettingsChange, SettingsChange.id == SettingsChangeField.change_id)
        .filter(
            SettingsChange.gara_id == gara_id,
            SettingsChange.from_round.isnot(None),
            SettingsChange.from_round > turno,
            SettingsChangeField.field == "catena_turno",
        )
        .order_by(
            SettingsChange.from_round,
            SettingsChange.created_at,
            SettingsChange.id,
        )
        .first()
    )
    if riga is None:
        return attuale if isinstance(attuale, str) else None
    return riga[0] or None


def _catena_della_gara(
    gara: Any, livello: Livello, testo: Optional[str], sistema: ClassificationSystem
) -> Catena:
    """La catena salvata sulla gara, o quella del campionato, o il default."""
    salvata = catena_dal_testo(testo)
    if salvata is None:
        campionato = getattr(gara, "campionato", None)
        salvata = catena_dal_testo(
            getattr(campionato, COLONNA_PROPOSTA[livello], None)
            if campionato is not None
            else None
        )
    if salvata is None:
        salvata = catena_di_default(livello, sistema)
    return normalizza_catena(salvata, livello, sistema)


def catena_di_turno(gara: Any, turno: Optional[int] = None) -> Catena:
    """La catena della classifica di turno: gara → campionato → default.

    Con ``turno``, quella in vigore a quel turno (vedi `_testo_al_turno`).
    """
    sistema = sistema_della_gara(gara)
    testo = (
        _testo_al_turno(gara, turno)
        if turno is not None
        else getattr(gara, "catena_turno", None)
    )
    return _catena_della_gara(gara, Livello.TURNO, testo, sistema)


def catena_di_gara(gara: Any) -> Catena:
    """La catena della classifica di gara: gara → campionato → default."""
    sistema = sistema_della_gara(gara)
    return _catena_della_gara(
        gara, Livello.GARA, getattr(gara, "catena_gara", None), sistema
    )


def ssr_fino_al_della_gara(gara: Any) -> Optional[int]:
    """Fin dove la gara scioglie i pari merito con lo spareggio, o None."""
    voce = ssr_della_catena(catena_di_gara(gara))
    if voce is None:
        return None
    return voce.fino_al or SSR_FINO_AL_DEFAULT


def catena_generale(campionato: Any, sistema: ClassificationSystem) -> Catena:
    """La catena della classifica generale del campionato, o il default."""
    salvata = catena_dal_testo(getattr(campionato, "catena_generale", None))
    if salvata is None:
        salvata = catena_di_default(Livello.CAMPIONATO, sistema)
    return normalizza_catena(salvata, Livello.CAMPIONATO, sistema)


def testo_dal_modulo(
    grezzo: object, livello: Livello, sistema: ClassificationSystem
) -> str:
    """La catena scritta dall'editor, ammessa a quel livello e pronta da salvare.

    Il modulo manda le voci separate da virgole (o una lista JSON). Le voci
    che quel livello non ammette — il criterio principale, lo SSR nel turno,
    un doppione — si tolgono invece di rifiutare il salvataggio: l'editor non
    le offre, quindi arrivano solo da un invio costruito a mano o da un cambio
    di sistema, e la regola è la stessa che vale in lettura.
    """
    if not ordina_con_la_catena(sistema):
        sistema = ClassificationSystem.WINS
    testo = grezzo if isinstance(grezzo, str) else ""
    catena = catena_dal_testo(testo) or ()
    return testo_della_catena(normalizza_catena(catena, livello, sistema))


def adegua_al_sistema(
    testo: Optional[str],
    livello: Livello,
    vecchio: ClassificationSystem,
    nuovo: ClassificationSystem,
) -> Optional[str]:
    """La catena dopo un cambio di sistema di classifica.

    Se era la catena di default del sistema vecchio, diventa quella del nuovo:
    nessuno l'aveva scelta, era il comportamento dell'app. Lo spareggio della
    catena di gara conserva il suo posto. Una catena scelta dal direttore
    resta com'è (in lettura se ne toglie solo il nuovo criterio principale).
    Restituisce None se non c'è niente da cambiare.
    """
    if not ordina_con_la_catena(vecchio):
        vecchio = ClassificationSystem.WINS
    if not ordina_con_la_catena(nuovo):
        nuovo = ClassificationSystem.WINS
    catena = catena_dal_testo(testo)
    if catena is None or vecchio is nuovo:
        return None
    voce_ssr = ssr_della_catena(catena)
    fino_al = voce_ssr.fino_al if voce_ssr is not None else None
    if livello is Livello.GARA:
        attesa = catena_di_default(livello, vecchio, ssr_fino_al=fino_al)
        dopo = catena_di_default(livello, nuovo, ssr_fino_al=fino_al)
    else:
        attesa = catena_di_default(livello, vecchio)
        dopo = catena_di_default(livello, nuovo)
    if normalizza_catena(catena, livello, vecchio) != normalizza_catena(
        attesa, livello, vecchio
    ):
        return None
    return testo_della_catena(normalizza_catena(dopo, livello, nuovo))


def usa_scontri(catena: Iterable[Any]) -> bool:
    return any(v.criterio is Criterio.SCONTRI_DIRETTI for v in catena)


def _scontro(match: Any) -> Optional[Scontro]:
    """La partita come scontro diretto, o None se non lo è.

    Solo le partite a due: la X non è uno scontro, e nel trio il «vincitore»
    non dice chi ha battuto chi.
    """
    if match.is_bye or match.is_trio or not match.player1_id or not match.player2_id:
        return None
    # Stessa regola di `ScoreAggregator._process_regular_match`: decide il
    # punteggio; a pari punteggio solo chi il direttore ha fatto passare nel
    # tabellone (ADR-077), altrimenti è un pareggio.
    punti1, punti2 = match.player1_score or 0, match.player2_score or 0
    if punti1 > punti2:
        vincitore: Optional[int] = match.player1_id
    elif punti2 > punti1:
        vincitore = match.player2_id
    elif match.winner_id in (match.player1_id, match.player2_id):
        vincitore = match.winner_id
    else:
        vincitore = None
    rack1, rack2 = punti1, punti2
    if match.is_multi_set:
        rack1 = sum(s.player1_racks or 0 for s in match.sets)
        rack2 = sum(s.player2_racks or 0 for s in match.sets)
    return Scontro(match.player1_id, match.player2_id, rack1, rack2, vincitore)


def scontri_delle_gare(
    gare_ids: Iterable[int], fino_al_turno: Optional[int] = None
) -> List[Scontro]:
    """Le partite a due chiuse di quelle gare, fino al turno indicato."""
    from models.base import db
    from models.match.models import Match

    ids = list(gare_ids)
    if not ids:
        return []
    query = db.session.query(Match).filter(
        Match.gara_id.in_(ids),
        Match.status.in_(MatchStatus.finished_values()),
    )
    if fino_al_turno is not None:
        query = query.filter(Match.round_number <= fino_al_turno)
    scontri = (_scontro(m) for m in query.all())
    return [s for s in scontri if s is not None]
