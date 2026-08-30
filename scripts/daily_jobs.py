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

from prod_env import bootstrap_and_create_app  # noqa: E402


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


def job_match_proposals() -> str:
    """Scadenza delle proposte di sfida individuale.

    `MatchProposal.expires_at` veniva scritto a ogni proposta e **non lo
    leggeva nessuno**: `expire_old_proposals` esisteva, con la sua notifica
    «Proposta scaduta» già pronta, e non la chiamava nessun task, nessuna
    route, solo i test. Una proposta pendente restava quindi pendente per
    sempre e continuava a comparire fra quelle attive, senza che il proponente
    avesse modo di capire perché.
    """
    from models.individual_match.services import MatchProposalService

    expired = MatchProposalService.expire_proposals()
    return f"{expired} proposte di sfida scadute"


# nome → (descrizione, callable). Il callable gira dentro l'app context e
# restituisce una stringa di riepilogo per il log.
def job_feedback() -> str:
    """Segnalazioni degli utenti: rispedizione e ritorno degli stati (#255).

    Tre cose in un giro solo, e in quest'ordine:

    1. **rispedisce** quelle rimaste senza `issue_number` — token assente quel
       giorno, GitHub in 5xx, rete muta. Prima del polling, così una
       segnalazione nata oggi può gia' ricevere il suo stato stasera;
    2. **chiede a GitHub** le issue toccate dall'ultimo giro riuscito, con
       l'`ETag` della volta prima: **una chiamata per tutta l'app**, non una
       per utente;
    3. **aggiorna gli stati** e notifica chi ha scritto.

    Niente thread nella web app: un controllo agganciato al login sarebbe una
    chiamata di rete dentro la richiesta di chi sta solo entrando, dentro
    worker che PythonAnywhere ricicla senza preavviso. Il prezzo e' che fra
    l'etichetta e la notifica puo' passare fino a un giorno — per «la tua
    segnalazione e' stata presa in considerazione» e' un prezzo che non si
    sente.
    """
    from models.feedback.sync import FeedbackSync

    esito = FeedbackSync.giro_completo()
    return (
        f"{esito['spedite']} spedite, "
        f"{esito['aggiornate']} aggiornate, "
        f"{esito['notificate']} notifiche"
        + (f" — {esito['nota']}" if esito.get("nota") else "")
    )


JOBS = {
    "demand": ("Segnali-domanda: riconferma e scadenze", job_demand_signals),
    "exam_requests": ("Richieste d'esame: scadenze", job_exam_requests),
    "match_proposals": ("Proposte di sfida: scadenze", job_match_proposals),
    "feedback": ("Segnalazioni: rispedizione e stati da GitHub", job_feedback),
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
    #
    # Il bootstrap non basta se l'app è già stata importata: `config` legge
    # l'ambiente e non lo rilegge. Per questo l'import di `app` sta dentro
    # `bootstrap_and_create_app`, dopo il caricamento — vedi la sua docstring.
    app = bootstrap_and_create_app()

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
