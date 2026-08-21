"""Il censimento dei dati di rating conta quello che dice di contare.

Lo script `scripts/rating_census.py` è il passo 0 di ADR-052: decide se i dati
bastano a scegliere fra i due motori di rating. Se sbaglia i conti, la
decisione la prende su numeri finti — e nessuno se ne accorge, perché non c'è
niente con cui confrontarli.

I test girano su oggetti finti e non toccano il DB: la parte che vale la pena
presidiare è l'aggregazione, non la query.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, List, Optional, Sequence

import pytest

_SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"


def _carica_modulo() -> Any:
    """Importa lo script per path, come farebbe chi lo lancia a mano."""
    if str(_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(_SCRIPTS))
    spec = importlib.util.spec_from_file_location(
        "rating_census", _SCRIPTS / "rating_census.py"
    )
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


censimento = _carica_modulo()


def _partita(
    player_ids: Sequence[int],
    racks: int = 10,
    esclusione: Optional[str] = None,
    is_trio: bool = False,
    mese: str = "2026-03",
    race_to: bool = False,
    distanza: int = 5,
) -> Any:
    """Una partita finta, già nella forma che il censimento consuma."""
    from datetime import datetime

    anno, mm = mese.split("-")
    return censimento.Partita(
        origine="torneo",
        id_=len(player_ids) * 100 + racks,
        player_ids=list(player_ids),
        racks=racks,
        ended_at=datetime(int(anno), int(mm), 15),
        distanza=distanza,
        race_to=race_to,
        multi_set=False,
        is_trio=is_trio,
        esclusione=esclusione,
    )


class TestMultiSet:
    """Regressione: la modalità dei set non dice se la partita usa i set."""

    def test_partita_a_set_singolo_non_e_multi_set(self):
        """Il bug originale marcava multi-set l'intero database.

        `effective_is_race_to_sets` vale `True` anche su una partita normale —
        dice *come* si conterebbero i set, non *se* ce ne siano. La fonte
        giusta è il value object `Distance` (ADR-027).
        """
        match = SimpleNamespace(
            distance_config=SimpleNamespace(is_multi_set=False),
            effective_is_race_to_sets=True,
        )
        assert censimento._e_multi_set(match) is False

    def test_partita_multi_set_e_riconosciuta(self):
        match = SimpleNamespace(distance_config=SimpleNamespace(is_multi_set=True))
        assert censimento._e_multi_set(match) is True

    def test_dato_storico_incompleto_non_fa_esplodere_il_censimento(self):
        """Un `distance_config` che solleva vale «non multi-set», non un crash."""

        class Rotto:
            @property
            def distance_config(self):
                raise ValueError("gara mancante")

        assert censimento._e_multi_set(Rotto()) is False


class TestFormatoDellaPartita:
    """Corsa a N o N rack esatti: la distinzione che lo script nascondeva."""

    def test_una_partita_a_rack_esatti_non_e_una_corsa(self):
        """Le gare fatte finora hanno quasi sempre distanza esatta.

        Lo script etichettava tutto «al N», il modo di dire delle corse, e il
        fatto strutturale piu' importante dei dati restava invisibile.
        """
        match = SimpleNamespace(distance_config=SimpleNamespace(is_race_to_racks=False))
        assert censimento._e_race_to(match) is False

    def test_le_due_distribuzioni_restano_separate(self):
        """Contarle insieme sommerebbe cose che producono rack diversi."""
        partite = [
            _partita([1, 2], race_to=False, distanza=5),
            _partita([1, 2], race_to=False, distanza=5),
            _partita([2, 3], race_to=True, distanza=7),
        ]
        dati = censimento._censimento(partite, "prova")

        assert dati["rack"]["distanze_esatte"] == {5: 2}
        assert dati["rack"]["distanze_a_corsa"] == {7: 1}

    def test_solo_i_rack_esatti_in_numero_pari_possono_finire_pari(self):
        """Una corsa non finisce mai in parita': si gioca finche' uno arriva."""
        partite = [
            _partita([1, 2], race_to=False, distanza=4),  # pari -> pareggiabile
            _partita([1, 2], race_to=False, distanza=5),  # dispari -> no
            _partita([2, 3], race_to=True, distanza=4),  # corsa -> no
        ]
        dati = censimento._censimento(partite, "prova")

        assert dati["rack"]["partite_pareggiabili"] == 1


class TestPercentili:
    def test_percentili_su_valori_noti(self):
        risultato = censimento._percentili(list(range(1, 101)), (25, 50, 75, 90))
        assert risultato == {"p25": 25, "p50": 50, "p75": 75, "p90": 90}

    def test_lista_vuota_non_solleva(self):
        assert censimento._percentili([], (50,)) == {"p50": 0}


class TestCensimento:
    def test_le_escluse_non_entrano_in_nessun_conteggio(self):
        partite: List[Any] = [
            _partita([1, 2], racks=9),
            _partita([3, 4], racks=9, esclusione="walkover"),
        ]
        dati = censimento._censimento(partite, "prova")

        assert dati["partite"]["totali"] == 2
        assert dati["partite"]["ammissibili"] == 1
        assert dati["partite"]["per_motivo"] == {"walkover": 1}
        assert dati["rack"]["totali"] == 9
        # I giocatori della partita esclusa non esistono per il censimento.
        assert dati["giocatori"]["totali"] == 2
        assert dati["grafo"]["nodi"] == 2

    def test_due_gruppi_che_non_si_incontrano_sono_due_componenti(self):
        """È la misura che può bocciare il rifit globale.

        Fra componenti diverse i rating non sono confrontabili: se il conteggio
        dicesse «una sola componente» si prenderebbe per buono un ordinamento
        che non ha fondamento nei dati.
        """
        partite = [
            _partita([1, 2]),
            _partita([2, 3]),
            _partita([10, 11]),
        ]
        dati = censimento._censimento(partite, "prova")

        assert dati["grafo"]["componenti"] == 2
        assert dati["grafo"]["dimensione_componenti"] == [3, 2]
        assert dati["grafo"]["giocatori_nella_maggiore"] == 3
        # 3 giocatori su 5, ma i rack si contano per giocatore coinvolto:
        # 2 partite × 2 giocatori × 10 rack = 40 su 60 totali. Il censimento
        # arrotonda a quattro decimali perché è un numero da leggere, non da
        # rimettere in un calcolo.
        assert dati["grafo"]["quota_rack_nella_maggiore"] == pytest.approx(
            40 / 60, abs=1e-4
        )

    def test_il_trio_collega_tutte_e_tre_le_coppie(self):
        """Nel trio il girone interno li fa incontrare tutti: tre archi, non due."""
        dati = censimento._censimento([_partita([1, 2, 3], is_trio=True)], "prova")

        assert dati["partite"]["trii"] == 1
        assert dati["grafo"]["coppie_distinte"] == 3
        assert dati["grafo"]["componenti"] == 1

    def test_le_finestre_mensili_contano_solo_i_mesi_popolati(self):
        soglia = censimento.MIN_PARTITE_PER_FINESTRA
        partite = [_partita([1, 2], mese="2026-01") for _ in range(soglia)]
        partite += [_partita([1, 2], mese="2026-02")]
        dati = censimento._censimento(partite, "prova")

        assert dati["tempo"]["mesi_coperti"] == 2
        assert dati["tempo"]["finestre_utili"] == ["2026-01"]

    def test_partite_senza_data_sono_segnalate_non_ignorate(self):
        """Una partita senza `ended_at` non sta in nessuna finestra temporale.

        Sono dati vecchi, e vanno contati esplicitamente: sparire in silenzio
        dal conteggio mensile le renderebbe invisibili proprio a chi deve
        decidere quante finestre di validazione esistono.
        """
        muta = _partita([1, 2])
        muta.ended_at = None
        dati = censimento._censimento([muta], "prova")

        assert dati["partite"]["senza_data_di_fine"] == 1
        assert dati["tempo"]["mesi_coperti"] == 0
        assert dati["rack"]["totali"] == 10
