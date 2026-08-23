"""La stagione giocata davvero: quindici iscritti, la X, gli spareggi, i playoff.

È il test più lento della suite e l'unico che percorre tutto il campionato
dall'inizio alla fine — quattro gare da tre turni con quindici iscritti sono
ottantaquattro partite segnate rack per rack via HTTP. Serve una volta sola, ma
serve: è l'unico posto in cui si vede che la classifica generale prodotta da
quattro gare vere regge l'avvio dei playoff, e che la finale nasce dai
qualificati giusti.

Le altre classi usano una stagione più corta — la sola quarta gara, che è la
più complicata perché cambia disciplina e distanza a ogni turno — perché quello
che mettono alla prova (la X, gli override, le risposte all'invito) non dipende
da quante gare si sono giocate.

Quindici è dispari: **ogni turno qualcuno prende la X** e vince a tavolino. È
la configurazione che il direttore avrà davvero, e cambia il conto delle
partite di ogni turno: sette giocate più una vinta a tavolino.
"""

from __future__ import annotations

import pytest

from campionato_driver import CampionatoDriver
from stagione import (
    CALENDARIO,
    ISCRITTI_AL_COMPLETO,
    QUALIFICATI_AL_PLAYOFF,
    TURNI,
    TURNI_MISTI,
    crea_stagione,
)
from models.playoff.models import QualificationStatus
from models.status_enum import GaraStatus, MatchStatus
from models.user.role_enum import UserRole

#: Sette partite giocate per turno, più la X.
PARTITE_PER_TURNO = ISCRITTI_AL_COMPLETO // 2


def _gioca_gara(campionato: CampionatoDriver, gara_id: int, direttore, giocatori):
    """Una gara della stagione dall'apertura delle iscrizioni alla chiusura."""
    campionato.entra(direttore)
    campionato.apri_iscrizioni(gara_id)
    campionato.iscrivi_tutti(gara_id, giocatori)

    campionato.entra(direttore)
    campionato.avvia_primo_turno(gara_id)
    for turno in range(1, TURNI + 1):
        if turno > 1:
            esito = campionato.avvia_turno(gara_id, turno)
            assert esito["success"] is True, esito.get("error")
        campionato.gioca_turno(gara_id, turno)
        campionato.pagina_gara(gara_id)

    return campionato.chiudi_gara(gara_id)


@pytest.fixture
def stagione_completa(campionato: CampionatoDriver):
    """Le quattro gare giocate con quindici iscritti, campionato terminato."""
    direttore = campionato.crea_utente(UserRole.DIRECTOR.value)
    giocatori = campionato.crea_giocatori(ISCRITTI_AL_COMPLETO)
    campionato_id, gare = crea_stagione(campionato, direttore)

    for programmata in CALENDARIO:
        _gioca_gara(campionato, gare[programmata.numero], direttore, giocatori)

    campionato.entra(direttore)
    campionato.termina_campionato(campionato_id)
    return campionato_id, gare, direttore, giocatori


@pytest.fixture
def solo_la_quarta(campionato: CampionatoDriver):
    """La sola quarta gara giocata, e il campionato terminato.

    Basta a produrre una classifica generale con tutti e quindici, che è tutto
    quello che serve ai test dei playoff — e costa un quarto della stagione
    intera. Le altre tre gare, mai giocate, la terminazione le soft-elimina.
    """
    direttore = campionato.crea_utente(UserRole.DIRECTOR.value)
    giocatori = campionato.crea_giocatori(ISCRITTI_AL_COMPLETO)
    campionato_id, gare = crea_stagione(campionato, direttore)

    _gioca_gara(campionato, gare[4], direttore, giocatori)

    campionato.entra(direttore)
    campionato.termina_campionato(campionato_id)
    return campionato_id, gare[4], direttore, giocatori


