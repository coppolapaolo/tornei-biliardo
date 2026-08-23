"""Due domande sul motore della gara: cosa vale la X, e come abbina Amalfi.

Entrambe hanno una risposta osservabile dall'esterno, ed entrambe cambiano la
classifica di chi gioca — quindi vale la pena che siano fissate da un test e
non affidate alla lettura del codice.

**La X.** Chi resta spaiato vince a tavolino. Quanto valga quella vittoria in
classifica non è ovvio: una vittoria, certo, ma quanti triangoli? La classifica
a vittorie ordina per `(vittorie, differenza triangoli)`, quindi la risposta
decide se chi riposa scavalca o no chi ha vinto giocando.

**Amalfi.** Il formato dichiara due cose: che due giocatori non si
reincontrano, e che gli abbinamenti seguono la classifica del turno precedente
con un «salto» che si accorcia man mano — `salto = turni_totali − turno + 1`.
La prima è una garanzia, la seconda è un criterio di ottimo, e si possono
verificare tutte e due sul campo invece che sulla carta.

Un avvertimento che vale per tutto il file: la garanzia anti-reincontro di
ADR-029 riguarda il **caso pari**, dove il sorteggio risolve un matching di
peso massimo sul grafo dei non-incontri. Con un numero **dispari** di giocatori
— che è il caso della stagione, quindici — il sentinella della X viene aggiunto
*dopo* quel controllo, quindi si prende la strada greedy, dove l'anti-reincontro
è un tentativo e non una garanzia. I due casi hanno quindi due classi di test
diverse, ed è deliberato.
"""

from __future__ import annotations

import pytest

from campionato_driver import CampionatoDriver
from stagione import TURNI, crea_stagione
from models.user.role_enum import UserRole

#: Dispari: ogni turno una X. Sette e non quindici perché la proprietà è la
#: stessa e costa un terzo.
GIOCATORI_DISPARI = 7
#: Pari: è il caso in cui ADR-029 promette zero reincontri.
GIOCATORI_PARI = 8
#: La distanza della prima gara della stagione.
DISTANZA = 5


def _gioca_gara(campionato: CampionatoDriver, gara_id: int, direttore, giocatori):
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


@pytest.fixture
def gara_dispari(campionato: CampionatoDriver):
    """Prima gara della stagione con sette iscritti, tre turni giocati."""
    direttore = campionato.crea_utente(UserRole.DIRECTOR.value)
    _campionato_id, gare = crea_stagione(campionato, direttore)
    giocatori = campionato.crea_giocatori(GIOCATORI_DISPARI)
    _gioca_gara(campionato, gare[1], direttore, giocatori)
    return gare[1], direttore, giocatori


@pytest.fixture
def gara_pari(campionato: CampionatoDriver):
    """Prima gara della stagione con otto iscritti, tre turni giocati."""
    direttore = campionato.crea_utente(UserRole.DIRECTOR.value)
    _campionato_id, gare = crea_stagione(campionato, direttore)
    giocatori = campionato.crea_giocatori(GIOCATORI_PARI)
    _gioca_gara(campionato, gare[1], direttore, giocatori)
    return gare[1], direttore, giocatori


def _chi_ha_preso_la_x(campionato: CampionatoDriver, gara_id: int, turno: int) -> int:
    (con_la_x,) = [p for p in campionato.partite(gara_id, turno=turno) if p.is_bye]
    return con_la_x.player1_id


def _riga(classifica, user_id):
    (voce,) = [riga for riga in classifica if riga.user_id == user_id]
    return voce


