"""La partita di altri due, tenuta da un istruttore o da un direttore (ADR-084).

Le regole del modello e della certificazione, senza database: chi segna non
firma per nessuno, ogni giocatore conferma o rifiuta per sé, il livello è per
giocatore e l'ELO per coppia.

``SPECIFICHE.md``, «Ciclo di vita dei Match» e «Livelli di certificazione»,
note del 2026-10-17; UC12 di ``docs/usecases/sfide-e-certificazione.md``.
"""

from __future__ import annotations

import pytest

from models.base import utc_now
from models.certificazione import (
    Livello,
    esito_dichiarato,
    livello_di_sfida,
    livello_di_sfida_per,
    sfida_conta_per_elo,
)
from models.exceptions import ConflictError, PermissionDeniedError
from models.individual_match.match_models import IndividualMatch
from models.status_enum import MatchStatus
from models.tpa.models import TpaReferto

A, B, MARCO = 1, 2, 3


def _di_un_terzo(
    dichiarata=True,
    p1=False,
    p2=False,
    r1=False,
    r2=False,
    status=MatchStatus.IN_PROGRESS,
    s1=3,
    s2=1,
):
    """Una partita «al 3» segnata da Marco, finita 3-1."""
    sfida = IndividualMatch(
        player1_id=A,
        player2_id=B,
        scorer_id=MARCO,
        status=status,
        player1_confirmed=p1,
        player2_confirmed=p2,
        player1_rejected_at=utc_now() if r1 else None,
        player2_rejected_at=utc_now() if r2 else None,
        player1_score=s1,
        player2_score=s2,
        distance=3,
        is_race_to=True,
    )
    sfida.tpa_referto = TpaReferto(
        compiler_id=MARCO,
        game_type=9,
        closed_at=utc_now() if dichiarata else None,
    )
    return sfida


class TestLivelloPerGiocatore:
    def test_non_ancora_dichiarata_non_ha_livello(self):
        """Chi segna sta ancora scrivendo: la partita non dice niente."""
        sfida = _di_un_terzo(dichiarata=False)
        assert livello_di_sfida_per(sfida, A) is None
        assert livello_di_sfida(sfida) is None

    def test_dichiarata_e_nessuno_ha_deciso_e_in_attesa_per_tutti_e_due(self):
        sfida = _di_un_terzo()
        assert livello_di_sfida_per(sfida, A) is Livello.IN_ATTESA
        assert livello_di_sfida_per(sfida, B) is Livello.IN_ATTESA

    def test_chi_conferma_la_vede_confermata_l_altro_in_attesa(self):
        sfida = _di_un_terzo(p1=True)
        assert livello_di_sfida_per(sfida, A) is Livello.CONFERMATA
        assert livello_di_sfida_per(sfida, B) is Livello.IN_ATTESA

    def test_chi_rifiuta_non_la_vede_chi_conferma_se_la_tiene(self):
        sfida = _di_un_terzo(p1=True, r2=True)
        assert livello_di_sfida_per(sfida, A) is Livello.CONFERMATA
        assert livello_di_sfida_per(sfida, B) is None

    def test_confermata_da_entrambi(self):
        sfida = _di_un_terzo(p1=True, p2=True, status=MatchStatus.CONFIRMED_BY_BOTH)
        assert livello_di_sfida_per(sfida, A) is Livello.CONFERMATA
        assert livello_di_sfida_per(sfida, B) is Livello.CONFERMATA

    def test_chi_segna_non_e_un_giocatore(self):
        assert livello_di_sfida_per(_di_un_terzo(p1=True), MARCO) is None

    def test_annullata_non_ha_livello(self):
        sfida = _di_un_terzo(status=MatchStatus.CANCELLED)
        assert livello_di_sfida_per(sfida, A) is None

    def test_la_sfida_normale_non_cambia(self):
        """Senza ``scorer_id`` la regola è quella di sempre (ADR-083)."""
        sfida = IndividualMatch(
            player1_id=A,
            player2_id=B,
            status=MatchStatus.IN_PROGRESS,
            player1_confirmed=True,
            player2_confirmed=False,
            player1_score=3,
            player2_score=1,
            distance=3,
            is_race_to=True,
        )
        assert livello_di_sfida_per(sfida, A) is Livello.IN_ATTESA
        assert livello_di_sfida_per(sfida, B) is Livello.IN_ATTESA


