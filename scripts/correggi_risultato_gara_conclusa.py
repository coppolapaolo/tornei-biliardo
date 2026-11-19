"""Corregge il risultato di una partita in una gara GIÀ CONCLUSA.

Nell'app non si può (issue #90): un risultato si corregge solo a gara in
corso. Quando l'errore si scopre a gara chiusa — Ronin Cup 2, gara 3, il
18/11/2026: MARCO–MAX P era 3-2 e non 2-3 — si passa da qui. Cosa cambia e
cosa no, e perché, è scritto in `models/match/correzione_gara_conclusa.py`.

In breve: cambiano la partita (con la traccia «corretto» visibile a tutti), le
classifiche di turno, di gara e di campionato, l'ELO e il podio della
gamification; gli abbinamenti dei turni dopo restano quelli giocati, e l'XP
della partita resta a chi l'ha ricevuto alla prima chiusura, come per ogni
correzione fatta dall'app. Un pari merito che si apre resta pari merito.

    # 1. ELENCO delle partite della gara, per trovare l'id e l'ordine dei
    #    giocatori (la gara si indica con l'id o con lo slug dell'indirizzo)
    venv/bin/python scripts/correggi_risultato_gara_conclusa.py \\
        --gara ronin-cup-2-gara-3 --elenca

    # 2. PROVA: fa tutto, controlli compresi, e poi annulla. Il punteggio è
    #    nell'ordine giocatore1-giocatore2 dell'elenco. Sul database vero
    #    tiene per qualche secondo il lock di scrittura: meglio farla sulla
    #    copia del punto 3, senza --commit
    venv/bin/python scripts/correggi_risultato_gara_conclusa.py \\
        --partita 1234 --punteggio 3-2 --by <ID_ADMIN> --nota "segnalato dai giocatori"

    # 3. PROVA GENERALE su una copia del database, scrivendo davvero. Il
    #    backup di SQLite è sicuro anche a sito acceso; un `cp` del file no
    sqlite3 instance/billiard_campionato.db ".backup /tmp/prova.db"
    venv/bin/python scripts/correggi_risultato_gara_conclusa.py \\
        --partita 1234 --punteggio 3-2 --by <ID_ADMIN> \\
        --database sqlite:////tmp/prova.db --commit

    # 4. ESECUZIONE sul database vero (web app su Disabled, backup fresco)
    venv/bin/python scripts/correggi_risultato_gara_conclusa.py \\
        --partita 1234 --punteggio 3-2 --by <ID_ADMIN> --commit

**Si ferma da solo, senza scrivere niente**, se lo stato salvato non è quello
che il codice ricalcolerebbe sui dati invariati — classifiche, ELO o XP di
podio. Vorrebbe dire che qualcosa era già fuori posto, e una correzione fatta
sopra mescolerebbe due cambiamenti. In quel caso il messaggio dice dove.

⚠️  IN PRODUZIONE VA ESEGUITO CON LA WEB APP SU **Disabled**, e riabilitata
subito dopo: lo storage di PythonAnywhere è NFS e SQLite non regge scritture
concorrenti; la riabilitazione fa anche ripartire i processi, che così non
tengono in memoria le classifiche di prima.
"""

import argparse
import logging
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
# Servono entrambe: la radice del progetto (per `app`, `models`) e la cartella
# scripts (per `prod_env`). La radice va inserita per ultima, così resta davanti.
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.dirname(_HERE))

from prod_env import PRODUCTION_REQUIRED, bootstrap_and_create_app  # noqa: E402

logging.basicConfig(level=logging.WARNING, format="%(message)s")


def _punteggio(testo: str):
    try:
        a, b = testo.replace("–", "-").split("-")
        return int(a), int(b)
    except ValueError:
        raise argparse.ArgumentTypeError("il punteggio si scrive così: 3-2")


def _trova_gara(db, Gara, valore: str):
    if valore.isdigit():
        return db.session.get(Gara, int(valore))
    return Gara.query.filter_by(slug=valore).first()


def _elenca(gara, Match) -> None:
    print(f"Gara {gara.id} «{gara.name}» — stato {gara.status}\n")
    partite = (
        Match.query.filter_by(gara_id=gara.id)
        .order_by(Match.round_number, Match.id)
        .all()
    )
    turno = None
    for m in partite:
        if m.round_number != turno:
            turno = m.round_number
            print(f"Turno {turno}")
        if m.is_bye:
            nome = m.player1.username if m.player1 else "?"
            print(f"  partita {m.id:>6}  {nome} — X")
            continue
        p1 = m.player1.username if m.player1 else "?"
        p2 = m.player2.username if m.player2 else "?"
        print(
            f"  partita {m.id:>6}  giocatore1 {p1}  {m.player1_score}-"
            f"{m.player2_score}  giocatore2 {p2}"
        )


def _tabella(titolo, righe, colonne) -> None:
    print(f"\n  {titolo}")
    if not righe:
        print("    (vuota)")
        return
    print("    " + "  ".join(colonne))
    for riga in righe:
        print("    " + "  ".join(str(v) for v in riga))


