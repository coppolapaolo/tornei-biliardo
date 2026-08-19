"""Assegna a mano le categorie delle gare con handicap già giocate.

Le categorie (ADR-049) decidono se una partita di una gara con handicap entra
nell'Elo: contano solo quelle fra giocatori della **stessa** categoria. Dalla
schermata si assegnano prima dell'avvio del primo turno, e dopo non più. Le
gare già giocate — che in produzione ci sono — restano quindi fuori portata, e
questo script è il modo di recuperarle.

È **interattivo**: si lancia e si risponde.

    venv/bin/python scripts/set_gara_categorie.py             # prova generale
    venv/bin/python scripts/set_gara_categorie.py --commit    # scrive davvero

Per ogni gara elenca gli iscritti uno alla volta e chiede la categoria. Si
accetta un nome nuovo (viene creato), uno già in elenco, oppure l'invio a vuoto
per lasciare il giocatore senza categoria. Finiti i giocatori mostra il
riepilogo per categoria e chiede conferma: se si conferma passa alla gara
successiva, altrimenti si ricomincia da capo la stessa gara con le risposte
appena date come proposta.

⚠️  IL RICALCOLO DELL'ELO È GLOBALE, NON CHIRURGICO
Le categorie appena scritte non cambiano nulla da sole su partite già chiuse:
serve rigiocare la storia. `recalculate_all_elo` azzera e rigioca **tutto** in
ordine cronologico, perché l'Elo è path-dependent: far entrare partite prima
escluse **sposta il rating di tutti**, non solo dei giocatori toccati. Non
esiste una versione locale onesta di questa operazione. Lo script lo chiede
esplicitamente prima di farlo.

⚠️  IN PRODUZIONE VA ESEGUITO CON LA WEB APP SU **Disabled**
Lo storage di PythonAnywhere è NFS e i lock di SQLite non sono affidabili: ogni
scrittura da console si fa con la web app disabilitata, riabilitandola subito
dopo.
"""

import argparse
import os
import sys
from collections import Counter
from typing import Dict, List

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# NB: nessun `from app import create_app` qui in cima. L'app si costruisce
# **dopo** aver caricato l'ambiente, dentro `main()` — vedi prod_env e il
# presidio in tests/new/unit/test_script_import_order.py.
from scripts.prod_env import bootstrap_and_create_app  # noqa: E402


def _chiedi(prompt: str, default: str = "") -> str:
    """Una domanda a riga di comando, con `default` mostrato fra parentesi.

    Sull'EOF si esce, non si tira a indovinare: uno script interattivo che ha
    perso il proprio ingresso non sa più cosa gli sia stato risposto, e
    proseguire con i valori di default scriverebbe categorie che nessuno ha
    scelto. (La prima stesura tornava il default, e con `_conferma` che
    rifiuta le risposte incomprensibili il risultato era un ciclo infinito.)
    """
    suffisso = f" [{default}]" if default else ""
    try:
        risposta = input(f"{prompt}{suffisso}: ").strip()
    except EOFError:
        raise SystemExit("\nInterrotto: ingresso terminato. Nulla è stato salvato.")
    return risposta or default


def _conferma(prompt: str) -> bool:
    while True:
        risposta = _chiedi(f"{prompt} (s/n)").lower()
        if risposta in ("s", "si", "sì", "y", "yes"):
            return True
        if risposta in ("n", "no"):
            return False
        print("  Rispondi 's' oppure 'n'.")


def gare_da_sistemare(db, Gara, GaraStatus, Inscription):
    """Le gare con handicap già avviate in cui manca almeno una categoria.

    Dalla più vecchia alla più recente: è l'ordine in cui sono state giocate,
    ed è quello in cui conviene ripercorrerle.
    """
    candidate = (
        Gara.query.filter(Gara.status != GaraStatus.SETUP.value)
        .order_by(Gara.date.asc(), Gara.id.asc())
        .all()
    )
    da_fare = []
    for gara in candidate:
        if not gara.effective_has_handicap:
            continue
        senza = Inscription.query.filter(
            Inscription.gara_id == gara.id,
            Inscription.categoria_id.is_(None),
            Inscription.is_withdrawn.is_(False),
        ).count()
        if senza:
            da_fare.append((gara, senza))
    return da_fare


def _iscritti(Inscription, gara_id) -> List:
    return (
        Inscription.query.filter(
            Inscription.gara_id == gara_id,
            Inscription.is_withdrawn.is_(False),
        )
        .order_by(Inscription.id.asc())
        .all()
    )


def _riepilogo(scelte: Dict[int, str], iscritti) -> None:
    conteggi = Counter(scelte.get(ins.id) or "— senza categoria —" for ins in iscritti)
    print("\n  Riepilogo per categoria:")
    for nome, quanti in sorted(conteggi.items()):
        print(f"    {nome:<24} {quanti}")
    senza = conteggi.get("— senza categoria —", 0)
    if senza == 1:
        print(
            "\n  ⚠️  1 giocatore resta senza categoria: le sue partite non "
            "conteranno per l'Elo."
        )
    elif senza:
        print(
            f"\n  ⚠️  {senza} giocatori restano senza categoria: le loro partite "
            "non conteranno per l'Elo."
        )


