"""Punto d'ingresso unico dei lavori periodici giornalieri.

Su PythonAnywhere gli scheduled task sono un numero limitato per piano, quindi
i lavori di dominio quotidiani passano tutti da qui: **un solo task registrato**
invece di uno per lavoro. Aggiungere un job futuro non richiede toccare la
configurazione di PythonAnywhere, solo la mappa ``JOBS`` qui sotto.

Perché non appoggiarsi a un task già esistente:

- ``backup_db.py`` non avvia Flask (usa ``sqlite3`` diretto) ed è deliberatamente
  la cosa più affidabile che c'è: agganciarci logica di dominio significherebbe
  che un errore applicativo può far saltare il backup.
- ``auto_deploy.py`` è uno script di deploy: esce prima del tempo quando non ci
  sono modifiche e si ferma apposta se non ricava la chiave di cifratura. Un
  lavoro periodico verrebbe saltato in silenzio in tutti quei casi.
- ``send_match_reminders.py`` gira ogni ora: cadenza diversa, non accorpabile
  al giornaliero.

Ogni job è **isolato**: se uno solleva, gli altri girano lo stesso e l'errore
finisce nel riepilogo. L'uscita è diversa da zero se almeno un job è fallito,
così PythonAnywhere segnala il task come fallito invece di far passare in
silenzio un guasto parziale.

Nota per job futuri: questo processo NON eredita le variabili d'ambiente del
file WSGI. Un job che deve decifrare PII va lanciato con ``ENCRYPTION_KEY``
impostata, altrimenti la decifratura fallisce in silenzio (cfr. l'incidente del
2026-06-25 in CLAUDE.md).

Usage:
    python scripts/daily_jobs.py            # tutti i job
    python scripts/daily_jobs.py demand     # solo quelli elencati

PythonAnywhere scheduled task:
    Command: cd /home/paolocoppola/mysite && python scripts/daily_jobs.py
    Frequency: giornaliera
"""

import os
import sys
import traceback

_HERE = os.path.dirname(os.path.abspath(__file__))
# Servono entrambe: la radice del progetto (per `app`, `models`) e la cartella
# scripts (per `prod_env`), anche quando il file viene caricato per path invece
# che eseguito, come fanno i test.
#
# L'ordine non è indifferente: la radice va inserita per ultima così da restare
# davanti a `scripts/` in sys.path. Eseguendo `python scripts/<file>.py` è
# Python stesso a mettere `scripts/` in testa, e senza questa precedenza un
# futuro `scripts/config.py` o simile oscurerebbe il modulo omonimo del
# progetto (oggi nessuna collisione, ma il guasto sarebbe silenzioso).
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.dirname(_HERE))

from prod_env import bootstrap_or_exit  # noqa: E402
from app import create_app  # noqa: E402


def job_demand_signals() -> str:
    """Ciclo di vita dei segnali-domanda (ADR-036 open item 3).

    Manda il prompt di riconferma ai segnali prossimi alla scadenza (saltando
    chi è stato attivo di recente: il suo segnale si rinnova da solo) e marca
    EXPIRED quelli scaduti.
    """
    from models.demand.service import DemandSignalService

    result = DemandSignalService.process_expiring_signals()
    expired = DemandSignalService.expire_due_signals()
    return (
        f"{result['refreshed']} auto-rinnovati, "
        f"{result['reminded']} promemoria inviati, "
        f"{expired} scaduti"
    )


def job_exam_requests() -> str:
    """Scadenza delle richieste d'esame senza accordo (ADR-042).

    La negoziazione di data e ora può non convergere: senza questa passata la
    richiesta resterebbe «in trattativa» per sempre e — dato che se ne ammette
    una sola aperta per esame — il candidato non potrebbe più richiedere quello
    stesso esame.
    """
    from models.exam.request_service import ExamRequestService

    expired = ExamRequestService.expire_pending_requests()
    return f"{expired} richieste d'esame scadute"


# nome → (descrizione, callable). Il callable gira dentro l'app context e
# restituisce una stringa di riepilogo per il log.
JOBS = {
    "demand": ("Segnali-domanda: riconferma e scadenze", job_demand_signals),
    "exam_requests": ("Richieste d'esame: scadenze", job_exam_requests),
}


def main() -> int:
    requested = sys.argv[1:]
    unknown = [name for name in requested if name not in JOBS]
    if unknown:
        print(f"Job sconosciuti: {', '.join(unknown)}")
        print(f"Disponibili: {', '.join(JOBS)}")
        return 2

    selected = requested or list(JOBS)

    # Lo scheduled task è un processo separato: non eredita né FLASK_ENV né
    # SECRET_KEY/ENCRYPTION_KEY dal file WSGI. Senza il bootstrap, create_app
    # in production solleverebbe su SECRET_KEY e il task fallirebbe ogni
    # giorno; con il solo default a "development" girerebbe invece sul DB
    # sbagliato, che è peggio.
    bootstrap_or_exit()
    app = create_app(os.environ.get("FLASK_ENV", "production"))

    failed = []
    with app.app_context():
        for name in selected:
            description, run = JOBS[name]
            try:
                summary = run()
                print(f"[ok]   {name}: {summary}")
            except Exception as exc:
                failed.append(name)
                print(f"[FAIL] {name} ({description}): {exc}")
                traceback.print_exc()

    print(f"\n{len(selected) - len(failed)}/{len(selected)} job completati")
    if failed:
        print(f"Falliti: {', '.join(failed)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
