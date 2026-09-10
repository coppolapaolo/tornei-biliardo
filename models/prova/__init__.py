"""Competizione di prova (ADR-058).

La stessa gara con un flag, visibile solo a chi la dirige, popolata da
giocatori fittizi e fuori da ELO e gamification. Specifica in
`docs/usecases/competizione-di-prova.md`.

* `visibility.py`: chi vede cosa — il filtro di sessione e l'opt-in.
* `guard.py`: «questo evento / questa gara è di prova?», per chi deve
  scartare (gamification, notifiche).
* `service.py`: creazione, giocatori fittizi, iscrizioni, scadenza,
  cancellazione.
* `nomi.py`: la tabella dei nomi dei fittizi.
"""

from .visibility import prova_visibili, register_prova_filters

__all__ = ["prova_visibili", "register_prova_filters"]
