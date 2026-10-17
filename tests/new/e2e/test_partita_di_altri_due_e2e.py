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

from models.certificazione import Livello, livello_di_sfida_per
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

        # Pietro rifiuta: per lui sparisce, per Paolo resta.
        sfida.esci()
        sfida.entra(pietro)
        sfida.client.post(f"/match/matches/{match_id}/reject")
        assert "Hai rifiutato la partita" in sfida.pagina(match_id)

        partita = sfida.partita(match_id)
        assert partita.status == MatchStatus.IN_PROGRESS
        assert (partita.player1_score, partita.player2_score) == (3, 0)
        assert livello_di_sfida_per(partita, paolo.id) is Livello.CONFERMATA
        assert livello_di_sfida_per(partita, pietro.id) is None

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
