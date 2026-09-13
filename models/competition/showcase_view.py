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

**Dove va ciascun dato.** La pagina è impaginata come un manifesto, non come
una scheda, e questo decide la forma dei campi: *quando si gioca* sta nel
pannello del titolo (`data_testo` / `ora_testo`, separati perché l'ora può
mancare), *chi organizza* è la firma in fondo (`organizzatore`), e in `righe`
restano solo i fatti che si leggono di seguito. Impaginare non è decorare: se
la data tornasse dentro `righe` finirebbe in mezzo alle altre voci, e la prima
cosa che si cerca su un volantino sarebbe l'ultima a farsi trovare.

**Nessuna scrittura.** Nemmeno indiretta: la classifica si legge già
calcolata (vedi `showcase_service.classifica_gia_calcolata`), perché questa
pagina la aprono i crawler e ogni loro passaggio innescherebbe altrimenti un
ricalcolo con relativo commit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as _date
from typing import Any, List, Optional

from flask_babel import format_date, gettext as _

from models.base import db, utc_now
from models.competition.models import Gara, Inscription
from models.status_enum import Discipline, GaraStatus, ProvaDerivedStatus

#: Quante righe di classifica finiscono in vetrina a gara conclusa. Il podio
#: più un contorno: è un manifesto, non un tabulato — chi vuole tutto apre la
#: pagina della gara.
RIGHE_CLASSIFICA_VETRINA = 8

#: Oltre questa capienza le tacche dei posti diventano trattini da due pixel,
#: che non si contano e non si leggono: sopra, la barra torna piena.
MAX_TACCHE_POSTI = 32

#: La grafica del sito, quando il direttore non ha caricato una locandina.
#: È **la stessa** che finisce in `og:image`, ed è il punto: chi vede
#: l'anteprima nel messaggio e poi apre il link ritrova la stessa figura. Un
#: ripiego scritto due volte — una per i meta e una per la pagina — è un
#: ripiego destinato a divergere.
LOCANDINA_DI_RIPIEGO = "/static/img/social/vetrina-default.png"


@dataclass(frozen=True)
class RigaInformativa:
    """Una voce del blocco dei fatti: etichetta, valore, icona.

    `dettaglio` è la seconda riga, più piccola, sotto il valore: la città di
    una sala, il numero di turni. Non è un secondo dato — è la stessa risposta
    guardata più da vicino, e sta lì per non moltiplicare le righe.
    """

    icona: str
    etichetta: str
    valore: str
    dettaglio: Optional[str] = None


@dataclass(frozen=True)
class RigaClassifica:
    """Una riga di classifica già ridotta a ciò che si mostra.

    Esiste per una ragione precisa: il template mostrava
    `riga.user.display_name`, e `User` **non ha** `display_name`. In Jinja un
    attributo inesistente è `Undefined`, che si stampa come stringa vuota —
    nessun errore, nessun log, solo una classifica di posizioni e punteggi
    senza un nome. Ridurre qui, dove un test può leggere `.nome`, è ciò che
    rende quel difetto impossibile da ripetere in silenzio.
    """

    posizione: int
    nome: str
    valore: int
    unita: str


@dataclass(frozen=True)
class Vetrina:
    """Tutto quello che la pagina pubblica di una gara mostra."""

    gara: Any
    titolo: str
    #: La riga sopra il titolo: il campionato e a che numero di prova siamo.
    sopratitolo: Optional[str]
    descrizione: Optional[str]
    #: L'immagine che apre la pagina: la locandina del direttore, oppure
    #: quella del sito. Non è mai `None` — vedi `LOCANDINA_DI_RIPIEGO`.
    banner_url: str
    data_testo: str = ""
    ora_testo: Optional[str] = None
    organizzatore: Optional[str] = None
    righe: List[RigaInformativa] = field(default_factory=list)
    #: Iscritti confermati e posti totali. `posti` è `None` quando la gara non
    #: ha un massimo: lì "12 iscritti" è tutto ciò che si può dire, e inventare
    #: una capienza sarebbe peggio che tacere.
    iscritti: int = 0
    posti: Optional[int] = None
    iscrizioni_aperte: bool = False
    stato_testo: str = ""
    #: Come si colora la pastiglia di stato: `open` (iscrizioni aperte),
    #: `live` (si sta giocando), `""` (tutto il resto, neutro).
    stato_tono: str = ""
    conclusa: bool = False
    classifica: List[RigaClassifica] = field(default_factory=list)
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

    @property
    def mostra_tacche(self) -> bool:
        """Una tacca per posto, o la barra piena se i posti sono troppi."""
        return self.posti is not None and 0 < self.posti <= MAX_TACCHE_POSTI


