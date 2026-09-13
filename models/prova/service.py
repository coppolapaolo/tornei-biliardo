"""Il ciclo di vita di una competizione di prova (ADR-058).

Creazione (i campi da dare alla gara), limite per direttore, giocatori
fittizi e loro iscrizione, scadenza e cancellazione fisica. La specifica è
in `docs/usecases/competizione-di-prova.md`; le regole numeriche sono in
`docs/reference/SPECIFICHE.md` e presidiate da
`tests/new/unit/test_specifiche_conformita.py`.

Tutto ciò che legge le prove lo fa dentro `prova_visibili()`: il servizio è
chiamato da route già autorizzate (chi dirige la prova) e da job fuori
richiesta, e in entrambi i casi deve vedere le prove che gli si chiede di
toccare.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from sqlalchemy import delete, or_, select

from models.base import db, utc_now
from models.exceptions import ConflictError, NotFoundError, ValidationError
from models.transaction.manager import transactional

from .nomi import nome_fittizio
from .visibility import invalida_ambito, prova_visibili

logger = logging.getLogger(__name__)

#: Quante prove (gare singole e campionati, sommati) un direttore può avere
#: aperte insieme. SPECIFICHE.md, «Competizione di prova».
LIMITE_PROVE_ATTIVE = 3

#: Dopo quanto una prova non cancellata sparisce da sola.
DURATA_PROVA = timedelta(days=14)

#: Quanto prima della scadenza il direttore riceve l'avviso.
PREAVVISO_SCADENZA = timedelta(days=3)

MODALITA_ISCRIZIONE = ("minimo", "massimo", "uno")


class ProvaService:
    """Creazione, popolamento e fine di una competizione di prova."""

    # ------------------------------------------------------------ creazione

    @staticmethod
    def campi_di_creazione(adesso: Optional[datetime] = None) -> Dict[str, Any]:
        """I campi in più che una radice di prova riceve alla creazione."""
        adesso = adesso or utc_now()
        return {"is_prova": True, "prova_expires_at": adesso + DURATA_PROVA}

    @staticmethod
    def prove_attive(user_id: int) -> List[Any]:
        """Le radici di prova che questo direttore ha in piedi.

        Gare singole con `director_id` e campionati assegnati; le gare dentro
        un campionato di prova non contano da sole, contano col campionato.
        """
        from models.campionato.models import Campionato
        from models.competition.models import Gara
        from models.user.models import DirectorAssignment

        with prova_visibili():
            gare = (
                db.session.query(Gara)
                .filter(
                    Gara.is_prova.is_(True),
                    Gara.campionato_id.is_(None),
                    Gara.director_id == user_id,
                    Gara.deleted_at.is_(None),
                )
                .order_by(Gara.id.asc())
                .all()
            )
            assegnati = select(DirectorAssignment.entity_id).where(
                DirectorAssignment.entity_type == "campionato",
                DirectorAssignment.user_id == user_id,
            )
            campionati = (
                db.session.query(Campionato)
                .filter(
                    Campionato.is_prova.is_(True),
                    Campionato.is_deleted.is_(False),
                    Campionato.id.in_(assegnati),
                )
                .order_by(Campionato.id.asc())
                .all()
            )
        return [*gare, *campionati]

    @staticmethod
    def puo_crearne_ancora(user_id: int) -> bool:
        return len(ProvaService.prove_attive(user_id)) < LIMITE_PROVE_ATTIVE

    @staticmethod
    def verifica_limite(user_id: int) -> None:
        """Solleva `ConflictError` se il direttore è già al limite."""
        if not ProvaService.puo_crearne_ancora(user_id):
            raise ConflictError(
                f"Hai già {LIMITE_PROVE_ATTIVE} prove aperte: eliminane una "
                "per crearne un'altra."
            )

    # ------------------------------------------------------------- fittizi

    @staticmethod
    def _radice(gara: Any) -> Tuple[Optional[int], Optional[int]]:
        """(gara_id, campionato_id) a cui appartengono i fittizi di questa gara."""
        if gara.campionato_id:
            return None, gara.campionato_id
        return gara.id, None

    @staticmethod
    def fittizi_della_radice(
        gara_id: Optional[int] = None, campionato_id: Optional[int] = None
    ) -> List[Any]:
        from models.user.models import User

        with prova_visibili():
            query = db.session.query(User).filter(User.is_fittizio.is_(True))
            if gara_id:
                query = query.filter(User.prova_gara_id == gara_id)
            else:
                query = query.filter(User.prova_campionato_id == campionato_id)
            return query.order_by(User.id.asc()).all()

    @staticmethod
    @transactional(domain="competition")
    def crea_fittizi(gara: Any, quanti: int) -> List[Any]:
        """Crea `quanti` giocatori fittizi per la prova a cui la gara appartiene.

        I nomi proseguono da dove la prova era arrivata: il nono fittizio di
        una prova si chiama sempre come il nono della tabella, anche se è nato
        in una gara successiva del campionato.

        Transazione **propria**, separata dalle iscrizioni che seguono:
        `InscriptionService.inscribe_user` è già `@transactional`, e
        annidarli fa rollback in silenzio (ADR-012).
        """
        from models.rating.models import PlayerRating, RatingSystem
        from models.user.models import User
        from models.user.role_enum import UserRole

        if not gara.is_prova:
            raise ValidationError("I giocatori fittizi esistono solo in una prova")

        gara_id, campionato_id = ProvaService._radice(gara)
        radice = f"g{gara_id}" if gara_id else f"c{campionato_id}"
        esistenti = len(ProvaService.fittizi_della_radice(gara_id, campionato_id))

        creati: List[Any] = []
        for indice in range(esistenti, esistenti + quanti):
            nome, cognome, rating = nome_fittizio(indice)
            utente = User(
                # Lo username e' il nome con cui si gioca — classifiche,
                # abbinamenti, segnapunti lo mostrano — quindi e' il nome
                # verosimile, non un codice. L'email resta tecnica.
                username=_username_libero(f"{nome} {cognome}"),
                email=f"prova-{radice}-{indice + 1}@fittizio.invalid",
                role=UserRole.PLAYER.value,
                # Nessuno può fare login: l'hash non corrisponde a niente.
                password_hash="!fittizio!",
                is_verified=True,
                onboarding_completed=True,
                first_name=nome,
                last_name=cognome,
                elo_rating=rating,
                is_fittizio=True,
                prova_gara_id=gara_id,
                prova_campionato_id=campionato_id,
            )
            db.session.add(utente)
            db.session.flush()
            db.session.add(
                PlayerRating(
                    user_id=utente.id,
                    rating_system=RatingSystem.ELO,
                    rating_value=float(rating),
                    robustness=0,
                )
            )
            creati.append(utente)
        db.session.flush()
        return creati

    # ---------------------------------------------------------- iscrizioni

    @staticmethod
    def iscritti_attivi(gara_id: int) -> int:
        from models.competition.models import Inscription

        return (
            db.session.query(Inscription)
            .filter_by(gara_id=gara_id, is_waitlist=False, is_withdrawn=False)
            .count()
        )

    @staticmethod
    def quanti_da_iscrivere(gara: Any, modalita: str) -> int:
        """Quanti fittizi aggiungerebbe il pulsante `modalita`, ora.

        Zero significa «pulsante disabilitato»: minimo già raggiunto,
        massimo raggiunto o non impostato.
        """
        attivi = ProvaService.iscritti_attivi(gara.id)
        massimo = gara.max_participants or 0
        if modalita == "minimo":
            mancanti = max(0, (gara.min_participants or 0) - attivi)
            if massimo:
                mancanti = min(mancanti, max(0, massimo - attivi))
            return mancanti
        if modalita == "massimo":
            return max(0, massimo - attivi) if massimo else 0
        if modalita == "uno":
            return 0 if massimo and attivi >= massimo else 1
        raise ValidationError(f"Modalità di iscrizione sconosciuta: {modalita}")

    @staticmethod
    def iscrivi_fittizi(gara_id: int, modalita: str) -> int:
        """Iscrive i fittizi che il pulsante chiede. Restituisce quanti.

        I fittizi sono **della prova**, non della gara: in un campionato di
        prova la seconda gara riusa quelli della prima — altrimenti la
        classifica generale non si formerebbe mai, con sedici nomi nuovi a
        ogni gara — e ne crea di nuovi solo se non bastano. Per una gara
        singola i due casi coincidono.

        Non è `@transactional` di proposito: chiama due metodi che lo sono
        già (`crea_fittizi`, `inscribe_user`), e il decoratore annidato fa
        rollback in silenzio (ADR-012).
        """
        from models.competition.inscription_service import InscriptionService
        from models.competition.models import Gara, Inscription
        from models.status_enum import GaraStatus

        with prova_visibili():
            gara = db.session.get(Gara, gara_id)
            if gara is None or not gara.is_prova:
                raise NotFoundError("Prova non trovata")
            if gara.status != GaraStatus.INSCRIPTION.value:
                raise ConflictError(
                    "I giocatori fittizi si iscrivono a iscrizioni aperte"
                )
            quanti = ProvaService.quanti_da_iscrivere(gara, modalita)
            if quanti == 0:
                return 0
            gia_in_gara = {
                uid
                for (uid,) in db.session.execute(
                    select(Inscription.user_id).where(Inscription.gara_id == gara.id)
                ).all()
            }
            gara_id_radice, campionato_id = ProvaService._radice(gara)
            liberi = [
                f
                for f in ProvaService.fittizi_della_radice(
                    gara_id_radice, campionato_id
                )
                if f.id not in gia_in_gara
            ][:quanti]
            fittizi = list(liberi)
            if len(fittizi) < quanti:
                fittizi += ProvaService.crea_fittizi(gara, quanti - len(fittizi))
            for fittizio in fittizi:
                InscriptionService.inscribe_user(fittizio.id, gara.id)
            return len(fittizi)

    # ------------------------------------------------------------ scadenza

    @staticmethod
    def _radici_scadute(adesso: datetime) -> List[Any]:
        from models.campionato.models import Campionato
        from models.competition.models import Gara

        # `include_deleted`: una prova soft-eliminata dall'admin deve scadere
        # lo stesso, altrimenti resterebbe in tabella per sempre.
        gare = (
            db.session.query(Gara)
            .filter(
                Gara.is_prova.is_(True),
                Gara.campionato_id.is_(None),
                Gara.prova_expires_at.isnot(None),
                Gara.prova_expires_at <= adesso,
            )
            .execution_options(include_deleted=True)
            .all()
        )
        campionati = (
            db.session.query(Campionato)
            .filter(
                Campionato.is_prova.is_(True),
                Campionato.prova_expires_at.isnot(None),
                Campionato.prova_expires_at <= adesso,
            )
            .execution_options(include_deleted=True)
            .all()
        )
        return [*gare, *campionati]

    @staticmethod
    def _radici_da_avvisare(adesso: datetime) -> List[Any]:
        from models.campionato.models import Campionato
        from models.competition.models import Gara

        soglia = adesso + PREAVVISO_SCADENZA
        gare = (
            db.session.query(Gara)
            .filter(
                Gara.is_prova.is_(True),
                Gara.campionato_id.is_(None),
                Gara.prova_expires_at.isnot(None),
                Gara.prova_expires_at > adesso,
                Gara.prova_expires_at <= soglia,
                Gara.prova_avviso_inviato_at.is_(None),
            )
            .all()
        )
        campionati = (
            db.session.query(Campionato)
            .filter(
                Campionato.is_prova.is_(True),
                Campionato.prova_expires_at.isnot(None),
                Campionato.prova_expires_at > adesso,
                Campionato.prova_expires_at <= soglia,
                Campionato.prova_avviso_inviato_at.is_(None),
            )
            .all()
        )
        return [*gare, *campionati]

    @staticmethod
    def direttori_della_radice(radice: Any) -> List[int]:
        """Chi riceve gli avvisi: il direttore titolare e gli assegnati."""
        from models.user.models import DirectorAssignment

        ids: List[int] = []
        tipo = "campionato" if _e_campionato(radice) else "gara"
        titolare = getattr(radice, "director_id", None)
        if titolare:
            ids.append(titolare)
        for (user_id,) in (
            db.session.query(DirectorAssignment.user_id)
            .filter(
                DirectorAssignment.entity_type == tipo,
                DirectorAssignment.entity_id == radice.id,
            )
            .all()
        ):
            if user_id not in ids:
                ids.append(user_id)
        return ids

    @staticmethod
    def avvisa_scadenze(adesso: Optional[datetime] = None) -> int:
        """Manda l'avviso «scade fra N giorni» a chi non l'ha ancora avuto.

        Non `@transactional`: `create_notification` lo è già (ADR-012). La
        data dell'avviso si scrive in una transazione propria, dopo.
        """
        from models.notification.models import (
            NotificationPriority,
            NotificationType,
        )
        from models.notification.services import NotificationService

        # Testi pigri: lo scheduled task scrive a ciascun direttore nella sua
        # lingua (ADR-062).
        from flask_babel import lazy_gettext as _l, lazy_ngettext

        adesso = adesso or utc_now()
        avvisate = 0
        with prova_visibili():
            for radice in ProvaService._radici_da_avvisare(adesso):
                giorni = max(1, (radice.prova_expires_at - adesso).days)
                chiave = "campionato_id" if _e_campionato(radice) else "gara_id"
                for user_id in ProvaService.direttori_della_radice(radice):
                    NotificationService.create_notification(
                        user_id=user_id,
                        notification_type=NotificationType.SYSTEM_ANNOUNCEMENT,
                        title=_l("La tua prova sta per scadere"),
                        message=lazy_ngettext(
                            "«%(nome)s» sparirà da sola fra %(num)s giorno. "
                            "Se hai finito puoi eliminarla tu.",
                            "«%(nome)s» sparirà da sola fra %(num)s giorni. "
                            "Se hai finito puoi eliminarla tu.",
                            giorni,
                            nome=radice.name,
                        ),
                        priority=NotificationPriority.NORMAL,
                        related_entities={chiave: radice.id},
                    )
                ProvaService._segna_avviso(radice, adesso)
                avvisate += 1
        return avvisate

    @staticmethod
    @transactional(domain="competition")
    def _segna_avviso(radice: Any, adesso: datetime) -> None:
        radice.prova_avviso_inviato_at = adesso

    @staticmethod
    def elimina_scadute(adesso: Optional[datetime] = None) -> int:
        """Elimina le prove scadute, una transazione per prova.

        Una per transazione e non tutte insieme: se una fallisce, le altre
        spariscono lo stesso, e l'errore finisce nel riepilogo del job.
        """
        adesso = adesso or utc_now()
        with prova_visibili():
            radici = ProvaService._radici_scadute(adesso)
            da_eliminare = [
                (("campionato_id" if _e_campionato(r) else "gara_id"), r.id)
                for r in radici
            ]
        eliminate = 0
        for chiave, radice_id in da_eliminare:
            try:
                ProvaService.elimina_prova(**{chiave: radice_id})
                eliminate += 1
            except Exception:  # noqa: BLE001 — una prova non deve fermare le altre
                logger.exception(
                    "Eliminazione della prova scaduta fallita (%s=%s)",
                    chiave,
                    radice_id,
                )
        return eliminate

    # ------------------------------------------------------- cancellazione

    @staticmethod
    @transactional(domain="competition")
    def elimina_prova(
        gara_id: Optional[int] = None, campionato_id: Optional[int] = None
    ) -> None:
        """Cancella **fisicamente** una prova: transazione propria."""
        ProvaService._elimina(gara_id=gara_id, campionato_id=campionato_id)

    @staticmethod
    def _elimina(
        gara_id: Optional[int] = None, campionato_id: Optional[int] = None
    ) -> None:
        """Cancella **fisicamente** una prova con tutto ciò che le appartiene.

        Senza decoratore: lavora nella transazione di chi chiama, così chi è
        già dentro una (`anonymize_user`) non annida un savepoint.

        La cancellazione segue le chiavi esterne dichiarate nei metadati,
        figli prima dei padri, con `PRAGMA foreign_keys=ON` rispettato: nessun
        elenco di tabelle scritto a mano (ADR-058). I fittizi sono righe
        `user` che riferiscono la radice, quindi cadono nella stessa passata
        con tutto ciò che li riferisce — rating, notifiche, XP.

        Due cose non hanno chiave esterna e si tolgono a mano: le
        assegnazioni dei direttori (`entity_id` polimorfico) e i fittizi
        stessi, che riferiscono la radice con due colonne senza FK (vedi
        `User.prova_gara_id`). I fittizi vanno **prima** della radice: le loro
        partite e iscrizioni riferiscono entrambi, e la cascata che parte da
        loro le toglie.
        """
        from models.campionato.models import Campionato
        from models.competition.models import Gara
        from models.user.models import DirectorAssignment, User

        if bool(gara_id) == bool(campionato_id):
            raise ValidationError("Indica la gara oppure il campionato, uno dei due")

        with prova_visibili():
            if gara_id:
                radice = db.session.get(Gara, gara_id)
                if radice is None or not radice.is_prova:
                    raise NotFoundError("Prova non trovata")
                if radice.campionato_id:
                    raise ValidationError(
                        "La gara sta in un campionato di prova: elimina quello"
                    )
                gare_ids = {radice.id}
                tabella = Gara.__table__
                radice_id = radice.id
            else:
                radice = db.session.get(Campionato, campionato_id)
                if radice is None or not radice.is_prova:
                    raise NotFoundError("Prova non trovata")
                gare_ids = {
                    gid
                    for (gid,) in db.session.execute(
                        select(Gara.id)
                        .where(Gara.campionato_id == radice.id)
                        .execution_options(include_deleted=True)
                    ).all()
                }
                tabella = Campionato.__table__
                radice_id = radice.id

            nome = radice.name
            assegnazioni = [
                (DirectorAssignment.entity_type == "gara")
                & DirectorAssignment.entity_id.in_(gare_ids)
            ]
            if campionato_id:
                assegnazioni.append(
                    (DirectorAssignment.entity_type == "campionato")
                    & (DirectorAssignment.entity_id == radice_id)
                )
            db.session.execute(
                delete(DirectorAssignment.__table__).where(or_(*assegnazioni))
            )
            fittizi = {
                uid
                for (uid,) in db.session.execute(
                    select(User.id)
                    .where(
                        User.is_fittizio.is_(True),
                        or_(
                            User.prova_gara_id.in_(gare_ids),
                            User.prova_campionato_id
                            == (radice_id if campionato_id else -1),
                        ),
                    )
                    .execution_options(include_prova=True, include_deleted=True)
                ).all()
            }
            _cancella_a_cascata(User.__table__, fittizi)
            _cancella_a_cascata(tabella, {radice_id})

        # Le righe sono sparite sotto i piedi dell'identity map: chi tiene
        # ancora un oggetto lo scopre alla prossima lettura, non a un flush.
        db.session.expire_all()
        invalida_ambito()
        logger.info("Prova eliminata: %s (%s=%s)", nome, tabella.name, radice_id)

    @staticmethod
    def elimina_prove_del_direttore(user_id: int) -> int:
        """Prima di anonimizzare un direttore: le sue prove se ne vanno con lui.

        Lavora nella transazione del chiamante (`anonymize_user` è già
        `@transactional`).
        """
        radici = ProvaService.prove_attive(user_id)
        for radice in radici:
            if _e_campionato(radice):
                ProvaService._elimina(campionato_id=radice.id)
            else:
                ProvaService._elimina(gara_id=radice.id)
        return len(radici)


def _username_libero(base: str) -> str:
    """`base`, o `base (2)`, `base (3)`… se e' gia' preso.

    Due prove aperte insieme hanno entrambe una Maria Rossi: la seconda si
    chiama «Maria Rossi (2)». Si guarda **tutta** la tabella, fittizi di altre
    prove e utenti soft-eliminati compresi: il vincolo di unicita' vale per
    tutte le righe, non per quelle visibili.
    """
    from models.user.models import User

    presi = {
        nome
        for (nome,) in db.session.execute(
            select(User.username)
            .where(or_(User.username == base, User.username.like(f"{base} (%")))
            .execution_options(include_prova=True, include_deleted=True)
        ).all()
    }
    if base not in presi:
        return base
    n = 2
    while f"{base} ({n})" in presi:
        n += 1
    return f"{base} ({n})"


# ---------------------------------------------------------------------------
# Cancellazione guidata dai metadati
# ---------------------------------------------------------------------------


def _e_campionato(radice: Any) -> bool:
    return getattr(radice, "__tablename__", "") == "campionato"


def _chiavi_esterne_verso(tabella: Any) -> Iterable[Tuple[Any, Any]]:
    """(tabella figlia, colonna) per ogni colonna che riferisce `tabella`."""
    for figlia in db.metadata.sorted_tables:
        for colonna in figlia.columns:
            for fk in colonna.foreign_keys:
                if fk.column.table is tabella:
                    yield figlia, colonna


def _cancella_a_cascata(
    tabella: Any, ids: Set[Any], visitati: Optional[Set[Tuple[str, Any]]] = None
) -> None:
    """Cancella le righe `ids` di `tabella` e, prima, tutto ciò che le riferisce.

    Ricorsiva sulle chiavi esterne dichiarate. Una tabella con chiave primaria
    composta non può essere riferita da nessuno, quindi si cancella senza
    scendere oltre. `visitati` spezza i cicli (una riga `user` fittizia
    riferisce la gara, e le partite della gara riferiscono lei).
    """
    if visitati is None:
        visitati = set()
    ids = {i for i in ids if (tabella.name, i) not in visitati}
    if not ids:
        return
    visitati.update((tabella.name, i) for i in ids)

    for figlia, colonna in _chiavi_esterne_verso(tabella):
        pk = list(figlia.primary_key.columns)
        if len(pk) == 1:
            figli = {
                riga[0]
                for riga in db.session.execute(
                    select(pk[0])
                    .where(colonna.in_(ids))
                    .execution_options(include_prova=True, include_deleted=True)
                ).all()
            }
            _cancella_a_cascata(figlia, figli, visitati)
        db.session.execute(delete(figlia).where(colonna.in_(ids)))

    db.session.execute(
        delete(tabella).where(list(tabella.primary_key.columns)[0].in_(ids))
    )
