"""Tavoli passati come stringa JSON: lo scrittore normalizza, il lettore tollera.

Una gara di prova creata da uno script passava `available_tables` come
stringa JSON (`'["1", "2"]'`) invece che come lista. Il setter la codificava
una seconda volta, il getter la decodificava una volta sola e restituiva una
stringa: i tavoli comparivano come caratteri singoli — «[», «"», «,».

Dall'app non succede (i moduli passano sempre una lista, via
`parse_tables_input`), ma il contratto non lo difendeva nessuno. Ora:

* il setter accetta una lista, `None`/vuoto o una stringa che *è* una lista
  JSON (decodificata); rifiuta tutto il resto con un `TypeError`;
* il getter, se dopo la prima decodifica trova ancora una stringa che è una
  lista JSON, la decodifica di nuovo: tollera i dati già scritti due volte.

Stesso schema per `Gara.available_tables` e `BilliardHall.table_names`.
"""

import json

import pytest

from models.competition.models import Gara
from models.location.models import BilliardHall


def _gara() -> Gara:
    return Gara(name="Tavoli", number=1)


def _sala() -> BilliardHall:
    return BilliardHall(name="Sala")


# --- Gara.available_tables ------------------------------------------------


class TestSetterGara:
    def test_lista_resta_lista(self):
        gara = _gara()
        gara.set_available_tables(["1", "2"])
        assert json.loads(gara.available_tables) == ["1", "2"]

    def test_stringa_json_decodificata_non_ricodificata(self):
        gara = _gara()
        gara.set_available_tables('["1", "2"]')
        assert gara.available_tables == '["1", "2"]'
        assert gara.get_available_tables() == ["1", "2"]

    def test_numeri_diventano_nomi(self):
        gara = _gara()
        gara.set_available_tables([1, 2])
        assert gara.get_available_tables() == ["1", "2"]

    @pytest.mark.parametrize("vuoto", [None, [], "", "[]", "  "])
    def test_vuoto_azzera(self, vuoto):
        gara = _gara()
        gara.available_tables = '["9"]'
        gara.set_available_tables(vuoto)
        assert gara.available_tables is None

    @pytest.mark.parametrize("sbagliato", ["1, 2", '{"a": 1}', 3, {"a": 1}, [["1"]]])
    def test_il_resto_e_rifiutato(self, sbagliato):
        gara = _gara()
        with pytest.raises(TypeError):
            gara.set_available_tables(sbagliato)


class TestGetterGara:
    def test_dato_scritto_due_volte_si_legge(self):
        gara = _gara()
        gara.available_tables = json.dumps(json.dumps(["1", "2"]))
        assert gara.get_available_tables() == ["1", "2"]

    def test_json_non_lista_non_diventa_caratteri(self):
        gara = _gara()
        gara.available_tables = json.dumps("abc")
        assert gara.get_available_tables() == []

    def test_json_rotto_lista_vuota(self):
        gara = _gara()
        gara.available_tables = "[non json"
        assert gara.get_available_tables() == []


# --- BilliardHall.table_names --------------------------------------------


class TestSetterSala:
    def test_lista_resta_lista(self):
        sala = _sala()
        sala.set_table_names(["A", "B"])
        assert json.loads(sala.table_names) == ["A", "B"]

    def test_stringa_json_decodificata_non_ricodificata(self):
        sala = _sala()
        sala.set_table_names('["A", "B"]')
        assert sala.get_table_names() == ["A", "B"]

    @pytest.mark.parametrize("vuoto", [None, [], "", "[]"])
    def test_vuoto_azzera(self, vuoto):
        sala = _sala()
        sala.table_names = '["9"]'
        sala.set_table_names(vuoto)
        assert sala.table_names is None

    @pytest.mark.parametrize("sbagliato", ["A, B", 3, {"a": 1}])
    def test_il_resto_e_rifiutato(self, sbagliato):
        sala = _sala()
        with pytest.raises(TypeError):
            sala.set_table_names(sbagliato)


class TestGetterSala:
    def test_dato_scritto_due_volte_si_legge(self):
        sala = _sala()
        sala.table_names = json.dumps(json.dumps(["A", "B"]))
        assert sala.get_table_names() == ["A", "B"]

    def test_json_non_lista_ripiega_sul_numero_di_tavoli(self):
        sala = _sala()
        sala.table_names = json.dumps("abc")
        sala.number_of_tables = 2
        assert sala.get_table_names() == ["1", "2"]
