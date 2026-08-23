"""Correggere una sfida appena aperta, dal punto di vista di chi gioca.

Perché al livello del percorso e non solo su servizio e route: il guasto che
questi test presidiano **non era nel codice**, era nell'HTML. `cancel_match`
funzionava, aveva la sua route, il suo test e il suo pulsante — dentro un
`{% if %}` che chiedeva `status == SCHEDULED`. Con l'avvio rapido (ADR-051) la
partita nasce già in corso, quindi quella condizione non era mai vera e il
pulsante non lo vedeva nessuno.

Un test sul servizio sarebbe passato per tutto il tempo. Da cui la disciplina
del driver: prima cosa mostra la pagina, poi cosa dice il DB.
"""

from __future__ import annotations

from models.status_enum import MatchStatus
from sfida_driver import SfidaDriver


class TestLaFinestraDiCorrezione:
    def test_la_partita_appena_aperta_offre_i_due_comandi(self, sfida: SfidaDriver):
        io_, avversario = sfida.crea_giocatori(2)
        sfida.entra(io_)
        match_id = sfida.apri_partita(avversario)

        pagina = sfida.pagina(match_id)

        assert f"/match/matches/{match_id}/edit" in pagina
        assert f"/match/matches/{match_id}/cancel" in pagina

    def test_dal_primo_triangolo_i_comandi_spariscono(self, sfida: SfidaDriver):
        io_, avversario = sfida.crea_giocatori(2)
        sfida.entra(io_)
        match_id = sfida.apri_partita(avversario)
        sfida.segna(match_id, io_)

        pagina = sfida.pagina(match_id)

        assert f"/match/matches/{match_id}/edit" not in pagina
        assert f"/match/matches/{match_id}/cancel" not in pagina

    def test_la_pagina_di_modifica_si_apre(self, sfida: SfidaDriver):
        io_, avversario = sfida.crea_giocatori(2)
        sfida.entra(io_)
        match_id = sfida.apri_partita(avversario)

        risposta = sfida.pagina_modifica(match_id)

        assert risposta.status_code == 200
        assert 'name="match_format"' in risposta.get_data(as_text=True)

    def test_a_partita_cominciata_la_pagina_rimanda_indietro(self, sfida: SfidaDriver):
        io_, avversario = sfida.crea_giocatori(2)
        sfida.entra(io_)
        match_id = sfida.apri_partita(avversario)
        sfida.segna(match_id, avversario)

        risposta = sfida.pagina_modifica(match_id)

        assert risposta.status_code == 302
        assert f"/match/matches/{match_id}" in risposta.headers["Location"]


class TestLaModificaArrivaADestinazione:
    def test_cambiare_la_distanza(self, sfida: SfidaDriver):
        io_, avversario = sfida.crea_giocatori(2)
        sfida.entra(io_)
        match_id = sfida.apri_partita(avversario, distance="5")

        risposta = sfida.modifica(match_id, match_format="single", distance="7")

        assert risposta.status_code == 200, risposta.get_data(as_text=True)
        assert sfida.partita(match_id).distance == 7

    def test_un_estraneo_non_modifica_niente(self, sfida: SfidaDriver):
        io_, avversario, estraneo = sfida.crea_giocatori(3)
        sfida.entra(io_)
        match_id = sfida.apri_partita(avversario, distance="5")

        sfida.esci()
        sfida.entra(estraneo)
        risposta = sfida.modifica(match_id, match_format="single", distance="9")

        assert risposta.status_code in (302, 403)
        assert sfida.partita(match_id).distance == 5


class TestAnnullamento:
    def test_una_partita_intonsa_si_annulla(self, sfida: SfidaDriver):
        io_, avversario = sfida.crea_giocatori(2)
        sfida.entra(io_)
        match_id = sfida.apri_partita(avversario)

        sfida.annulla(match_id)

        assert sfida.stato(match_id) == MatchStatus.CANCELLED

    def test_con_dei_triangoli_segnati_l_annullamento_e_rifiutato(
        self, sfida: SfidaDriver
    ):
        io_, avversario = sfida.crea_giocatori(2)
        sfida.entra(io_)
        match_id = sfida.apri_partita(avversario)
        sfida.segna(match_id, io_)

        risposta = sfida.annulla(match_id)

        assert risposta.status_code == 400
        assert sfida.stato(match_id) == MatchStatus.IN_PROGRESS
