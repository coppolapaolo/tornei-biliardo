"""La lingua di chi legge: da dove si ricava, e come si scrive a qualcun altro.

Gemello di ``utils/local_time.py`` (ADR-043), per la lingua invece del fuso
(ADR-062). Una pagina si traduce nella lingua di chi la guarda, e Flask-Babel
lo sa già fare. Il problema sono i testi scritti **per qualcun altro**: una
notifica composta mentre un direttore preme un pulsante, un promemoria
composto da uno scheduled task. Lì la lingua corrente è quella sbagliata, o
non c'è affatto, e il risultato è una frase in una lingua che il destinatario
magari non legge.

Due cose vivono qui, insieme:

* **da dove viene la lingua di un utente**: ``User.language``, scritta dal
  selettore (una scelta) o dedotta dal browser (che riempie solo un vuoto);
* **come si compone un testo per lui**: dentro ``nella_lingua_di(user_id)``, a
  partire da una stringa pigra (``lazy_gettext``) o da una funzione senza
  argomenti. Un testo già tradotto non si può ritradurre: va passato *da
  comporre*.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from typing import Any, Callable, Iterator, Optional, Union

from flask_babel import force_locale
from flask_babel.speaklater import LazyString

#: Le lingue che l'app parla. Una lingua fuori da qui non si salva: un
#: catalogo che non esiste darebbe il testo sorgente, cioè l'italiano, con
#: l'aggravante di sembrare una scelta.
LINGUE_SUPPORTATE = ("it", "en")

#: Il ripiego per chi una lingua non ce l'ha: account creato prima della
#: colonna, utente che non ha ancora aperto una pagina. È l'italiano perché è
#: la lingua sorgente dei testi e il comportamento che l'app ha sempre avuto.
LINGUA_DI_RIPIEGO = "it"

#: Un testo da comporre per un destinatario: una stringa (testo libero, scritto
#: da un utente, che non si traduce), una stringa pigra, o una funzione senza
#: argomenti per i testi fatti di pezzi.
TestoNotifica = Union[str, LazyString, Callable[[], Any]]


def normalizza_lingua(valore: Optional[str]) -> Optional[str]:
    """Il codice di una lingua che l'app parla, o ``None``.

    Accetta quello che mandano i browser e le intestazioni: ``en-GB``,
    ``en_US``, ``IT``. Tutto ciò che non si riduce a una lingua supportata si
    scarta, invece di finire in colonna.
    """
    if not valore or not isinstance(valore, str):
        return None
    codice = valore.strip().replace("_", "-").split("-")[0].lower()
    return codice if codice in LINGUE_SUPPORTATE else None


def lingua_per_user_id(user_id: Optional[int]) -> str:
    """La lingua in cui scrivere a un **destinatario preciso**.

    Non quella della richiesta in corso: chi compone il testo è quasi sempre
    un'altra persona, o nessuna.
    """
    if not user_id:
        return LINGUA_DI_RIPIEGO
    try:
        from models.base import db
        from models.user.models import User

        utente = db.session.get(User, user_id)
    except Exception:
        return LINGUA_DI_RIPIEGO
    return normalizza_lingua(getattr(utente, "language", None)) or LINGUA_DI_RIPIEGO


@contextmanager
def nella_lingua_di(user_id: Optional[int]) -> Iterator[str]:
    """Traduce nella lingua del destinatario tutto ciò che si compone dentro.

    All'uscita la lingua di chi ha premuto il pulsante torna com'era: la
    pagina che segue la notifica resta nella sua lingua.
    """
    lingua = lingua_per_user_id(user_id)
    with force_locale(lingua):
        yield lingua


def componi(testo: Optional[TestoNotifica]) -> Optional[str]:
    """Il testo reso stringa nella lingua attiva in questo momento.

    Va chiamato dentro ``nella_lingua_di``: fuori, una stringa pigra si
    tradurrebbe nella lingua di chi preme.
    """
    if testo is None:
        return None
    if callable(testo) and not isinstance(testo, LazyString):
        testo = testo()
    return str(testo)


def data_ora_per(user_id: Optional[int], valore: Any) -> str:
    """Data e ora nel fuso del destinatario, per un testo scritto a lui.

    Il fuso lo sa ``utils/local_time.py`` (ADR-043): qui lo si lega solo a
    un destinatario, perché chi compone una notifica ha in mano un id, non un
    fuso. Un ``datetime`` è naive UTC per convenzione; qualunque altro valore
    passa com'è.
    """
    if not valore:
        return ""
    if not isinstance(valore, datetime):
        return str(valore)

    from utils.jinja import format_datetime_local_text
    from utils.local_time import resolve_timezone_for_user_id

    return format_datetime_local_text(valore, tz=resolve_timezone_for_user_id(user_id))


def ricorda_lingua_dedotta(utente: Any) -> bool:
    """Scrive la lingua di un utente che non l'ha ancora, dedotta dalla richiesta.

    Prima la lingua di sessione, perché è quella in cui l'utente sta leggendo
    la pagina; poi l'intestazione ``Accept-Language`` del browser. Un utente che
    una lingua ce l'ha già non si tocca: la deduzione riempie un vuoto, non
    corregge una scelta.

    Non solleva mai: una lingua non registrata è un fastidio, una pagina che
    non si apre è una porta chiusa.
    """
    if not getattr(utente, "is_authenticated", False):
        return False
    if normalizza_lingua(getattr(utente, "language", None)):
        return False
    try:
        from flask import request, session

        dedotta = normalizza_lingua(session.get("language")) or normalizza_lingua(
            request.accept_languages.best_match(LINGUE_SUPPORTATE)
        )
        if not dedotta:
            return False

        from models.user.services import UserService

        return UserService.remember_language(utente.id, dedotta)
    except Exception:
        import logging

        logging.getLogger(__name__).warning(
            "Lingua dell'utente non registrata", exc_info=True
        )
        return False
