"""I casi che si rompono solo nel passaggio interfaccia↔server.

Non ci sono regole di dominio, qui: il trio, il bye, gli spareggi e
l'anti-reincontro hanno i loro test di unità, dove si decidono. Quello che si
verifica qui è l'altra metà — che l'interfaccia offra quelle strade a chi di
dovere, ne rifiuti altre a chi non deve, e trasformi un rifiuto del dominio in
un messaggio invece che in un 500.

È la classe di guasti che ha prodotto l'issue #66 (il pulsante «+» puntava
all'endpoint scelto in base al *ruolo globale* invece che ai permessi sulla
gara: il direttore che giocava si prendeva un 403 in faccia).
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from gara_driver import GaraDriver
from models.competition.models import Inscription
from models.status_enum import GaraStatus, MatchStatus
from models.user.role_enum import UserRole


@pytest.fixture
def gara_in_corso(driver: GaraDriver):
    """Gara Amalfi con 8 iscritti e il primo turno sorteggiato."""
    direttore = driver.crea_utente(UserRole.DIRECTOR.value)
    giocatori = driver.crea_giocatori(8)

    driver.entra(direttore)
    gara_id = driver.crea_gara(matchmaking_strategy="amalfi", min_participants=4)
    driver.apri_iscrizioni(gara_id)
    driver.iscrivi_tutti(gara_id, giocatori)

    driver.entra(direttore)
    driver.avvia_primo_turno(gara_id)
    return gara_id, direttore, {g.id: g for g in giocatori}


# ══ Chi segna, e da quale pulsante ═══════════════════════════════════


@pytest.mark.e2e
class TestPercorsiDiSegnatura:

    def test_i_giocatori_segnano_e_servono_due_conferme(
        self, driver: GaraDriver, gara_in_corso
    ):
        """Il percorso del giocatore chiude la partita solo a quattro mani.

        Differenza sostanziale col percorso del direttore, che chiude subito:
        qui i rack lasciano la partita «pronta da validare», e serve la firma
        di entrambi. Una conferma sola non basta, ed è il punto.
        """
        gara_id, _direttore, per_id = gara_in_corso
        partita = driver.partite(gara_id, turno=1)[0]
        uno, due = per_id[partita.player1_id], per_id[partita.player2_id]
        traguardo = partita.distance_config.get_winning_racks()

        driver.entra(uno)
        for _ in range(traguardo):
            risposta = driver.aggiungi_rack_da_giocatore(partita.id, uno.id)
            assert risposta.status_code == 200, risposta.get_data(as_text=True)

        driver.conferma(partita.id)
        assert not MatchStatus.is_finished(driver.partite(gara_id, turno=1)[0].status)

        driver.entra(due)
        driver.conferma(partita.id)

        chiusa = [p for p in driver.partite(gara_id, turno=1) if p.id == partita.id][0]
        assert MatchStatus.is_finished(chiusa.status)
        assert chiusa.winner_id == uno.id

    def test_al_giocatore_e_negato_il_pulsante_del_direttore(
        self, driver: GaraDriver, gara_in_corso
    ):
        """La porta di servizio è chiusa anche a chi è in campo.

        L'endpoint del direttore segna con `validated_by_admin=True`, cioè
        chiude la partita all'istante: aperto ai giocatori, permetteva a uno dei
        due di chiuderla col punteggio che preferiva, saltando la firma
        dell'avversario che il suo percorso pretende. Nessuna schermata glielo
        proponeva (il template sceglie il flusso player, issue #66), ma l'URL
        era raggiungibile a mano.
        """
        gara_id, _direttore, per_id = gara_in_corso
        partita = driver.partite(gara_id, turno=1)[0]
        uno = per_id[partita.player1_id]

        driver.entra(uno)
        risposta = driver.aggiungi_rack(partita.id, uno.id)

        assert risposta.status_code == 403
        assert driver.partite(gara_id, turno=1)[0].player1_score == 0

    def test_chi_non_gioca_quella_partita_non_la_segna(
        self, driver: GaraDriver, gara_in_corso
    ):
        """Neanche dal percorso giocatore: bisogna essere in campo.

        Il rifiuto qui non è un 403 ma un rimando alla dashboard con un
        messaggio — coerente con l'essere una pagina e non una chiamata dati.
        """
        gara_id, _direttore, per_id = gara_in_corso
        turno = driver.partite(gara_id, turno=1)
        partita, altra = turno[0], turno[1]
        estraneo = per_id[altra.player1_id]

        driver.entra(estraneo)
        risposta = driver.aggiungi_rack_da_giocatore(partita.id, partita.player1_id)

        assert risposta.status_code == 302
        assert driver.partite(gara_id, turno=1)[0].player1_score == 0

    def test_rack_a_rack_e_risultato_secco_finiscono_nello_stesso_stato(
        self, driver: GaraDriver, gara_in_corso
    ):
        """Due strade che l'interfaccia offre per la stessa cosa.

        Il direttore può segnare rack per rack, oppure inserire il risultato
        finale in un colpo. Devono lasciare la partita nello stesso stato: se
        divergono, metà delle serate finiscono in un modo e metà nell'altro.
        """
        gara_id, _direttore, _per_id = gara_in_corso
        una, altra = driver.partite(gara_id, turno=1)[:2]
        traguardo = una.distance_config.get_winning_racks()

        driver.gioca_match(una.id, una.player1_id)
        driver.imposta_risultato(altra.id, traguardo, 0)

        rifatte = {p.id: p for p in driver.partite(gara_id, turno=1)}
        a_rack, secca = rifatte[una.id], rifatte[altra.id]

        assert MatchStatus.is_finished(a_rack.status)
        assert MatchStatus.is_finished(secca.status)
        assert a_rack.status == secca.status
        # Il margine non è l'oggetto del confronto — `gioca_match` lo fa
        # variare apposta — ma l'invariante del race-to sì: chi vince arriva
        # al traguardo, e chi perde ci resta sotto.
        assert a_rack.player1_score == traguardo
        assert a_rack.player2_score < traguardo
        assert (secca.player1_score, secca.player2_score) == (traguardo, 0)
        assert secca.winner_id == secca.player1_id


# ══ Tornare indietro ═════════════════════════════════════════════════


@pytest.mark.e2e
class TestAnnullamenti:

    def test_il_sorteggio_si_annulla_finche_nessuno_ha_giocato(
        self, driver: GaraDriver, gara_in_corso
    ):
        gara_id, _direttore, _per_id = gara_in_corso

        driver.annulla_primo_turno(gara_id)

        gara = driver.gara(gara_id)
        assert gara.status == GaraStatus.INSCRIPTION.value
        assert gara.current_round == 0
        assert driver.partite(gara_id) == []
        # Gli iscritti restano: si annulla il sorteggio, non la gara.
        assert Inscription.query.filter_by(gara_id=gara_id).count() == 8

    def test_col_primo_risultato_il_sorteggio_e_definitivo(
        self, driver: GaraDriver, gara_in_corso
    ):
        gara_id, _direttore, _per_id = gara_in_corso
        prima = {p.id for p in driver.partite(gara_id, turno=1)}
        driver.gioca_match(driver.partite(gara_id, turno=1)[0].id)

        risposta = driver.annulla_primo_turno(gara_id)

        assert risposta.status_code == 200
        assert driver.gara(gara_id).status == GaraStatus.PLAYING.value
        assert {p.id for p in driver.partite(gara_id, turno=1)} == prima


@pytest.mark.e2e
class TestSequenzeRifiutate:

    def test_non_si_termina_con_le_partite_aperte(
        self, driver: GaraDriver, gara_in_corso
    ):
        """Un rifiuto deve essere un messaggio, non un errore del server."""
        gara_id, _direttore, _per_id = gara_in_corso

        risposta = driver.termina(gara_id)

        assert risposta.status_code == 200
        assert "non tutti i turni" in risposta.get_data(as_text=True).lower()
        assert driver.gara(gara_id).status == GaraStatus.PLAYING.value


# ══ Chi può fare cosa ════════════════════════════════════════════════


@pytest.mark.e2e
class TestPermessiSullaGara:

    def test_il_giocatore_non_governa_la_gara(self, driver: GaraDriver, gara_in_corso):
        gara_id, _direttore, per_id = gara_in_corso
        qualcuno = next(iter(per_id.values()))

        driver.entra(qualcuno)

        assert driver.avvia_primo_turno(gara_id).status_code == 403
        assert driver.termina(gara_id).status_code == 403

    def test_un_direttore_estraneo_non_governa_la_gara_di_un_altro(
        self, driver: GaraDriver, gara_in_corso
    ):
        """Il ruolo `director` non è una chiave universale.

        È il permesso *su questa gara* che conta — la distinzione che l'issue
        #66 aveva perso, ma dall'altro lato.
        """
        gara_id, _direttore, _per_id = gara_in_corso
        estraneo = driver.crea_utente(UserRole.DIRECTOR.value)

        driver.entra(estraneo)

        assert driver.avvia_primo_turno(gara_id).status_code == 403

    def test_l_ospite_guarda_ma_non_tocca(self, driver: GaraDriver, gara_in_corso):
        gara_id, _direttore, _per_id = gara_in_corso
        driver.esci()

        assert driver.client.get(f"/admin/gara/{gara_id}").status_code == 200

        risposta = driver.client.post(f"/admin/gara/{gara_id}/start_first_round")
        assert risposta.status_code == 302
        assert "/auth/login" in risposta.headers["Location"]


# ══ Il percorso del giocatore che si iscrive ═════════════════════════


@pytest.mark.e2e
class TestIscrizioni:

    @pytest.fixture
    def gara_aperta(self, driver: GaraDriver):
        direttore = driver.crea_utente(UserRole.DIRECTOR.value)
        driver.entra(direttore)
        gara_id = driver.crea_gara(min_participants=4)
        driver.apri_iscrizioni(gara_id)
        return gara_id, direttore

    def test_la_finestra_troppo_lunga_viene_accorciata_e_lo_dice(
        self, driver: GaraDriver
    ):
        """Iscriversi a partita cominciata non vuol dire niente: la fine si
        accorcia all'inizio della gara. Ma l'apertura deve **avvenire**.

        Prima l'aggiustamento veniva annunciato sollevando un ValueError dentro
        un metodo `@transactional`: il rollback lo cancellava insieme
        all'apertura, e all'utente restava un messaggio che descriveva una
        correzione mai avvenuta, sopra a una gara rimasta chiusa.
        """
        direttore = driver.crea_utente(UserRole.DIRECTOR.value)
        driver.entra(direttore)
        gara_id = driver.crea_gara(min_participants=4)
        oltre_la_gara = driver.gara(gara_id).date + timedelta(days=30)

        risposta = driver.apri_iscrizioni(gara_id, chiusura=oltre_la_gara)

        gara = driver.gara(gara_id)
        assert gara.status == GaraStatus.INSCRIPTION.value
        assert gara.inscription_end.date() == gara.date
        assert "anticipata" in risposta.get_data(as_text=True).lower()

        # E la finestra è viva: chi arriva riesce davvero a iscriversi.
        giocatore = driver.crea_utente(UserRole.PLAYER.value)
        driver.iscrivi(gara_id, giocatore)
        assert (
            Inscription.query.filter_by(gara_id=gara_id, user_id=giocatore.id).count()
            == 1
        )

    def test_non_ci_si_iscrive_due_volte(self, driver: GaraDriver, gara_aperta):
        gara_id, _direttore = gara_aperta
        giocatore = driver.crea_utente(UserRole.PLAYER.value)

        driver.iscrivi(gara_id, giocatore)
        risposta = driver.iscrivi(gara_id, giocatore)

        assert "già iscritto" in risposta.get_data(as_text=True).lower()
        assert (
            Inscription.query.filter_by(gara_id=gara_id, user_id=giocatore.id).count()
            == 1
        )

    def test_oltre_la_capienza_si_finisce_in_lista_d_attesa(self, driver: GaraDriver):
        direttore = driver.crea_utente(UserRole.DIRECTOR.value)
        driver.entra(direttore)
        gara_id = driver.crea_gara(min_participants=2, max_participants=2)
        driver.apri_iscrizioni(gara_id)
        primi = driver.crea_giocatori(2)
        tardivo = driver.crea_utente(UserRole.PLAYER.value)

        driver.iscrivi_tutti(gara_id, primi)
        driver.iscrivi(gara_id, tardivo)

        iscrizione = Inscription.query.filter_by(
            gara_id=gara_id, user_id=tardivo.id
        ).one()
        assert iscrizione.is_waitlist is True

    def test_ci_si_disiscrive_finche_non_si_sorteggia(
        self, driver: GaraDriver, gara_aperta
    ):
        gara_id, direttore = gara_aperta
        giocatore = driver.crea_utente(UserRole.PLAYER.value)
        compagno = driver.crea_utente(UserRole.PLAYER.value)
        driver.iscrivi(gara_id, giocatore)
        driver.iscrivi(gara_id, compagno)

        driver.entra(giocatore)
        driver.client.post(f"/player/gara/{gara_id}/unsubscribe", follow_redirects=True)

        assert (
            Inscription.query.filter_by(
                gara_id=gara_id, user_id=giocatore.id, is_withdrawn=False
            ).count()
            == 0
        )

    def test_a_gara_avviata_le_iscrizioni_sono_chiuse(
        self, driver: GaraDriver, gara_aperta
    ):
        gara_id, direttore = gara_aperta
        driver.iscrivi_tutti(gara_id, driver.crea_giocatori(4))
        driver.entra(direttore)
        driver.avvia_primo_turno(gara_id)

        tardivo = driver.crea_utente(UserRole.PLAYER.value)
        risposta = driver.iscrivi(gara_id, tardivo)

        assert "non sono disponibili" in risposta.get_data(as_text=True).lower()
        assert (
            Inscription.query.filter_by(gara_id=gara_id, user_id=tardivo.id).count()
            == 0
        )


# ══ Numero dispari ═══════════════════════════════════════════════════


@pytest.mark.e2e
class TestGiocatoriDispari:
    """Le due risposte al numero dispari, viste dall'interfaccia.

    *Quali* giocatori finiscano nel bye o nel trio lo decidono gli algoritmi, e
    hanno i loro test (`test_amalfi_trio_selection.py`, `test_cancel_round_bye.py`).
    Qui interessa solo che la scelta fatta nel form arrivi fino al tavolo, e che
    la partita speciale che ne nasce sia gestibile dai pulsanti giusti.
    """

    def _gara_con_sette(self, driver: GaraDriver, **opzioni) -> int:
        direttore = driver.crea_utente(UserRole.DIRECTOR.value)
        giocatori = driver.crea_giocatori(7)
        driver.entra(direttore)
        gara_id = driver.crea_gara(min_participants=4, **opzioni)
        driver.apri_iscrizioni(gara_id)
        driver.iscrivi_tutti(gara_id, giocatori)
        driver.entra(direttore)
        driver.avvia_primo_turno(gara_id)
        return gara_id

    def test_col_bye_uno_riposa_e_la_sua_partita_e_gia_decisa(self, driver: GaraDriver):
        gara_id = self._gara_con_sette(driver, odd_number_policy="bye")

        partite = driver.partite(gara_id, turno=1)
        bye = [p for p in partite if p.is_bye]

        assert len(bye) == 1
        assert len(partite) == 4  # tre vere più il riposo
        assert MatchStatus.is_finished(bye[0].status)

    def test_col_trio_tre_giocano_insieme(self, driver: GaraDriver):
        gara_id = self._gara_con_sette(driver, odd_number_policy="trio", distance=5)

        partite = driver.partite(gara_id, turno=1)
        trii = [p for p in partite if p.is_trio]

        assert len(trii) == 1
        assert len(partite) == 3  # due normali più il trio
        assert trii[0].trio_match is not None

    def test_il_trio_non_si_segna_dal_pulsante_delle_partite_normali(
        self, driver: GaraDriver
    ):
        """Un incontro, un segnapunti.

        Il punteggio del trio vive nel `TrioMatch`, con la sua rotazione e le
        sue route. Scriverlo anche su `player1_score` del `Match` significava
        due tabellini sullo stesso incontro, liberi di divergere al primo tocco
        — il male che ADR-044 descrive per il referto TPA, sull'altro formato
        a tre.
        """
        gara_id = self._gara_con_sette(driver, odd_number_policy="trio", distance=5)
        trio = [p for p in driver.partite(gara_id, turno=1) if p.is_trio][0]

        risposta = driver.aggiungi_rack(trio.id, trio.player1_id)

        assert risposta.status_code == 400
        rifatto = [p for p in driver.partite(gara_id, turno=1) if p.is_trio][0]
        assert (rifatto.player1_score, rifatto.player2_score) == (0, 0)


# ══ Conferme e ripensamenti ══════════════════════════════════════════


@pytest.mark.e2e
class TestConfermeERipensamenti:
    """Chi ha già detto la sua non deve ridirlo, e chi sbaglia deve poter
    tornare indietro."""

    def _match_e_giocatori(self, driver: GaraDriver, gara_in_corso):
        gara_id, _direttore, per_id = gara_in_corso
        partita = driver.partite(gara_id, turno=1)[0]
        return (
            gara_id,
            partita,
            per_id[partita.player1_id],
            per_id[partita.player2_id],
        )

    def test_il_perdente_che_segna_il_rack_decisivo_ha_gia_accettato(
        self, driver: GaraDriver, gara_in_corso
    ):
        """Segnare il punto che ti fa perdere *è* accettare il risultato.

        Il vincitore era già confermato d'ufficio («non ha motivo di
        contestare»). Se il rack decisivo lo segna chi perde, mancava solo la
        sua firma — su un risultato che ha appena dichiarato lui. La partita si
        chiude lì, senza una schermata di conferma che sembra un ostacolo.
        """
        gara_id, partita, uno, due = self._match_e_giocatori(driver, gara_in_corso)
        traguardo = partita.distance_config.get_winning_racks()

        # È `due` a segnare, sempre a favore di `uno`: si sta dando per battuto.
        driver.entra(due)
        for _ in range(traguardo):
            driver.aggiungi_rack_da_giocatore(partita.id, uno.id)

        chiusa = driver.partite(gara_id, turno=1)[0]
        assert MatchStatus.is_finished(chiusa.status)
        assert chiusa.winner_id == uno.id

    def test_se_il_vincitore_segna_serve_ancora_la_firma_dell_altro(
        self, driver: GaraDriver, gara_in_corso
    ):
        """Il caso opposto, che resta com'era: la parola di uno solo non basta."""
        gara_id, partita, uno, _due = self._match_e_giocatori(driver, gara_in_corso)
        traguardo = partita.distance_config.get_winning_racks()

        driver.entra(uno)
        for _ in range(traguardo):
            driver.aggiungi_rack_da_giocatore(partita.id, uno.id)

        aperta = driver.partite(gara_id, turno=1)[0]
        assert not MatchStatus.is_finished(aperta.status)

    def test_l_ultimo_rack_si_annulla_anche_a_distanza_raggiunta(
        self, driver: GaraDriver, gara_in_corso
    ):
        """Il rack di troppo fa più danno proprio quando è quello che chiude.

        Prima il pannello del segnapunti spariva appena la distanza era
        raggiunta (il vincitore risultava confermato d'ufficio), e con esso
        l'unico modo di tornare indietro.
        """
        gara_id, partita, uno, _due = self._match_e_giocatori(driver, gara_in_corso)
        traguardo = partita.distance_config.get_winning_racks()

        driver.entra(uno)
        for _ in range(traguardo):
            driver.aggiungi_rack_da_giocatore(partita.id, uno.id)

        pagina = driver.client.get(f"/admin/match/{partita.id}").get_data(as_text=True)
        assert "Annulla ultimo triangolo" in pagina

        risposta = driver.client.post(
            f"/player/match/{partita.id}/racks/remove",
            data={"player_id": str(uno.id)},
        )
        assert risposta.status_code == 200, risposta.get_data(as_text=True)

        tornata = driver.partite(gara_id, turno=1)[0]
        assert tornata.player1_score + tornata.player2_score == traguardo - 1
        assert not MatchStatus.is_finished(tornata.status)

    def test_dopo_la_chiusura_implicita_si_puo_ancora_tornare_indietro(
        self, driver: GaraDriver, gara_in_corso
    ):
        """La conferma implicita del perdente non è irrevocabile.

        Chiude la partita, ma finché il direttore non valida resta un
        ripensamento possibile: il gesto poteva essere un tocco sbagliato.
        """
        gara_id, partita, uno, due = self._match_e_giocatori(driver, gara_in_corso)
        traguardo = partita.distance_config.get_winning_racks()

        driver.entra(due)
        for _ in range(traguardo):
            driver.aggiungi_rack_da_giocatore(partita.id, uno.id)
        assert MatchStatus.is_finished(driver.partite(gara_id, turno=1)[0].status)

        # Prima si guarda la **pagina**: un endpoint che risponde 200 non serve
        # a niente se il pulsante che lo chiama non viene disegnato. È il buco
        # in cui era caduta la prima versione di questa correzione — l'intera
        # sezione del segnapunti vive dentro un `if` sullo stato "in corso".
        pagina = driver.client.get(f"/admin/match/{partita.id}").get_data(as_text=True)
        assert "Annulla ultimo triangolo" in pagina

        risposta = driver.client.post(
            f"/player/match/{partita.id}/racks/remove",
            data={"player_id": str(uno.id)},
        )
        assert risposta.status_code == 200, risposta.get_data(as_text=True)

        riaperta = driver.partite(gara_id, turno=1)[0]
        assert riaperta.status == MatchStatus.PLAYING.value
        assert riaperta.player1_score + riaperta.player2_score == traguardo - 1

    def test_quando_chiude_il_direttore_il_risultato_e_agli_atti(
        self, driver: GaraDriver, gara_in_corso
    ):
        """Il ripensamento vale fra giocatori, non contro il direttore.

        Nota sui nomi degli stati, che ingannano: la chiusura del direttore
        lascia il match in `completed`, quella dei due giocatori in
        `validated`. È da `validated` che si torna indietro, non da
        `completed`.
        """
        gara_id, partita, uno, _due = self._match_e_giocatori(driver, gara_in_corso)
        direttore = gara_in_corso[1]

        driver.entra(direttore)
        driver.gioca_match(partita.id, uno.id)
        chiusa = driver.partite(gara_id, turno=1)[0]
        assert chiusa.status == MatchStatus.CLOSED_UNILATERALLY.value
        agli_atti = (chiusa.player1_score, chiusa.player2_score)

        driver.entra(uno)
        risposta = driver.client.post(
            f"/player/match/{partita.id}/racks/remove",
            data={"player_id": str(uno.id)},
        )

        assert risposta.status_code == 400
        rimasta = driver.partite(gara_id, turno=1)[0]
        # Il punto non è quanto fosse il punteggio, ma che il rifiuto non lo
        # abbia toccato.
        assert (rimasta.player1_score, rimasta.player2_score) == agli_atti

    def test_il_direttore_che_gioca_non_deve_farsi_confermare(self, driver: GaraDriver):
        """Chi dirige la gara ed è in campo scrive già il punteggio ufficiale.

        Tiene il segnapunti da tavolo — è quello comodo mentre si gioca, ed è
        la scelta giusta dopo l'issue #66 — ma non gli si chiede di accettare
        un risultato che ha appena scritto lui: sarebbe validare sé stesso.
        Il permesso si guarda **su questa gara**: un direttore ospite in una
        gara altrui resta un giocatore come gli altri.
        """
        direttore = driver.crea_utente(UserRole.DIRECTOR.value)
        avversari = driver.crea_giocatori(3)

        driver.entra(direttore)
        gara_id = driver.crea_gara(min_participants=4)
        driver.apri_iscrizioni(gara_id)
        driver.iscrivi_tutti(gara_id, avversari)
        driver.iscrivi(gara_id, direttore)
        driver.entra(direttore)
        driver.avvia_primo_turno(gara_id)

        sua = [
            p
            for p in driver.partite(gara_id, turno=1)
            if direttore.id in (p.player1_id, p.player2_id)
        ][0]
        traguardo = sua.distance_config.get_winning_racks()

        driver.entra(direttore)
        for _ in range(traguardo):
            risposta = driver.aggiungi_rack_da_giocatore(sua.id, direttore.id)
            assert risposta.status_code == 200, risposta.get_data(as_text=True)

        chiusa = [p for p in driver.partite(gara_id, turno=1) if p.id == sua.id][0]
        assert MatchStatus.is_finished(chiusa.status)
        assert chiusa.winner_id == direttore.id