#: Gli stati in cui una gara **ha finito di giocare**. Sono due, e il secondo
#: è quello che si dimentica: una gara che ha completato tutti i turni resta
#: `status='playing'` in colonna, e `get_real_status()` risponde
#: `campionato_completed` — non `completed`. Confrontare con il solo
#: `GaraStatus.COMPLETED` la classifica come «ancora da giocare», senza
#: vincitore e senza classifica finale, e sulla vetrina di un campionato la
#: fa comparire fra le gare in attesa mesi dopo che si è giocata.
STATI_CONCLUSI = frozenset(
    {
        GaraStatus.COMPLETED.value,
        ProvaDerivedStatus.TOURNAMENT_COMPLETED.value,
    }
)


#: Gli stati in cui una gara **si sta giocando**. Vale lo stesso avvertimento:
#: fra un turno e l'altro il risolutore risponde `round_completed`, e una gara
#: a metà torneo confrontata col solo `GaraStatus.PLAYING` risultava «da
#: giocare» — con tanto di «iscrizioni dal…» per una gara già cominciata.
STATI_IN_GIOCO = frozenset(
    {
        GaraStatus.PLAYING.value,
        GaraStatus.AWAITING_SSR.value,
        ProvaDerivedStatus.ROUND_COMPLETED.value,
    }
)


def gara_ha_finito(gara) -> bool:
    """La gara ha finito di giocare? Unica risposta per tutte le vetrine."""
    return gara.get_real_status() in STATI_CONCLUSI


def gara_si_sta_giocando(gara) -> bool:
    """La gara è cominciata e non è ancora finita?"""
    return gara.get_real_status() in STATI_IN_GIOCO


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
        "%(disciplina)s — %(n)s triangoli esatti",
        disciplina=nome_disciplina,
        n=gara.distance,
    )


def _dove_si_gioca(gara: Gara):
    """Sede e città, come coppia. La città è il dettaglio sotto il nome.

    `billiard_hall` è il dato buono (ha anche la città); `location` è il
    residuo storico e resta come ripiego perché su molte gare è l'unica cosa
    scritta.
    """
    sala = getattr(gara, "billiard_hall", None)
    if sala is not None and getattr(sala, "name", None):
        return sala.name, getattr(sala, "city", None)
    return (gara.location or None), None


def _quando_si_gioca(gara: Gara):
    """Data e ora dell'evento, già formattate e già separate.

    `Gara.date` e `Gara.time` sono **già l'ora locale dell'evento**: il
    direttore scrive «sabato alle 20:30» e quello resta, colonne `Date` e
    `Time` senza fuso. Non sono la stessa cosa di `inscription_start`, che è
    un `DateTime` in UTC e infatti si formatta con `|datetime_local`.

    Convertirle nel fuso del lettore (ADR-043) sarebbe qui un difetto, non una
    correttezza: sposterebbe l'orario di una gara che si gioca in un posto
    solo, e a un giocatore in viaggio direbbe di presentarsi all'ora
    sbagliata.
    """
    data = format_date(gara.date, "EEE d MMM yyyy") if gara.date else ""
    ora = gara.time.strftime("%H:%M") if gara.time is not None else None
    return data, ora


def _chi_organizza(gara: Gara) -> Optional[str]:
    """Il direttore, con il nome che ha scelto di mostrare."""
    direttori = getattr(gara, "directors", None) or []
    nomi = [
        getattr(d, "display_name", None) or getattr(d, "username", "")
        for d in direttori
    ]
    nomi = [n for n in nomi if n]
    return ", ".join(nomi) if nomi else None


def _sopratitolo(gara: Gara) -> Optional[str]:
    """«Campionato Sociale 2026 · gara 3», o solo il nome del campionato.

    Si dice «gara» e non «prova» perché in questo vocabolario **prova è già
    presa**: nel catalogo delle traduzioni indica il tentativo di un esercizio
    (`Prove` → *Attempts*), e le tappe di un campionato l'app le chiama gare.
    Riusare la parola qui reintrodurrebbe l'ambiguità che il progetto ha già
    disfatto una volta con «sfida».

    Il numero da solo non si mostra: fuori da un campionato non vuol dire
    niente, e «gara 3» senza dire di quale campionato è un'informazione che il
    lettore non può usare.
    """
    if gara.campionato is None:
        return None
    if gara.number:
        return _(
            "%(campionato)s · gara %(n)s",
            campionato=gara.campionato.name,
            n=gara.number,
        )
    return gara.campionato.name


