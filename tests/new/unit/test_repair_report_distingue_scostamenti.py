"""Il report della riparazione separa le riscritture dai numeri sbagliati.

Senza questa distinzione il dry-run in produzione dichiarava «455 righe da
correggere» e dava l'impressione di uno storico pieno di errori. Non lo era:
quasi tutte quelle righe contenevano un numero **giusto**, scritto in una
casella che allora aveva un altro significato. La classifica mostrata a suo
tempo era corretta.

Le poche righe che invece contengono un numero non ricavabile dalle partite
sono quelle da guardare davvero, e vanno viste separate dalle altre.
"""

from __future__ import annotations

import importlib.util
import os

import pytest

_SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
    "scripts",
    "repair_round_classification_racks.py",
)


def _load_module():
    """Carica lo script per path: non è un package importabile."""
    spec = importlib.util.spec_from_file_location("repair_racks", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fix(old_racks_won, new_racks_won, old_difference, new_difference):
    module = _load_module()
    return module.RowFix(
        gara_id=1,
        gara_name="Gara",
        round_number=1,
        user_id=1,
        old_racks_won=old_racks_won,
        new_racks_won=new_racks_won,
        old_difference=old_difference,
        new_difference=new_difference,
    )


@pytest.mark.unit
class TestDistinzioneRiscritturaScostamento:

    def test_totale_nella_casella_della_differenza_e_una_riscrittura(self):
        """Il caso più comune: la casella conteneva il totale, ed era giusto.

        Prima della separazione, in una gara a triangoli il numero salvato era
        il totale (4). Oggi quel 4 va nella casella dei totali e la differenza
        vera (3) nell'altra. Il valore non era sbagliato.
        """
        fix = _fix(
            old_racks_won=None, new_racks_won=4, old_difference=4, new_difference=3
        )
        assert fix.is_discrepancy is False

    def test_totale_mancante_in_gara_a_vittorie_e_una_riscrittura(self):
        """La differenza era ed è giusta; il totale semplicemente non c'era."""
        fix = _fix(
            old_racks_won=None, new_racks_won=9, old_difference=3, new_difference=3
        )
        assert fix.is_discrepancy is False

    def test_totale_salvato_diverso_dal_ricalcolato_e_uno_scostamento(self):
        """Il caso di «Primo Open da Mimmo»: racks_won 3 → 4.

        Qui il totale esisteva già *come totale* e valeva 3, mentre le partite
        ne dicono 4. Nessuna convenzione lo spiega.
        """
        fix = _fix(old_racks_won=3, new_racks_won=4, old_difference=1, new_difference=1)
        assert fix.is_discrepancy is True

    def test_entrambi_i_numeri_fuori_posto_e_uno_scostamento(self):
        """Il caso di «3ª prova», turno 2: racks_won 2 → 3, differenza 1 → 0."""
        fix = _fix(old_racks_won=2, new_racks_won=3, old_difference=1, new_difference=0)
        assert fix.is_discrepancy is True

    def test_un_valore_che_coincide_con_l_altra_grandezza_non_e_scostamento(self):
        """Il criterio non presume quale convenzione fosse in vigore.

        È cambiata due volte (fix B14 sul calcolatore, poi la separazione delle
        colonne) e non è ricostruibile riga per riga. Basta che il numero
        salvato coincida con **uno dei due** valori ricalcolati.
        """
        fix = _fix(
            old_racks_won=None, new_racks_won=7, old_difference=7, new_difference=-1
        )
        assert fix.is_discrepancy is False

    def test_zero_non_e_confuso_con_assente(self):
        """Un totale salvato pari a 0 è un valore, non un'assenza."""
        fix = _fix(
            old_racks_won=0, new_racks_won=2, old_difference=-3, new_difference=-2
        )
        assert fix.is_discrepancy is True