# ══ Limiti che si vedono prima di sbagliare ══════════════════════════


@pytest.mark.e2e
class TestLimitiDelSegnapunti:
    """Presidio statico dei ganci che spengono i «+» al limite.

    Il calcolo vive nel JavaScript e nessun test Python lo esegue. Qui si
    verifica che i ganci esistano ancora nella pagina servita: se qualcuno
    rifà lo stepper e li perde per strada, il limite torna a scoprirsi solo
    dopo aver premuto «Imposta risultato».
    """

    def test_la_pagina_del_match_ha_i_ganci_dei_limiti(
        self, driver: GaraDriver, gara_in_corso
    ):
        gara_id, direttore, _per_id = gara_in_corso
        partita = driver.partite(gara_id, turno=1)[0]

        driver.entra(direttore)
        pagina = driver.client.get(f"/admin/match/{partita.id}").get_data(as_text=True)

        assert 'data-piu-per="adminScore1"' in pagina
        assert 'data-piu-per="adminScore2"' in pagina
        assert "aggiornaLimitiRack" in pagina
        assert 'id="matchResultForm"' in pagina

    def test_il_modal_del_risultato_rapido_ha_i_ganci_dei_limiti(
        self, driver: GaraDriver, gara_in_corso
    ):
        gara_id, direttore, _per_id = gara_in_corso

        driver.entra(direttore)
        pagina = driver.pagina_gara(gara_id)

        assert 'data-piu-per="quickPlayer1Score"' in pagina
        assert 'data-piu-per="quickPlayer2Score"' in pagina
        assert "aggiornaLimitiQuickResult" in pagina


