"""Un campionato intero — quattro gare Amalfi e i playoff — solo via HTTP.

È il percorso che nessun test attraversava per intero. Le due metà erano
coperte, ma ciascuna partendo dallo stato dell'altra costruito a mano:

* `tests/new/integration/test_gare_usecase_4_campionato_workflow.py` gioca più
  gare di un campionato chiamando i **service**, e si ferma un attimo prima dei
  playoff (il commento nel test dice «Ready for playoff phase»);
* `tests/new/integration/test_avvio_playoff_route.py` percorre le route dei
  playoff, ma da una fixture che scrive `terminated_at` e le righe di
  classifica direttamente sul DB, senza che una sola partita sia stata giocata.

In mezzo c'è un giunto, ed è lì che è nato il guasto del bug 8 di
`docs/debug20260528.md`: `start_playoff` non trovava qualificati perché la
classifica non era mai stata materializzata. Un difetto invisibile a entrambe
le metà, verdi ciascuna per conto suo. Percorrerlo ne ha trovato subito un
secondo, che ha il suo test di regressione in
`tests/new/unit/test_playoff_gara_date_sequence.py`: la gara di playoff nasceva
datata *oggi* pur essendo l'ultima del calendario, e con l'ultima gara ancora
nel futuro l'ordine cronologico di ADR-016 la rifiutava — playoff
irraggiungibili, con un messaggio in pagina al posto della finale.

Le gare sono configurate tutte uguali — tre turni, distanza **esattamente 5
rack** — perché l'uniformità è essa stessa l'oggetto del test: la gara di
playoff non la configura nessuno, la eredita dalla prima gara conclusa del
campionato (`PlayoffConfiguration.get_gara_params`), e se l'ereditarietà si
rompe il campionato finisce con una finale che si gioca in un altro formato.

«Esattamente 5 rack» non è «al 5»: la partita finisce quando i rack giocati
sono cinque e vince chi ne ha di più, quindi chiude su un 3-2 che in un race-to
sarebbe ancora in corso. È la differenza che rende osservabile, dall'esterno,
quale dei due formati la partita stia davvero usando.

Come in `test_gara_e2e_amalfi.py`, il sorteggio è casuale e persistito: si
asserisce sulla **forma** (quanti qualificati, quali posizioni) e mai su chi
incontra chi o su chi vince.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from campionato_driver import CampionatoDriver
from models.playoff.models import QualificationStatus
from models.status_enum import GaraStatus, MatchStatus
from models.user.role_enum import UserRole

GIOCATORI = 8
GARE = 4
TURNI = 3
#: Rack di ogni partita, in formato «esattamente N» (non «al N»).
DISTANZA = 5
#: Quanti ne porta ai playoff la configurazione Elite del wizard. Sei e non
#: quattro perché `DEFAULT_MIN_PARTICIPANTS` è 6: una finale con meno iscritti
#: si crea ma non si avvia, e questi test la finale la giocano davvero.
QUALIFICATI = 6


def _data_gara(numero: int) -> str:
    """Le gare di un campionato sono in ordine cronologico (ADR-016)."""
    return (date.today() + timedelta(days=7 * numero)).isoformat()


def _allestisci(campionato: CampionatoDriver, quante_gare: int):
    """Un campionato con `quante_gare` gare Amalfi giocate, e terminato."""
    direttore = campionato.crea_utente(UserRole.DIRECTOR.value)
    giocatori = campionato.crea_giocatori(GIOCATORI)

    campionato.entra(direttore)
    campionato_id = campionato.crea_campionato(
        planned_gare_count=quante_gare,
        playoff_elite_enabled="on",
        playoff_elite_participants=QUALIFICATI,
    )

    for numero in range(1, quante_gare + 1):
        gara_id = campionato.crea_gara_di_campionato(
            campionato_id,
            numero,
            date=_data_gara(numero),
            distance=DISTANZA,
            exact_number="1",
            rounds_count=TURNI,
            min_participants=4,
        )
        campionato.gioca_gara_intera(gara_id, direttore, giocatori, TURNI)

    campionato.entra(direttore)
    campionato.termina_campionato(campionato_id)
    return campionato_id, direttore, giocatori


@pytest.fixture
def campionato_terminato(campionato: CampionatoDriver):
    """Quattro gare Amalfi giocate per intero, campionato terminato.

    È l'allestimento più caro della suite — 8 giocatori × 3 turni × 4 gare = 48
    partite segnate rack per rack via HTTP — quindi lo usano solo i test in cui
    le *quattro* gare contano davvero. Agli altri basta `campionato_breve`.
    """
    return _allestisci(campionato, GARE)


@pytest.fixture
def campionato_breve(campionato: CampionatoDriver):
    """Una gara sola: quanto basta per avere una classifica e dei playoff.

    I test dei permessi e dei vincoli sulla lista non guardano quante gare si
    sono giocate, e replicare un campionato intero per ciascuno costerebbe
    quattro volte tanto senza dire niente di più.
    """
    return _allestisci(campionato, 1)


@pytest.mark.e2e
class TestQuattroGareAmalfiUguali:
    """Le quattro gare sono la stessa gara quattro volte: forma e formato."""

    def test_il_campionato_si_gioca_e_si_chiude(
        self, campionato: CampionatoDriver, campionato_terminato
    ):
        campionato_id, _direttore, giocatori = campionato_terminato

        gare = campionato.gare_del_campionato(campionato_id)
        assert [gara.number for gara in gare] == list(range(1, GARE + 1))
        assert all(gara.status == GaraStatus.COMPLETED.value for gara in gare)

        for gara in gare:
            partite = campionato.partite(gara.id)
            # Tre turni da quattro partite: otto giocatori, nessun bye.
            assert campionato.turni_creati(gara.id) == set(range(1, TURNI + 1))
            assert len(partite) == TURNI * (GIOCATORI // 2)
            assert all(MatchStatus.is_finished(p.status) for p in partite)

        assert campionato.campionato(campionato_id).terminated_at is not None

        # Tutti e otto compaiono nella classifica generale, con le posizioni
        # assegnate da 1 in poi e senza buchi.
        classifica = campionato.classifica_generale(campionato_id)
        assert {riga.user_id for riga in classifica} == {g.id for g in giocatori}
        assert [riga.position for riga in classifica] == list(range(1, GIOCATORI + 1))

        # E la pagina che il direttore apre dopo la premiazione regge: è quella
        # da cui poi partiranno i playoff.
        assert "html" in campionato.pagina_campionato(campionato_id).lower()

    def test_ogni_partita_e_esattamente_cinque_rack(
        self, campionato: CampionatoDriver, campionato_terminato
    ):
        """Il formato configurato è quello che le partite hanno davvero usato.

        La firma di «esattamente N» è la somma: i rack giocati sono sempre
        cinque. In un «al 5» la somma starebbe fra 5 e 9 e il vincitore avrebbe
        sempre 5, perché la partita si chiuderebbe lì.
        """
        campionato_id, _direttore, _ = campionato_terminato

        punteggi = [
            (partita.player1_score, partita.player2_score)
            for gara in campionato.gare_del_campionato(campionato_id)
            for partita in campionato.partite(gara.id)
        ]

        assert punteggi, "nessuna partita giocata: l'allestimento è rotto"
        assert all(uno + due == DISTANZA for uno, due in punteggi)
        # Un 5-0 è legittimo anche a rack esatti, quindi da solo non prova
        # niente. La prova è che *esista* almeno una partita vinta senza
        # arrivare a cinque: in un «al 5» non potrebbe esistere.
        assert any(
            max(uno, due) < DISTANZA for uno, due in punteggi
        ), "nessuna partita chiusa sotto la distanza: sembra un race-to, non un esatto"

    def test_le_gare_condividono_turni_e_distanza(
        self, campionato: CampionatoDriver, campionato_terminato
    ):
        campionato_id, _direttore, _ = campionato_terminato

        for gara in campionato.gare_del_campionato(campionato_id):
            assert gara.rounds_count == TURNI
            assert gara.distance == DISTANZA
            assert gara.is_race_to is False


@pytest.mark.e2e
class TestAvvioDeiPlayoff:
    """Dalla classifica generale alle qualificazioni, passando dalle route."""

    def test_i_qualificati_sono_i_primi_della_classifica(
        self, campionato: CampionatoDriver, campionato_terminato
    ):
        campionato_id, direttore, _ = campionato_terminato

        campionato.entra(direttore)
        campionato.avvia_playoff(campionato_id)

        (configurazione,) = campionato.configurazioni_playoff(campionato_id)
        qualificazioni = campionato.qualificazioni(configurazione.id)

        assert len(qualificazioni) == QUALIFICATI
        # Chi arriva primo lo decide il campo: si asserisce che i qualificati
        # siano *le prime posizioni*, non quali giocatori le occupino.
        assert sorted(q.qualifying_position for q in qualificazioni) == list(
            range(1, QUALIFICATI + 1)
        )
        classifica = campionato.classifica_generale(campionato_id)
        assert {q.user_id for q in qualificazioni} == {
            riga.user_id for riga in classifica[:QUALIFICATI]
        }

    def test_prima_di_confermare_nessuno_e_dentro(
        self, campionato: CampionatoDriver, campionato_breve
    ):
        """L'invito è un invito: finché non c'è risposta, la lista è vuota.

        È la premessa dell'altro percorso — quello in cui il direttore la lista
        se la scrive da solo: senza conferme la finale nascerebbe deserta.
        """
        campionato_id, direttore, _ = campionato_breve

        campionato.entra(direttore)
        campionato.avvia_playoff(campionato_id)
        (configurazione,) = campionato.configurazioni_playoff(campionato_id)

        assert all(
            q.status == QualificationStatus.PENDING
            for q in campionato.qualificazioni(configurazione.id)
        )
        assert campionato.qualificati_confermati(configurazione.id) == []

    def test_i_playoff_non_si_avviano_due_volte(
        self, campionato: CampionatoDriver, campionato_breve
    ):
        campionato_id, direttore, _ = campionato_breve

        campionato.entra(direttore)
        campionato.avvia_playoff(campionato_id)
        (configurazione,) = campionato.configurazioni_playoff(campionato_id)
        prima = len(campionato.qualificazioni(configurazione.id))

        campionato.avvia_playoff(campionato_id)

        assert len(campionato.qualificazioni(configurazione.id)) == prima

    def test_un_giocatore_non_avvia_i_playoff(
        self, campionato: CampionatoDriver, campionato_breve
    ):
        campionato_id, _direttore, giocatori = campionato_breve

        campionato.entra(giocatori[0])
        risposta = campionato.client.post(
            f"/admin/campionato/{campionato_id}/start-playoff"
        )

        assert risposta.status_code == 403
        (configurazione,) = campionato.configurazioni_playoff(campionato_id)
        assert campionato.qualificazioni(configurazione.id) == []


@pytest.mark.e2e
class TestPercorsoConLeConferme:
    """Il percorso previsto: si invita, i giocatori accettano, si gioca."""

    def test_dalla_conferma_alla_finale_giocata(
        self, campionato: CampionatoDriver, campionato_terminato
    ):
        campionato_id, direttore, giocatori = campionato_terminato
        per_id = {giocatore.id: giocatore for giocatore in giocatori}

        campionato.entra(direttore)
        campionato.avvia_playoff(campionato_id)
        (configurazione,) = campionato.configurazioni_playoff(campionato_id)

        # Ciascuno apre il suo invito e accetta, come dalla notifica.
        for qualificazione in campionato.qualificazioni(configurazione.id):
            invitato = per_id[qualificazione.user_id]
            pagina = campionato.invito_playoff(qualificazione.id, invitato)
            assert pagina.status_code == 200
            campionato.conferma_playoff(qualificazione.id, invitato)

        confermati = campionato.qualificati_confermati(configurazione.id)
        assert len(confermati) == QUALIFICATI

        campionato.entra(direttore)
        gara_playoff = campionato.crea_gara_playoff(campionato_id, configurazione.id)

        # Chi ha confermato è iscritto, e nessun altro.
        assert campionato.iscritti(gara_playoff) == {q.user_id for q in confermati}

        # La finale eredita il formato del campionato, che nessuno le ha
        # ridetto: tre turni, esattamente cinque rack.
        gara = campionato.gara(gara_playoff)
        assert gara.distance == DISTANZA
        assert gara.is_race_to is False
        assert gara.rounds_count == TURNI

        # E si gioca fino in fondo, come le altre.
        campionato.gioca_gara_gia_iscritta(gara_playoff, direttore, TURNI)

        partite = campionato.partite(gara_playoff)
        assert len(partite) == TURNI * (QUALIFICATI // 2)
        assert all(MatchStatus.is_finished(p.status) for p in partite)
        assert all(
            p.player1_score + p.player2_score == DISTANZA for p in partite
        ), "la finale non ha ereditato «esattamente 5 rack»"

    def test_chi_rifiuta_resta_fuori(
        self, campionato: CampionatoDriver, campionato_breve
    ):
        campionato_id, direttore, giocatori = campionato_breve
        per_id = {giocatore.id: giocatore for giocatore in giocatori}

        campionato.entra(direttore)
        campionato.avvia_playoff(campionato_id)
        (configurazione,) = campionato.configurazioni_playoff(campionato_id)

        qualificazioni = campionato.qualificazioni(configurazione.id)
        rinunciatario = qualificazioni[0]
        campionato.rifiuta_playoff(rinunciatario.id, per_id[rinunciatario.user_id])
        for qualificazione in qualificazioni[1:]:
            campionato.conferma_playoff(
                qualificazione.id, per_id[qualificazione.user_id]
            )

        campionato.entra(direttore)
        gara_playoff = campionato.crea_gara_playoff(campionato_id, configurazione.id)

        assert rinunciatario.user_id not in campionato.iscritti(gara_playoff)


@pytest.mark.e2e
class TestListaSceltaDalDirettore:
    """Il direttore compone la lista da sé, senza aspettare le risposte.

    È il percorso vero di molte serate: la finale si gioca la settimana dopo e
    chi c'è lo si sa perché lo si è chiesto a voce. `admin_add_player` esiste
    apposta e scrive la qualificazione **già confermata**, saltando l'invito —
    quindi il direttore può anche non avviare mai i playoff.
    """

    def test_il_direttore_iscrive_chi_vuole_e_la_gara_nasce_piena(
        self, campionato: CampionatoDriver, campionato_terminato
    ):
        campionato_id, direttore, giocatori = campionato_terminato

        campionato.entra(direttore)
        (configurazione,) = campionato.configurazioni_playoff(campionato_id)

        # Nessun `avvia_playoff`: la lista la scrive il direttore, e la scrive
        # come vuole lui — qui gli **ultimi** della classifica, che il criterio
        # automatico (prime sei posizioni) non avrebbe scelto tutti.
        classifica = campionato.classifica_generale(campionato_id)
        per_id = {giocatore.id: giocatore for giocatore in giocatori}
        scelti = [per_id[riga.user_id] for riga in classifica[-QUALIFICATI:]]
        for giocatore in scelti:
            campionato.aggiungi_al_playoff(campionato_id, configurazione.id, giocatore)

        qualificazioni = campionato.qualificazioni(configurazione.id)
        assert len(qualificazioni) == QUALIFICATI
        assert all(
            q.status == QualificationStatus.CONFIRMED for q in qualificazioni
        ), "aggiunto dal direttore è già dentro: non c'è nessun invito da attendere"

        gara_playoff = campionato.crea_gara_playoff(campionato_id, configurazione.id)
        assert campionato.iscritti(gara_playoff) == {g.id for g in scelti}

        # E la finale così composta si gioca come le altre.
        campionato.gioca_gara_gia_iscritta(gara_playoff, direttore, TURNI)
        assert all(
            MatchStatus.is_finished(partita.status)
            for partita in campionato.partite(gara_playoff)
        )

    def test_lo_stesso_giocatore_non_si_aggiunge_due_volte(
        self, campionato: CampionatoDriver, campionato_breve
    ):
        campionato_id, direttore, giocatori = campionato_breve

        campionato.entra(direttore)
        (configurazione,) = campionato.configurazioni_playoff(campionato_id)
        campionato.aggiungi_al_playoff(campionato_id, configurazione.id, giocatori[0])

        html = campionato.aggiungi_al_playoff(
            campionato_id, configurazione.id, giocatori[0]
        )

        assert "già presente" in html
        assert len(campionato.qualificazioni(configurazione.id)) == 1

    def test_chi_non_ha_giocato_il_campionato_non_si_aggiunge(
        self, campionato: CampionatoDriver, campionato_breve
    ):
        campionato_id, direttore, _ = campionato_breve
        estraneo = campionato.crea_utente(UserRole.PLAYER.value)

        campionato.entra(direttore)
        (configurazione,) = campionato.configurazioni_playoff(campionato_id)

        html = campionato.aggiungi_al_playoff(
            campionato_id, configurazione.id, estraneo
        )

        assert "non ha partecipato" in html
        assert campionato.qualificazioni(configurazione.id) == []

    def test_il_direttore_toglie_un_invitato_e_ne_mette_un_altro(
        self, campionato: CampionatoDriver, campionato_breve
    ):
        """Il caso misto: si invita, uno non risponde, il direttore rimedia."""
        campionato_id, direttore, giocatori = campionato_breve
        per_id = {giocatore.id: giocatore for giocatore in giocatori}

        campionato.entra(direttore)
        campionato.avvia_playoff(campionato_id)
        (configurazione,) = campionato.configurazioni_playoff(campionato_id)

        qualificazioni = campionato.qualificazioni(configurazione.id)
        silenzioso = qualificazioni[-1]
        for qualificazione in qualificazioni[:-1]:
            campionato.conferma_playoff(
                qualificazione.id, per_id[qualificazione.user_id]
            )

        campionato.entra(direttore)
        campionato.rimuovi_dal_playoff(campionato_id, configurazione.id, silenzioso.id)

        invitati = {q.user_id for q in campionato.qualificazioni(configurazione.id)}
        ripescato = next(g for g in giocatori if g.id not in invitati)
        campionato.aggiungi_al_playoff(campionato_id, configurazione.id, ripescato)

        gara_playoff = campionato.crea_gara_playoff(campionato_id, configurazione.id)
        iscritti = campionato.iscritti(gara_playoff)

        assert ripescato.id in iscritti
        assert silenzioso.user_id not in iscritti
        assert len(iscritti) == QUALIFICATI

    def test_a_gara_creata_la_lista_non_si_tocca_piu(
        self, campionato: CampionatoDriver, campionato_breve
    ):
        campionato_id, direttore, giocatori = campionato_breve

        campionato.entra(direttore)
        (configurazione,) = campionato.configurazioni_playoff(campionato_id)
        for giocatore in giocatori[:QUALIFICATI]:
            campionato.aggiungi_al_playoff(campionato_id, configurazione.id, giocatore)
        campionato.crea_gara_playoff(campionato_id, configurazione.id)

        html = campionato.aggiungi_al_playoff(
            campionato_id, configurazione.id, giocatori[-1]
        )

        assert "dopo creazione gara" in html
        assert len(campionato.qualificazioni(configurazione.id)) == QUALIFICATI


@pytest.mark.e2e
class TestChiusuraDellaFinale:
    """Chiudere la finale non è come chiudere una gara del campionato."""

    def test_la_finale_nasce_con_lo_spareggio_acceso(
        self, campionato: CampionatoDriver, campionato_breve
    ):
        """La finale non eredita tutto, e su un punto diverge senza dirlo.

        Le gare create dal form arrivano con lo spareggio SSR **spento**
        (`tiebreaker_enabled` è una casella non spuntata, quindi assente). La
        gara di playoff non passa da nessun form: `create_playoff_gara`
        eredita disciplina, distanza, turni, strategia, dispari, sede e quota,
        e per tutto il resto prende i default del modello — fra cui lo
        spareggio **acceso**.

        È difendibile (una finale i pari merito li deve sciogliere) ma nessuno
        l'ha scelto. Questo test tiene ferma la divergenza, così se un domani
        l'ereditarietà venisse completata la cosa si nota subito.

        Che poi lo spareggio *serva* dipende dai risultati, non dal formato:
        con la classifica a vittorie due giocatori sono pari merito solo se
        hanno le **stesse vittorie e la stessa differenza triangoli**. Qui si
        chiude con `chiudi_gara`, che è la sequenza del direttore — termina, e
        se ci sono pari merito li scioglie e ritermina — e si guarda solo che
        la finale arrivi in fondo.
        """
        campionato_id, direttore, giocatori = campionato_breve

        campionato.entra(direttore)
        (configurazione,) = campionato.configurazioni_playoff(campionato_id)
        for giocatore in giocatori[:QUALIFICATI]:
            campionato.aggiungi_al_playoff(campionato_id, configurazione.id, giocatore)
        gara_playoff = campionato.crea_gara_playoff(campionato_id, configurazione.id)

        finale = campionato.gara(gara_playoff)
        assert finale.tiebreaker_enabled is True
        # Le gare del campionato, nate dal form, lo hanno spento.
        assert all(
            gara.tiebreaker_enabled is False
            for gara in campionato.gare_del_campionato(campionato_id)
            if gara.playoff_config_id is None
        )

        campionato.gioca_gara_gia_iscritta(gara_playoff, direttore, TURNI)

        assert campionato.chiudi_gara(gara_playoff) == GaraStatus.COMPLETED.value
