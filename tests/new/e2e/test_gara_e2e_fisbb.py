"""La formula FISBB — doppio KO con gironi — giocata per intero dalle route.

`double_ko_rounds = w` tronca il doppio KO dopo `w` turni di winners: la taglia
del girone è `G = 2^(w+1)` e ne qualifica quattro (due diretti, due ripescati).
Con `w = 2`, che è la formula usata dalle federazioni, i gironi sono da 8.

**Perché serve un e2e qui.** Il doppio KO ha già i suoi test, ma chiamano la
strategia direttamente; la fase a gironi non era percorsa da nessuno attraverso
le route. Ed è lì che vive la differenza fra "l'algoritmo è giusto" e "il
direttore riesce a fare la gara": nel giro del 2026-08-30 il formato si è
rivelato completo nel motore e incompleto in ciò che dichiara di sé.
"""

from __future__ import annotations

import pytest

from models.matchmaking.bracket import group_format_total_rounds
from models.user.role_enum import UserRole
from tests.new.e2e.gara_driver import GaraDriver

pytestmark = pytest.mark.e2e

ISCRITTI = 16
GIRONI_ATTESI = 2  # 16 / G=8
TURNI_DI_GIRONE = 3  # 2w - 1, con w = 2
TURNI_TOTALI_ATTESI = 6  # gironi (3) + tabellone finale da 8 (3)


@pytest.fixture
def gara_fisbb(driver: GaraDriver):
    """Gara FISBB con 16 iscritti, sorteggiata e pronta da giocare."""
    direttore = driver.crea_utente(UserRole.DIRECTOR.value)
    giocatori = driver.crea_giocatori(ISCRITTI)

    driver.entra(direttore)
    gara_id = driver.crea_gara(
        matchmaking_strategy="double_knockout",
        double_ko_rounds=2,
        classification_system="POSITION",
        odd_number_policy="no",
        anti_rematch_enabled="",
        min_participants=8,
        max_participants=ISCRITTI,
    )
    driver.apri_iscrizioni(gara_id)
    driver.iscrivi_tutti(gara_id, giocatori)

    # `iscrivi_tutti` entra come ogni giocatore: si rientra da direttore.
    driver.entra(direttore)
    return gara_id, direttore, giocatori


class TestFormulaFisbb:
    def test_il_sorteggio_forma_i_gironi(self, driver, gara_fisbb):
        gara_id, _direttore, _giocatori = gara_fisbb
        driver.avvia_primo_turno(gara_id)

        partite = driver.partite(gara_id, turno=1)
        gironi = {m.bracket_group for m in partite}

        assert driver.gara(gara_id).status == "playing"
        assert gironi == set(range(GIRONI_ATTESI)), f"gironi trovati: {gironi}"
        # Ogni girone da 8 apre con 4 partite di winners.
        assert len(partite) == GIRONI_ATTESI * 4

    def test_la_gara_si_gioca_fino_in_fondo(self, driver, gara_fisbb):
        """I tre turni di girone, poi il tabellone finale, poi la chiusura."""
        gara_id, _direttore, _giocatori = gara_fisbb
        driver.avvia_primo_turno(gara_id)

        giocati = []
        for numero in range(1, TURNI_TOTALI_ATTESI + 1):
            if not driver.partite(gara_id, turno=numero):
                assert driver.avvia_turno(gara_id, numero)[
                    "success"
                ], f"turno {numero} non avviabile"
            partite = driver.partite(gara_id, turno=numero)
            giocati.append((numero, len(partite), {m.bracket_group for m in partite}))
            driver.gioca_turno(gara_id, numero)

        # I primi tre turni stanno dentro i gironi, gli altri no.
        for numero, _quante, gironi in giocati[:TURNI_DI_GIRONE]:
            assert gironi == set(range(GIRONI_ATTESI)), f"turno {numero}: {gironi}"
        for numero, _quante, gironi in giocati[TURNI_DI_GIRONE:]:
            assert gironi == {None}, f"turno {numero} dovrebbe essere fuori dai gironi"

        # Il tabellone finale dimezza a ogni turno: 8 qualificati → 4, 2, 1.
        assert [quante for _n, quante, _g in giocati[TURNI_DI_GIRONE:]] == [4, 2, 1]

        driver.termina(gara_id)
        assert driver.gara(gara_id).status == "completed"

    def test_la_pagina_del_tabellone_risponde(self, driver, client, gara_fisbb):
        gara_id, _direttore, _giocatori = gara_fisbb
        driver.avvia_primo_turno(gara_id)

        assert client.get(f"/admin/gara/{gara_id}/tabellone").status_code == 200


class TestTurniDichiarati:
    """Quanti turni la gara dice di avere, prima e dopo il sorteggio.

    Il sorteggio ha sempre saputo contarli — `DoubleKnockoutStrategy` fissa
    `rounds_count` sugli iscritti effettivi con `group_format_total_rounds`.
    Ma **prima** del sorteggio la stima veniva dal doppio KO pieno sulla
    capienza, ignorando i gironi: 8 invece di 6 con 16 iscritti, 12 invece di 8
    con 48. Il direttore leggeva quel numero mentre configurava la gara.
    """

    def test_la_stima_in_creazione_tiene_conto_dei_gironi(self, driver, gara_fisbb):
        gara_id, _direttore, _giocatori = gara_fisbb
        assert driver.gara(gara_id).rounds_count == TURNI_TOTALI_ATTESI

    def test_il_sorteggio_conferma_lo_stesso_numero(self, driver, gara_fisbb):
        """Le due strade devono dare lo stesso conto, o una delle due mente."""
        gara_id, _direttore, _giocatori = gara_fisbb
        driver.avvia_primo_turno(gara_id)
        assert driver.gara(gara_id).rounds_count == TURNI_TOTALI_ATTESI

    @pytest.mark.parametrize("iscritti,attesi", [(16, 6), (24, 7), (32, 7), (48, 8)])
    def test_la_formula_del_conteggio(self, iscritti, attesi):
        assert group_format_total_rounds(iscritti, 2) == attesi