def _stato(gara: Gara, aperte: bool):
    """Una riga che dice a che punto è la gara, e con che tono mostrarla."""
    stato = gara.get_real_status()
    if stato in STATI_CONCLUSI:
        return _("Gara conclusa"), ""
    if stato in STATI_IN_GIOCO:
        return _("Gara in corso"), "live"
    if aperte:
        return _("Iscrizioni aperte"), "open"
    # `inscription_start` è naive-UTC come tutte le colonne `DateTime` del
    # progetto: si confronta con `utc_now()`, non con l'ora locale della
    # macchina — altrimenti d'estate la finestra si sposta di due ore.
    if gara.inscription_start and gara.inscription_start > utc_now():
        return _("Iscrizioni non ancora aperte"), ""
    return _("Iscrizioni chiuse"), ""


def _nome_giocatore(utente) -> str:
    """Come si chiama un giocatore in vetrina.

    `display_name` non esiste su `User` — è una proprietà di `Gara` — quindi
    il `getattr` non è pigrizia: è il ripiego che tiene la funzione corretta
    se un giorno venisse aggiunta, senza dipendere da lei oggi.
    """
    if utente is None:
        return "—"
    return getattr(utente, "display_name", None) or utente.username


def _righe_classifica(classifiche) -> List[RigaClassifica]:
    """Il podio più un contorno, con i nomi già risolti."""
    return [
        RigaClassifica(
            posizione=riga.position,
            nome=_nome_giocatore(riga.user),
            valore=riga.matches_won or 0,
            unita=_("V"),
        )
        for riga in classifiche[:RIGHE_CLASSIFICA_VETRINA]
    ]


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
    conclusa = gara_ha_finito(gara)
    stato_testo, stato_tono = _stato(gara, aperte)
    data_testo, ora_testo = _quando_si_gioca(gara)

    righe = []

    sede, citta = _dove_si_gioca(gara)
    if sede:
        righe.append(
            RigaInformativa(
                icona="fa-location-dot",
                etichetta=_("Dove"),
                valore=sede,
                dettaglio=citta,
            )
        )

    righe.append(
        RigaInformativa(
            icona="fa-trophy",
            etichetta=_("Formato"),
            valore=_formato_di_gioco(gara),
            dettaglio=(
                _("%(n)s turni", n=gara.rounds_count) if gara.rounds_count else None
            ),
        )
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

    # La chiusura delle iscrizioni si mostra solo mentre sono aperte: dopo è
    # una data passata che non dice più a nessuno cosa fare.
    if aperte and gara.inscription_end:
        righe.append(
            RigaInformativa(
                icona="fa-hourglass-half",
                etichetta=_("Chiusura iscrizioni"),
                valore=format_date(gara.inscription_end, "d MMM"),
            )
        )

    banner = gara.effective_banner_path
    banner_url = (
        ImagePathManager.url_from_db_path(banner) if banner else LOCANDINA_DI_RIPIEGO
    )

    link = gara.effective_external_link

    return Vetrina(
        gara=gara,
        titolo=gara.display_name,
        sopratitolo=_sopratitolo(gara),
        descrizione=(gara.description or "").strip() or None,
        banner_url=banner_url,
        data_testo=data_testo,
        ora_testo=ora_testo,
        organizzatore=_chi_organizza(gara),
        righe=righe,
        iscritti=iscritti,
        posti=gara.max_participants,
        iscrizioni_aperte=aperte,
        stato_testo=stato_testo,
        stato_tono=stato_tono,
        conclusa=conclusa,
        classifica=(
            _righe_classifica(classifica_gia_calcolata(gara.id)) if conclusa else []
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
    prende le cose che fanno decidere: quando, dove, e se ci si può ancora
    iscrivere. La descrizione libera del direttore verrebbe tagliata a metà, e
    non è detto che le prime parole siano quelle importanti.

    I pezzi si nominano **uno per uno** invece di pescare le prime righe di
    `righe`: quella lista cambia con lo stato della gara — la chiusura delle
    iscrizioni compare e sparisce — e un'anteprima che cambia forma a seconda
    del giorno in cui la si condivide è esattamente il difetto che non si
    vedrebbe mai in prova.
    """
    quando = vetrina.data_testo
    if vetrina.ora_testo:
        quando = f"{quando}, {vetrina.ora_testo}"

    pezzi = [quando]
    for riga in vetrina.righe:
        if riga.etichetta in (_("Dove"), _("Formato")):
            pezzi.append(riga.valore)

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
