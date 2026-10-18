"""La partita di Marco contro Gino, che non ha un account.

UC13 e UC14 di ``docs/usecases/sfide-e-certificazione.md`` (ADR-085 e
ADR-086, emendamenti del 2026-10-18). Dalla segnalazione dell'utente: «non
posso prendere il TPA di una mia partita con un altro giocatore che non è
iscritto»; e dalla regola della sera: «quando un match con giocatore aggiunto
finisce non deve aspettare la conferma da parte del giocatore aggiunto».

Solo route: Marco, istruttore, apre la sfida dall'avvio rapido aggiungendo
Gino con nome e cognome, la tiene col referto TPA e alla distanza è chiusa,
registrata da lui. Gino si registra, la riscatta, e nella revisione la
riconosce o la contesta.
"""

from __future__ import annotations

import pytest

from models.certificazione import Livello, livello_di_sfida
from models.status_enum import Discipline, MatchStatus
from models.user.claim_request import ClaimRequest
from sfida_driver import Giocatore, SfidaDriver

DESCRIZIONE = "Finale del giovedì, su YouTube"


@pytest.mark.e2e
class TestLaSfidaControGinoNonRegistrato:
    def test_marco_la_tiene_gino_la_riscatta_e_la_conferma(self, sfida: SfidaDriver):
        marco = sfida.crea_istruttore()
        sfida.entra(marco)

        # L'avvio rapido offre «Non ha un account? Aggiungilo».
        assert "Non ha un account? Aggiungilo" in sfida.pagina_avvio_rapido()
        risposta = sfida.avvio_rapido_con_nuovo(
            "Gino",
            "Verdini",
            discipline=Discipline.NINE_BALL.value,
            match_format="single",
            distance=3,
            tpa_referto="on",
            description=DESCRIZIONE,
        )
        assert risposta.status_code == 200, risposta.get_data(as_text=True)[:300]
        match_id = risposta.get_json()["match_id"]
        assert risposta.get_json()["url"].endswith(f"/match/matches/{match_id}/tpa")
        partita = sfida.partita(match_id)
        gino_id = partita.player2_id
        assert partita.player2.is_placeholder
        assert partita.description == DESCRIZIONE
        assert sfida.referto(match_id).compiler_id == marco.id

        # Il referto lo tiene Marco; alla distanza vince Gino, e firma Marco.
        for _ in range(3):
            sfida.vinci_rack_nel_referto(match_id, posto=2)
        partita = sfida.partita(match_id)
        assert (partita.player1_score, partita.player2_score) == (0, 3)
        assert partita.player1_confirmed and not partita.player2_confirmed
        assert livello_di_sfida(partita) is Livello.IN_ATTESA
        # Finita la partita Marco chiude il referto.
        sfida.chiudi_referto(match_id)

        # Chiusa, registrata da Marco: non aspetta Gino, e Marco non è bloccato.
        assert partita.status == MatchStatus.CLOSED_UNILATERALLY
        assert partita.recorded_by_id == marco.id
        pagina = sfida.pagina(match_id)
        assert "Registrata da te" in pagina
        assert "Manca la conferma" not in pagina
        altro = sfida.crea_giocatore()
        assert sfida.avvio_rapido(altro).status_code == 200
        assert sfida.notifiche(Giocatore(gino_id, "", "")) == []

        # Gino si registra e chiede il riscatto; Marco lo conferma.
        gino = self._riscatta(sfida, marco, gino_id)
        assert sfida.partita(match_id).player2_id == gino.id

        # Ora Gino è invitato a rivederla, e la riconosce.
        assert any(n.action_url == "/match/revisione" for n in sfida.notifiche(gino))
        assert f'name="partite" value="{match_id}"' in sfida.pagina_revisione()
        assert sfida.rivedi([match_id], "riconosci_tutte").status_code == 302
        partita = sfida.partita(match_id)
        assert partita.status == MatchStatus.CONFIRMED_BY_BOTH
        assert livello_di_sfida(partita) is Livello.CONFERMATA
        assert partita.winner_id == gino.id

    def test_gino_contesta_e_la_sfida_resta_a_marco(self, sfida: SfidaDriver):
        marco = sfida.crea_istruttore()
        sfida.entra(marco)
        risposta = sfida.avvio_rapido_con_nuovo(
            "Gino", "Contesti", match_format="single", distance=3
        )
        match_id = risposta.get_json()["match_id"]
        gino_id = sfida.partita(match_id).player2_id
        sfida.segna_piu_volte(match_id, marco, 3)
        assert sfida.partita(match_id).recorded_by_id == marco.id

        gino = self._riscatta(sfida, marco, gino_id)
        assert sfida.rivedi([match_id], "contesta_tutte").status_code == 302
        # Per Gino sparisce.
        assert f"/match/matches/{match_id}" not in sfida.pagina_elenco()

        # A Marco resta, contestata, con l'avviso.
        sfida.esci()
        sfida.entra(marco)
        assert "Contestata" in sfida.pagina(match_id)
        assert any(
            n.action_url == f"/match/matches/{match_id}" for n in sfida.notifiche(marco)
        )
        partita = sfida.partita(match_id)
        assert partita.is_contested
        assert livello_di_sfida(partita) is Livello.IN_ATTESA
        assert gino.id == partita.player2_id

    @staticmethod
    def _riscatta(sfida: SfidaDriver, creatore: Giocatore, giocatore_id: int):
        """Chi si registra chiede il riscatto, il creatore lo conferma; alla
        fine è entrato chi ha riscattato."""
        sfida.esci()
        nuovo = sfida.crea_giocatore()
        sfida.entra(nuovo)
        sfida.chiedi_riscatto(giocatore_id)
        richiesta = ClaimRequest.query.filter_by(placeholder_id=giocatore_id).one()
        sfida.esci()
        sfida.entra(creatore)
        sfida.decidi_riscatto(richiesta.id)
        sfida.esci()
        sfida.entra(nuovo)
        return nuovo

    def test_un_giocatore_senza_ruolo_non_lo_aggiunge(self, sfida: SfidaDriver):
        paolo = sfida.crea_giocatore()
        sfida.entra(paolo)

        assert "Non ha un account? Aggiungilo" not in sfida.pagina_avvio_rapido()
        assert sfida.avvio_rapido_con_nuovo("Gino", "Verdini").status_code == 403
