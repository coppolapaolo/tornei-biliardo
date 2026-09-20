"""La pagina di un gruppo: la scheda comune, la media, le sedute, l'esito.

Sono i quattro numeri che l'artboard `IstruttoreGruppo` chiede e che la fase 8c
non poteva ancora dire: senza una **scheda comune** «media del gruppo, su 60»
è un numero falso — la media fra un 51 su 60 e un 14 su 20 non vuol dire
niente (ADR-070 §5, rinvio chiuso qui).

Come in `allievi_view`, le definizioni stanno scritte per esteso perché sono la
parte in cui è più facile inventare una metrica che sembra vera.

* **La scheda del gruppo** è l'ultima che hai proposto *dal gruppo*, e i suoi
  numeri sono quelli del giro: mandata a quanti, presa da quanti. Il
  denominatore sono **le proposte partite**, non gli allievi di adesso: quel
  conto risponde a «di quelli a cui l'ho data, quanti l'hanno presa», che è
  l'unica domanda a cui quelle righe possano rispondere. Chi è entrato nel
  corso dopo, o chi era già in attesa di un'altra tua proposta, non l'ha mai
  ricevuta — e si dice a parte, perché è una cosa da fare, non un fallimento.
* **La media** si fa sulle copie che **leggi davvero**, una per allievo, e su
  quante si dice sempre. Si media la **quota** — quanto ha preso di quanto
  poteva — e la si riporta sulla scala della scheda del gruppo, perché sommare
  numeri grezzi qui sarebbe sbagliato tre volte: una seduta a metà ha un
  massimo più basso (`max_total` si legge dalle registrazioni), una scheda a
  giorni ha un massimo per giorno, e la copia è dell'allievo, che può
  cambiarla. È la stessa scala sola dell'ADR-068.
* **Le sedute di questa settimana** sono quelle della settimana **del corso**,
  la stessa che il riquadro in cima chiama «settimana 3 di 13». Un corso senza
  data d'inizio non ha settimane: lì sono gli ultimi sette giorni, e la pagina
  lo dice. Si contano su **tutte** le schede che leggi dei suoi allievi, non
  solo sulla scheda del gruppo: la domanda è se il corso si muove.
* **«N al livello dopo»** conta le persone che hanno superato un livello
  **mentre erano nel gruppo**, e mentre tu leggevi quella scheda. Il fatto è
  `passed_at` — il timbro — e non `promotes_sheet_id`: quello misurerebbe un
  gesto *tuo* (avergli dato la scheda dopo) più la sua accettazione, e con
  `level_up=auto` non esiste nessuna proposta, quindi un corso in cui tutti
  passano per soglia direbbe zero. «Mentre leggevi» rende il numero **stabile
  nel tempo**: un ex allievo che oggi ti richiude le schede non può cambiare
  ciò che il tuo storico dice di tre anni fa. Lo storico dice quello che hai
  visto succedere.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Sequence, Set, Tuple

from ..base import db, utc_now
from ..training_sheet.models import TrainingSession, TrainingSheet, TrainingSheetReader
from ..user.models import User
from .allievi_view import RigaAllievo, sedute_per_scheda
from .models import TrainingAssignment, TrainingGroup, TrainingGroupMember

#: Quanti giorni dura una settimana per un corso che non ha detto quando
#: comincia. Sette, all'indietro da oggi: senza `started_on` non esiste una
#: «settimana 3», e inventarne una vorrebbe dire scegliere un lunedì a caso.
GIORNI_SETTIMANA = 7


# ── la scheda del gruppo ────────────────────────────────────────────────────


@dataclass(frozen=True)
class SchedaDelGruppo:
    """La scheda proposta a tutto il corso, e com'è andata.

    ``copie`` sono le schede **nate** dalle accettazioni, per allievo, e solo
    quelle che l'istruttore legge davvero: prenderla e fargliela leggere sono
    due decisioni distinte dello stesso modulo (ADR-071), e la seconda si può
    togliere il giorno dopo.
    """

    modello: TrainingSheet
    proposte: List[TrainingAssignment]
    copie: Dict[int, TrainingSheet]
    senza: List[User]

    @property
    def mandate(self) -> int:
        return len(self.proposte)

    @property
    def prese(self) -> int:
        return sum(1 for p in self.proposte if p.is_accepted)

    @property
    def in_attesa(self) -> int:
        return sum(1 for p in self.proposte if p.is_pending)

    @property
    def lette(self) -> int:
        """Quante di quelle prese te le fanno leggere. Non è un rimprovero.

        Sta accanto alla media perché **è** il suo denominatore: una media su
        tre schede di cinque è un'altra cosa da una media su cinque.
        """
        return len(self.copie)


def scheda_del_gruppo(
    gruppo: TrainingGroup, righe: Sequence[RigaAllievo]
) -> Optional[SchedaDelGruppo]:
    """L'ultima scheda proposta da questo gruppo, con i numeri del giro.

    Il «giro» sono tutte le proposte partite dal gruppo con quel modello, anche
    quelle mandate più tardi a chi è arrivato dopo: è la stessa scheda, ed è
    quella la cosa che il corso ha in comune. Proporne una diversa — il livello
    dopo, a metà corso — cambia la scheda del gruppo, che è ciò che è
    successo davvero.
    """
    proposte = (
        TrainingAssignment.query.filter(TrainingAssignment.group_id == gruppo.id)
        .order_by(TrainingAssignment.proposed_at.desc(), TrainingAssignment.id.desc())
        .all()
    )
    if not proposte:
        return None

    modello = proposte[0].source_sheet
    if modello is None:
        return None
    giro = [p for p in proposte if p.source_sheet_id == modello.id]

    # Le schede che questo istruttore legge, allievo per allievo: `righe` viene
    # da `build_allievi`, che le ha già lette. Una copia presa e poi richiusa
    # semplicemente non c'è.
    leggibili = {
        riga.persona.id: {scheda.id: scheda for scheda in riga.schede} for riga in righe
    }
    copie: Dict[int, TrainingSheet] = {}
    for proposta in giro:
        nata = leggibili.get(proposta.user_id, {}).get(proposta.sheet_id or 0)
        if nata is not None:
            copie[proposta.user_id] = nata

    destinatari = {p.user_id for p in giro}
    senza = [riga.persona for riga in righe if riga.persona.id not in destinatari]
    return SchedaDelGruppo(modello=modello, proposte=giro, copie=copie, senza=senza)


def gia_ce_l_hanno(source_sheet_id: int, user_ids: Sequence[int]) -> Set[int]:
    """Chi, fra questi, ha **ancora** una scheda nata da quel modello.

    Serve a non ripetere una proposta a chi l'ha già presa: gliene nascerebbe
    una seconda copia identica, e si ritroverebbe due «Tecnica di base» da
    riempire. Chi l'aveva presa e poi l'ha **archiviata** non è qui dentro, e
    rimandargliela ha senso: la sua copia non c'è più.

    Non passa dalle letture: davide ha preso la scheda e non la fa leggere a
    nessuno, ma ce l'ha — e un doppione lo riceverebbe lo stesso.
    """
    if not user_ids:
        return set()
    righe = (
        db.session.query(TrainingAssignment.user_id)
        .join(TrainingSheet, TrainingSheet.id == TrainingAssignment.sheet_id)
        .filter(
            TrainingAssignment.source_sheet_id == source_sheet_id,
            TrainingAssignment.user_id.in_(list(user_ids)),
            TrainingSheet.is_active.is_(True),
        )
        .all()
    )
    return {user_id for (user_id,) in righe}


# ── la media del gruppo ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class MediaDelGruppo:
    """«47 su 60», e su quante schede è stata fatta.

    ``fuori`` sono le copie che leggi e che non hanno ancora fatto numeri —
    nessuna seduta chiusa, o una seduta in cui non c'era niente da contare.
    Si contano e si dicono, invece di sparire nel denominatore (ADR-068).
    """

    valore: int
    su: int
    schede: int
    fuori: int


def media_del_gruppo(
    scheda: Optional[SchedaDelGruppo],
    sedute: Dict[int, List[TrainingSession]],
) -> Optional[MediaDelGruppo]:
    """La media del gruppo sull'**ultima seduta** di ciascuno.

    Una seduta a testa, e non tutte: chi si allena tre volte a settimana
    sposterebbe da solo la media di un corso di cinque persone, e il numero
    finirebbe per dire quanto si allena lui invece che a che punto è il gruppo.

    Torna ``None`` quando non c'è niente da mediare: nessuna scheda comune, una
    scheda che di totale non ne ha (nessuna voce «a riusciti»), o nessuna copia
    con una seduta utile. Uno zero al posto di un numero che non esiste è la
    bugia più facile da scrivere in questa pagina.
    """
    if scheda is None:
        return None
    su = scheda.modello.total
    if su <= 0:
        return None

    quote: List[float] = []
    fuori = 0
    for copia in scheda.copie.values():
        quota = _quota_ultima_seduta(sedute.get(copia.id, []))
        if quota is None:
            fuori += 1
        else:
            quote.append(quota)

    if not quote:
        return None
    return MediaDelGruppo(
        valore=round(sum(quote) / len(quote) * su),
        su=su,
        schede=len(quote),
        fuori=fuori,
    )


def _quota_ultima_seduta(sedute: List[TrainingSession]) -> Optional[float]:
    """Quanto ha preso di quanto poteva, nell'ultima seduta che conta.

    Le sedute arrivano dalla più recente. Si scarta quella in cui non c'era
    niente da contare (`max_total` zero: una scheda fatta di sole spunte, o una
    seduta di sole voci a minuti) e si guarda quella prima: non è «l'ultima
    volta che si è allenato» ad avere un senso qui, ma l'ultima volta che ha
    prodotto un numero confrontabile.
    """
    for seduta in sedute:
        massimo = seduta.max_total
        if massimo > 0:
            return seduta.total / massimo
    return None


# ── le sedute di questa settimana ───────────────────────────────────────────


def settimana_del_corso(gruppo: TrainingGroup) -> Tuple[datetime, bool]:
    """Da quando comincia la settimana in corso, e se è quella **del corso**.

    Con una data d'inizio la settimana è quella che il riquadro in cima chiama
    «settimana 3 di 13»: comincia il giorno della settimana in cui è cominciato
    il corso, non il lunedì. Senza, sono gli ultimi sette giorni — e il
    booleano serve alla pagina per dirlo invece di far finta di niente.
    """
    adesso = utc_now()
    if gruppo.started_on is None or gruppo.week_of is None:
        return adesso - timedelta(days=GIORNI_SETTIMANA), False
    inizio = gruppo.started_on + timedelta(days=(gruppo.week_of - 1) * 7)
    return datetime.combine(inizio, datetime.min.time()), True


def sedute_della_settimana(
    gruppo: TrainingGroup, sedute: Dict[int, List[TrainingSession]]
) -> int:
    """Quante sedute hanno chiuso, in tutto, gli allievi di questo corso.

    Su tutte le schede che leggi, non solo su quella del gruppo: un allievo che
    si allena sulla scheda che aveva già si è allenato lo stesso.
    """
    da, _del_corso = settimana_del_corso(gruppo)
    return sum(
        1
        for elenco in sedute.values()
        for seduta in elenco
        if seduta.ended_at is not None and seduta.ended_at >= da
    )


# ── «N al livello dopo» ─────────────────────────────────────────────────────


def esiti_dei_corsi(
    instructor_id: int, gruppi: Sequence[TrainingGroup]
) -> Dict[int, int]:
    """Per ogni gruppo, quante persone hanno superato un livello **dentro**.

    Una query per tutta la pagina dello storico, e non una per corso.

    Non si filtra sulle schede attive: la scheda superata di solito viene
    **archiviata** proprio dal passaggio di livello (è la casella del modulo di
    accettazione, ADR-071), e cercarla fra le attive vorrebbe dire non trovare
    mai i passaggi andati a buon fine fino in fondo.
    """
    if not gruppi:
        return {}

    per_gruppo = {gruppo.id: gruppo for gruppo in gruppi}
    membri = (
        TrainingGroupMember.query.filter(
            TrainingGroupMember.group_id.in_(list(per_gruppo))
        )
        .order_by(TrainingGroupMember.joined_at.asc())
        .all()
    )
    if not membri:
        return {gid: 0 for gid in per_gruppo}

    righe: List[Tuple[TrainingSheet, TrainingSheetReader]] = (
        db.session.query(TrainingSheet, TrainingSheetReader)
        .join(TrainingSheetReader, TrainingSheetReader.sheet_id == TrainingSheet.id)
        .filter(
            TrainingSheetReader.user_id == instructor_id,
            TrainingSheet.passed_at.isnot(None),
            TrainingSheet.owner_id.in_({m.user_id for m in membri}),
        )
        .all()
    )

    timbri: Dict[int, List[datetime]] = {}
    for scheda, permesso in righe:
        if not _letta_quando(permesso, scheda.passed_at):
            continue
        timbri.setdefault(scheda.owner_id, []).append(scheda.passed_at)

    esiti: Dict[int, set] = {gid: set() for gid in per_gruppo}
    for membro in membri:
        dentro = _finestra(membro, per_gruppo[membro.group_id])
        for quando in timbri.get(membro.user_id, []):
            if dentro[0] <= quando <= dentro[1]:
                esiti[membro.group_id].add(membro.user_id)
                break
    return {gid: len(persone) for gid, persone in esiti.items()}


def esito_del_corso(instructor_id: int, gruppo: TrainingGroup) -> int:
    """Quante persone hanno superato un livello dentro **questo** corso."""
    return esiti_dei_corsi(instructor_id, [gruppo]).get(gruppo.id, 0)


def _finestra(
    membro: TrainingGroupMember, gruppo: TrainingGroup
) -> Tuple[datetime, datetime]:
    """Da quando a quando questa persona faceva parte del corso.

    Si guarda il **membro** e non il calendario del gruppo: chi è entrato a
    novembre non ha superato niente «nel corso» a settembre, e un corso può
    avere date dichiarate che nessuno ha rispettato.
    """
    fine = membro.left_at or gruppo.closed_at or utc_now()
    return membro.joined_at, max(fine, membro.joined_at)


def _letta_quando(permesso: TrainingSheetReader, quando: datetime) -> bool:
    """Se in quel momento l'istruttore leggeva davvero quella scheda."""
    if permesso.granted_at > quando:
        return False
    return permesso.revoked_at is None or permesso.revoked_at >= quando


