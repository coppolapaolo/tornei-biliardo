"""La partita di altri due, tenuta da un istruttore o da un direttore (ADR-084).

Le regole del modello e della certificazione, senza database: chi segna non
firma per nessuno, ogni giocatore conferma o rifiuta, il livello è per
giocatore e l'ELO per coppia. Un rifiuto basta: la partita è rifiutata per
tutti e due, e chi l'ha segnata la corregge o la cancella.

``SPECIFICHE.md``, «Ciclo di vita dei Match» e «Livelli di certificazione»,
note del 2026-10-17 e del 2026-10-18; UC12 di
``docs/usecases/sfide-e-certificazione.md``.
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

    def test_rifiutata_non_ha_livello_per_nessuno_dei_due(self):
        """Regola del 2026-10-18: con un rifiuto la partita esce anche per chi
        l'aveva confermata."""
        sfida = _di_un_terzo(p1=True)
        sfida.reject_as_player(B)
        assert livello_di_sfida_per(sfida, A) is None
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

    @pytest.mark.parametrize("p1", [True, False])
    def test_un_rifiuto_la_toglie_dall_elo_di_tutti_e_due(self, p1):
        sfida = _di_un_terzo(p1=p1)
        sfida.reject_as_player(B)
        assert livello_di_sfida(sfida) is None
        assert sfida_conta_per_elo(sfida) is False

    def test_l_esito_dichiarato_viene_dal_punteggio(self):
        """A ha confermato, B non ha ancora deciso: per A è una vittoria."""
        assert esito_dichiarato(_di_un_terzo(p1=True)) == A


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

    def test_un_rifiuto_dopo_una_conferma_rifiuta_la_partita(self):
        """Il rifiuto vale per tutti e due e non tocca i triangoli: chi segna
        li corregge, se c'è da correggere."""
        sfida = _di_un_terzo(p1=True)
        sfida.reject_as_player(B)
        assert sfida.status == MatchStatus.REJECTED
        assert sfida.is_rejected
        assert sfida.player2_rejected_at is not None
        assert (sfida.player1_score, sfida.player2_score) == (3, 1)
        assert sfida.decision_of(B) == "rejected"
        assert not sfida.awaits_decision_from(A)
        assert not sfida.awaits_decision_from(B)

    def test_un_rifiuto_prima_della_conferma_chiude_le_decisioni(self):
        """Rifiutata da A, B non ha più niente da confermare."""
        sfida = _di_un_terzo()
        sfida.reject_as_player(A)
        assert sfida.status == MatchStatus.REJECTED
        with pytest.raises(ConflictError):
            sfida.confirm_as_player(B)
        with pytest.raises(ConflictError):
            sfida.reject_as_player(B)

    def test_si_decide_una_volta_sola(self):
        sfida = _di_un_terzo(p1=True)
        with pytest.raises(ConflictError):
            sfida.confirm_as_player(A)
        with pytest.raises(ConflictError):
            sfida.reject_as_player(A)

    def test_la_rifiutata_non_compare_ai_giocatori_ma_a_chi_segna(self):
        sfida = _di_un_terzo()
        assert not sfida.is_hidden_from(A)
        sfida.reject_as_player(A)
        assert sfida.is_hidden_from(A)
        assert sfida.is_hidden_from(B)
        assert not sfida.is_hidden_from(MARCO)

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

    def test_la_rifiutata_si_cancella_anche_dopo_una_conferma(self):
        sfida = _di_un_terzo(p1=True)
        sfida.reject_as_player(B)
        sfida.cancel_by_scorer(MARCO)
        assert sfida.status == MatchStatus.CANCELLED


class TestCorrezioneDiChiSegna:
    def test_la_correzione_riapre_il_referto_e_azzera_le_decisioni(self):
        sfida = _di_un_terzo(p1=True)
        sfida.reject_as_player(B)
        sfida.reopen_by_scorer(MARCO)

        assert sfida.status == MatchStatus.IN_PROGRESS
        assert not sfida.is_declared_by_scorer
        assert sfida.tpa_referto.closed_at is None
        assert not sfida.player1_confirmed and not sfida.player2_confirmed
        assert sfida.player1_confirmed_at is None
        assert sfida.player1_rejected_at is None
        assert sfida.player2_rejected_at is None
        assert sfida.decision_of(A) is None and sfida.decision_of(B) is None

    def test_la_corregge_solo_chi_segna(self):
        sfida = _di_un_terzo()
        sfida.reject_as_player(B)
        for chi in (A, B, 99):
            with pytest.raises(PermissionDeniedError):
                sfida.reopen_by_scorer(chi)

    def test_si_corregge_solo_una_partita_rifiutata(self):
        for sfida in (
            _di_un_terzo(),
            _di_un_terzo(dichiarata=False),
            _di_un_terzo(p1=True, p2=True, status=MatchStatus.CONFIRMED_BY_BOTH),
            _di_un_terzo(status=MatchStatus.CANCELLED),
        ):
            with pytest.raises(ConflictError):
                sfida.reopen_by_scorer(MARCO)


class TestChiPuoSegnare:
    """«admin non dovrebbe segnare partite» (2026-10-18): l'admin non gioca e
    non segna, nemmeno con il ruolo di istruttore concesso."""

    class _Utente:
        is_authenticated = True

        def __init__(self, admin=False, director=False, instructor=False):
            self.is_admin = admin
            self.is_director = director
            self.is_instructor = instructor

    def test_istruttori_e_direttori_segnano(self):
        from models.individual_match.scored_match_service import ScoredMatchService

        assert ScoredMatchService.can_score(self._Utente(instructor=True))
        assert ScoredMatchService.can_score(self._Utente(director=True))
        assert not ScoredMatchService.can_score(self._Utente())
        assert not ScoredMatchService.can_score(None)

    def test_l_admin_non_segna(self):
        from models.individual_match.scored_match_service import ScoredMatchService

        assert not ScoredMatchService.can_score(self._Utente(admin=True))
        assert not ScoredMatchService.can_score(
            self._Utente(admin=True, instructor=True)
        )


def test_chi_segna_scrive_video_e_descrizione():
    sfida = _di_un_terzo()
    assert sfida.can_edit_info(MARCO)
    assert sfida.can_edit_info(A)
    assert not sfida.can_edit_info(99)
