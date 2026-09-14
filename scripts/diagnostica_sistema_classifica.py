"""Sistema di classifica di campionati, gare e finali: cosa c'è e cosa stona.

**Sola lettura.** Non scrive niente, non ha un `--apply`: si lancia anche con la
web app attiva.

Serve dal 2026-09-14, quando la regola di `SPECIFICHE.md` riga 289 è stata resa
eseguibile. Fino ad allora:

* la gara di playoff nasceva **sempre a vittorie**, qualunque fosse il sistema
  del campionato;
* cambiare il sistema sul campionato lasciava le gare già create col sistema
  vecchio.

Le correzioni valgono per ciò che si crea o si cambia **da quel giorno**: i dati
esistenti non sono stati toccati. Questo script dice se ce n'è qualcuno da
guardare. Per ogni campionato elenca il sistema, le gare che hanno un sistema
diverso e, per ogni configurazione dei playoff, modalità, strategia e sistema
della finale.

Una finale di sistema diverso **non è un problema** in modalità «solo
playoff», dove della finale conta solo l'ordine d'arrivo. Lo è in modalità
sommata, dove si sommerebbero vittorie e triangoli: lo script la segnala con
``DA GUARDARE``.

Uso, dalla console di PythonAnywhere::

    cd /home/paolocoppola/mysite
    venv/bin/python scripts/diagnostica_sistema_classifica.py
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
# Prima `scripts/` (per `prod_env`), poi la radice, che così resta davanti.
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.dirname(_HERE))

from prod_env import bootstrap_and_create_app  # noqa: E402


def _righe_del_campionato(campionato) -> tuple[list[str], int]:
    from models.matchmaking.configuration import BRACKET_STRATEGIES
    from models.playoff.models import PlayoffRankingMode
    from models.status_enum import ClassificationSystem, GaraStatus

    sistema = campionato.classification_system
    righe = [
        f"Campionato {campionato.id} «{campionato.name}» — sistema {sistema.value}"
    ]
    da_guardare = 0

    finali = {
        cfg.gara.id for cfg in campionato.playoff_configurations if cfg.gara is not None
    }
    for gara in campionato.gare:
        if gara.is_deleted or gara.status == GaraStatus.CANCELLED.value:
            continue
        if gara.id in finali:
            continue
        sistema_gara = ClassificationSystem.resolve(gara.classification_system)
        if (
            sistema_gara != sistema
            and gara.matchmaking_strategy not in BRACKET_STRATEGIES
        ):
            righe.append(
                f"  gara {gara.id} «{gara.name}» ({gara.status}) — sistema "
                f"{sistema_gara.value}, diverso dal campionato"
            )

    for cfg in campionato.playoff_configurations:
        modo = cfg.ranking_mode
        finale = cfg.gara
        testo = (
            f"  playoff {cfg.id} «{cfg.name}» — "
            f"{'attivo' if cfg.is_active else 'disattivato'}, modalità {modo.value}, "
            f"strategia {cfg.strategy_type or 'ereditata'}"
        )
        if finale is None:
            righe.append(testo + ", finale non ancora creata")
            continue
        sistema_finale = ClassificationSystem.resolve(finale.classification_system)
        testo += (
            f", finale gara {finale.id} ({finale.status}) a sistema "
            f"{sistema_finale.value}"
        )
        if (
            cfg.is_active
            and modo is PlayoffRankingMode.CAMPIONATO_PLUS_PLAYOFF
            and sistema_finale != sistema
        ):
            testo += " — DA GUARDARE: si somma con un sistema diverso"
            da_guardare += 1
        righe.append(testo)

    return righe, da_guardare


def main() -> int:
    app = bootstrap_and_create_app()
    with app.app_context():
        from models.campionato.models import Campionato

        totale = 0
        campionati = Campionato.query.order_by(Campionato.id).all()
        for campionato in campionati:
            if not campionato.playoff_configurations:
                continue
            righe, da_guardare = _righe_del_campionato(campionato)
            totale += da_guardare
            print("\n".join(righe))
            print()

        print(f"Finali da guardare: {totale}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
