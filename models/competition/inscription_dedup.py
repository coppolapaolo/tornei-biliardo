"""Ridurre a una sola le iscrizioni doppie di un giocatore alla stessa gara.

Un giocatore ha **una** iscrizione per gara: è quello che
`InscriptionService.inscribe_user` garantisce dal primo giorno (`if existing:
return existing`), ed è l'unico punto del codice che crea iscrizioni. Ma la
regola viveva solo lì, in un `if` di Python, e chi scrive in SQL diretto non ci
passa: l'unione di due account (`UserMergeService`) riassegnava le iscrizioni
della sorgente con un `UPDATE` di massa, e sulle gare a cui erano iscritti
entrambi gli account il giocatore compariva **due volte** — una con la
categoria assegnata dal direttore, una senza.

Da qui due cose. La prima è il vincolo `uq_inscription_gara_user`, che sposta
la regola dove non si può aggirare. La seconda è questo modulo, perché il
vincolo da solo non basterebbe: la dedup generica del merge, sull'errore di
unicità, tiene la riga del **destinatario** e butta quella della sorgente —
cioè, nel caso reale, avrebbe tenuto l'iscrizione nuova e perso la categoria.
Un dato che il direttore ha inserito a mano non si cancella per un dettaglio
di implementazione dell'unione.

**La regola.** Sopravvive la riga più vecchia — quella che il direttore ha in
mano e a cui puntano i riferimenti — e su di lei si scrive:

* i campi vuoti si riempiono con quelli delle altre (categoria, squadra,
  ordine di sorteggio): un valore assente non è una scelta, è un buco;
* lo stato si prende **in blocco** dalla riga più avanzata, dove
  *attivo > lista d'attesa > ritirato*. In blocco e non campo per campo perché
  i sette campi di stato si raccontano a vicenda: `waitlist_position` senza
  `is_waitlist` è una riga che non vuol dire niente. E la riga più avanzata
  vince perché il posto in gara è un fatto acquisito da uno dei due account:
  l'unione non può rispedire in lista d'attesa chi era entrato.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

#: Campi che descrivono **come** il giocatore sta in gara. Si prendono tutti
#: dalla stessa riga: mescolarli produce stati incoerenti.
CAMPI_STATO = (
    "is_waitlist",
    "waitlist_position",
    "waitlist_reason",
    "is_withdrawn",
    "withdrawn_at",
    "is_forfeit",
    "forfeit_at",
)

#: Campi che sono un dato indipendente: si riempiono a buchi.
CAMPI_DATO = ("categoria_id", "squadra_id", "initial_order")


@dataclass
class PianoFusione:
    """Cosa fare per ridurre a una le iscrizioni di un gruppo.

    Separato dall'esecuzione perché il piano si sa **mostrare** senza toccare
    niente: è quello che stampa `scripts/fix_iscrizioni_duplicate.py` prima di
    chiedere il `--commit`.
    """

    sopravvissuta_id: int
    valori: Dict[str, Any] = field(default_factory=dict)
    da_cancellare: List[int] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.da_cancellare or self.valori)


def _rango_stato(riga: Mapping[str, Any]) -> int:
    """Quanto è «avanzato» lo stato: attivo 2, lista d'attesa 1, ritirato 0."""
    if riga.get("is_withdrawn"):
        return 0
    return 1 if riga.get("is_waitlist") else 2


def _anzianita(riga: Mapping[str, Any]):
    """Chiave d'ordinamento: prima la più vecchia, a parità l'id più basso.

    `created_at` è nullable (le iscrizioni antiche non ce l'hanno): un NULL
    finisce in coda invece di far esplodere il confronto fra `None` e data.
    """
    creata = riga.get("created_at")
    return (creata is None, creata or datetime.max, riga["id"])


def piano_di_fusione(righe: Sequence[Mapping[str, Any]]) -> Optional[PianoFusione]:
    """Il piano per fondere ``righe`` (iscrizioni alla stessa gara) in una.

    Funzione **pura**: legge dizionari e ne restituisce un altro, senza toccare
    il database. La usano tre chiamanti diversi — l'unione di account, lo
    script di riparazione e il presidio della migration — e restare pura è
    l'unico modo perché la regola sia davvero una sola.

    Restituisce ``None`` se non c'è niente da fondere (zero o una riga).
    """
    if len(righe) < 2:
        return None

    per_anzianita = sorted(righe, key=_anzianita)
    sopravvissuta = per_anzianita[0]

    valori: Dict[str, Any] = {}

    # I buchi si riempiono col primo valore disponibile, dalla più vecchia in
    # avanti: se due righe dicono cose diverse vince quella che c'era prima.
    for campo in CAMPI_DATO:
        if sopravvissuta.get(campo) is not None:
            continue
        for altra in per_anzianita[1:]:
            if altra.get(campo) is not None:
                valori[campo] = altra[campo]
                break

    # Lo stato arriva tutto insieme dalla riga più avanzata (a parità, la più
    # vecchia — `sorted` è stabile e `per_anzianita` è già in quell'ordine).
    piu_avanzata = max(per_anzianita, key=_rango_stato)
    if piu_avanzata["id"] != sopravvissuta["id"]:
        for campo in CAMPI_STATO:
            if piu_avanzata.get(campo) != sopravvissuta.get(campo):
                valori[campo] = piu_avanzata.get(campo)

    return PianoFusione(
        sopravvissuta_id=sopravvissuta["id"],
        valori=valori,
        da_cancellare=[r["id"] for r in per_anzianita[1:]],
    )