@pytest.mark.e2e
class TestLaStagioneIntera:
    def test_quattro_gare_giocate_e_una_classifica_di_quindici(
        self, campionato: CampionatoDriver, stagione_completa
    ):
        campionato_id, gare, _direttore, giocatori = stagione_completa

        chiuse = campionato.gare_del_campionato(campionato_id)
        assert [gara.number for gara in chiuse] == [g.numero for g in CALENDARIO]
        assert all(gara.status == GaraStatus.COMPLETED.value for gara in chiuse)

        for gara in chiuse:
            partite = campionato.partite(gara.id)
            assert campionato.turni_creati(gara.id) == set(range(1, TURNI + 1))
            assert all(MatchStatus.is_finished(p.status) for p in partite)

        classifica = campionato.classifica_generale(campionato_id)
        assert {riga.user_id for riga in classifica} == {g.id for g in giocatori}
        assert [riga.position for riga in classifica] == list(
            range(1, ISCRITTI_AL_COMPLETO + 1)
        )
        assert campionato.campionato(campionato_id).terminated_at is not None

    def test_la_classifica_generale_conta_tutte_e_quattro_le_gare(
        self, campionato: CampionatoDriver, stagione_completa
    ):
        """Nessuno resta indietro: ognuno ha giocato le quattro gare."""
        campionato_id, _gare, _direttore, _giocatori = stagione_completa

        classifica = campionato.classifica_generale(campionato_id)

        assert all(riga.gare_played == len(CALENDARIO) for riga in classifica)


@pytest.mark.e2e
class TestLaXAOgniTurno:
    """Quindici è dispari: uno riposa e vince a tavolino, e cambia ogni turno."""

    def test_sette_partite_giocate_e_una_vinta_a_tavolino(
        self, campionato: CampionatoDriver, solo_la_quarta
    ):
        _campionato_id, gara_id, _direttore, giocatori = solo_la_quarta

        for turno in range(1, TURNI + 1):
            partite = campionato.partite(gara_id, turno=turno)
            con_la_x = [p for p in partite if p.is_bye]
            quale = f"turno {turno}"
            assert len(con_la_x) == 1, quale
            assert len(partite) == PARTITE_PER_TURNO + 1, quale
            # Tutti e quindici scendono in campo, X compresa: nessuno sparisce.
            in_campo = {p.player1_id for p in partite} | {
                p.player2_id for p in partite if p.player2_id
            }
            assert in_campo == {g.id for g in giocatori}, quale

    def test_la_x_e_gia_vinta_e_non_si_segna(
        self, campionato: CampionatoDriver, solo_la_quarta
    ):
        _campionato_id, gara_id, _direttore, _giocatori = solo_la_quarta

        for turno in range(1, TURNI + 1):
            (con_la_x,) = [
                p for p in campionato.partite(gara_id, turno=turno) if p.is_bye
            ]
            assert MatchStatus.is_finished(con_la_x.status)
            assert con_la_x.winner_id == con_la_x.player1_id
            assert con_la_x.player2_id is None

    def test_la_x_non_tocca_sempre_allo_stesso(
        self, campionato: CampionatoDriver, solo_la_quarta
    ):
        """Tre turni, tre X: che tocchino tutte alla stessa persona sarebbe un
        sorteggio rotto, non sfortuna."""
        _campionato_id, gara_id, _direttore, _giocatori = solo_la_quarta

        riposati = [
            p.player1_id
            for turno in range(1, TURNI + 1)
            for p in campionato.partite(gara_id, turno=turno)
            if p.is_bye
        ]

        assert len(set(riposati)) == len(riposati)


@pytest.mark.e2e
class TestLaQuartaGaraTurnoPerTurno:
    """Ogni turno la sua disciplina e la sua distanza, sulle partite vere."""

    def test_le_partite_seguono_l_override_del_loro_turno(
        self, campionato: CampionatoDriver, solo_la_quarta
    ):
        _campionato_id, gara_id, _direttore, _giocatori = solo_la_quarta

        for turno in TURNI_MISTI:
            partite = [
                p
                for p in campionato.partite(gara_id, turno=turno.numero)
                if not p.is_bye
            ]
            assert partite, f"turno {turno.numero} senza partite giocate"
            for partita in partite:
                quale = f"turno {turno.numero}, partita {partita.id}"
                assert partita.get_effective_discipline() == turno.disciplina, quale
                distanza = partita.distance_config
                assert distanza.racks == turno.distanza, quale
                assert distanza.is_race_to_racks is False, quale
                # E il punteggio conferma il formato: i rack giocati sono
                # esattamente quelli previsti da *quel* turno.
                assert (
                    partita.player1_score + partita.player2_score == turno.distanza
                ), quale


