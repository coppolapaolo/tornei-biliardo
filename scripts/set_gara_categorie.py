"""Assegna a mano le categorie delle gare con handicap già giocate.

Le categorie (ADR-049) decidono se una partita di una gara con handicap entra
nell'Elo: contano solo quelle fra giocatori della **stessa** categoria. Dalla
schermata si assegnano prima dell'avvio del primo turno, e dopo non più. Le
gare già giocate — che in produzione ci sono — restano quindi fuori portata, e
questo script è il modo di recuperarle.

È **interattivo**: si lancia e si risponde.

    venv/bin/python scripts/set_gara_categorie.py             # prova generale
    venv/bin/python scripts/set_gara_categorie.py --commit    # scrive davvero

Chiede la categoria **solo di chi non si sa già**: chi ha giocato l'Open di
giugno da «C» è ancora «C» a luglio, quindi dalla seconda gara in poi si
risponde ai soli nuovi arrivati. Su un circuito di otto prove è la differenza
fra ottanta domande e otto. Si accetta un nome nuovo (viene creato), uno già in
elenco, o l'invio a vuoto per lasciare il giocatore senza categoria.

Finiti i giocatori mostra **tutti** gli iscritti ordinati per categoria e poi
per nome, marcando quelli riportati da una gara precedente — sono quelli che
nessuno ha riguardato, quindi è lì che si nasconde chi nel frattempo è salito
di categoria. Poi chiede cosa farne:

    s   salva e passa alla gara successiva
    n   rivedi: richiede **tutti** i giocatori, con i valori attuali come
        proposta. È il momento in cui si corregge chi è cambiato di categoria
    x   salta questa gara senza scrivere niente

Durante le domande si può anche digitare `!salta` al posto di una categoria per
abbandonare la gara in corso.

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
    except KeyboardInterrupt:
        # Ctrl-C è un modo legittimo di smettere: merita una riga, non una
        # traccia di stack lunga dieci righe che sembra un guasto.
        raise SystemExit("\n\nInterrotto. Le gare già confermate restano salvate.")
    return risposta or default


#: Digitata al posto di una categoria, abbandona la gara in corso senza
#: scrivere niente. Con il punto esclamativo perché una categoria può
#: chiamarsi in qualunque modo, «salta» compreso.
SALTA = "!salta"


class GaraSaltata(Exception):
    """Chi risponde `!salta` passa alla gara successiva senza salvare."""


def _conferma(prompt: str) -> bool:
    while True:
        risposta = _chiedi(f"{prompt} (s/n)").lower()
        if risposta in ("s", "si", "sì", "y", "yes"):
            return True
        if risposta in ("n", "no"):
            return False
        print("  Rispondi 's' oppure 'n'.")


def _conferma_gara() -> str:
    """Cosa fare della gara appena compilata: salva, rivedi o salta."""
    while True:
        risposta = _chiedi(
            "\n  Confermi? (s = salva · n = rivedi · x = salta questa gara)"
        ).lower()
        if risposta in ("s", "si", "sì", "y", "yes"):
            return "salva"
        if risposta in ("n", "no"):
            return "rivedi"
        if risposta in ("x", "salta"):
            return "salta"
        print("  Rispondi 's', 'n' oppure 'x'.")


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


SENZA = "—"


def _riepilogo(scelte: Dict[int, str], iscritti, riportate: set) -> None:
    """Tutti i giocatori, ordinati per categoria e poi per nome.

    Non un conteggio per categoria: quello dice quanti sono ma non **chi**, e
    l'errore da cercare qui è una persona sola nel posto sbagliato — chi è
    salito di categoria dall'ultima gara. Le voci riportate da una gara
    precedente sono marcate, perché sono esattamente quelle che nessuno ha
    riguardato in questo giro.
    """
    righe = []
    for ins in iscritti:
        categoria = scelte.get(ins.id) or ""
        righe.append(
            (
                categoria.lower() if categoria else "\uffff",  # i senza in fondo
                ins.user.username.lower(),
                categoria or SENZA,
                ins.user.username,
                ins.id in riportate,
            )
        )
    righe.sort()

    print("\n  Riepilogo:")
    for _k1, _k2, categoria, username, riportata in righe:
        marcatore = "  ·riportata" if riportata else ""
        print(f"    {categoria:<12} {username}{marcatore}")

    senza = sum(1 for r in righe if r[2] == SENZA)
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


def _memoria_dal_db(db, Inscription, Categoria, Gara) -> Dict[int, str]:
    """La categoria già nota per ogni giocatore, dalla gara più recente.

    Serve a non richiedere ciò che si sa già: chi ha giocato l'Open di giugno
    da «C» è ancora «C» a luglio, salvo che sia salito. Si legge dal DB e non
    solo dalla memoria di questa esecuzione, così rilanciare lo script dopo
    un'interruzione riparte da dove si era arrivati.

    In ordine cronologico, quindi l'ultima assegnazione vince.
    """
    righe = (
        db.session.query(Inscription.user_id, Categoria.name)
        .join(Categoria, Inscription.categoria_id == Categoria.id)
        .join(Gara, Inscription.gara_id == Gara.id)
        .order_by(Gara.date.asc(), Gara.id.asc())
        .all()
    )
    return {user_id: nome for user_id, nome in righe}


def _raccogli(gara, iscritti, CategoriaService, memoria: Dict[int, str], tutti: bool):
    """Chiede le categorie e restituisce {inscription_id: nome}.

    Con `tutti=False` — la prima passata su una gara — chiede **solo i
    giocatori che non hanno ancora una categoria nota**: gli altri la portano
    dietro dalla gara precedente. Su un circuito di otto prove è la differenza
    fra rispondere ottanta volte e rispondere ai due nuovi arrivati.

    Con `tutti=True` — dopo un «rivedi» — le chiede tutte, con i valori
    correnti come proposta: è il momento in cui si corregge chi è cambiato di
    categoria, e per farlo bisogna poter passare anche su chi era stato
    riportato senza domande.

    Restituisce anche l'insieme delle iscrizioni **non** chieste, che il
    riepilogo marca come riportate.
    """
    esistenti = [c.name for c in CategoriaService.list_for_gara(gara)]
    if esistenti:
        print(f"  Categorie già in elenco: {', '.join(esistenti)}")
    print(f"  (invio a vuoto = nessuna categoria · {SALTA} = passa alla prossima gara)")

    def _nota(ins) -> str:
        if ins.categoria:
            return ins.categoria.name
        return memoria.get(ins.user_id, "")

    da_chiedere = [ins for ins in iscritti if tutti or not _nota(ins)]
    chieste = {ins.id for ins in da_chiedere}
    riportate = {ins.id for ins in iscritti if ins.id not in chieste}

    if riportate and not tutti:
        print(f"  {len(riportate)} categorie riportate dalle gare precedenti.")
    print()

    scelte: Dict[int, str] = {ins.id: _nota(ins) for ins in iscritti}
    for indice, ins in enumerate(da_chiedere, start=1):
        etichetta = f"  [{indice}/{len(da_chiedere)}] {ins.user.username}"
        risposta = _chiedi(etichetta, _nota(ins))
        if risposta.strip().lower() == SALTA:
            raise GaraSaltata
        scelte[ins.id] = risposta

    return _canonizza(gara, scelte, CategoriaService), riportate


def _canonizza(gara, scelte: Dict[int, str], CategoriaService) -> Dict[int, str]:
    """Riscrive i nomi come verranno davvero salvati.

    Maiuscole e spazi non contano — «a» e «A» sono la stessa categoria e in
    scrittura si fondono — ma un riepilogo che mostra le due grafie affiancate
    sembra elencare due categorie diverse, e chi rilegge cerca un errore che
    non c'è. Le categorie riportate da un'altra gara arrivano con la grafia di
    lì: qui prendono quella già in uso in questa competizione.
    """
    # Import ritardato come tutti gli altri: `models` a livello di modulo
    # eseguirebbe mezzo dominio prima che `bootstrap_and_create_app` abbia
    # popolato l'ambiente.
    from models.shared.naming import normalize_list_name

    canonico = {
        c.normalized_name: c.name
        for c in CategoriaService.list_for_gara(gara, include_inactive=True)
    }
    return {
        ins_id: canonico.get(normalize_list_name(nome), nome) if nome else nome
        for ins_id, nome in scelte.items()
    }


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

    from models import db, Categoria, Gara, Inscription  # noqa: WPS433
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

        # Quello che gia' si sa: evita di richiedere la categoria di chi l'ha
        # gia' avuta in una gara precedente.
        memoria = _memoria_dal_db(db, Inscription, Categoria, Gara)

        sistemate = saltate = 0
        for gara, _senza in da_fare:
            iscritti = _iscritti(Inscription, gara.id)
            if not iscritti:
                continue

            # Prima passata: solo i giocatori senza categoria nota. Dopo un
            # «rivedi» si chiede tutto, perche' e' li' che si corregge chi e'
            # cambiato di categoria.
            tutti = False
            try:
                while True:
                    print("\n" + "=" * 64)
                    print(f"Gara #{gara.id} — {gara.display_name}  ({gara.date})")
                    print("=" * 64)
                    scelte, riportate = _raccogli(
                        gara, iscritti, CategoriaService, memoria, tutti
                    )
                    _riepilogo(scelte, iscritti, riportate)

                    esito = _conferma_gara()
                    if esito == "salva":
                        if args.commit:
                            _applica(gara, iscritti, scelte, CategoriaService, db)
                            print("  ✓ Salvate.")
                        else:
                            print("  ⏭️  Prova generale: non salvate.")
                        # La memoria si aggiorna comunque, anche in prova
                        # generale: serve a far proseguire il giro senza
                        # richiedere gli stessi nomi gara dopo gara.
                        for ins in iscritti:
                            nome = scelte.get(ins.id) or ""
                            if nome:
                                memoria[ins.user_id] = nome
                        sistemate += 1
                        break
                    if esito == "salta":
                        raise GaraSaltata
                    tutti = True
                    print("  ↻ Rivediamo tutti i giocatori di questa gara.")
            except GaraSaltata:
                print("  ⏭️  Gara saltata: niente scritto, passo alla prossima.")
                saltate += 1

        print(
            f"\nGare sistemate: {sistemate}"
            + (f" · saltate: {saltate}" if saltate else "")
        )

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
