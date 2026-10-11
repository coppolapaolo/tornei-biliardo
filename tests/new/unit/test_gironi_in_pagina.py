"""Le classifiche per girone delle pagine della gara (ADR-076).

Le righe di classifica di una gara a gironi sono nell'ordine della gara
(prima i primi, poi i secondi) e portano girone e posizione nel girone.
Mentre si gioca le pagine ne fanno una tabella per girone; a gara finita
mostrano la gara intera, con «1º girone A» accanto al nome. Col girone unico
non cambia niente: è il presidio che la pagina di sempre resti com'è.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from models.classification.gironi_in_pagina import (
    dividi_per_girone,
    girone_della_riga,
    gironi_in_pagina,
)
from models.competition.schermo_sala import _gironi_sala, _righe
from models.status_enum import GaraStatus

pytestmark = pytest.mark.unit


def _riga(user_id, position, group_index=None, group_position=None):
    return SimpleNamespace(
        user_id=user_id,
        position=position,
        group_index=group_index,
        group_position=group_position,
        round_number=None,
        gara_id=None,
        user=SimpleNamespace(username=f"g{user_id}", is_deleted=False),
        is_rack_ranking=False,
        is_points_ranking=False,
        matches_won=3,
        ranking_rack_value=2,
        points=None,
        racks_won=None,
        rack_difference=None,
    )


# Sei giocatori in due gironi, nell'ordine della gara: 1ºA, 1ºB, 2ºB, 2ºA,
# 3ºA, 3ºB.
_RIGHE = [
    _riga(1, 1, 0, 1),
    _riga(2, 2, 1, 1),
    _riga(3, 3, 1, 2),
    _riga(4, 4, 0, 2),
    _riga(5, 5, 0, 3),
    _riga(6, 6, 1, 3),
]


class TestDividiPerGirone:
    def test_una_tabella_per_girone_nell_ordine_del_girone(self):
        gironi = dividi_per_girone(_RIGHE)
        assert [g.nome for g in gironi] == ["A", "B"]
        assert [v.riga.user_id for v in gironi[0].righe] == [1, 4, 5]
        assert [v.riga.user_id for v in gironi[1].righe] == [2, 3, 6]
        assert [v.posizione for v in gironi[1].righe] == [1, 2, 3]

    def test_la_freccia_guarda_la_posizione_nel_girone_prima(self):
        gironi = dividi_per_girone(_RIGHE, {4: 1, 1: 2})
        assert [v.precedente for v in gironi[0].righe] == [2, 1, None]

    def test_i_pari_merito_nel_girone_condividono_la_posizione(self):
        righe = [_riga(1, 1, 0, 1), _riga(2, 1, 1, 1), _riga(3, 3, 0, 1)]
        gironi = dividi_per_girone(righe)
        assert [v.posizione for v in gironi[0].righe] == [1, 1]

    def test_girone_unico_nessuna_divisione(self):
        """Le righe del girone di sempre non hanno girone: tutto com'era."""
        assert dividi_per_girone([_riga(1, 1), _riga(2, 2)]) == []

    def test_un_solo_girone_distinto_nessuna_divisione(self):
        assert dividi_per_girone([_riga(1, 1, 0, 1), _riga(2, 2, 0, 2)]) == []

    def test_una_riga_senza_girone_tiene_la_classifica_intera(self):
        """Nessuno sparisce dalla pagina: meglio la tabella unica."""
        assert dividi_per_girone(_RIGHE + [_riga(7, 7)]) == []


class TestQuandoSiMostranoIGironi:
    def test_mentre_si_gioca_una_tabella_per_girone(self):
        gara = SimpleNamespace(status=GaraStatus.PLAYING.value)
        assert [g.nome for g in gironi_in_pagina(gara, _RIGHE)] == ["A", "B"]

    @pytest.mark.parametrize(
        "stato", [GaraStatus.AWAITING_SSR.value, GaraStatus.COMPLETED.value]
    )
    def test_a_gara_finita_la_classifica_della_gara(self, stato):
        """Lo spareggio e la classifica finale guardano la posizione nella gara."""
        assert gironi_in_pagina(SimpleNamespace(status=stato), _RIGHE) == []

    def test_accanto_al_nome_girone_e_posizione_nel_girone(self):
        assert girone_della_riga(_RIGHE[2]) == ("B", 2)
        assert girone_della_riga(_riga(1, 1)) is None


class TestSchermoInSala:
    def test_una_classifica_per_girone_mentre_si_gioca(self):
        gara = SimpleNamespace(status=GaraStatus.PLAYING.value)
        gironi = _gironi_sala(gara, _RIGHE, False)
        assert [g.nome for g in gironi] == ["A", "B"]
        assert [(r.posizione, r.nome) for r in gironi[0].righe] == [
            (1, "g1"),
            (2, "g4"),
            (3, "g5"),
        ]

    def test_a_gara_finita_la_riga_dice_da_che_girone_viene(self):
        gara = SimpleNamespace(status=GaraStatus.COMPLETED.value)
        assert _gironi_sala(gara, _RIGHE, False) == ()
        righe, _rack = _righe(_RIGHE)
        assert righe[1].girone == ("B", 1)

    def test_girone_unico_come_sempre(self):
        gara = SimpleNamespace(status=GaraStatus.PLAYING.value)
        righe = [_riga(1, 1), _riga(2, 2)]
        assert _gironi_sala(gara, righe, False) == ()
        assert all(r.girone is None for r in _righe(righe)[0])