@pytest.mark.e2e
class TestQuantoValeLaX:
    """La X dà una vittoria — e, oggi, anche i triangoli della distanza."""

    def test_la_x_vale_una_vittoria(self, campionato: CampionatoDriver, gara_dispari):
        gara_id, _direttore, _giocatori = gara_dispari
        riposato = _chi_ha_preso_la_x(campionato, gara_id, 1)

        classifica = campionato.classifica_di_turno(gara_id, 1)

        assert _riga(classifica, riposato).matches_won == 1

    def test_oggi_la_x_porta_in_dote_anche_i_triangoli_della_distanza(
        self, campionato: CampionatoDriver, gara_dispari
    ):
        """Il comportamento attuale, fissato perché si veda quando cambia.

        La partita con la X nasce con `player1_score = distanza` e nessun
        avversario; `ScoreAggregator._process_bye_match` somma quei triangoli
        ai vinti e non ne conta nessuno di persi. Risultato: chi riposa entra
        in classifica con **+5 di differenza**, mentre chi ha vinto giocando
        un 3-2 ne ha **+1**.
        """
        gara_id, _direttore, _giocatori = gara_dispari
        riposato = _chi_ha_preso_la_x(campionato, gara_id, 1)

        riga = _riga(campionato.classifica_di_turno(gara_id, 1), riposato)

        assert riga.racks_won == DISTANZA
        assert riga.rack_difference == DISTANZA

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "Rilievo aperto: la X dovrebbe valere una vittoria e differenza "
            "triangoli ZERO. Oggi vale una vittoria e +distanza, quindi chi "
            "riposa scavalca in classifica chi ha vinto giocando a parità di "
            "vittorie. La correzione sta in "
            "ScoreAggregator._process_bye_match e cambia le classifiche di "
            "tutte le gare con numero dispari: è una decisione di prodotto, "
            "non una svista da correggere di nascosto."
        ),
    )
    def test_la_x_non_dovrebbe_spostare_la_differenza_triangoli(
        self, campionato: CampionatoDriver, gara_dispari
    ):
        gara_id, _direttore, _giocatori = gara_dispari
        riposato = _chi_ha_preso_la_x(campionato, gara_id, 1)

        riga = _riga(campionato.classifica_di_turno(gara_id, 1), riposato)

        assert riga.rack_difference == 0

    def test_a_parita_di_vittorie_chi_ha_riposato_sta_davanti(
        self, campionato: CampionatoDriver, gara_dispari
    ):
        """La conseguenza visibile, ed è quella che conta in sala.

        Dopo il primo turno tutti quelli che hanno vinto hanno una vittoria: chi
        ha vinto giocando ha differenza pari al suo margine (da +1 a +5), chi ha
        riposato ha +5 pieni. La X quindi non è neutra: vale come la vittoria
        più larga possibile.
        """
        gara_id, _direttore, _giocatori = gara_dispari
        riposato = _chi_ha_preso_la_x(campionato, gara_id, 1)
        classifica = campionato.classifica_di_turno(gara_id, 1)

        con_una_vittoria = [riga for riga in classifica if riga.matches_won == 1]
        differenze = {riga.user_id: riga.rack_difference for riga in con_una_vittoria}

        assert differenze[riposato] == DISTANZA
        assert differenze[riposato] >= max(differenze.values())

    def test_nessuno_prende_la_x_due_volte(
        self, campionato: CampionatoDriver, gara_dispari
    ):
        """Con tre turni e sette giocatori le X sono tre, a tre persone diverse.

        È una regola esplicita del sorteggio (`_get_players_with_bye`), non un
        effetto del caso: senza, in una gara lunga qualcuno accumulerebbe
        vittorie a tavolino.
        """
        gara_id, _direttore, _giocatori = gara_dispari

        riposati = [
            _chi_ha_preso_la_x(campionato, gara_id, turno)
            for turno in range(1, TURNI + 1)
        ]

        assert len(set(riposati)) == len(riposati), riposati


@pytest.mark.e2e
class TestAmalfiNonFaRigiocareGliStessi:
    def test_col_numero_pari_nessuno_reincontra_nessuno(
        self, campionato: CampionatoDriver, gara_pari
    ):
        """La garanzia di ADR-029, nel caso in cui è una garanzia."""
        gara_id, _direttore, _giocatori = gara_pari

        incontri = [
            frozenset((partita.player1_id, partita.player2_id))
            for turno in range(1, TURNI + 1)
            for partita in campionato.partite(gara_id, turno=turno)
            if not partita.is_bye
        ]

        assert len(set(incontri)) == len(incontri), "due giocatori si sono rincontrati"

    def test_col_numero_dispari_neanche(
        self, campionato: CampionatoDriver, gara_dispari
    ):
        """Qui non è una garanzia, ma con sette giocatori e tre turni deve
        comunque riuscirci: il greedy ha spazio di manovra abbondante.

        Se un giorno questo test diventasse rosso non sarebbe una regressione
        del test: sarebbe il segnale che la strada greedy del caso dispari ha
        esaurito le combinazioni prima del previsto.
        """
        gara_id, _direttore, _giocatori = gara_dispari

        incontri = [
            frozenset((partita.player1_id, partita.player2_id))
            for turno in range(1, TURNI + 1)
            for partita in campionato.partite(gara_id, turno=turno)
            if not partita.is_bye
        ]

        assert len(set(incontri)) == len(incontri), "due giocatori si sono rincontrati"

    def test_ogni_turno_tutti_scendono_in_campo(
        self, campionato: CampionatoDriver, gara_dispari
    ):
        gara_id, _direttore, giocatori = gara_dispari

        for turno in range(1, TURNI + 1):
            partite = campionato.partite(gara_id, turno=turno)
            in_campo: list[int] = []
            for partita in partite:
                in_campo.append(partita.player1_id)
                if partita.player2_id:
                    in_campo.append(partita.player2_id)
            assert sorted(in_campo) == sorted(g.id for g in giocatori), f"turno {turno}"