def _raccogli(gara, iscritti, CategoriaService, proposte: Dict[int, str]):
    """Chiede la categoria di ogni iscritto. Ritorna {inscription_id: nome}."""
    esistenti = [c.name for c in CategoriaService.list_for_gara(gara)]
    if esistenti:
        print(f"  Categorie già in elenco: {', '.join(esistenti)}")
    print("  (invio a vuoto = nessuna categoria)\n")

    scelte: Dict[int, str] = {}
    for indice, ins in enumerate(iscritti, start=1):
        etichetta = f"  [{indice}/{len(iscritti)}] {ins.user.username}"
        proposta = proposte.get(ins.id) or (ins.categoria.name if ins.categoria else "")
        scelte[ins.id] = _chiedi(etichetta, proposta)
    return scelte


def _applica(gara, iscritti, scelte, CategoriaService, db) -> None:
    for ins in iscritti:
        CategoriaService.set_inscription_categoria_by_name(
            gara, ins, scelte.get(ins.id) or "", force=True
        )
    db.session.commit()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Assegna le categorie alle gare con handicap già giocate."
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Scrive davvero (default: prova generale, nulla viene salvato).",
    )
    parser.add_argument(
        "--gara",
        type=int,
        default=None,
        help="Limita a una sola gara, per id.",
    )
    parser.add_argument(
        "--no-recalc",
        action="store_true",
        help="Non ricalcolare l'Elo alla fine (lo si farà a parte).",
    )
    args = parser.parse_args(argv)

    app = bootstrap_and_create_app()

    from models import db, Gara, Inscription  # noqa: WPS433
    from models.categoria.service import CategoriaService
    from models.rating.calculation_service import RatingCalculationService
    from models.status_enum import GaraStatus

    with app.app_context():
        da_fare = gare_da_sistemare(db, Gara, GaraStatus, Inscription)
        if args.gara:
            da_fare = [(g, n) for g, n in da_fare if g.id == args.gara]

        if not da_fare:
            print("Nessuna gara con handicap ha iscritti senza categoria.")
            return 0

        print(f"\nGare da sistemare: {len(da_fare)} (dalla più vecchia)\n")
        for gara, senza in da_fare:
            print(f"  #{gara.id:<5} {gara.date}  {gara.display_name}  ({senza} senza)")

        if not args.commit:
            print(
                "\nℹ️  PROVA GENERALE: puoi rispondere a tutto, ma non verrà "
                "salvato nulla. Rilancia con --commit per scrivere."
            )

        sistemate = 0
        for gara, _senza in da_fare:
            iscritti = _iscritti(Inscription, gara.id)
            if not iscritti:
                continue

            proposte: Dict[int, str] = {}
            while True:
                print("\n" + "=" * 64)
                print(f"Gara #{gara.id} — {gara.display_name}  ({gara.date})")
                print("=" * 64)
                scelte = _raccogli(gara, iscritti, CategoriaService, proposte)
                _riepilogo(scelte, iscritti)

                if _conferma("\n  Confermi queste categorie?"):
                    if args.commit:
                        _applica(gara, iscritti, scelte, CategoriaService, db)
                        print("  ✓ Salvate.")
                    else:
                        print("  ⏭️  Prova generale: non salvate.")
                    sistemate += 1
                    break

                # Non confermata: si ricomincia dal primo giocatore, con le
                # risposte appena date come proposta — così correggerne una non
                # costa ridigitarle tutte.
                proposte = scelte
                print("  ↻ Ricominciamo da capo questa gara.")

        print(f"\nGare sistemate: {sistemate}")

        if args.commit and sistemate and not args.no_recalc:
            print(
                "\n⚠️  Le categorie appena scritte non cambiano nulla finché "
                "l'Elo non viene rigiocato.\n"
                "    Il ricalcolo è GLOBALE: l'Elo è path-dependent, quindi "
                "far entrare partite\n"
                "    prima escluse sposta il rating di TUTTI, non solo dei "
                "giocatori toccati."
            )
            if _conferma("    Ricalcolare adesso l'Elo di tutti?"):
                esito = RatingCalculationService.recalculate_all_elo()
                db.session.commit()
                print(f"    ✓ Elo competitivo: {esito}")
                esito_globale = RatingCalculationService.recalculate_all_elo_global()
                db.session.commit()
                print(f"    ✓ Elo globale: {esito_globale}")
                print(
                    "\n    Ora conviene riconciliare i traguardi:\n"
                    "        venv/bin/python scripts/reconcile_achievements.py"
                )
            else:
                print(
                    "    ⏭️  Saltato. Ricordati:\n"
                    "        venv/bin/python scripts/recalc_elo.py --commit"
                )

    return 0


if __name__ == "__main__":
    sys.exit(main())