def _stampa(rapporto) -> None:
    print("=" * 72)
    print("ESEGUITO" if rapporto["scritto"] else "PROVA (niente è stato scritto)")
    g = rapporto["gara"]
    print(f"Gara {g['id']} «{g['name']}», campionato {g['campionato_id']}")
    gioc = rapporto["giocatori"]
    a, b = rapporto["punteggio_prima"]
    c, d = rapporto["punteggio_dopo"]
    print(
        f"Partita {rapporto['match_id']}: {gioc['player1']} {a}-{b} {gioc['player2']}"
        f"  →  {gioc['player1']} {c}-{d} {gioc['player2']}"
    )
    print(f"Vincitore: {rapporto['vincitore_prima']} → {rapporto['vincitore_dopo']}")
    print("=" * 72)

    print("\nTRIANGOLI GIRATI")
    for t in rapporto["triangoli_girati"]:
        extra = "  (runout tolto)" if t["runout_tolto"] else ""
        print(f"  triangolo {t['rack_number']}: {t['da']} → {t['a']}{extra}")

    colonne = ("pos", "giocatore", "vinte", "diff")
    _tabella(
        "CLASSIFICA DELLA GARA — prima", rapporto["classifica_gara_prima"], colonne
    )
    _tabella("CLASSIFICA DELLA GARA — dopo", rapporto["classifica_gara_dopo"], colonne)
    if g["campionato_id"]:
        colonne_c = ("pos", "giocatore", "vinte", "diff", "punti")
        _tabella(
            "CLASSIFICA GENERALE — prima",
            rapporto["classifica_campionato_prima"],
            colonne_c,
        )
        _tabella(
            "CLASSIFICA GENERALE — dopo",
            rapporto["classifica_campionato_dopo"],
            colonne_c,
        )

    print("\nELO competitivo che cambia")
    if rapporto["elo"]:
        for nome, prima, dopo in rapporto["elo"]:
            print(f"  {nome}: {prima} → {dopo}")
    else:
        print("  (nessuno)")

    podio = rapporto["podio"]
    print("\nXP DI PODIO")
    print(f"  tolto a: {', '.join(podio['tolto_a']) or '(nessuno)'}")
    print(f"  dato a:  {', '.join(podio['dato_a']) or '(nessuno)'}")
    trag = rapporto["traguardi"]
    for chi, slugs in trag["tolti"].items():
        print(f"  traguardi tolti a {chi}: {', '.join(slugs)}")
    for chi, slugs in trag["sbloccati"].items():
        print(f"  traguardi sbloccati a {chi}: {', '.join(slugs)}")

    print("\nDA SAPERE")
    for avviso in rapporto["avvisi"]:
        print(f"  - {avviso}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--gara", help="id o slug della gara (con --elenca)")
    parser.add_argument("--elenca", action="store_true", help="elenca le partite")
    parser.add_argument("--partita", type=int, help="id della partita da correggere")
    parser.add_argument(
        "--punteggio", type=_punteggio, help="giocatore1-giocatore2, per esempio 3-2"
    )
    parser.add_argument("--by", type=int, help="id dell'admin che corregge")
    parser.add_argument("--nota", default=None, help="perché si corregge")
    parser.add_argument(
        "--commit", action="store_true", help="scrive davvero (default: prova)"
    )
    parser.add_argument(
        "--database", help="URI SQLAlchemy alternativo, per la prova su una copia"
    )
    args = parser.parse_args()

    if args.elenca and not args.gara:
        parser.error("--elenca vuole --gara")
    if not args.elenca and not (args.partita and args.punteggio and args.by):
        parser.error("servono --partita, --punteggio e --by (oppure --gara --elenca)")

    if args.database:
        # Prima di costruire l'app: la config legge l'ambiente all'avvio.
        os.environ["DATABASE_URL"] = args.database

    # L'app si costruisce DOPO aver caricato le env (test_script_import_order).
    app = bootstrap_and_create_app(required=PRODUCTION_REQUIRED + ("ENCRYPTION_KEY",))

    from models import db
    from models.competition.models import Gara
    from models.match.correzione_gara_conclusa import CorrezioneRifiutata, correggi
    from models.match.models import Match

    with app.app_context():
        print(f"Database: {app.config.get('SQLALCHEMY_DATABASE_URI')}\n")
        if args.elenca:
            gara = _trova_gara(db, Gara, args.gara)
            if gara is None:
                print(f"Gara «{args.gara}» non trovata")
                return 1
            _elenca(gara, Match)
            return 0

        p1, p2 = args.punteggio
        try:
            rapporto = correggi(
                args.partita, p1, p2, args.by, args.nota, scrivi=args.commit
            )
        except CorrezioneRifiutata as motivo:
            print(f"Correzione NON fatta, niente è stato scritto.\nMotivo: {motivo}")
            return 1

        _stampa(rapporto)
        if not args.commit:
            print(
                "\nProva: niente è stato scritto. Prova generale su una copia con "
                "--database e --commit, poi --commit sul database vero."
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
