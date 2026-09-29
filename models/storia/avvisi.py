"""Le notifiche delle modifiche a una gara, accorpate (ADR-075).

La storia è la verità; le **notifiche** si accorpano. La prima modifica che
interessa i giocatori apre una notifica in attesa per quella gara
(`SettingsNotice`), e le successive ci confluiscono: si confronta lo stato di
partenza con quello di adesso, quindi sala A → B → C arriva come «A → C», e
A → B → A non manda niente.

Parte:

* dopo **30 minuti** senza nuove modifiche — in pratica fra 30 e 90, perché il
  controllo gira con lo scheduled task orario (`send_match_reminders.py`);
* **subito** se il direttore preme «Invia ora»;
* **subito** se la gara comincia entro **3 ore**.

Cosa non si annuncia: il nome, i tavoli, la descrizione, il peso, una quota
che scende, un orario che si sposta di un'ora al massimo. Restano nella
storia.

Se una notifica non può partire per un giocatore — ore di silenzio, limite del
giorno — resta in attesa per lui e riprova al giro dopo: la riga tiene chi
manca. Chi ha spento questo tipo di notifica non la riceve, come sempre.
"""

from __future__ import annotations

import json
from datetime import datetime, time, timedelta
from typing import Any, Dict, List, Optional, Tuple

from ..base import BaseModel, db, utc_now
from ..transaction.manager import transactional

#: Quanto aspettare dall'ultima modifica prima di mandare.
ATTESA = timedelta(minutes=30)
#: Sotto questo anticipo sull'inizio della gara si manda subito.
IMMINENTE = timedelta(hours=3)
#: Uno spostamento d'orario fino a qui non si annuncia.
SPOSTAMENTO_PICCOLO = timedelta(hours=1)


