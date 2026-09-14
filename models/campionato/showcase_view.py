"""Cosa mostra la vetrina di un campionato (issue #235, secondo lotto).

Un campionato non è una gara più grande: è una **stagione**, e chi apre il suo
link si fa domande diverse. Non «quando si gioca» ma «quando si è giocato e
quando si gioca ancora»; non «quanti posti restano» ma «a che punto siamo e
chi sta vincendo»; e soprattutto — la domanda che decide se questa pagina
serve a qualcosa — «da dove entro adesso».

Da lì viene l'unica scelta di progetto che conta qui: **la chiamata all'azione
di un campionato punta a una gara**. Non esiste «iscriviti al campionato»; ci
si iscrive alla prova aperta, e se nessuna lo è la pagina lo dice invece di
mostrare un pulsante che non porta da nessuna parte (`prossima`).

Nessuna scrittura, come per la gara: la classifica generale arriva da
`TournamentStatisticsService.calculate_general_classification`, che è
`@read_only`, e i vincitori delle prove concluse da una query sola.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from flask_babel import format_date, gettext as _

from models.base import db
from models.campionato.conteggio_gare import ConteggioGare

# Stessa forma della classifica della gara, e di proposito: le due vetrine
# la disegnano con lo stesso markup, e due dataclass gemelle sarebbero due
# occasioni di farle divergere.
from models.competition.showcase_view import (
    LOCANDINA_DI_RIPIEGO,
    RigaClassifica,
    gara_ha_finito,
    gara_si_sta_giocando,
)
from models.status_enum import ClassificationSystem

#: Quante righe di classifica generale finiscono in vetrina. Come per la gara:
#: il podio più un contorno, non un tabulato.
RIGHE_CLASSIFICA = 8


@dataclass(frozen=True)
class TappaVetrina:
    """Una prova nel calendario del campionato."""

    gara: Any
    numero: Optional[int]
    giorno: str
    mese: str
    titolo: str
    sottotitolo: Optional[str]
    #: `done` (conclusa), `open` (iscrizioni aperte), `live` (in corso),
    #: `todo` (ancora da giocare). Decide sia la parola sia la superficie.
    stato: str
    stato_testo: str


@dataclass(frozen=True)
class VetrinaCampionato:
    """Tutto quello che la pagina pubblica di un campionato mostra."""

    campionato: Any
    titolo: str
    descrizione: Optional[str]
    banner_url: str
    periodo: Optional[str] = None
    sede: Optional[str] = None
    citta: Optional[str] = None
    formula: Optional[str] = None
    giocatori: int = 0
    #: Le gare regolari in calendario e quelle giocate. La finale dei playoff
    #: non ne fa parte: si conta a parte in `finali` (`conteggio_gare.py`).
    prove_totali: int = 0
    prove_giocate: int = 0
    finali: int = 0
    finali_giocate: int = 0
    organizzatore: Optional[str] = None
    calendario: List[TappaVetrina] = field(default_factory=list)
    classifica: List[RigaClassifica] = field(default_factory=list)
    #: La gara su cui si può agire adesso: quella con le iscrizioni aperte.
    #: `None` quando non ce n'è, ed è un caso normale — fra una prova e
    #: l'altra la pagina resta un resoconto.
    prossima: Optional[TappaVetrina] = None
    stato_testo: str = ""
    stato_tono: str = ""
    link_esterno: Optional[str] = None
    etichetta_link: Optional[str] = None
    indicizzabile: bool = True

    @property
    def conteggio(self) -> ConteggioGare:
        """Le gare in calendario: «5 gare + finale»."""
        return ConteggioGare(regolari=self.prove_totali, finali=self.finali)

    @property
    def conteggio_giocate(self) -> ConteggioGare:
        """Le gare già giocate, con la finale se è conclusa."""
        return ConteggioGare(regolari=self.prove_giocate, finali=self.finali_giocate)


def _vincitori_delle_prove(gare) -> Dict[int, str]:
    """Chi ha vinto ciascuna prova conclusa, in **una** query.

    Si legge la riga in prima posizione della classifica dell'ultimo turno,
    che è la stessa fonte che la pagina della gara mostra davvero. Batchare
    sulle coppie `(gara_id, ultimo_turno)` invece di interrogare gara per gara
    è ciò che tiene questa pagina a query costanti anche su un campionato di
    dodici prove: la vetrina la aprono i crawler, e un N+1 qui si paga a ogni
    passaggio.
    """
    from sqlalchemy import tuple_
    from sqlalchemy.orm import joinedload
    from models.classification.models import RoundClassification

    coppie = [
        (g.id, g.rounds_count) for g in gare if gara_ha_finito(g) and g.rounds_count
    ]
    if not coppie:
        return {}

    righe = (
        db.session.query(RoundClassification)
        .filter(
            tuple_(RoundClassification.gara_id, RoundClassification.round_number).in_(
                coppie
            ),
            RoundClassification.position == 1,
        )
        .options(joinedload(RoundClassification.user))
        .all()
    )
    vincitori = {}
    for riga in righe:
        if riga.user is not None:
            nome = getattr(riga.user, "display_name", None) or riga.user.username
            vincitori[riga.gara_id] = nome
    return vincitori


def _tappa(gara, vincitori: Dict[int, str], iscritti: Dict[int, int]) -> TappaVetrina:
    """Una riga del calendario, con la frase giusta per il suo stato."""
    from models.competition.invite_service import GaraInviteService

    aperte = GaraInviteService.inscription_open(gara)

    if gara_ha_finito(gara):
        stato, stato_testo = "done", _("Conclusa")
        vincitore = vincitori.get(gara.id)
        sottotitolo = _("Vince %(nome)s", nome=vincitore) if vincitore else None
    elif gara_si_sta_giocando(gara):
        stato, stato_testo = "live", _("In corso")
        sottotitolo = None
    elif aperte:
        stato, stato_testo = "open", _("Aperta")
        quanti = iscritti.get(gara.id, 0)
        liberi = (
            max(0, gara.max_participants - quanti)
            if gara.max_participants is not None
            else None
        )
        sottotitolo = (
            _("%(n)s iscritti · %(liberi)s liberi", n=quanti, liberi=liberi)
            if liberi is not None
            else _("%(n)s iscritti", n=quanti)
        )
    else:
        stato, stato_testo = "todo", _("Da giocare")
        sottotitolo = (
            _(
                "Iscrizioni dal %(data)s",
                data=format_date(gara.inscription_start, "d MMM"),
            )
            if gara.inscription_start
            else None
        )

    return TappaVetrina(
        gara=gara,
        numero=gara.number,
        giorno=format_date(gara.date, "d") if gara.date else "—",
        mese=format_date(gara.date, "MMM") if gara.date else "",
        # `display_name` e basta: anteporre il numero è l'applicazione che si
        # sovrappone alla scelta del direttore, e su un nome come «3ª prova»
        # produrrebbe «3ª prova · 3ª prova». Il numero lo dicono già l'ordine
        # della lista e la data nella colonna a sinistra.
        titolo=gara.display_name,
        sottotitolo=sottotitolo,
        stato=stato,
        stato_testo=stato_testo,
    )


def _formula(campionato) -> str:
    """Su cosa si ordina la classifica, detto a chi non conosce l'app.

    Si legge `classification_system` e **non** `campionato_type` (ADR-047): il
    tipo dice come si formano gli abbinamenti, il sistema su cosa si ordina, e
    sono scelte indipendenti — coincidono abbastanza spesso da rendere lo
    scambio invisibile per mesi.
    """
    sistema = ClassificationSystem.resolve(
        getattr(campionato, "classification_system", None)
    )
    if sistema == ClassificationSystem.RACK:
        return _("Classifica a triangoli vinti")
    if sistema == ClassificationSystem.POSITION:
        return _("Classifica a punti per piazzamento")
    return _("Classifica a vittorie")


def _classifica(campionato) -> List[RigaClassifica]:
    """La classifica generale, ridotta alle colonne che stanno su un telefono.

    Il numero mostrato dipende dal sistema, per la stessa ragione di
    `_formula`: mostrare le vittorie in un campionato che ordina per triangoli
    darebbe una lista che sembra ordinata male.
    """
    from models.campionato.statistics_service import TournamentStatisticsService

    sistema = ClassificationSystem.resolve(
        getattr(campionato, "classification_system", None)
    )
    if sistema == ClassificationSystem.RACK:
        chiave, unita = "total_racks_won", _("T")
    elif sistema == ClassificationSystem.POSITION:
        chiave, unita = "total_points", _("P")
    else:
        chiave, unita = "total_matches_won", _("V")

    generale = TournamentStatisticsService().calculate_general_classification(
        campionato.id
    )
    return [
        RigaClassifica(
            posizione=posizione,
            nome=dati.get("username", "—"),
            valore=dati.get(chiave, 0) or 0,
            unita=unita,
        )
        for posizione, dati in generale[:RIGHE_CLASSIFICA]
    ]


def _periodo(gare) -> Optional[str]:
    """«giu – nov 2026», dalle date della prima e dell'ultima prova.

    Si ricava dal calendario invece di essere un campo a sé: un campionato non
    ha una data d'inizio in colonna, e chiederne una al direttore sarebbe un
    dato in più da tenere allineato a quello che le gare già dicono.
    """
    date = sorted(g.date for g in gare if g.date is not None)
    if not date:
        return None
    prima, ultima = date[0], date[-1]
    if prima.year == ultima.year:
        if prima.month == ultima.month:
            return format_date(prima, "MMMM yyyy")
        return _(
            "%(a)s – %(b)s",
            a=format_date(prima, "MMM"),
            b=format_date(ultima, "MMM yyyy"),
        )
    return _(
        "%(a)s – %(b)s",
        a=format_date(prima, "MMM yyyy"),
        b=format_date(ultima, "MMM yyyy"),
    )


def _stato(campionato, calendario) -> tuple:
    """A che punto è la stagione, e con che tono dirlo."""
    if campionato.terminated_at is not None:
        return _("Campionato concluso"), ""

    aperta = next((t for t in calendario if t.stato == "open"), None)
    if aperta is not None:
        return (
            _("Iscrizioni aperte · gara %(n)s", n=aperta.numero)
            if aperta.numero
            else _("Iscrizioni aperte")
        ), "open"

    in_corso = next((t for t in calendario if t.stato == "live"), None)
    if in_corso is not None:
        return _("Gara in corso"), "live"

    giocate = sum(1 for t in calendario if t.stato == "done")
    if giocate and giocate == len(calendario):
        return _("Tutte le gare giocate"), ""
    if giocate:
        return _("In corso · %(n)s gare giocate", n=giocate), ""
    return _("Non ancora iniziato"), ""


def costruisci_vetrina_campionato(campionato) -> VetrinaCampionato:
    """Prepara tutto ciò che la vetrina pubblica di un campionato mostra."""
    from models.competition.models import Gara, Inscription
    from utils.image_paths import ImagePathManager

    gare = Gara.query.filter_by(campionato_id=campionato.id).order_by(Gara.number).all()

    # Iscritti per gara, in una query sola invece che una per riga del
    # calendario: stessa ragione di `_vincitori_delle_prove`.
    conteggi = dict(
        db.session.query(Inscription.gara_id, db.func.count(Inscription.id))
        .filter(
            Inscription.gara_id.in_([g.id for g in gare] or [0]),
            Inscription.is_withdrawn.is_(False),
            Inscription.is_waitlist.is_(False),
        )
        .group_by(Inscription.gara_id)
        .all()
    )

    vincitori = _vincitori_delle_prove(gare)
    calendario = [_tappa(g, vincitori, conteggi) for g in gare]

    giocatori = (
        db.session.query(db.func.count(db.distinct(Inscription.user_id)))
        .join(Gara, Inscription.gara_id == Gara.id)
        .filter(Gara.campionato_id == campionato.id)
        .scalar()
        or 0
    )

    sala = getattr(campionato, "default_venue", None)
    banner = campionato.banner_path
    link = campionato.effective_external_link
    stato_testo, stato_tono = _stato(campionato, calendario)

    return VetrinaCampionato(
        campionato=campionato,
        titolo=campionato.name,
        descrizione=(campionato.description or "").strip() or None,
        banner_url=(
            ImagePathManager.url_from_db_path(banner)
            if banner
            else LOCANDINA_DI_RIPIEGO
        ),
        periodo=_periodo(gare),
        sede=getattr(sala, "name", None) if sala is not None else None,
        citta=getattr(sala, "city", None) if sala is not None else None,
        formula=_formula(campionato),
        giocatori=giocatori,
        prove_totali=sum(1 for t in calendario if not t.gara.is_playoff),
        prove_giocate=sum(
            1 for t in calendario if t.stato == "done" and not t.gara.is_playoff
        ),
        finali=sum(1 for t in calendario if t.gara.is_playoff),
        finali_giocate=sum(
            1 for t in calendario if t.stato == "done" and t.gara.is_playoff
        ),
        organizzatore=_chi_organizza(campionato),
        calendario=calendario,
        classifica=_classifica(campionato),
        prossima=next((t for t in calendario if t.stato == "open"), None),
        stato_testo=stato_testo,
        stato_tono=stato_tono,
        link_esterno=link[0] if link else None,
        etichetta_link=(link[1] if link else None) or _("Regolamento e informazioni"),
        # Un campionato senza nemmeno una prova in calendario non è ancora
        # niente: il link funziona per chi ce l'ha, ma non si offre ai motori
        # di ricerca una pagina che non ha ancora contenuto.
        indicizzabile=bool(calendario),
    )


def _chi_organizza(campionato) -> Optional[str]:
    """I direttori del campionato, col nome che hanno scelto di mostrare."""
    direttori = getattr(campionato, "directors", None) or []
    nomi = [
        getattr(d, "display_name", None) or getattr(d, "username", "")
        for d in direttori
    ]
    nomi = [n for n in nomi if n]
    return ", ".join(nomi) if nomi else None


def descrizione_social_campionato(vetrina: VetrinaCampionato) -> str:
    """La riga sotto il titolo nell'anteprima quando si condivide il link."""
    pezzi = []
    if vetrina.periodo:
        pezzi.append(vetrina.periodo)
    if vetrina.prove_totali:
        pezzi.append(vetrina.conteggio.gare_testo)
    if vetrina.sede:
        pezzi.append(vetrina.sede)
    pezzi.append(vetrina.stato_testo)
    return " · ".join(p for p in pezzi if p)