# ══ Co-direttori ═════════════════════════════════════════════════════


@pytest.mark.e2e
class TestCoDirettori:

    def _gara_di(self, driver: GaraDriver, direttore):
        driver.entra(direttore)
        return driver.crea_gara(min_participants=4)

    @staticmethod
    def _candidati(pagina: str) -> str:
        """Il solo elenco dei candidati, ritagliato dalla pagina.

        La sezione è «Direzione di gara» (canvas 1.6): i candidati sono righe
        con un form «Aggiungi», non più le `<option>` di una tendina. Finché
        questi test cercavano le `<option>`, due fallivano e il terzo —
        «i giocatori non compaiono» — passava sempre, perché di `<option>`
        non ce n'era nessuna: la CI esegue solo i test unitari e non li vedeva.
        Si ritaglia l'elenco perché gli stessi id compaiono anche altrove
        nella pagina (il form per togliere un co-direttore, l'accesso rapido).
        """
        inizio = pagina.index('id="direzioneCandidati"')
        fine = pagina.index('id="direzioneNessuno"', inizio)
        return pagina[inizio:fine]

    def test_la_sezione_c_e_anche_quando_non_c_e_nessuno_da_aggiungere(
        self, driver: GaraDriver
    ):
        """Una sezione che sparisce non si distingue da una che non è mai esistita.

        Con un solo direttore sulla piattaforma l'elenco dei candidati è vuoto,
        e la card intera spariva: chi cercava «aggiungi co-direttore» non aveva
        modo di sapere se fosse stata rimossa, nascosta o mai esistita.
        """
        direttore = driver.crea_utente(UserRole.DIRECTOR.value)
        gara_id = self._gara_di(driver, direttore)

        pagina = driver.pagina_gara(gara_id)

        assert "Direzione di gara" in pagina
        assert "Nessun altro direttore in zona" in self._candidati(pagina)

    def test_un_altro_direttore_compare_nell_elenco(self, driver: GaraDriver):
        direttore = driver.crea_utente(UserRole.DIRECTOR.value)
        collega = driver.crea_utente(UserRole.DIRECTOR.value)
        gara_id = self._gara_di(driver, direttore)

        pagina = driver.pagina_gara(gara_id)

        candidati = self._candidati(pagina)
        assert f'name="user_id" value="{collega.id}"' in candidati
        assert collega.username in candidati

    def test_i_giocatori_non_compaiono_fra_i_candidati(self, driver: GaraDriver):
        """Co-direttore si nasce, non si diventa per assegnazione.

        Si guarda il solo elenco dei candidati e non la pagina intera: in
        sviluppo la pagina porta anche il pannello di accesso rapido, dove i
        nomi di tutti compaiono comunque.
        """
        direttore = driver.crea_utente(UserRole.DIRECTOR.value)
        giocatore = driver.crea_utente(UserRole.PLAYER.value)
        gara_id = self._gara_di(driver, direttore)

        pagina = driver.pagina_gara(gara_id)

        candidati = self._candidati(pagina)
        assert f'name="user_id" value="{giocatore.id}"' not in candidati
        assert giocatore.username not in candidati

    def test_il_co_direttore_aggiunto_compare_fra_i_direttori(self, driver: GaraDriver):
        direttore = driver.crea_utente(UserRole.DIRECTOR.value)
        collega = driver.crea_utente(UserRole.DIRECTOR.value)
        gara_id = self._gara_di(driver, direttore)

        risposta = driver.client.post(
            f"/admin/gara/{gara_id}/add_director",
            data={"user_id": str(collega.id)},
            follow_redirects=True,
        )
        assert risposta.status_code == 200

        # Ora è un direttore, quindi non è più un candidato da aggiungere.
        pagina = driver.pagina_gara(gara_id)
        assert "Nessun altro direttore in zona" in pagina
        assert collega.username in pagina


