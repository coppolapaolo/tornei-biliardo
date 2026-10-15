"""Il pari merito si mostra alla posizione più alta (2026-10-11).

Regola dell'utente: «Il pari merito va sempre sulla posizione più alta. Se uno
è pari merito col primo allora è primo pari merito, non secondo.»

Pari merito = uguali su tutti i criteri veri della catena. Il **sorteggio**
ordina le righe e decide dove serve un taglio, ma non toglie il pari merito
nella posizione mostrata: due giocatori separati solo dal sorteggio hanno
posizione 1 e 2 (quella che decide) e sono mostrati entrambi al 1° posto.

Una sola definizione: `ordinamento.posizioni_mostrate`, applicata dal motore
(`Fascia.posizione_mostrata`) e da chi riordina una classifica già fatta.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from models.classification.gironi import Giocate, ordina_a_gironi
from models.classification.gironi_in_pagina import dividi_per_girone
from models.classification.models import (
    posizione_mostrata,
    posizione_mostrata_nel_girone,
    posizione_mostrata_prima,
)
from models.competition.schermo_sala import _gironi_sala
from models.competition.schermo_sala import _righe as righe_sala
from models.status_enum import GaraStatus
from models.classification.ordinamento import (
    Concorrente,
    Criterio,
    Scontro,
    Voce,
    ordina,
    posizioni_mostrate,
)

pytestmark = pytest.mark.unit

V = Voce
SORTEGGIO = V(Criterio.SORTEGGIO)
DIFF = V(Criterio.DIFFERENZA_RACK)
PREC = V(Criterio.POSIZIONE_PRECEDENTE)


def _c(pid, **kw) -> Concorrente:
    kw.setdefault("sorteggio", pid)
    return Concorrente(player_id=pid, **kw)


def _righe(fasce):
    return [
        (g.player_id, f.posizione, f.posizione_mostrata)
        for f in fasce
        for g in f.giocatori
    ]


class TestLaFunzioneUnica:
    def test_chi_ha_lo_stesso_merito_del_precedente_ne_prende_la_posizione(self):
        assert posizioni_mostrate([(1, "a"), (2, "a"), (3, "b"), (4, "c")]) == [
            1,
            1,
            3,
            4,
        ]

    def test_tre_pari_in_mezzo(self):
        assert posizioni_mostrate([(1, 0), (2, 1), (3, 1), (4, 1), (5, 2)]) == [
            1,
            2,
            2,
            2,
            5,
        ]

    def test_le_posizioni_gia_condivise_restano(self):
        """1, 2, 2, 4 della classifica di gara: già il pari merito di sempre."""
        assert posizioni_mostrate([(1, 0), (2, 1), (2, 1), (4, 2)]) == [1, 2, 2, 4]

    def test_lo_stesso_merito_non_adiacente_non_unisce(self):
        """Il pari merito è fra righe vicine: chi è stato separato resta separato."""
        assert posizioni_mostrate([(1, "a"), (2, "b"), (3, "a")]) == [1, 2, 3]

    def test_vuota(self):
        assert posizioni_mostrate([]) == []


class TestIlMotore:
    def test_il_sorteggio_ordina_ma_non_toglie_il_pari_merito(self):
        """Il caso della tessera: 2 vinte e +6 entrambi, decide il sorteggio."""
        fasce = ordina(
            [
                _c(1, vittorie=2, differenza_rack=6, sorteggio=9),
                _c(2, vittorie=2, differenza_rack=6, sorteggio=1),
                _c(3, vittorie=1),
            ],
            Criterio.VITTORIE,
            (DIFF, SORTEGGIO),
        )
        assert _righe(fasce) == [(2, 1, 1), (1, 2, 1), (3, 3, 3)]

    def test_completa_aggiunge_il_sorteggio_e_il_pari_merito_resta(self):
        fasce = ordina(
            [_c(1, vittorie=1), _c(2, vittorie=1), _c(3, vittorie=1)],
            Criterio.VITTORIE,
            (),
            completa=True,
        )
        assert [m for _p, _pos, m in _righe(fasce)] == [1, 1, 1]
        assert [pos for _p, pos, _m in _righe(fasce)] == [1, 2, 3]

    def test_un_criterio_vero_separa_davvero(self):
        """La posizione al turno precedente è un criterio della catena, non un caso."""
        fasce = ordina(
            [
                _c(1, vittorie=2, posizione_precedente=3),
                _c(2, vittorie=2, posizione_precedente=1),
            ],
            Criterio.VITTORIE,
            (PREC, SORTEGGIO),
        )
        assert _righe(fasce) == [(2, 1, 1), (1, 2, 2)]

    def test_senza_sorteggio_la_posizione_mostrata_e_la_posizione(self):
        fasce = ordina(
            [_c(1, vittorie=1), _c(2, vittorie=1), _c(3, vittorie=0)],
            Criterio.VITTORIE,
            (),
        )
        assert _righe(fasce) == [(1, 1, 1), (2, 1, 1), (3, 3, 3)]

    def test_pari_in_mezzo_alla_classifica(self):
        fasce = ordina(
            [
                _c(1, vittorie=3),
                _c(2, vittorie=2),
                _c(3, vittorie=2),
                _c(4, vittorie=2),
                _c(5, vittorie=0),
            ],
            Criterio.VITTORIE,
            (DIFF, SORTEGGIO),
        )
        assert [m for _p, _pos, m in _righe(fasce)] == [1, 2, 2, 2, 5]

    def test_lo_scontro_diretto_non_crea_pari_merito_falsi(self):
        """Topologico: A ha battuto C, A e B pari sul resto, C meglio di B.

        Col sorteggio l'ordine è A, C, B; senza, A e B sono una fascia sola.
        A e B non sono vicini: nessuno dei tre è mostrato a pari merito.
        """
        fasce = ordina(
            [
                _c(1, vittorie=2, differenza_rack=0, sorteggio=1),
                _c(2, vittorie=2, differenza_rack=0, sorteggio=2),
                _c(3, vittorie=2, differenza_rack=5, sorteggio=3),
            ],
            Criterio.VITTORIE,
            (V(Criterio.SCONTRI_DIRETTI), DIFF, SORTEGGIO),
            scontri=[Scontro(1, 3, 3, 1, vincitore=1)],
        )
        ordine = [p for p, _pos, _m in _righe(fasce)]
        mostrate = [m for _p, _pos, m in _righe(fasce)]
        assert len(set(mostrate)) == len(mostrate)
        assert ordine[0] == 1

    def test_da_posizione(self):
        fasce = ordina(
            [_c(1, vittorie=1), _c(2, vittorie=1)],
            Criterio.VITTORIE,
            (SORTEGGIO,),
            da_posizione=5,
        )
        assert [m for _p, _pos, m in _righe(fasce)] == [5, 5]


class TestIGironi:
    def test_nel_girone_il_sorteggio_non_toglie_il_pari_merito(self):
        concorrenti = [
            _c(1, vittorie=2, differenza_rack=6, sorteggio=9),
            _c(2, vittorie=2, differenza_rack=6, sorteggio=1),
            _c(3, vittorie=0),
            _c(4, vittorie=1),
        ]
        esito = ordina_a_gironi(
            concorrenti,
            {1: 0, 2: 0, 3: 0, 4: 1},
            {pid: Giocate(partite=2) for pid in (1, 2, 3, 4)},
            Criterio.VITTORIE,
            (DIFF, SORTEGGIO),
        )
        assert esito.posizione_nel_girone[2] == 1
        assert esito.posizione_nel_girone[1] == 2
        assert esito.mostrata_nel_girone == {2: 1, 1: 1, 3: 3, 4: 1}


def _riga(
    user_id,
    position,
    shown=None,
    group_index=None,
    group_position=None,
    shown_group=None,
    previous=None,
    shown_previous=None,
):
    return SimpleNamespace(
        user_id=user_id,
        position=position,
        shown_position=shown,
        group_index=group_index,
        group_position=group_position,
        shown_group_position=shown_group,
        previous_position=previous,
        shown_previous_position=shown_previous,
        round_number=None,
        gara_id=None,
        user=SimpleNamespace(username=f"g{user_id}", is_deleted=False),
        is_rack_ranking=False,
        is_points_ranking=False,
        matches_won=2,
        ranking_rack_value=6,
        points=None,
        racks_won=None,
        rack_difference=None,
    )


class TestLeRighe:
    def test_la_riga_scritta_prima_ripiega_sulla_posizione(self):
        vecchia = _riga(1, 2, group_index=0, group_position=2, previous=3)
        assert posizione_mostrata(vecchia) == 2
        assert posizione_mostrata_nel_girone(vecchia) == 2
        assert posizione_mostrata_prima(vecchia) == 3

    def test_la_riga_nuova_dice_la_posizione_mostrata(self):
        nuova = _riga(1, 2, 1, 0, 2, 1, previous=3, shown_previous=2)
        assert posizione_mostrata(nuova) == 1
        assert posizione_mostrata_nel_girone(nuova) == 1
        assert posizione_mostrata_prima(nuova) == 2


class TestLePagine:
    def test_nel_girone_i_pari_merito_mostrano_la_posizione_piu_alta(self):
        righe = [
            _riga(1, 1, 1, 0, 1, 1),
            _riga(2, 2, 1, 1, 1, 1),
            _riga(3, 3, 2, 0, 2, 1),
            _riga(4, 4, 4, 1, 2, 2),
        ]
        gironi = dividi_per_girone(righe)
        assert [v.posizione for v in gironi[0].righe] == [1, 1]
        assert [v.posizione for v in gironi[1].righe] == [1, 2]

    def test_la_freccia_del_girone_guarda_la_posizione_mostrata_prima(self):
        """Il turno prima erano entrambi primi a pari merito: nessuno è salito."""
        righe = [
            _riga(1, 1, 1, 0, 1, 1),
            _riga(2, 2, 1, 1, 1, 1),
            _riga(3, 3, 2, 0, 2, 1),
        ]
        gironi = dividi_per_girone(righe, {1: 1, 3: 1})
        assert [v.posizione - v.precedente for v in gironi[0].righe] == [0, 0]

    def test_lo_schermo_in_sala_mostra_la_posizione_piu_alta(self):
        righe, _rack = righe_sala([_riga(1, 1, 1), _riga(2, 2, 1), _riga(3, 3, 3)])
        assert [r.posizione for r in righe] == [1, 1, 3]

    def test_lo_schermo_in_sala_nei_gironi(self):
        gara = SimpleNamespace(status=GaraStatus.PLAYING.value)
        righe = [
            _riga(1, 1, 1, 0, 1, 1),
            _riga(2, 2, 1, 1, 1, 1),
            _riga(3, 3, 2, 0, 2, 1),
            _riga(4, 4, 4, 1, 2, 2),
        ]
        gironi = _gironi_sala(gara, righe, False)
        assert [r.posizione for r in gironi[0].righe] == [1, 1]


def _totali(**per_giocatore):
    return {
        int(pid[1:]): {
            "total_matches_won": vinte,
            "total_racks_won": 0,
            "total_rack_difference": diff,
            "total_points": 0,
            "total_spot_shot_wins": 0,
        }
        for pid, (vinte, diff) in per_giocatore.items()
    }


class TestLaClassificaGenerale:
    """Nel campionato l'ordine è completo (inviti ai playoff), il pari merito
    si mostra."""

    def test_l_ordine_resta_completo_e_il_pari_merito_si_mostra(self, db_session):
        from models.campionato.statistics_service import TournamentStatisticsService
        from models.status_enum import ClassificationSystem

        mostrate: dict = {}
        ordine = TournamentStatisticsService()._sort_and_rank_players(
            _totali(g1=(2, 4), g2=(2, 4), g3=(1, 0)),
            ClassificationSystem.WINS,
            mostrate=mostrate,
        )
        assert [pos for pos, _uid in ordine] == [1, 2, 3]
        assert sorted(mostrate.values()) == [1, 1, 3]
        assert mostrate[3] == 3

    def test_il_playoff_che_riordina_separa_i_suoi(self, db_session, monkeypatch):
        """Chi ha giocato il playoff ha il merito della finale; fra gli altri
        resta quello del campionato. Qui la finale li ha separati (due
        finali, un giocatore ciascuna); il pari merito *in* finale lo copre
        `test_classifica_decisa_dai_playoff_in_pagina.py`."""
        from types import SimpleNamespace

        from models.campionato.statistics_service import TournamentStatisticsService
        from models.classification.campionato_classification import (
            ClassificationService,
        )

        def _riga(uid):
            return SimpleNamespace(user_id=uid, posizione_mostrata=1)

        monkeypatch.setattr(
            ClassificationService,
            "playoff_finali",
            staticmethod(lambda campionato: [(None, [_riga(2)]), (None, [_riga(1)])]),
        )
        # Prima del playoff: 1 e 2 pari merito al 1°, 3 e 4 pari merito al 3°.
        mostrate = {1: 1, 2: 1, 3: 3, 4: 3}
        dopo = [(1, 2), (2, 1), (3, 3), (4, 4)]
        assert TournamentStatisticsService._mostrate_dopo_il_playoff(
            None, dopo, mostrate
        ) == {2: 1, 1: 2, 3: 3, 4: 3}
