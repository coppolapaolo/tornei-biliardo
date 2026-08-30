"""Cosa mostra la vetrina di una gara, e come lo dice (issue #235).

Chi apre `/g/<link>` da un post non conosce la gara: non sa cosa sia «Amalfi»,
né perché in classifica ci sia una X. Le domande a cui deve rispondere una
schermata sola, sul telefono, sono sei — **cosa si gioca, quando, dove, quanto
costa, chi organizza, come ci si iscrive** — e questo modulo le prepara tutte.

Sta separato dalla route per due ragioni. La prima è che si verifica senza
HTTP: `costruisci_vetrina(gara)` prende una gara e restituisce un oggetto, e
un test può leggerne i campi invece di cercare stringhe dentro dell'HTML. La
seconda è che gli stessi dati servono due volte — una alla pagina e una ai
meta Open Graph, che sono quello che lo scraper del social legge — e comporli
due volte è il modo sicuro per farli divergere.

**Nessuna scrittura.** Nemmeno indiretta: la classifica si legge già
calcolata (vedi `showcase_service.classifica_gia_calcolata`), perché questa
pagina la aprono i crawler e ogni loro passaggio innescherebbe altrimenti un
ricalcolo con relativo commit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as _date, datetime
from typing import Any, List, Optional

from flask_babel import gettext as _

from models.base import db, utc_now
from models.competition.models import Gara, Inscription
from models.status_enum import Discipline, GaraStatus

#: Quante righe di classifica finisce in vetrina a gara conclusa. Il podio più
#: un contorno: è un manifesto, non un tabulato — chi vuole tutto apre la
#: pagina della gara.
RIGHE_CLASSIFICA_VETRINA = 8


@dataclass(frozen=True)
class RigaInformativa:
    """Una voce del riquadro dei dati: etichetta, valore, icona."""

    icona: str
    etichetta: str
    valore: str


@dataclass(frozen=True)
class Vetrina:
    """Tutto quello che la pagina pubblica di una gara mostra."""

    gara: Any
    titolo: str
    sottotitolo: Optional[str]
    descrizione: Optional[str]
    banner_url: Optional[str]
    righe: List[RigaInformativa] = field(default_factory=list)
    #: Iscritti confermati e posti totali. `posti` è `None` quando la gara non
    #: ha un massimo: lì "12 iscritti" è tutto ciò che si può dire, e inventare
    #: una capienza sarebbe peggio che tacere.
    iscritti: int = 0
    posti: Optional[int] = None
    iscrizioni_aperte: bool = False
    stato_testo: str = ""
    conclusa: bool = False
    classifica: List[Any] = field(default_factory=list)
    link_esterno: Optional[str] = None
    etichetta_link: Optional[str] = None
    #: Una gara in preparazione con la data già passata è un residuo (ADR-030):
    #: la lista pubblica la nasconde, e qui si evita di darla in pasto ai motori
    #: di ricerca invece di far finta che non esista — chi ha il link la vede
    #: comunque, ed è giusto, perché il link gliel'ha dato il direttore.
    indicizzabile: bool = True

    @property
    def posti_liberi(self) -> Optional[int]:
        if self.posti is None:
            return None
        return max(0, self.posti - self.iscritti)

    @property
    def percentuale_riempimento(self) -> int:
        """Quanto è piena la gara, 0-100. Serve alla barra dei posti."""
        if not self.posti:
            return 0
        return min(100, round(self.iscritti * 100 / self.posti))


def _formato_di_gioco(gara: Gara) -> str:
    """La formula di gara detta come la direbbe un giocatore.

    «Palla 9, al 5» e non `9_ball / race_to=True / distance=5`: chi arriva da
    un post non ha motivo di conoscere i nomi interni, e questa riga è metà
    della ragione per cui deciderà se venire.
    """
    disciplina = Discipline.normalize(gara.discipline)
    nome_disciplina = disciplina.display_name if disciplina else gara.discipline

    if gara.is_multi_set and gara.match_distance:
        set_txt = (
            _("al %(n)s", n=gara.match_distance)
            if gara.is_race_to_sets
            else _("%(n)s set", n=gara.match_distance)
        )
        return _(
            "%(disciplina)s — %(set)s, ogni set al %(rack)s",
            disciplina=nome_disciplina,
            set=set_txt,
            rack=gara.distance,
        )

    if gara.is_race_to:
        return _(
            "%(disciplina)s — al %(n)s", disciplina=nome_disciplina, n=gara.distance
        )
    return _(
        "%(disciplina)s — %(n)s rack esatti",
        disciplina=nome_disciplina,
        n=gara.distance,
    )


def _dove_si_gioca(gara: Gara) -> Optional[str]:
    """Sede: la sala se c'è, la stringa libera se no.

    `billiard_hall` è il dato buono (ha anche la città); `location` è il
    residuo storico e resta come ripiego perché su molte gare è l'unica cosa
    scritta.
    """
    sala = getattr(gara, "billiard_hall", None)
    if sala is not None and getattr(sala, "name", None):
        citta = getattr(sala, "city", None)
        return f"{sala.name}, {citta}" if citta else sala.name
    return gara.location or None


def _quando_si_gioca(gara: Gara) -> str:
    """Quando si gioca, come è scritto sul calendario della sala.

    `Gara.date` e `Gara.time` sono **già l'ora locale dell'evento**: il
    direttore scrive «sabato alle 20:30» e quello resta, colonne `Date` e
    `Time` senza fuso. Non sono la stessa cosa di `inscription_start`, che è
    un `DateTime` in UTC e infatti si formatta con `|datetime_local`.

    Convertirle nel fuso del lettore (ADR-043) sarebbe qui un difetto, non una
    correttezza: sposterebbe l'orario di una gara che si gioca in un posto
    solo, e a un giocatore in viaggio direbbe di presentarsi all'ora
    sbagliata.
    """
    if gara.time is not None:
        return datetime.combine(gara.date, gara.time).strftime("%d/%m/%Y, %H:%M")
    return gara.date.strftime("%d/%m/%Y")


def _chi_organizza(gara: Gara) -> Optional[str]:
    """Il direttore, con il nome che ha scelto di mostrare."""
    direttori = getattr(gara, "directors", None) or []
    nomi = [
        getattr(d, "display_name", None) or getattr(d, "username", "")
        for d in direttori
    ]
    nomi = [n for n in nomi if n]
    return ", ".join(nomi) if nomi else None


def _stato_leggibile(gara: Gara, aperte: bool) -> str:
    """Una riga che dice a che punto è la gara, senza gergo."""
    stato = gara.get_real_status()
    if stato == GaraStatus.COMPLETED.value:
        return _("Gara conclusa")
    if stato == GaraStatus.PLAYING.value:
        return _("Gara in corso")
    if aperte:
        return _("Iscrizioni aperte")
    # `inscription_start` è naive-UTC come tutte le colonne `DateTime` del
    # progetto: si confronta con `utc_now()`, non con l'ora locale della
    # macchina — altrimenti d'estate la finestra si sposta di due ore.
    if gara.inscription_start and gara.inscription_start > utc_now():
        return _("Iscrizioni non ancora aperte")
    return _("Iscrizioni chiuse")


def costruisci_vetrina(gara: Gara) -> Vetrina:
    """Prepara tutto ciò che la vetrina pubblica di una gara mostra."""
    from models.competition.invite_service import GaraInviteService
    from models.competition.showcase_service import classifica_gia_calcolata
    from utils.image_paths import ImagePathManager

    iscritti = (
        db.session.query(db.func.count(Inscription.id))
        .filter_by(gara_id=gara.id, is_withdrawn=False, is_waitlist=False)
        .scalar()
        or 0
    )

    aperte = GaraInviteService.inscription_open(gara)
    stato_reale = gara.get_real_status()
    conclusa = stato_reale == GaraStatus.COMPLETED.value

    righe = [
        RigaInformativa(
            icona="fa-calendar-day",
            etichetta=_("Quando"),
            valore=_quando_si_gioca(gara),
        ),
        RigaInformativa(
            icona="fa-trophy",
            etichetta=_("Formato"),
            valore=_formato_di_gioco(gara),
        ),
    ]

    dove = _dove_si_gioca(gara)
    if dove:
        righe.append(
            RigaInformativa(icona="fa-location-dot", etichetta=_("Dove"), valore=dove)
        )

    # La quota si mostra sempre che sia stata decisa, zero compreso: «Gratuito»
    # è un'informazione, il silenzio no — chi legge non sa se sia gratis o se
    # nessuno l'abbia scritto.
    if gara.entry_fee is not None:
        righe.append(
            RigaInformativa(
                icona="fa-euro-sign",
                etichetta=_("Quota"),
                valore=(
                    _("Gratuito")
                    if not gara.entry_fee
                    else _("%(fee)s €", fee=f"{gara.entry_fee:g}")
                ),
            )
        )

    organizza = _chi_organizza(gara)
    if organizza:
        righe.append(
            RigaInformativa(
                icona="fa-user-tie", etichetta=_("Organizza"), valore=organizza
            )
        )

    banner = gara.effective_banner_path
    banner_url = ImagePathManager.url_from_db_path(banner) if banner else None

    link = gara.effective_external_link
    titolo_campionato = gara.campionato.name if gara.campionato is not None else None

    return Vetrina(
        gara=gara,
        titolo=gara.display_name,
        sottotitolo=titolo_campionato,
        descrizione=(gara.description or "").strip() or None,
        banner_url=banner_url,
        righe=righe,
        iscritti=iscritti,
        posti=gara.max_participants,
        iscrizioni_aperte=aperte,
        stato_testo=_stato_leggibile(gara, aperte),
        conclusa=conclusa,
        classifica=(
            classifica_gia_calcolata(gara.id)[:RIGHE_CLASSIFICA_VETRINA]
            if conclusa
            else []
        ),
        link_esterno=link[0] if link else None,
        etichetta_link=(link[1] if link else None) or _("Regolamento e informazioni"),
        indicizzabile=not (
            gara.status == GaraStatus.SETUP.value
            and gara.date is not None
            and gara.date < _date.today()
        ),
    )


def descrizione_social(vetrina: Vetrina) -> str:
    """La riga che compare sotto il titolo nell'anteprima di WhatsApp.

    Ha spazio per poco — i client ne mostrano circa 150 caratteri — quindi
    prende le tre cose che fanno decidere: quando, dove, e se ci si può ancora
    iscrivere. La descrizione libera del direttore verrebbe tagliata a metà, e
    non è detto che le prime parole siano quelle importanti.
    """
    pezzi = [riga.valore for riga in vetrina.righe[:3]]
    if vetrina.conclusa:
        pezzi.append(_("Gara conclusa"))
    elif vetrina.iscrizioni_aperte:
        liberi = vetrina.posti_liberi
        pezzi.append(
            _("Iscrizioni aperte — %(n)s posti liberi", n=liberi)
            if liberi is not None
            else _("Iscrizioni aperte")
        )
    else:
        pezzi.append(vetrina.stato_testo)
    return " · ".join(p for p in pezzi if p)
