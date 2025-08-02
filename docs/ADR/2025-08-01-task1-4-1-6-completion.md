# ADR 2025-08-01 – Chiusura Task 1.4 & 1.6

## Contesto
La Fase 1 prevedeva:
* **Task 1.4** – Implementare statistiche utente complete.
* **Task 1.6** – Potenziare il reset dati con utenti/ruoli d’esempio.

Alcuni metodi erano placeholder e la cartella `utils_reset/` duplicava la logica.

## Decisione
* Completati `get_managed_tournaments` e `get_statistics` in `models/user/models.py`.
* Consolidato reset avanzato in `utils/reset_data.py`; rimosso `utils_reset/`.
* Aggiunti test di regressione minimi.
* Nessuna migrazione schema necessaria.

## Conseguenze
* Le dashboard e i servizi ora ricevono statistiche corrette.
* Un singolo entry-point per il reset semplifica CI e demo.