@pytest.mark.e2e
class TestIPlayoffDeiPrimiOtto:
    def test_si_qualificano_i_primi_otto_della_classifica(
        self, campionato: CampionatoDriver, solo_la_quarta
    ):
        campionato_id, _gara_id, direttore, _giocatori = solo_la_quarta

        campionato.entra(direttore)
        campionato.avvia_playoff(campionato_id)

        (configurazione,) = campionato.configurazioni_playoff(campionato_id)
        qualificazioni = campionato.qualificazioni(configurazione.id)
        assert len(qualificazioni) == QUALIFICATI_AL_PLAYOFF
        assert sorted(q.qualifying_position for q in qualificazioni) == list(
            range(1, QUALIFICATI_AL_PLAYOFF + 1)
        )
        classifica = campionato.classifica_generale(campionato_id)
        assert {q.user_id for q in qualificazioni} == {
            riga.user_id for riga in classifica[:QUALIFICATI_AL_PLAYOFF]
        }

    def test_chi_accetta_chi_rifiuta_e_chi_non_risponde(
        self, campionato: CampionatoDriver, solo_la_quarta
    ):
        """Il caso reale: le risposte arrivano parziali, e il direttore rimedia.

        Cinque accettano, uno rifiuta, due non rispondono. Alla gara di playoff
        arrivano **solo i confermati**: il silenzio non vale come sì, ed è la
        proprietà che rende necessario l'intervento del direttore.
        """
        campionato_id, _gara_id, direttore, giocatori = solo_la_quarta
        per_id = {g.id: g for g in giocatori}

        campionato.entra(direttore)
        campionato.avvia_playoff(campionato_id)
        (configurazione,) = campionato.configurazioni_playoff(campionato_id)
        qualificazioni = campionato.qualificazioni(configurazione.id)

        accettano = qualificazioni[:5]
        rifiuta = qualificazioni[5]
        silenziosi = qualificazioni[6:]

        for qualificazione in accettano:
            campionato.conferma_playoff(
                qualificazione.id, per_id[qualificazione.user_id]
            )
        campionato.rifiuta_playoff(rifiuta.id, per_id[rifiuta.user_id])

        stato = {
            q.user_id: q.status for q in campionato.qualificazioni(configurazione.id)
        }
        assert stato[rifiuta.user_id] == QualificationStatus.DECLINED
        for qualificazione in silenziosi:
            assert stato[qualificazione.user_id] == QualificationStatus.PENDING

        campionato.entra(direttore)
        gara_playoff = campionato.crea_gara_playoff(campionato_id, configurazione.id)

        assert campionato.iscritti(gara_playoff) == {q.user_id for q in accettano}

    def test_il_direttore_completa_la_lista_e_la_finale_parte(
        self, campionato: CampionatoDriver, solo_la_quarta
    ):
        """Cinque conferme non bastano: il direttore porta la finale a otto."""
        campionato_id, _gara_id, direttore, giocatori = solo_la_quarta
        per_id = {g.id: g for g in giocatori}

        campionato.entra(direttore)
        campionato.avvia_playoff(campionato_id)
        (configurazione,) = campionato.configurazioni_playoff(campionato_id)
        qualificazioni = campionato.qualificazioni(configurazione.id)

        for qualificazione in qualificazioni[:5]:
            campionato.conferma_playoff(
                qualificazione.id, per_id[qualificazione.user_id]
            )

        campionato.entra(direttore)
        for qualificazione in qualificazioni[5:]:
            campionato.rimuovi_dal_playoff(
                campionato_id, configurazione.id, qualificazione.id
            )

        gia_dentro = {q.user_id for q in campionato.qualificazioni(configurazione.id)}
        ripescati = [g for g in giocatori if g.id not in gia_dentro][:3]
        for giocatore in ripescati:
            campionato.aggiungi_al_playoff(campionato_id, configurazione.id, giocatore)

        gara_playoff = campionato.crea_gara_playoff(campionato_id, configurazione.id)
        iscritti = campionato.iscritti(gara_playoff)

        assert len(iscritti) == QUALIFICATI_AL_PLAYOFF
        assert {g.id for g in ripescati} <= iscritti


