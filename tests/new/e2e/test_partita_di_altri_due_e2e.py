"""La partita di altri due, dal punto di vista di chi segna e di chi gioca.

UC12 di ``docs/usecases/sfide-e-certificazione.md`` (ADR-084). Solo route,
come il resto delle e2e delle sfide: prima cosa mostra la pagina, poi cosa
dice il DB.

Il giunto delicato è quello fra il referto e le firme: col referto di un
terzo nessuno firma d'ufficio, e le pagine dei due giocatori non devono
offrire né il segnapunti né «Continua», ma, a referto chiuso, conferma e
rifiuto per sé.
"""

from __future__ import annotations

import re

import pytest

from models.certificazione import livello_di_sfida_per
from models.individual_match.models import IndividualMatch
from models.status_enum import MatchStatus
from sfida_driver import SfidaDriver

DESCRIZIONE = "Finale 1ª giornata, serie C FVG"


def _tasti_segnapunti(pagina: str) -> list[str]:
    return re.findall(r"<button[^>]*c7-rackpad__btn[^>]*>", pagina)


def _ultima_partita_segnata_da(scorer_id: int) -> int:
    partita = (
        IndividualMatch.query.filter_by(scorer_id=scorer_id)
        .order_by(IndividualMatch.id.desc())
        .first()
    )
    assert partita is not None, "la partita di altri due non è nata"
    return partita.id


