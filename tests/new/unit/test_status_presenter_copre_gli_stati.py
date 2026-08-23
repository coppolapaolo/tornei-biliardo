"""Nessuno stato deve cadere sul ripiego «Sconosciuto».

`StatusPresenter.match` mappava solo `PENDING` e `PLAYING`, cioè il percorso
dei match **di gara**. Le sfide individuali usano lo stesso enum ma passano da
`SCHEDULED` a `IN_PROGRESS`, e finiscono su `CANCELLED`: nessuno dei tre era
in tabella, quindi il pallino di stato di **ogni** sfida individuale diceva
«Sconosciuto».

Il test non elenca gli stati: li chiede all'enum. Un membro nuovo senza
etichetta lo fa fallire, che è l'unico modo perché il ripiego resti quello che
dovrebbe essere — una rete, non il comportamento normale.
"""

from models.status_enum import (
    DirectorRequestStatus,
    GaraStatus,
    MatchStatus,
    TournamentStatus,
)
from utils.status_ui import StatusPresenter


def _senza_etichetta(presenter, enum_class):
    return [
        stato.name for stato in enum_class if presenter(stato.value)[1] == "Sconosciuto"
    ]


class TestOgniStatoHaUnaEtichetta:
    def test_match(self, app):
        with app.test_request_context():
            assert _senza_etichetta(StatusPresenter.match, MatchStatus) == []

    def test_gara(self, app):
        with app.test_request_context():
            assert _senza_etichetta(StatusPresenter.gara, GaraStatus) == []

    def test_campionato(self, app):
        with app.test_request_context():
            assert _senza_etichetta(StatusPresenter.campionato, TournamentStatus) == []

    def test_richiesta_direttore(self, app):
        with app.test_request_context():
            assert (
                _senza_etichetta(
                    StatusPresenter.director_request, DirectorRequestStatus
                )
                == []
            )


def test_una_sfida_in_corso_non_dice_sconosciuto(app):
    """Il caso concreto visto a schermo il 2026-08-23."""
    with app.test_request_context():
        _, testo = StatusPresenter.match(MatchStatus.IN_PROGRESS.value)
        assert testo == "In Corso"