# ══ Profilo del giocatore ════════════════════════════════════════════


@pytest.mark.e2e
class TestProfiloGiocatore:

    def test_le_iscrizioni_portano_alla_gara(self, driver: GaraDriver):
        """L'elenco delle proprie iscrizioni era un vicolo cieco.

        Si leggeva il nome della propria gara e non ci si poteva andare: per
        aprirla bisognava ripartire dall'elenco pubblico e ritrovarla.
        """
        direttore = driver.crea_utente(UserRole.DIRECTOR.value)
        giocatore = driver.crea_utente(UserRole.PLAYER.value)

        driver.entra(direttore)
        gara_id = driver.crea_gara(min_participants=4)
        driver.apri_iscrizioni(gara_id)
        driver.iscrivi(gara_id, giocatore)

        profilo = driver.client.get("/player/profile").get_data(as_text=True)

        assert f'href="/admin/gara/{gara_id}"' in profilo

    def test_citta_e_squadra_si_rivedono_nel_profilo(self, driver: GaraDriver):
        """Un dato che ha effetti ma non si vede è un dato che nessuno corregge.

        La città guida la discovery per prossimità e la squadra precompila
        l'iscrizione alle gare che separano i compagni: entrambe erano
        compilabili e poi invisibili.
        """
        giocatore = driver.crea_utente(UserRole.PLAYER.value)
        driver.entra(giocatore)
        driver.client.post(
            "/player/profile/edit",
            data={
                # Il form vero manda anche identità e contatti: mandarne solo
                # una parte li azzererebbe.
                "username": giocatore.username,
                "email": f"{giocatore.username}@example.test",
                "home_city": "Udine",
                "squadra": "Biliardo Club Test",
            },
            follow_redirects=True,
        )

        profilo = driver.client.get("/player/profile").get_data(as_text=True)

        assert "Udine" in profilo
        assert "Biliardo Club Test" in profilo