@pytest.mark.e2e
class TestLaFinaleATreTurniDiversi:
    """Il playoff ripete la struttura della quarta gara, e la ripete a mano.

    `create_playoff_gara` eredita disciplina, distanza, turni e strategia dalla
    prima gara conclusa del campionato, ma **non** gli override per turno: le
    `RoundConfiguration` sono legate alla gara che le ha, non al campionato.
    Il direttore le riscrive sulla finale, che nasce in `setup` e quindi li
    accetta ancora.
    """

    def test_il_direttore_configura_i_tre_turni_e_la_finale_li_usa(
        self, campionato: CampionatoDriver, solo_la_quarta
    ):
        campionato_id, _gara_id, direttore, giocatori = solo_la_quarta
        per_id = {g.id: g for g in giocatori}

        campionato.entra(direttore)
        campionato.avvia_playoff(campionato_id)
        (configurazione,) = campionato.configurazioni_playoff(campionato_id)
        for qualificazione in campionato.qualificazioni(configurazione.id):
            campionato.conferma_playoff(
                qualificazione.id, per_id[qualificazione.user_id]
            )

        campionato.entra(direttore)
        finale = campionato.crea_gara_playoff(campionato_id, configurazione.id)

        # La finale nasce senza override: li mette il direttore, uno per turno.
        assert campionato.override_dei_turni(finale) == {}
        for turno in TURNI_MISTI:
            esito = campionato.configura_turno(
                finale,
                turno.numero,
                discipline=turno.disciplina,
                distance=turno.distanza,
                is_race_to=False,
            )
            assert esito.get("success"), esito

        campionato.gioca_gara_gia_iscritta(finale, direttore, TURNI)

        for turno in TURNI_MISTI:
            partite = [
                p
                for p in campionato.partite(finale, turno=turno.numero)
                if not p.is_bye
            ]
            assert partite, f"turno {turno.numero} della finale senza partite"
            for partita in partite:
                quale = f"finale, turno {turno.numero}"
                assert partita.get_effective_discipline() == turno.disciplina, quale
                assert (
                    partita.player1_score + partita.player2_score == turno.distanza
                ), quale


@pytest.mark.e2e
class TestLoSpareggioFinoAlTerzoPosto:
    """Con la classifica a vittorie i pari merito in cima sono la norma.

    Quanti siano dipende dal sorteggio, quindi qui li si rende **certi**:
    nella seconda gara la distanza è 6 — pari — e una partita può finire 3-3.
    Facendo finire in parità tutte le partite, tutti e sei restano a zero
    vittorie e a zero differenza rack, cioè tutti primi a pari merito.

    Il campionato vero non finirà così, ma il percorso che il direttore dovrà
    fare è esattamente questo, ed è l'unico modo di percorrerlo senza affidarsi
    alla fortuna del sorteggio.
    """

    @pytest.fixture
    def gara_tutta_pari(self, campionato: CampionatoDriver):
        direttore = campionato.crea_utente(UserRole.DIRECTOR.value)
        giocatori = campionato.crea_giocatori(6)
        _campionato_id, gare = crea_stagione(campionato, direttore)
        gara_id = gare[2]

        campionato.entra(direttore)
        campionato.apri_iscrizioni(gara_id)
        campionato.iscrivi_tutti(gara_id, giocatori)
        campionato.entra(direttore)
        campionato.avvia_primo_turno(gara_id)
        for turno in range(1, TURNI + 1):
            if turno > 1:
                esito = campionato.avvia_turno(gara_id, turno)
                assert esito["success"] is True, esito.get("error")
            campionato.pareggia_turno(gara_id, turno)
            campionato.pagina_gara(gara_id)

        return gara_id, direttore, giocatori

    def test_tutte_le_partite_sono_pari(
        self, campionato: CampionatoDriver, gara_tutta_pari
    ):
        gara_id, _direttore, _giocatori = gara_tutta_pari

        partite = campionato.partite(gara_id)
        assert partite
        for partita in partite:
            assert MatchStatus.is_finished(partita.status)
            assert partita.winner_id is None
            assert partita.player1_score == partita.player2_score == 3

    def test_il_pulsante_termina_rimanda_allo_spareggio(
        self, campionato: CampionatoDriver, gara_tutta_pari
    ):
        gara_id, direttore, _giocatori = gara_tutta_pari

        campionato.entra(direttore)
        campionato.termina(gara_id)

        assert campionato.gara(gara_id).status == GaraStatus.PLAYING.value

    def test_risolti_i_pari_merito_la_gara_si_chiude(
        self, campionato: CampionatoDriver, gara_tutta_pari
    ):
        gara_id, direttore, _giocatori = gara_tutta_pari

        campionato.entra(direttore)
        campionato.termina(gara_id)
        risolti = campionato.risolvi_spareggi(gara_id)

        assert risolti >= 1
        assert campionato.gara(gara_id).status == GaraStatus.AWAITING_SSR.value

        campionato.termina(gara_id)
        assert campionato.gara(gara_id).status == GaraStatus.COMPLETED.value

    def test_la_sequenza_completa_del_direttore_chiude_la_gara(
        self, campionato: CampionatoDriver, gara_tutta_pari
    ):
        """`chiudi_gara` è la sequenza vera: termina, spareggia, termina."""
        gara_id, direttore, _giocatori = gara_tutta_pari

        campionato.entra(direttore)

        assert campionato.chiudi_gara(gara_id) == GaraStatus.COMPLETED.value
