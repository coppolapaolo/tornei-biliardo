"""La partita di Marco contro Gino, che non ha un account.

UC13 di ``docs/usecases/sfide-e-certificazione.md`` (ADR-085, emendamento del
2026-10-18). Dalla segnalazione dell'utente: «non posso prendere il TPA di
una mia partita con un altro giocatore che non è iscritto».

Solo route: Marco, istruttore, apre la sfida dall'avvio rapido aggiungendo
Gino con nome e cognome, la tiene col referto TPA, la firma e continua a
giocare. Gino si registra, la riscatta, e la trova da confermare.
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
        # Finita la partita Marco chiude il referto: con il referto aperto la
        # pagina della sfida non mostra il segnapunti, né «Accetta».
        sfida.chiudi_referto(match_id)

        # La pagina non sollecita la firma di Gino, e Marco non è bloccato.
        pagina = sfida.pagina(match_id)
        assert "In attesa del riscatto" in pagina
        assert "Manca la conferma" not in pagina
        altro = sfida.crea_giocatore()
        assert sfida.avvio_rapido(altro).status_code == 200
        assert sfida.notifiche(Giocatore(gino_id, "", "")) == []

        # Gino si registra e chiede il riscatto; Marco lo conferma.
        sfida.esci()
        gino = sfida.crea_giocatore()
        sfida.entra(gino)
        sfida.chiedi_riscatto(gino_id)
        richiesta = ClaimRequest.query.filter_by(placeholder_id=gino_id).one()
        sfida.esci()
        sfida.entra(marco)
        sfida.decidi_riscatto(richiesta.id)
        assert sfida.partita(match_id).player2_id == gino.id

        # Ora la sfida aspetta Gino come un avversario qualunque.
        sfida.esci()
        sfida.entra(gino)
        assert any(
            n.action_url == f"/match/matches/{match_id}" for n in sfida.notifiche(gino)
        )
        assert "Accetta" in sfida.pagina(match_id)
        assert sfida.conferma(match_id).status_code == 200
        partita = sfida.partita(match_id)
        assert partita.status == MatchStatus.CONFIRMED_BY_BOTH
        assert partita.winner_id == gino.id

    def test_un_giocatore_senza_ruolo_non_lo_aggiunge(self, sfida: SfidaDriver):
        paolo = sfida.crea_giocatore()
        sfida.entra(paolo)

        assert "Non ha un account? Aggiungilo" not in sfida.pagina_avvio_rapido()
        assert sfida.avvio_rapido_con_nuovo("Gino", "Verdini").status_code == 403
