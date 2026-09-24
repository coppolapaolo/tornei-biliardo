"""Riallinea gli inviti ai playoff già partiti alla classifica in pagina.

Serve quando gli inviti sono partiti da una classifica sbagliata: chi doveva
entrare riceve l'invito di sempre, con la stessa scadenza degli altri; chi non
doveva entrare vede il suo invito ritirato e riceve un avviso che lo spiega.
Chi ha rifiutato, chi ha lasciato scadere e chi è stato aggiunto a mano dal
direttore restano come sono (dettagli in `models/playoff/riallineamento.py`).

Nato per il campionato 5 (24/09/2026): la X non contava nelle righe da cui
partono gli inviti, e l'ottavo posto è andato a RIZA invece che a serpico67.

    # 1. INVENTARIO (default): sola lettura, dice cosa cambierebbe
    venv/bin/python scripts/riallinea_inviti_playoff.py --campionato 5

    # 2. PROVA GENERALE su una copia del database
    cp instance/billiard_campionato.db /tmp/prova.db
    venv/bin/python scripts/riallinea_inviti_playoff.py --campionato 5 \\
        --database sqlite:////tmp/prova.db --commit

    # 3. ESECUZIONE sul database vero, con la web app su Disabled
    venv/bin/python scripts/riallinea_inviti_playoff.py --campionato 5 --commit

`--config` serve solo se il campionato ha più configurazioni di playoff attive.

In produzione (PythonAnywhere) va lanciato con la **web app su Disabled** e con
un backup fresco: lo storage è NFS e SQLite non regge scritture concorrenti
(vedi CLAUDE.md). Le notifiche partono dentro la stessa transazione: senza
`--commit` non arriva niente a nessuno.
"""

import argparse
import json
import logging
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
# Servono entrambe: la radice del progetto (per `app`, `models`) e la cartella
# scripts (per `prod_env`). La radice va inserita per ultima così da restare
# davanti a `scripts/` in sys.path.
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.dirname(_HERE))

from prod_env import bootstrap_and_create_app  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("riallinea_inviti_playoff")


def _print_report(piano):
    print(
        f"Playoff «{piano.config_nome}» (config {piano.config_id}) · "
        f"campionato {piano.campionato_id} · scadenza inviti {piano.scadenza}"
    )
    print()
    print("Chi deve avere l'invito, dalla classifica in pagina:")
    for a in piano.attesi:
        print(f"  {a.posizione:>3}  {a.username:<24} {a.motivo}")
    print()
    if piano.niente_da_fare:
        print("Gli inviti sono già allineati: niente da fare.")
        return
    if piano.da_ritirare:
        print("Inviti da ritirare:")
        for r in piano.da_ritirare:
            in_pagina = r.posizione_in_pagina or "—"
            print(
                f"  {r.username:<24} invitato come {r.posizione_invito}°, "
                f"in pagina {in_pagina}° · stato {r.stato}"
                + (f" · al suo posto {r.al_suo_posto}" if r.al_suo_posto else "")
            )
    if piano.da_invitare:
        print("Inviti da mandare:")
        for i in piano.da_invitare:
            print(f"  {i.username:<24} {i.posizione}° · {i.motivo}")
    print()
    if piano.eseguito:
        print("Fatto: inviti aggiornati e notifiche mandate.")


def _config_id(campionato_id, esplicito):
    from models.playoff.models import PlayoffConfiguration

    if esplicito:
        return esplicito
    attive = PlayoffConfiguration.query.filter_by(
        campionato_id=campionato_id, is_active=True
    ).all()
    if len(attive) != 1:
        raise SystemExit(
            f"Il campionato {campionato_id} ha {len(attive)} configurazioni playoff "
            "attive: indica quale con --config"
        )
    return attive[0].id


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--campionato", type=int, required=True, help="ID del campionato"
    )
    parser.add_argument(
        "--config", type=int, help="ID della configurazione playoff, se più di una"
    )
    parser.add_argument(
        "--commit", action="store_true", help="Scrive davvero (default: sola lettura)"
    )
    parser.add_argument(
        "--database",
        help="URI SQLAlchemy alternativo, per la prova generale su una copia",
    )
    parser.add_argument("--json", action="store_true", help="Report in JSON")
    args = parser.parse_args()

    if args.database:
        # Prima di costruire l'app: la config legge l'ambiente all'avvio.
        os.environ["DATABASE_URL"] = args.database

    # L'app si costruisce DOPO aver caricato le env: importare `app` in cima al
    # file congelerebbe un ambiente vuoto (presidio: test_script_import_order).
    app = bootstrap_and_create_app()

    from models import db
    from models.playoff import riallineamento

    with app.app_context():
        print(f"Database: {app.config.get('SQLALCHEMY_DATABASE_URI')}\n")
        try:
            config_id = _config_id(args.campionato, args.config)
            if args.commit:
                piano = riallineamento.esegui(config_id)
                db.session.commit()
            else:
                piano = riallineamento.pianifica(config_id)
                db.session.rollback()
        except Exception as exc:
            db.session.rollback()
            logger.error("Riallineamento annullato: %s", exc)
            return 1

        if args.json:
            print(
                json.dumps(piano.as_dict(), indent=2, ensure_ascii=False, default=str)
            )
        else:
            _print_report(piano)

        if not args.commit:
            print(
                "\nSola lettura: niente è stato scritto e nessuno è stato avvisato. "
                "Prova generale su una copia con --database, poi --commit sul "
                "database vero."
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
