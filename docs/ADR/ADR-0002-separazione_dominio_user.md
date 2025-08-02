# ADR-0002: Separazione del Dominio “User”

Data: 2025-08-01

## Stato
Accettato

## Contesto
Tutti i modelli SQLAlchemy vivevano in `models.py`: file monolitico, import circolari, scarsa manutenibilità. Dovevamo:
* segregare i bounded context (**User** vs **Tournament**),
* facilitare i test unitari,
* introdurre funzioni ACL più evolute.

## Decisione
* Spostare i modelli utente in un package dedicato `models/user/`.
* Lasciare alias di compatibilità in `models.py`.
* Introdurre facade `UserService` per orchestrazione; le route dipendono dal servizio e non dalle tabelle direttamente.
* Aggiornare gli import in tutti i Blueprint.
* Nessuna variazione sugli schemi DB: nomi tabelle invariati, quindi no migrazione.

## Conseguenze
+ Maggiore coesione, minore accoppiamento.
+ Consente migrazioni indipendenti per contesti separati.
− Richiede refactor massivo dei path di import.

## Alternative
*Prefissi sui nomi dei modelli* – eliminava solo il sintomo.
*Framework Django con “app”* – overkill per Flask.
