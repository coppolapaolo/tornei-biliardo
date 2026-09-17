"""Chi accede resta collegato su quel dispositivo per trenta giorni (ADR-064).

Il cookie di sessione nasceva senza scadenza, e un cookie senza scadenza vive
quanto il browser decide: iOS lo butta quando chiude la scheda o la web app.
Sul telefono voleva dire rifare l'accesso a ogni apertura, in sala, a gara in
corso.

Con la spunta «Resta collegato» la sessione diventa *permanent* e Flask dà al
cookie la scadenza di `PERMANENT_SESSION_LIFETIME`. Due scelte non ovvie:

* `SESSION_REFRESH_EACH_REQUEST` è **False**. La sessione sta nel cookie, non
  sul server: rimandarlo a ogni risposta vuol dire che un poll partito prima e
  arrivato dopo riscrive la sessione con lo stato vecchio — un messaggio flash
  che ricompare, l'attività dell'admin che torna indietro. Con due poll ogni
  tre secondi non è un caso di scuola.
* la scadenza si rinnova lo stesso, ma **al più una volta al giorno** e solo
  sulle pagine: chi usa l'app non viene mai scollegato, chi la lascia per un
  mese sì. I poll non contano, come nell'ADR-063: una scheda dimenticata
  aperta non deve tenersi viva da sola.

L'admin resta sotto l'ADR-063: il cookie dura, ma dopo mezz'ora senza aprire
pagine la sessione cade comunque.
"""

from __future__ import annotations

import time

from flask import request, session

CHIAVE = "_sessione_rinnovata"
CAMPO = "resta_collegato"

PASSO_RINNOVO_SECONDI = 86_400


def _adesso() -> float:
    """Secondi epoch, indipendenti dal fuso (vedi `inattivita_admin._adesso`)."""
    return time.time()


def applica_scelta_al_login() -> None:
    """Dopo `login_user`: la spunta del form decide quanto vive il cookie.

    Senza il campo la sessione resta com'era prima, legata al browser: vale
    per il computer condiviso e per chi invia il form da una pagina di login
    rimasta in cache da prima di questa modifica.
    """
    if request.form.get(CAMPO) == "1":
        session.permanent = True
        session[CHIAVE] = _adesso()
    else:
        session.permanent = False
        session.pop(CHIAVE, None)


def rinnova_sessione_duratura() -> None:
    """`before_request`: sposta in avanti la scadenza, al più una volta al giorno.

    Non legge `current_user`: basta la sessione, e caricare l'utente da qui
    sarebbe una query in più su ogni richiesta.
    """
    if request.endpoint == "static" or request.blueprint == "sse":
        return
    if not session.permanent or "_user_id" not in session:
        return

    adesso = _adesso()
    ultima = session.get(CHIAVE)
    if not isinstance(ultima, (int, float)) or adesso - ultima >= PASSO_RINNOVO_SECONDI:
        session[CHIAVE] = adesso