class TestEloPerCoppia:
    def test_dichiarata_senza_rifiuti_conta_per_tutte(self):
        sfida = _di_un_terzo()
        assert livello_di_sfida(sfida) is Livello.IN_ATTESA
        assert sfida_conta_per_elo(sfida) is True

    def test_confermata_da_entrambi_conta_per_confermate(self):
        sfida = _di_un_terzo(p1=True, p2=True, status=MatchStatus.CONFIRMED_BY_BOTH)
        sfida.winner_id = A
        assert livello_di_sfida(sfida) is Livello.CONFERMATA
        assert sfida_conta_per_elo(sfida) is True

    @pytest.mark.parametrize("p1,r2", [(True, True), (False, True)])
    def test_un_rifiuto_la_toglie_dall_elo_di_tutti_e_due(self, p1, r2):
        sfida = _di_un_terzo(p1=p1, r2=r2)
        assert livello_di_sfida(sfida) is None
        assert sfida_conta_per_elo(sfida) is False

    def test_l_esito_viene_dal_punteggio_anche_con_un_rifiuto(self):
        """A ha confermato, B rifiutato: per A resta una vittoria."""
        assert esito_dichiarato(_di_un_terzo(p1=True, r2=True)) == A


class TestDecisioniDeiGiocatori:
    def test_nessuno_aspetta_una_firma_sola(self):
        """La partita di un terzo non blocca nessuno e non si ritira."""
        sfida = _di_un_terzo(p1=True)
        assert sfida.awaiting_confirmation_from_id is None
        assert not sfida.signed_and_waiting(A)
        with pytest.raises(ConflictError):
            sfida.withdraw_by_signer(A)

    def test_aspetta_la_decisione_di_chi_non_ha_ancora_deciso(self):
        sfida = _di_un_terzo(p1=True)
        assert not sfida.awaits_decision_from(A)
        assert sfida.awaits_decision_from(B)
        assert not sfida.awaits_decision_from(MARCO)
        assert not _di_un_terzo(dichiarata=False).awaits_decision_from(A)

    def test_il_rifiuto_non_tocca_triangoli_ne_l_altro(self):
        sfida = _di_un_terzo(p1=True)
        sfida.reject_as_player(B)
        assert sfida.player2_rejected_at is not None
        assert (sfida.player1_score, sfida.player2_score) == (3, 1)
        assert sfida.player1_confirmed is True
        assert sfida.decision_of(B) == "rejected"
        assert sfida.decision_of(A) == "confirmed"

    def test_si_decide_una_volta_sola(self):
        sfida = _di_un_terzo(r1=True)
        with pytest.raises(ConflictError):
            sfida.confirm_as_player(A)
        with pytest.raises(ConflictError):
            sfida.reject_as_player(A)

    def test_prima_della_chiusura_del_referto_non_si_decide(self):
        sfida = _di_un_terzo(dichiarata=False)
        with pytest.raises(ConflictError):
            sfida.confirm_as_player(A)
        with pytest.raises(ConflictError):
            sfida.reject_as_player(A)

    def test_chi_segna_non_decide(self):
        with pytest.raises(PermissionDeniedError):
            _di_un_terzo().reject_as_player(MARCO)


class TestAnnullamentoDiChiSegna:
    def test_annulla_anche_a_triangoli_segnati(self):
        sfida = _di_un_terzo(dichiarata=False)
        sfida.cancel_by_scorer(MARCO)
        assert sfida.status == MatchStatus.CANCELLED

    def test_dopo_una_conferma_non_annulla_piu(self):
        sfida = _di_un_terzo(p1=True)
        with pytest.raises(ConflictError):
            sfida.cancel_by_scorer(MARCO)

    def test_solo_chi_segna(self):
        with pytest.raises(PermissionDeniedError):
            _di_un_terzo().cancel_by_scorer(A)


def test_chi_segna_scrive_video_e_descrizione():
    sfida = _di_un_terzo()
    assert sfida.can_edit_info(MARCO)
    assert sfida.can_edit_info(A)
    assert not sfida.can_edit_info(99)