@pytest.mark.e2e
class TestLaFinaleSegnataDaMarco:
    def test_marco_segna_paolo_conferma_pietro_rifiuta(self, sfida: SfidaDriver):
        marco = sfida.crea_istruttore()
        paolo, pietro = sfida.crea_giocatori(2)

        # Marco vede la voce e crea la partita: si arriva dritti al referto.
        sfida.entra(marco)
        assert "Segna la partita di altri due" in sfida.pagina_sfide()
        risposta = sfida.segna_partita_di_altri(paolo, pietro, description=DESCRIZIONE)
        assert risposta.status_code == 302
        match_id = _ultima_partita_segnata_da(marco.id)
        assert risposta.headers["Location"].endswith(f"/match/matches/{match_id}/tpa")
        assert sfida.referto(match_id).compiler_id == marco.id

        # Paolo la vede fra le sue sfide, senza segnapunti e senza «Continua».
        sfida.esci()
        sfida.entra(paolo)
        pagina = sfida.pagina(match_id)
        assert _tasti_segnapunti(pagina) == []
        assert DESCRIZIONE in pagina
        assert "Continua" not in sfida.pagina_sfide()
        assert sfida.premi(match_id, "seat:1").status_code == 403

        # Marco porta la partita alla distanza: nessuno firma d'ufficio.
        sfida.esci()
        sfida.entra(marco)
        for _ in range(3):
            sfida.vinci_rack_nel_referto(match_id, posto=1)
        partita = sfida.partita(match_id)
        assert (partita.player1_score, partita.player2_score) == (3, 0)
        assert not partita.player1_confirmed and not partita.player2_confirmed
        sfida.chiudi_referto(match_id)
        assert sfida.referto(match_id).is_closed

        # Tutti e due ricevono l'avviso, con la descrizione.
        for giocatore in (paolo, pietro):
            assert any(
                DESCRIZIONE in (n.message or "") for n in sfida.notifiche(giocatore)
            )

        # Paolo conferma dalla sua pagina.
        sfida.esci()
        sfida.entra(paolo)
        assert f"/match/matches/{match_id}/confirm" in sfida.pagina(match_id)
        sfida.client.post(f"/match/matches/{match_id}/confirm")

        # Pietro rifiuta: vale il rifiuto, per tutti e due (2026-10-18).
        sfida.esci()
        sfida.entra(pietro)
        sfida.client.post(f"/match/matches/{match_id}/reject")
        assert f"/match/matches/{match_id}" not in sfida.pagina_sfide()

        partita = sfida.partita(match_id)
        assert partita.status == MatchStatus.REJECTED
        assert (partita.player1_score, partita.player2_score) == (3, 0)
        assert livello_di_sfida_per(partita, paolo.id) is None
        assert livello_di_sfida_per(partita, pietro.id) is None

        # Paolo, che l'aveva confermata, non la vede più e riceve un avviso.
        sfida.esci()
        sfida.entra(paolo)
        assert f"/match/matches/{match_id}" not in sfida.pagina_sfide()
        assert f"/match/matches/{match_id}" not in sfida.pagina_elenco()
        assert any(
            DESCRIZIONE in (n.message or "") and pietro.username in (n.message or "")
            for n in sfida.notifiche(paolo)
        )

        # Marco la vede rifiutata, con la correzione e la cancellazione.
        sfida.esci()
        sfida.entra(marco)
        assert "Rifiutata" in sfida.pagina_sfide()
        pagina = sfida.pagina(match_id)
        assert f"/match/matches/{match_id}/reopen" in pagina
        assert f"/match/matches/{match_id}/cancel" in pagina

    def test_marco_corregge_la_rifiutata_e_i_due_confermano(self, sfida: SfidaDriver):
        marco = sfida.crea_istruttore()
        paolo, pietro = sfida.crea_giocatori(2)
        sfida.entra(marco)
        sfida.segna_partita_di_altri(paolo, pietro, description=DESCRIZIONE)
        match_id = _ultima_partita_segnata_da(marco.id)
        for _ in range(3):
            sfida.vinci_rack_nel_referto(match_id, posto=1)
        sfida.chiudi_referto(match_id)

        sfida.esci()
        sfida.entra(pietro)
        sfida.client.post(f"/match/matches/{match_id}/reject")

        # Marco corregge: il referto si riapre e le decisioni si azzerano.
        sfida.esci()
        sfida.entra(marco)
        risposta = sfida.client.post(f"/match/matches/{match_id}/reopen")
        assert risposta.headers["Location"].endswith(f"/match/matches/{match_id}/tpa")
        partita = sfida.partita(match_id)
        assert partita.status == MatchStatus.IN_PROGRESS
        assert not sfida.referto(match_id).is_closed
        for _ in range(4):
            sfida.annulla_tocco(match_id)
        sfida.vinci_rack_nel_referto(match_id, posto=2)
        sfida.vinci_rack_nel_referto(match_id, posto=1)
        sfida.chiudi_referto(match_id)
        assert sfida.punteggio(match_id) == (3, 1)

        # I due ricevono di nuovo la richiesta, e la confermano.
        for giocatore in (paolo, pietro):
            sfida.esci()
            sfida.entra(giocatore)
            assert f"/match/matches/{match_id}/confirm" in sfida.pagina(match_id)
            sfida.client.post(f"/match/matches/{match_id}/confirm")
        assert sfida.stato(match_id) == MatchStatus.CONFIRMED_BY_BOTH

    def test_marco_cancella_la_rifiutata(self, sfida: SfidaDriver):
        marco = sfida.crea_istruttore()
        paolo, pietro = sfida.crea_giocatori(2)
        sfida.entra(marco)
        sfida.segna_partita_di_altri(paolo, pietro)
        match_id = _ultima_partita_segnata_da(marco.id)
        for _ in range(3):
            sfida.vinci_rack_nel_referto(match_id, posto=1)
        sfida.chiudi_referto(match_id)

        sfida.esci()
        sfida.entra(paolo)
        sfida.client.post(f"/match/matches/{match_id}/confirm")
        sfida.esci()
        sfida.entra(pietro)
        sfida.client.post(f"/match/matches/{match_id}/reject")
        # Un giocatore non la cancella: non la vede nemmeno.
        sfida.client.post(f"/match/matches/{match_id}/cancel")
        assert sfida.stato(match_id) == MatchStatus.REJECTED

        sfida.esci()
        sfida.entra(marco)
        assert "Cancella la partita" in sfida.pagina(match_id)
        sfida.client.post(f"/match/matches/{match_id}/cancel")
        assert sfida.stato(match_id) == MatchStatus.CANCELLED

    def test_l_admin_non_segna(self, sfida: SfidaDriver):
        """«admin non dovrebbe segnare partite» (2026-10-18)."""
        admin = sfida.crea_admin()
        paolo, pietro = sfida.crea_giocatori(2)
        sfida.entra(admin)
        risposta = sfida.segna_partita_di_altri(paolo, pietro)
        assert risposta.status_code in (302, 403)
        assert IndividualMatch.query.filter_by(scorer_id=admin.id).count() == 0

    def test_un_giocatore_senza_ruolo_non_segna(self, sfida: SfidaDriver):
        gianni, paolo, pietro = sfida.crea_giocatori(3)
        sfida.entra(gianni)
        assert "Segna la partita di altri due" not in sfida.pagina_sfide()
        risposta = sfida.segna_partita_di_altri(paolo, pietro)
        assert risposta.status_code == 302
        assert IndividualMatch.query.filter_by(scorer_id=gianni.id).count() == 0

    def test_marco_annulla_la_partita_a_meta(self, sfida: SfidaDriver):
        marco = sfida.crea_istruttore()
        paolo, pietro = sfida.crea_giocatori(2)
        sfida.entra(marco)
        sfida.segna_partita_di_altri(paolo, pietro)
        match_id = _ultima_partita_segnata_da(marco.id)
        sfida.vinci_rack_nel_referto(match_id, posto=2)

        assert "Annulla la partita" in sfida.pagina(match_id)
        sfida.client.post(f"/match/matches/{match_id}/cancel")
        assert sfida.stato(match_id) == MatchStatus.CANCELLED