class SettingsNotice(BaseModel):
    """La notifica in attesa per una gara: al più una per gara."""

    __tablename__ = "settings_notice"

    id = db.Column(db.Integer, primary_key=True)
    gara_id = db.Column(
        db.Integer,
        db.ForeignKey("gara.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    #: `{campo: valore serializzato}` al momento della prima modifica.
    initial_values = db.Column(db.Text, nullable=False, default="{}")
    #: Chi manca ancora, dopo un invio parziale. NULL: nessun invio tentato.
    pending_user_ids = db.Column(db.Text, nullable=True)
    first_change_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    last_change_at = db.Column(db.DateTime, nullable=False, default=utc_now)

    gara = db.relationship("Gara", foreign_keys=[gara_id], viewonly=True)

    def iniziali(self) -> Dict[str, str]:
        try:
            return json.loads(self.initial_values or "{}")
        except ValueError:
            return {}

    def mancanti(self) -> Optional[List[int]]:
        if self.pending_user_ids is None:
            return None
        try:
            return [int(u) for u in json.loads(self.pending_user_ids)]
        except ValueError:
            return None

    def parte_alle(self) -> datetime:
        """Quando parte, se nessuno la manda prima."""
        return self.last_change_at + ATTESA


def _campi_avvisati() -> frozenset:
    from ..competition.campi_modificabili import REGOLE, SPAREGGIO, STRUTTURA

    return (
        frozenset({"location", "date", "time", "entry_fee"})
        | REGOLE
        | SPAREGGIO
        | STRUTTURA
    )


def _inizio_in_utc(gara: Any) -> Optional[datetime]:
    """L'inizio della gara in UTC: data e ora sono quelle della sala."""
    if gara.date is None:
        return None
    from utils.local_time import FALLBACK_TIMEZONE, to_utc_naive

    return to_utc_naive(
        datetime.combine(gara.date, gara.time or time(20, 0)), FALLBACK_TIMEZONE
    )


def _imminente(gara: Any, adesso: datetime) -> bool:
    inizio = _inizio_in_utc(gara)
    return inizio is not None and inizio - adesso <= IMMINENTE


def _valori_attuali(gara: Any, campi: List[str]) -> Dict[str, str]:
    from ..competition.services import GaraService
    from .service import serializza

    return {
        campo: serializza(valore)
        for campo, valore in GaraService._valori_per_la_storia(gara, campi).items()
    }


def _numero(testo: str) -> Optional[float]:
    try:
        return float(testo)
    except (TypeError, ValueError):
        return None


def righe_da_annunciare(
    iniziali: Dict[str, str], attuali: Dict[str, str]
) -> List[Tuple[str, str, str]]:
    """Le righe della notifica: campo, prima, dopo. Vuota: niente da dire."""
    righe = []
    for campo, prima in iniziali.items():
        dopo = attuali.get(campo, prima)
        if dopo == prima:
            continue
        if campo == "entry_fee":
            vecchia, nuova = _numero(prima), _numero(dopo)
            if vecchia is not None and nuova is not None and nuova < vecchia:
                continue  # una quota che scende non cambia la decisione
        if campo == "time" and iniziali.get("date", attuali.get("date")) == (
            attuali.get("date")
        ):
            try:
                ore = [datetime.strptime(v, "%H:%M") for v in (prima, dopo)]
            except ValueError:
                ore = []
            if ore and abs(ore[1] - ore[0]) <= SPOSTAMENTO_PICCOLO:
                continue
        righe.append((campo, prima, dopo))
    return righe


class AvvisiModifiche:
    """Accodare, mandare, mostrare le notifiche in attesa."""

    @staticmethod
    def in_attesa(gara_id: int) -> Optional[SettingsNotice]:
        return SettingsNotice.query.filter_by(gara_id=gara_id).first()

    @staticmethod
    @transactional(domain="storia")
    def accoda(gara: Any, cambi: Dict[str, Tuple[Any, Any]]) -> None:
        """Una modifica appena salvata: entra nella notifica in attesa."""
        from .service import serializza

        campi = _campi_avvisati()
        utili = {c: v for c, v in cambi.items() if c in campi}
        if not utili:
            return
        adesso = utc_now()
        avviso = AvvisiModifiche.in_attesa(gara.id)
        if avviso is None:
            avviso = SettingsNotice(
                gara_id=gara.id, first_change_at=adesso, last_change_at=adesso
            )
            db.session.add(avviso)
        iniziali = avviso.iniziali()
        for campo, (prima, _dopo) in utili.items():
            iniziali.setdefault(campo, serializza(prima))
        avviso.initial_values = json.dumps(iniziali, sort_keys=True)
        avviso.last_change_at = adesso
        # Un contenuto nuovo va a tutti, anche a chi aveva già ricevuto il
        # vecchio in un invio parziale.
        avviso.pending_user_ids = None
        db.session.flush()
        if _imminente(gara, adesso):
            AvvisiModifiche.invia(gara.id)

    @staticmethod
    @transactional(domain="storia")
    def invia(gara_id: int) -> int:
        """Manda la notifica in attesa. Restituisce a quanti è arrivata."""
        from ..competition.models import Gara, Inscription
        from ..notification.models import (
            NotificationPreference,
            NotificationPriority,
            NotificationType,
        )
        from ..notification.services import NotificationService

        avviso = AvvisiModifiche.in_attesa(gara_id)
        gara = db.session.get(Gara, gara_id)
        if avviso is None:
            return 0
        if gara is None or gara.is_deleted:
            db.session.delete(avviso)
            return 0
        iniziali = avviso.iniziali()
        righe = righe_da_annunciare(iniziali, _valori_attuali(gara, list(iniziali)))
        if not righe:
            db.session.delete(avviso)
            return 0

        destinatari = avviso.mancanti()
        if destinatari is None:
            destinatari = sorted(
                {
                    i.user_id
                    for i in Inscription.query.filter_by(
                        gara_id=gara.id, is_withdrawn=False
                    )
                }
            )
        tipo = NotificationType.GARA_MODIFICATA
        restano: List[int] = []
        arrivate = 0
        # Chi deve riconfermare (data, orario, sala, quota in aumento) lo
        # legge nella stessa notifica: una sola richiesta, non due messaggi.
        da_chiedere = {
            i.user_id
            for i in Inscription.query.filter_by(gara_id=gara.id, is_withdrawn=False)
            if i.campi_da_riconfermare
        }
        for user_id in destinatari:
            chiedi = user_id in da_chiedere
            notifica = NotificationService.create_notification(
                user_id=user_id,
                notification_type=tipo,
                title=lambda: _titolo(gara),
                message=lambda chiedi=chiedi: _messaggio(righe, chiedi),
                priority=NotificationPriority.NORMAL,
                related_entities={"gara_id": gara.id},
                action_url=f"/gara/{gara.id}",
            )
            if notifica is not None:
                arrivate += 1
                continue
            preferenza = NotificationPreference.get_user_preference(user_id, tipo)
            spenta = not NotificationPreference.is_notification_enabled(user_id, tipo)
            if preferenza is not None and not spenta:
                restano.append(user_id)  # ore di silenzio o limite: si riprova

        if restano:
            avviso.pending_user_ids = json.dumps(restano)
        else:
            db.session.delete(avviso)
        return arrivate

    @staticmethod
    def invia_scaduti(adesso: Optional[datetime] = None) -> int:
        """Il giro orario: manda le notifiche che hanno aspettato abbastanza.

        Gira fuori da una richiesta, dove le competizioni di prova sono
        invisibili: le apre, perché anche i loro giocatori vanno avvisati.
        """
        from ..prova.visibility import prova_visibili

        adesso = adesso or utc_now()
        mandate = 0
        with prova_visibili():
            for avviso in SettingsNotice.query.all():
                gara = avviso.gara
                if gara is None:
                    continue
                if avviso.parte_alle() <= adesso or _imminente(gara, adesso):
                    mandate += AvvisiModifiche.invia(avviso.gara_id)
        return mandate


def _titolo(gara: Any) -> str:
    from flask_babel import gettext as _

    return _("%(gara)s è cambiata", gara=gara.display_name)


def _messaggio(righe: List[Tuple[str, str, str]], chiedi: bool = False) -> str:
    """Le righe nella lingua di chi riceve: si compone dentro la sua lingua."""
    from flask_babel import gettext as _

    from .etichette import etichetta, valore

    testo = "\n".join(
        f"{etichetta(campo)}: {valore(campo, prima)} → {valore(campo, dopo)}"
        for campo, prima, dopo in righe
    )
    if chiedi:
        testo += "\n" + _(
            "Ci sei ancora? Apri la gara e confermalo: finché non rispondi resti "
            "iscritto, e decide il direttore."
        )
    return testo


__all__ = ["SettingsNotice", "AvvisiModifiche", "righe_da_annunciare"]