# ── la pagina ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class GruppoVista:
    """Tutto ciò che la pagina di un gruppo mostra in cima."""

    gruppo: TrainingGroup
    dentro: List[RigaAllievo]
    fuori: List[RigaAllievo]
    scheda: Optional[SchedaDelGruppo]
    media: Optional[MediaDelGruppo]
    sedute_settimana: int
    settimana_del_corso: bool
    al_livello_dopo: int

    @property
    def quanti(self) -> int:
        return len(self.dentro)


def build_gruppo(
    instructor: User,
    gruppo: TrainingGroup,
    dentro: Sequence[RigaAllievo],
    fuori: Sequence[RigaAllievo],
) -> GruppoVista:
    """I numeri di un corso, a partire dagli allievi già letti dalla pagina.

    ``dentro`` e ``fuori`` arrivano da `build_allievi`, che ha già fatto la
    query cara (le sedute di tutti). Qui se ne rifà una sola, mirata alle
    schede di chi è dentro: una pagina che rileggesse tutto farebbe due volte
    il lavoro più costoso che ha.
    """
    sedute = sedute_per_scheda([scheda.id for riga in dentro for scheda in riga.schede])
    scheda = scheda_del_gruppo(gruppo, dentro)
    _, del_corso = settimana_del_corso(gruppo)

    return GruppoVista(
        gruppo=gruppo,
        dentro=list(dentro),
        fuori=list(fuori),
        scheda=scheda,
        media=media_del_gruppo(scheda, sedute),
        sedute_settimana=sedute_della_settimana(gruppo, sedute),
        settimana_del_corso=del_corso,
        al_livello_dopo=esito_del_corso(instructor.id, gruppo),
    )


__all__ = [
    "GIORNI_SETTIMANA",
    "GruppoVista",
    "MediaDelGruppo",
    "SchedaDelGruppo",
    "build_gruppo",
    "esiti_dei_corsi",
    "esito_del_corso",
    "gia_ce_l_hanno",
    "media_del_gruppo",
    "scheda_del_gruppo",
    "sedute_della_settimana",
    "settimana_del_corso",
]
