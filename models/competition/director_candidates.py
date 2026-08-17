"""Chi si può proporre come co-direttore di una gara.

Un elenco di *tutti* i direttori della piattaforma non è una scelta, è un
sondaggio: il co-direttore lo si chiama perché quella sera è in sala, quindi la
domanda vera è «chi c'è qui intorno». La zona si legge con gli stessi strumenti
del resto dell'app (ADR-034/ADR-036): città dichiarata → centroide delle sale di
quella città → distanza in linea d'aria dal centroide del direttore che ha
creato la gara, entro il raggio che quel direttore si è dato.

Due scelte da tenere a mente:

* **Senza zona non si filtra.** Se chi ha creato la gara non ha una città
  dichiarata (o la città non contiene sale con coordinate), la domanda «chi c'è
  qui intorno» non ha un "qui": si elencano tutti, invece di elencare nessuno.
* **Chi non ha dichiarato la città resta in elenco.** Non sappiamo se è vicino,
  ma escluderlo lo renderebbe inaggiungibile per un dato che non ha mai
  compilato — un buco silenzioso, esattamente quello che si vuole evitare. Va
  in fondo, dopo chi risulta in zona.
"""

from __future__ import annotations

from typing import Iterable, List, Optional, Tuple

from models.base import db
from models.user.models import User
from models.user.role_enum import UserRole
from utils.geo import clamp_radius, haversine_km

#: Stesso default del servizio segnali-domanda: la zona di un director è una
#: sola cosa, non una per funzione.
RAGGIO_PREDEFINITO_KM = 30


def _centroide(citta: Optional[str]) -> Optional[Tuple[float, float]]:
    from models.individual_match.availability_service import AvailabilityService

    if not citta:
        return None
    return AvailabilityService.city_centroid_for(citta)


def direttori_candidati(
    gara,
    escludi_ids: Iterable[int] = (),
    richiedente_id: Optional[int] = None,
) -> List[User]:
    """Direttori proponibili come co-direttori di ``gara``.

    Args:
        gara: la competizione a cui aggiungere un co-direttore.
        escludi_ids: chi è già direttore (della gara o ereditato dal campionato).
        richiedente_id: chi sta guardando la schermata, escluso dall'elenco
            perché ci è già dentro.

    Returns:
        I direttori in zona, poi quelli senza città dichiarata; in ordine
        alfabetico dentro ciascun gruppo.
    """
    esclusi = {uid for uid in escludi_ids if uid}
    if richiedente_id:
        esclusi.add(richiedente_id)

    query = User.query.filter(
        User.role == UserRole.DIRECTOR.value,
        User.deleted_at.is_(None),
    )
    if esclusi:
        query = query.filter(~User.id.in_(esclusi))
    candidati = query.order_by(User.username).all()

    origine = _origine_della_gara(gara)
    if origine is None:
        return candidati

    raggio = clamp_radius(_raggio_della_gara(gara))
    centroidi: dict[str, Optional[Tuple[float, float]]] = {}

    in_zona: List[User] = []
    senza_citta: List[User] = []
    for candidato in candidati:
        citta = (candidato.home_city or "").strip()
        if not citta:
            senza_citta.append(candidato)
            continue
        if citta not in centroidi:
            centroidi[citta] = _centroide(citta)
        punto = centroidi[citta]
        if punto is None:
            # Città dichiarata ma sconosciuta all'anagrafica delle sale: non è
            # "lontano", è "non misurabile". Stesso trattamento di chi la città
            # non l'ha scritta.
            senza_citta.append(candidato)
            continue
        if haversine_km(origine[0], origine[1], punto[0], punto[1]) <= raggio:
            in_zona.append(candidato)

    return in_zona + senza_citta


def _proprietario(gara) -> Optional[User]:
    """Il direttore che ha creato la gara: è la sua zona a fare da centro."""
    director_id = getattr(gara, "director_id", None)
    if not director_id:
        return None
    return db.session.get(User, director_id)


def _origine_della_gara(gara) -> Optional[Tuple[float, float]]:
    """Il centro della zona: la sede della gara se nota, altrimenti il creatore.

    La sala viene prima della città del direttore perché è dove si gioca
    davvero — una gara organizzata fuori casa cerca gente vicina al tavolo, non
    vicina a chi l'ha creata.
    """
    sala = getattr(gara, "billiard_hall", None)
    if sala is not None and sala.latitude is not None and sala.longitude is not None:
        return (sala.latitude, sala.longitude)

    proprietario = _proprietario(gara)
    if proprietario is None:
        return None
    return _centroide(getattr(proprietario, "home_city", None))


def _raggio_della_gara(gara) -> int:
    proprietario = _proprietario(gara)
    if proprietario is None:
        return RAGGIO_PREDEFINITO_KM
    return getattr(proprietario, "signal_radius_km", None) or RAGGIO_PREDEFINITO_KM


__all__ = ["direttori_candidati", "RAGGIO_PREDEFINITO_KM"]
