"""Cercare un istruttore a cui aprire una scheda (ADR-069).

Due scelte che si vedono nei risultati:

* **senza una domanda non c'è una risposta.** Una ricerca vuota torna vuota, e
  non l'elenco degli istruttori della piattaforma: quell'elenco non è una
  pagina che si apre per sbaglio, e chi cerca sa già chi sta cercando;
* **si cerca per nome utente e per scuola**, non per nome e cognome. Non è una
  dimenticanza: l'anagrafica è cifrata (`EncryptedString`), quindi in SQL non
  è filtrabile — e portarsi in memoria tutti gli istruttori per decifrarli uno
  a uno sarebbe una query che peggiora col crescere della piattaforma.
"""

from __future__ import annotations

from typing import Collection, List, Optional

from ..base import db
from ..user.models import User
from ..user.role_enum import GrantableRole
from ..user.role_grant import RoleGrant

#: Quanti risultati si mostrano. Chi ne trova cinquanta non sta cercando
#: qualcuno che conosce: sta guardando un elenco, e deve restringere.
MAX_RISULTATI = 20


def cerca_istruttori(
    testo: str,
    escludi: Optional[Collection[int]] = None,
    limite: int = MAX_RISULTATI,
) -> List[User]:
    """Gli istruttori il cui nome utente o la cui scuola contengono ``testo``."""
    domanda = (testo or "").strip()
    if not domanda:
        return []

    like = f"%{domanda}%"
    query = (
        User.query.join(RoleGrant, RoleGrant.user_id == User.id)
        .filter(
            RoleGrant.role == GrantableRole.INSTRUCTOR.value,
            RoleGrant.revoked_at.is_(None),
            db.or_(User.username.ilike(like), User.organization.ilike(like)),
        )
        .order_by(User.username.asc())
    )
    if escludi:
        query = query.filter(~User.id.in_(list(escludi)))
    return query.limit(limite).all()
