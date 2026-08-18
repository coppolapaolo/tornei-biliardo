"""Quando disegnare il blocco «Come stai andando».

Il blocco e' un saluto, non un cruscotto: si mostra **una volta per sessione**,
al primo ingresso in dashboard dopo il login, e da li' in poi lascia il posto
alle cose da fare. Chi torna in dashboard dieci volte in un pomeriggio non ha
bisogno di rileggere dieci volte com'e' andata.

Il turno vale per l'intero **posto** in cima alla home, non per un singolo
componente: lo occupa il blocco «Come stai andando» a chi ha gia' giocato e la
card dei tre passi a chi non ha ancora fatto niente. Sono due facce della
stessa cosa, e spariscono insieme.

Lo stato vive nella sessione del server, non in `sessionStorage`: il blocco
deve sparire *senza essere renderizzato* — nasconderlo lato client vorrebbe
dire calcolarlo e spedirlo comunque, e quello e' lavoro di database per una
cosa che nessuno vedra'.
"""

from __future__ import annotations

from flask import has_request_context, session

#: Chiave di sessione. Il valore e' l'id dell'utente che l'ha gia' visto, non
#: un booleano: due account che si alternano sullo stesso browser sono due
#: persone diverse, e la seconda il suo saluto non l'ha ancora ricevuto.
SESSION_KEY = "activity_feedback_seen_by"


def claim_activity_feedback_view(user_id: int) -> bool:
    """True la prima volta nella sessione, False da li' in poi.

    Ha un effetto: chiamarla *consuma* il turno. Va invocata una volta sola per
    richiesta, da chi sta davvero per disegnare la dashboard.
    """
    if not has_request_context():
        # Fuori da una richiesta (script, test di servizio) non c'e' una
        # sessione da consumare: non e' il posto dove si nasconde niente.
        return True
    if session.get(SESSION_KEY) == user_id:
        return False
    session[SESSION_KEY] = user_id
    return True


def reset_activity_feedback_view() -> None:
    """Rimette il blocco in coda: si chiama al login.

    `logout_user()` toglie dalla sessione solo le chiavi di Flask-Login, non le
    nostre. Senza questa riga chi esce e rientra dallo stesso browser non
    rivedrebbe il saluto — «dopo il login» smetterebbe di essere vero.
    """
    if has_request_context():
        session.pop(SESSION_KEY, None)


__all__ = [
    "SESSION_KEY",
    "claim_activity_feedback_view",
    "reset_activity_feedback_view",
]
