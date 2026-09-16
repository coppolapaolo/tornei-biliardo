"""Adotta una gara standalone giocata come finale di playoff di un campionato.

Serve quando la finale è stata giocata **fuori** dal campionato — per esempio
perché gli inviti erano scaduti e il direttore ha creato una gara a parte — e
il campionato è rimasto «in attesa dei playoff» con una gara di playoff vuota.
Niente si sposta: la gara giocata cambia proprietario, gli inviti di chi ha
giocato risultano accettati e registrati dall'admin, la gara vuota sparisce e
la classifica generale si ricalcola (dettagli in `models/playoff/adozione.py`).

    # 1. INVENTARIO (default): sola lettura, dice cosa cambierebbe
    venv/bin/python scripts/adotta_gara_come_playoff.py \\
        --campionato 4 --gara 48 --by <ID_ADMIN>

    # 2. PROVA GENERALE su una copia del database (mostra la classifica finale)
    cp instance/billiard_campionato.db /tmp/prova.db
    venv/bin/python scripts/adotta_gara_come_playoff.py \\
        --campionato 4 --gara 48 --by <ID_ADMIN> \\
        --database sqlite:////tmp/prova.db --commit

    # 3. ESECUZIONE sul database vero, con la web app su Disabled
    venv/bin/python scripts/adotta_gara_come_playoff.py \\
        --campionato 4 --gara 48 --by <ID_ADMIN> --commit

La gara adottata prende il nome della configurazione, come una finale nata
dall'app; `--nome` lo sovrascrive. `--config` serve solo se il campionato ha
più configurazioni di playoff attive.

In produzione (PythonAnywhere) va lanciato con la **web app su Disabled** e con
un backup fresco: lo storage è NFS e SQLite non regge scritture concorrenti
(vedi CLAUDE.md). Il ricalcolo della classifica è l'unica scrittura derivata:
ELO e XP non cambiano, perché le partite restano dove sono.
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
logger = logging.getLogger("adotta_gara_come_playoff")


def _riga(*celle, larghezze):
    return "  ".join(str(c).ljust(w) for c, w in zip(celle, larghezze))


def _print_report(report):
    c, cfg, g, s = (
        report["campionato"],
        report["config"],
        report["gara_giocata"],
        report["gara_scartata"],
    )
    print(f"Campionato {c['id']} «{c['nome']}» · sistema {c['sistema']}")
    print(f"  stato prima: {c['stato_prima']}", end="")
    if report["eseguito"]:
        print(f" → dopo: {c['stato_dopo']}")
    else:
        print()
    print(
        f"Playoff «{cfg['nome']}» (config {cfg['id']}) · modalità {cfg['modalita']} "
        f"· peso {cfg['peso']} · posti {cfg['posti']}"
    )
    print(
        f"  scadenza inviti {cfg['scadenza_inviti']} · "
        f"data prevista {cfg['data_prevista']}"
    )
    print()
    print(
        f"Gara giocata {g['id']} «{g['nome']}» · {g['data']:%d/%m/%Y %H:%M} · "
        f"{g['stato']} · {g['turni']} turni · {g['strategia']} · sistema {g['sistema']}"
    )
    print(f"  {g['iscritti']} iscritti · {g['partite']} partite giocate")
    if g["nome_nuovo"] != g["nome"]:
        print(f"  verrà rinominata «{g['nome_nuovo']}»")
    print(
        f"  diventa la gara n. {report['numero_assegnato']} del campionato, "
        f"peso {report['peso_applicato']}"
    )
    if s is None:
        print("Nessuna gara di playoff da scartare")
    else:
        print(
            f"Gara di playoff da scartare: {s['id']} «{s['nome']}» (n. {s['numero']}, "
            f"{s['stato']}, {s['iscritti']} iscritti, nessuna partita) → cancellata"
        )
    if report["confronto"]:
        print()
        print(
            "Differenze fra la finale prevista dalla configurazione e quella giocata:"
        )
        for d in report["confronto"]:
            print(
                f"  {d['campo']:<22} prevista {d['prevista']!s:<24} "
                f"giocata {d['giocata']}"
            )
    if report["allineamenti"]:
        print()
        print("Campi amministrativi riportati a come li scrive l'app su una finale:")
        for a in report["allineamenti"]:
            print(f"  {a['campo']:<22} {a['da']!s:<24} → {a['a']}")
    if report["co_direttori_della_gara"]:
        print(
            "Co-direttori assegnati alla gara (restano): "
            + ", ".join(report["co_direttori_della_gara"])
        )

    print()
    print("Inviti di chi ha giocato:")
    w = (4, 24, 12, 24)
    print("  " + _riga("pos", "giocatore", "stato", "azione", larghezze=w))
    for r in report["inviti"]:
        print(
            "  "
            + _riga(r["posizione"], r["username"], r["stato"], r["azione"], larghezze=w)
        )
    if report["inviti_non_giocanti"]:
        print("Inviti di chi non ha giocato (restano come sono):")
        for r in report["inviti_non_giocanti"]:
            print(
                "  "
                + _riga(r["posizione"], r["username"], r["stato"], "—", larghezze=w)
            )

    print()
    if report["eseguito"]:
        print("Classifica finale del campionato (ricalcolata):")
        w = (4, 24, 10, 9, 5)
        print(
            "  "
            + _riga("pos", "giocatore", "triangoli", "vittorie", "gare", larghezze=w)
        )
        for r in report["classifica_finale"]:
            print(
                "  "
                + _riga(
                    r["posizione"],
                    r["username"],
                    r["triangoli"],
                    r["vittorie"],
                    r["gare"],
                    larghezze=w,
                )
            )
    else:
        print(
            "Classifica attesa (stagione + finale × peso; l'ordine vero lo dà il "
            "ricalcolo, spareggi compresi):"
        )
        w = (24, 10, 8, 8, 8, 8)
        print(
            "  "
            + _riga(
                "giocatore",
                "atteso",
                "tri.st.",
                "tri.fin",
                "vit.st.",
                "vit.fin",
                larghezze=w,
            )
        )
        for r in report["classifica_attesa"]:
            print(
                "  "
                + _riga(
                    r["username"],
                    r["atteso"],
                    r["triangoli_stagione"],
                    r["triangoli_finale"],
                    r["vittorie_stagione"],
                    r["vittorie_finale"],
                    larghezze=w,
                )
            )


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
        "--gara", type=int, required=True, help="ID della gara standalone giocata"
    )
    parser.add_argument(
        "--by", type=int, required=True, help="ID dell'admin che esegue la correzione"
    )
    parser.add_argument(
        "--config", type=int, help="ID della configurazione playoff, se più di una"
    )
    parser.add_argument("--nome", help="Nuovo nome della gara adottata (facoltativo)")
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
    from models.playoff.adozione import AdozioneGaraGiocata

    with app.app_context():
        print(f"Database: {app.config.get('SQLALCHEMY_DATABASE_URI')}\n")
        try:
            config_id = _config_id(args.campionato, args.config)
            if args.commit:
                report = AdozioneGaraGiocata.esegui(
                    config_id, args.gara, performed_by_id=args.by, nome=args.nome
                )
                db.session.commit()
            else:
                report = AdozioneGaraGiocata.plan(
                    config_id, args.gara, performed_by_id=args.by, nome=args.nome
                )
                db.session.rollback()
        except Exception as exc:
            db.session.rollback()
            logger.error("Adozione annullata: %s", exc)
            return 1

        if args.json:
            print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
        else:
            _print_report(report)

        if not args.commit:
            print(
                "\nSola lettura: niente è stato scritto. Prova generale su una "
                "copia con --database, poi --commit sul database vero."
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