# --------------------------------------------------------------------- ORM


def _come_dizionario(iscrizione) -> Dict[str, Any]:
    """Un'``Inscription`` nella forma che `piano_di_fusione` sa leggere."""
    riga: Dict[str, Any] = {"id": iscrizione.id, "created_at": iscrizione.created_at}
    for campo in CAMPI_STATO + CAMPI_DATO:
        riga[campo] = getattr(iscrizione, campo)
    return riga


def applica_piano(piano: PianoFusione, iscrizioni: Iterable) -> None:
    """Esegue ``piano`` sulle ``Inscription`` passate, nella sessione corrente.

    Le righe nascoste dal profilo (`hidden_inscription`) puntano all'id
    dell'iscrizione: prima di cancellarne una le si ripuntano sulla
    sopravvissuta, altrimenti il `CASCADE` se le porterebbe via e chi aveva
    nascosto quella gara se la ritroverebbe pubblica.
    """
    from models.base import db
    from models.user.privacy_models import HiddenInscription

    per_id = {i.id: i for i in iscrizioni}
    sopravvissuta = per_id[piano.sopravvissuta_id]

    for campo, valore in piano.valori.items():
        setattr(sopravvissuta, campo, valore)

    for vecchio_id in piano.da_cancellare:
        for nascosta in HiddenInscription.query.filter_by(
            inscription_id=vecchio_id
        ).all():
            gia_presente = HiddenInscription.query.filter_by(
                user_id=nascosta.user_id, inscription_id=piano.sopravvissuta_id
            ).first()
            if gia_presente is not None:
                db.session.delete(nascosta)
            else:
                nascosta.inscription_id = piano.sopravvissuta_id
        db.session.delete(per_id[vecchio_id])

    db.session.flush()


def fondi_gruppo(iscrizioni: Sequence) -> Optional[PianoFusione]:
    """Fonde in una le ``Inscription`` passate. Restituisce il piano eseguito."""
    piano = piano_di_fusione([_come_dizionario(i) for i in iscrizioni])
    if piano is None:
        return None
    applica_piano(piano, iscrizioni)
    return piano


def fondi_tra_utenti(source_id: int, target_id: int) -> List[PianoFusione]:
    """Fonde le iscrizioni dei due account gara per gara, intestandole al target.

    Chiamata **prima** della riassegnazione generica delle chiavi esterne
    dell'unione: dopo, ogni gara ha una riga sola e il passo generico non
    incontra più conflitti di unicità.
    """
    from models.base import db
    from models.competition.models import Inscription

    iscrizioni = (
        db.session.query(Inscription)
        .filter(Inscription.user_id.in_([source_id, target_id]))
        .all()
    )

    per_gara: Dict[int, List] = {}
    for iscrizione in iscrizioni:
        per_gara.setdefault(iscrizione.gara_id, []).append(iscrizione)

    piani: List[PianoFusione] = []
    for gruppo in per_gara.values():
        if len(gruppo) < 2:
            continue
        piano = fondi_gruppo(gruppo)
        if piano is not None:
            sopravvissuta = next(i for i in gruppo if i.id == piano.sopravvissuta_id)
            sopravvissuta.user_id = target_id
            piani.append(piano)

    if piani:
        db.session.flush()
    return piani


def trova_duplicati() -> Dict[tuple, List]:
    """Le iscrizioni doppie già presenti nel database, per (gara, giocatore).

    Serve alla riparazione dei dati storici: quelli scritti prima del vincolo
    `uq_inscription_gara_user`, quando l'unione di due account poteva lasciare
    due righe.
    """
    from models.base import db
    from models.competition.models import Inscription

    doppioni = (
        db.session.query(Inscription.gara_id, Inscription.user_id)
        .group_by(Inscription.gara_id, Inscription.user_id)
        .having(db.func.count(Inscription.id) > 1)
        .all()
    )

    gruppi: Dict[tuple, List] = {}
    for gara_id, user_id in doppioni:
        gruppi[(gara_id, user_id)] = (
            db.session.query(Inscription)
            .filter_by(gara_id=gara_id, user_id=user_id)
            .all()
        )
    return gruppi
