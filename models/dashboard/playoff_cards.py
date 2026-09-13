"""Il playoff in dashboard dopo l'invito: iscritto, in lista, iscrizioni chiuse.

Fino al 2026-09-13 il playoff compariva solo come **invito da accettare**
(`DashboardSectionBuilder.build_playoff_invitations`): chi rispondeva lo
perdeva di vista, e chi era fuori zona non lo vedeva mai. Eppure fra l'invito
e il primo turno il playoff è una gara che sta per cominciare, e il parallelo
con le gare lo ha fissato l'utente:

* chi ha **accettato** ci è iscritto, come a una gara a cui si è iscritto;
* chi è **fuori zona** è in lista d'attesa: se un qualificato rifiuta,
  l'invito passa al primo degli esclusi (SPECIFICHE.md, «Playoff»);
* chi ha **rifiutato** — o ha lasciato scadere l'invito, o è stato sostituito
  — trova una gara a cui non è iscritto e con le iscrizioni chiuse.

L'invito ancora senza risposta **non** è una scheda: resta la sezione in cima
alla dashboard (decisione del 2026-09-10), perché è una cosa da fare con una
scadenza.

La scheda vale finché la gara di playoff non comincia: prima che il direttore
la crei la scheda si disegna dalla configurazione, dopo porta la gara. Dal
primo turno il playoff è una gara come le altre, con la sua tessera — partite,
classifica, diretta — e questo modulo non la tocca più.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as date_cls
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set, cast

from sqlalchemy import or_, select

from models.base import db
from models.status_enum import GaraStatus

from .gara_cards import ElenchiGare, GaraCardVM, _ordine_delle_mie


class PostoPlayoff(str, Enum):
    """Dove sta chi guarda, rispetto al playoff."""

    ISCRITTO = "iscritto"
    IN_LISTA = "in_lista"
    CHIUSO = "chiuso"


class MotivoChiuso(str, Enum):
    """Perché per chi guarda le iscrizioni al playoff sono chiuse."""

    RIFIUTATO = "rifiutato"
    SCADUTO = "scaduto"
    SOSTITUITO = "sostituito"
    #: Fuori zona e non chiamabile: la cascata lo salta (gare minime).
    REQUISITI = "requisiti"


#: Gli stati in cui la gara di playoff non è ancora cominciata.
STATI_PRIMA_DEL_VIA = (GaraStatus.SETUP.value, GaraStatus.INSCRIPTION.value)


@dataclass
class PlayoffCardVM:
    """Un playoff come lo vede **una persona precisa**, prima del primo turno.

    Espone le stesse scorciatoie di `GaraCardVM` che servono a ordinare le
    sezioni (`date`, `real_status`, `is_conclusa`, `ha_un_fatto_mio`), così le
    due schede convivono nello stesso elenco.
    """

    config: Any
    posto: str
    #: Posti del playoff e quanti hanno già accettato.
    posti: int
    confermati: int
    #: C'è ancora qualcuno che deve rispondere: la cascata non è finita.
    inviti_aperti: bool
    motivo: Optional[str] = None
    posizione_in_lista: Optional[int] = None
    #: In lista perché ha accettato tardi e i posti erano pieni, non perché è
    #: fuori zona: i due casi si spiegano in modo diverso.
    lista_per_posti: bool = False
    gara: Optional[Any] = None
    #: Disciplina, sala e quota ereditate dal campionato, finché la gara non c'è.
    parametri: Dict[str, Any] = field(default_factory=dict)

    #: Il template sceglie la scheda da questo: non `gara.is_playoff`, che
    #: vale anche per la tessera del playoff già cominciato.
    is_scheda_playoff = True

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def campionato_name(self) -> Optional[str]:
        campionato = self.config.campionato
        return campionato.name if campionato is not None else None

    @property
    def date(self) -> Optional[date_cls]:
        if self.gara is not None:
            return self.gara.date
        quando = self.config.scheduled_date
        return quando.date() if isinstance(quando, datetime) else quando

    @property
    def real_status(self) -> str:
        if self.gara is not None:
            return self.gara.get_real_status()
        return GaraStatus.SETUP.value

    @property
    def is_conclusa(self) -> bool:
        return False

    @property
    def is_in_corso(self) -> bool:
        return False

    @property
    def ha_un_fatto_mio(self) -> bool:
        return self.posto != PostoPlayoff.CHIUSO.value

    @property
    def discipline(self) -> Optional[str]:
        if self.gara is not None:
            return self.gara.discipline
        return self.parametri.get("discipline")

    @property
    def location(self) -> Optional[str]:
        if self.gara is not None and self.gara.location:
            return self.gara.location
        return self.config.location or self.parametri.get("location")

    @property
    def liberi(self) -> int:
        return max(self.posti - self.confermati, 0)

    @property
    def quota(self) -> Optional[float]:
        if self.gara is not None:
            return self.gara.entry_fee or None
        return self.parametri.get("entry_fee") or None

    @property
    def is_prova(self) -> bool:
        campionato = self.config.campionato
        return bool(campionato is not None and campionato.is_prova)

    # -- scorciatoie per il template: niente letterali di dominio in Jinja --

    @property
    def is_iscritto(self) -> bool:
        return self.posto == PostoPlayoff.ISCRITTO.value

    @property
    def is_in_lista(self) -> bool:
        return self.posto == PostoPlayoff.IN_LISTA.value

    @property
    def is_chiuso(self) -> bool:
        return self.posto == PostoPlayoff.CHIUSO.value

    @property
    def per_rifiuto(self) -> bool:
        return self.motivo == MotivoChiuso.RIFIUTATO.value

    @property
    def per_scadenza(self) -> bool:
        return self.motivo == MotivoChiuso.SCADUTO.value

    @property
    def per_sostituzione(self) -> bool:
        return self.motivo == MotivoChiuso.SOSTITUITO.value


def _motivo(stato: Any) -> str:
    from models.playoff.models import QualificationStatus

    return {
        QualificationStatus.DECLINED: MotivoChiuso.RIFIUTATO.value,
        QualificationStatus.EXPIRED: MotivoChiuso.SCADUTO.value,
        QualificationStatus.REPLACED: MotivoChiuso.SOSTITUITO.value,
    }[stato]


def _coda_degli_esclusi(config: Any, con_invito: Set[int]) -> List[int]:
    """Chi verrebbe chiamato, in ordine, se i qualificati rifiutassero.

    La stessa valutazione della cascata (`find_replacement_player`), ma sulla
    classifica intera: la cascata guarda una finestra che si allarga a ogni
    invito emesso, e il secondo escluso deve leggere «#2» anche prima che
    tocchi a lui.
    """
    from models.classification.models import Classification

    righe = Classification.query.filter_by(campionato_id=config.campionato_id).count()
    valutati = config.evaluate_qualifications(posti=max(righe, config.max_participants))
    return [d["user_id"] for d in valutati if d["user_id"] not in con_invito]


def build_playoff_cards(user_id: int) -> List[PlayoffCardVM]:
    """Le schede dei playoff per chi guarda: una per configurazione.

    Compaiono quando gli inviti sono partiti — prima la zona è solo una
    previsione, e la classifica generale la mostra già — e solo a chi ha
    giocato il campionato o ha un invito.
    """
    from models.campionato.models import Campionato
    from models.classification.models import Classification
    from models.competition.models import Gara, Inscription
    from models.playoff.models import (
        PlayoffConfiguration,
        PlayoffQualification,
        QualificationStatus,
    )

    con_inviti_partiti = select(PlayoffQualification.configuration_id).where(
        PlayoffQualification.invited_at.isnot(None)
    )
    campionati_giocati = select(Classification.campionato_id).where(
        Classification.user_id == user_id
    )
    miei_inviti = select(PlayoffQualification.configuration_id).where(
        PlayoffQualification.user_id == user_id
    )

    # Il join su `Campionato` fa scattare i filtri di sessione — soft-delete e
    # prove (ADR-058) — che si applicano solo alle entità presenti nella query:
    # stessa trappola documentata in `build_playoff_invitations`.
    configurazioni = (
        db.session.query(PlayoffConfiguration)
        .join(Campionato, Campionato.id == PlayoffConfiguration.campionato_id)
        .filter(
            PlayoffConfiguration.is_active.is_(True),
            Campionato.is_deleted.is_(False),
            PlayoffConfiguration.id.in_(con_inviti_partiti),
            or_(
                PlayoffConfiguration.campionato_id.in_(campionati_giocati),
                PlayoffConfiguration.id.in_(miei_inviti),
            ),
        )
        .order_by(PlayoffConfiguration.id)
        .all()
    )

    schede: List[PlayoffCardVM] = []
    for config in configurazioni:
        gara = (
            db.session.query(Gara).filter(Gara.playoff_config_id == config.id).first()
        )
        if gara is not None and gara.status not in STATI_PRIMA_DEL_VIA:
            continue

        inviti = PlayoffQualification.query.filter_by(configuration_id=config.id).all()
        mio = next((q for q in inviti if q.user_id == user_id), None)
        if mio is not None and mio.status == QualificationStatus.PENDING:
            continue  # è l'invito in cima alla dashboard, non una scheda

        comune: Dict[str, Any] = {
            "config": config,
            "posti": config.max_participants,
            "confermati": sum(
                1 for q in inviti if q.status == QualificationStatus.CONFIRMED
            ),
            "inviti_aperti": any(
                q.status == QualificationStatus.PENDING for q in inviti
            ),
            "gara": gara,
            "parametri": config.get_gara_params() if gara is None else {},
        }

        if mio is None:
            coda = _coda_degli_esclusi(config, {q.user_id for q in inviti})
            if user_id in coda:
                schede.append(
                    PlayoffCardVM(
                        posto=PostoPlayoff.IN_LISTA.value,
                        posizione_in_lista=coda.index(user_id) + 1,
                        **comune,
                    )
                )
            else:
                schede.append(
                    PlayoffCardVM(
                        posto=PostoPlayoff.CHIUSO.value,
                        motivo=MotivoChiuso.REQUISITI.value,
                        **comune,
                    )
                )
        elif mio.status == QualificationStatus.CONFIRMED:
            # Chi accetta tardi e trova i posti pieni va in lista d'attesa
            # nella gara, come in ogni gara (`_iscrivi_alla_gara`).
            iscrizione = (
                Inscription.query.filter_by(gara_id=gara.id, user_id=user_id).first()
                if gara is not None
                else None
            )
            if (
                iscrizione is not None
                and iscrizione.is_waitlist
                and not iscrizione.is_withdrawn
            ):
                schede.append(
                    PlayoffCardVM(
                        posto=PostoPlayoff.IN_LISTA.value,
                        posizione_in_lista=iscrizione.waitlist_position,
                        lista_per_posti=True,
                        **comune,
                    )
                )
            else:
                schede.append(
                    PlayoffCardVM(posto=PostoPlayoff.ISCRITTO.value, **comune)
                )
        else:
            schede.append(
                PlayoffCardVM(
                    posto=PostoPlayoff.CHIUSO.value,
                    motivo=_motivo(mio.status),
                    **comune,
                )
            )
    return schede


def unisci_schede_playoff(gare: ElenchiGare, schede: List[PlayoffCardVM]) -> None:
    """Mette le schede dei playoff negli elenchi delle gare, una per gara.

    Chi ha accettato o è in lista la trova fra le sue; chi ha le iscrizioni
    chiuse in arrivo, come una gara a cui non è iscritto. Se la gara di
    playoff esiste già, la sua tessera generica lascia il posto alla scheda —
    a iscrizioni aperte direbbe «Iscrizioni aperte» anche a chi ha rifiutato —
    tranne per chi la dirige: a lui serve la tessera con «Gestisci».

    Va chiamata **dopo** gli `enrich_with_*`, che lavorano sulle `GaraCardVM`.
    """
    if not schede:
        return

    dirette = {c.id for c in gare.mie if c.can_manage}
    schede = [s for s in schede if s.gara is None or s.gara.id not in dirette]
    sostituite = {s.gara.id for s in schede if s.gara is not None}

    gare.mie = [c for c in gare.mie if c.id not in sostituite]
    gare.aperte = [c for c in gare.aperte if c.id not in sostituite]
    gare.in_arrivo = [c for c in gare.in_arrivo if c.id not in sostituite]

    def ordine_mie(card: Any):
        return _ordine_delle_mie(card)

    def per_data(card: Any):
        return (card.date is None, card.date or date_cls.max)

    # Gli elenchi sono dichiarati di `GaraCardVM`, e da qui in poi li legge
    # solo il template: le due schede espongono le stesse scorciatoie.
    miste_mie: List[Any] = [*gare.mie, *(s for s in schede if s.ha_un_fatto_mio)]
    miste_arrivo: List[Any] = [
        *gare.in_arrivo,
        *(s for s in schede if not s.ha_un_fatto_mio),
    ]
    gare.mie = cast(List[GaraCardVM], sorted(miste_mie, key=ordine_mie))
    gare.in_arrivo = cast(List[GaraCardVM], sorted(miste_arrivo, key=per_data))