@pytest.mark.e2e
class TestAmalfiRispettaIlSalto:
    """Il criterio: abbinare secondo la classifica, col salto del turno.

    Il salto vale `turni_totali − turno + 1`, quindi 2 al secondo turno e 1 al
    terzo. Nel caso pari il sorteggio risolve un **matching di peso massimo**
    sul grafo dei non-incontri, dove il peso premia le coppie la cui distanza
    in classifica è vicina al salto: fra tutti gli accoppiamenti possibili
    senza reincontri, sceglie quello che **minimizza lo scarto complessivo dal
    salto**.

    È una proprietà di ottimo, e come tale si verifica per confronto: si
    enumerano tutti gli accoppiamenti ammissibili e si controlla che quello
    prodotto sia fra i migliori. Con otto giocatori sono 105 combinazioni.
    """

    @staticmethod
    def _scarto(coppie, posizione, salto: int) -> int:
        return sum(abs(abs(posizione[a] - posizione[b]) - salto) for a, b in coppie)

    @classmethod
    def _scarto_minimo(cls, giocatori, gia_visti, posizione, salto: int) -> int:
        """Lo scarto del miglior accoppiamento senza reincontri, per forza bruta."""
        migliore = [None]

        def cerca(rimasti, coppie):
            if not rimasti:
                valore = cls._scarto(coppie, posizione, salto)
                if migliore[0] is None or valore < migliore[0]:
                    migliore[0] = valore
                return
            primo, resto = rimasti[0], rimasti[1:]
            for indice, altro in enumerate(resto):
                if frozenset((primo, altro)) in gia_visti:
                    continue
                cerca(resto[:indice] + resto[indice + 1 :], coppie + [(primo, altro)])

        cerca(list(giocatori), [])
        return migliore[0]

    def test_il_secondo_turno_e_il_migliore_accoppiamento_possibile(
        self, campionato: CampionatoDriver, gara_pari
    ):
        gara_id, _direttore, _giocatori = gara_pari
        salto = TURNI - 2 + 1

        classifica = campionato.classifica_di_turno(gara_id, 1)
        posizione = {riga.user_id: indice for indice, riga in enumerate(classifica)}
        gia_visti = {
            frozenset((p.player1_id, p.player2_id))
            for p in campionato.partite(gara_id, turno=1)
            if not p.is_bye
        }

        coppie = [
            (p.player1_id, p.player2_id)
            for p in campionato.partite(gara_id, turno=2)
            if not p.is_bye
        ]
        assert coppie

        atteso = self._scarto_minimo(list(posizione), gia_visti, posizione, salto)
        assert self._scarto(coppie, posizione, salto) == atteso

    def test_il_terzo_turno_stringe_il_salto_a_uno(
        self, campionato: CampionatoDriver, gara_pari
    ):
        """Al terzo turno il salto è 1: si abbina chi è vicino in classifica."""
        gara_id, _direttore, _giocatori = gara_pari
        salto = TURNI - 3 + 1
        assert salto == 1

        classifica = campionato.classifica_di_turno(gara_id, 2)
        posizione = {riga.user_id: indice for indice, riga in enumerate(classifica)}
        gia_visti = {
            frozenset((p.player1_id, p.player2_id))
            for turno in (1, 2)
            for p in campionato.partite(gara_id, turno=turno)
            if not p.is_bye
        }

        coppie = [
            (p.player1_id, p.player2_id)
            for p in campionato.partite(gara_id, turno=3)
            if not p.is_bye
        ]

        atteso = self._scarto_minimo(list(posizione), gia_visti, posizione, salto)
        assert self._scarto(coppie, posizione, salto) == atteso

    def test_il_primo_turno_invece_e_sorteggiato(
        self, campionato: CampionatoDriver, gara_pari
    ):
        """Nessuna classifica da cui partire: il primo turno è casuale.

        Si asserisce sulla forma, non sugli accoppiamenti: quattro partite,
        tutti in campo una volta sola.
        """
        gara_id, _direttore, giocatori = gara_pari

        partite = campionato.partite(gara_id, turno=1)

        assert len(partite) == GIOCATORI_PARI // 2
        in_campo = [p.player1_id for p in partite] + [p.player2_id for p in partite]
        assert sorted(in_campo) == sorted(g.id for g in giocatori)
