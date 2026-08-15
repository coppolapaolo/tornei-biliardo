"""Blueprint dell'esame: catalogo, sessioni e appuntamenti (ADR-042).

Diviso per superficie come ``routes/individual_match/``, non per modello: chi
cerca «dove si accetta una richiesta d'esame» guarda ``requests.py``, non deve
sapere in quale tabella finisce.

Le route non contengono logica di dominio né controlli di ruolo scritti a mano:
chiedono al servizio, che solleva l'eccezione giusta
(``NotFoundError``/``ConflictError``/``PermissionDeniedError``) e la route la
lascia diventare 404/409/403 tramite ``handle_service_action``.
"""

from flask import Blueprint

exam_bp = Blueprint("exam", __name__)

from . import catalog  # noqa: E402, F401
from . import attempts  # noqa: E402, F401
from . import requests  # noqa: E402, F401

__all__ = ["exam_bp"]
