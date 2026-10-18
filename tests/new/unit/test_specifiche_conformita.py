"""Le regole numeriche di SPECIFICHE.md, rese eseguibili.

Questo modulo esiste per una ragione precisa, ed è un guasto già capitato due
volte: **la specifica è prosa, e la prosa perde sempre contro un test.**

Il meccanismo, osservato dal vivo:

1. `docs/reference/SPECIFICHE.md` fissa una regola numerica — quanto vale la X
   in classifica, a chi passa l'invito ai playoff quando qualcuno rifiuta.
2. L'implementazione ne scrive un'altra. Nessuno se ne accorge, perché nessun
   test confronta il codice con la specifica: i test confrontano il codice con
   sé stesso.
3. Prima o poi una code review trova **due parti del codice incoerenti fra
   loro** e le allinea. Se allinea alla parte sbagliata, aggiunge un test di
   regressione che da quel momento **difende la deviazione**: chi provasse a
   correggere vedrebbe un test rosso con una motivazione scritta bene, e si
   fermerebbe.

Il rimedio è togliere alla specifica il ruolo di documento e darle quello di
test. Ogni test qui sotto **cita la riga di SPECIFICHE.md che verifica**, così
che la catena sia percorribile nei due sensi: dal codice alla regola, e dalla
regola al codice.

Regole d'uso, brevi:

* **Un test per regola**, con la citazione nel docstring. Se la regola cambia
  si cambia la specifica *e* il test, nello stesso commit.
* **Una divergenza trovata si scrive `xfail(strict=True)`**, mai si silenzia e
  mai si «adatta» il test al codice. `strict` fa scattare la suite il giorno in
  cui qualcuno corregge, così il test diventa da solo la regressione.
* **Se una regola nella specifica non c'è**, non si inventa qui: si scrive
  prima nella specifica. Un test senza citazione, in questo file, è fuori posto.
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest

from models.classification.score_aggregator import ScoreAggregator
from models.competition.models import Gara, Inscription
from models.competition.spareggio_service import SpareggioService
from models.matchmaking import bye_preference
from models.status_enum import Discipline, GaraStatus, MatchStatus
from models.match.models import Match
from models.playoff.models import (
    PlayoffConfiguration,
    PlayoffQualification,
    PlayoffType,
    QualificationStatus,
)
from models.playoff.services import PlayoffService
from models.user.models import User
from models.user.role_enum import UserRole

SPEC = "docs/reference/SPECIFICHE.md"


def _utente(db_session) -> User:
    sigla = uuid.uuid4().hex[:8]
    utente = User(
        username=f"spec_{sigla}",
        email=f"spec_{sigla}@test.local",
        role=UserRole.PLAYER.value,
    )
    utente.set_password("prova1234")
    db_session.add(utente)
    db_session.flush()
    return utente


def _gara(db_session, *, distanza: int = 5, sistema: str = "WINS") -> Gara:
    quante = db_session.query(Gara).count()
    gara = Gara(
        name=f"Gara spec {quante + 1}",
        number=quante + 1,
        date=date.today(),
        discipline=Discipline.NINE_BALL.value,
        distance=distanza,
        is_race_to=False,
        status=GaraStatus.PLAYING.value,
        rounds_count=3,
        current_round=1,
        classification_system=sistema,
        matchmaking_strategy="amalfi",
        odd_number_policy="bye",
    )
    db_session.add(gara)
    db_session.flush()
    return gara


def _punteggi(gara_id: int, fino_al_turno: int = 1) -> dict[int, object]:
    return {
        voce.player_id: voce
        for voce in ScoreAggregator().aggregate_round_scores(gara_id, fino_al_turno)
    }


# ══ Classifica: i tre sistemi ════════════════════════════════════════════


@pytest.mark.unit
class TestSistemiDiClassifica:
    def test_wins_ordina_per_vittorie_poi_differenza_rack(self, db_session):
        """`SPECIFICHE.md` riga 168.

        > **WINS**: ordina per match vinti (decrescente), poi differenza rack
        > (decrescente), poi spareggio

        La chiave di pari merito deve essere la **coppia**: due giocatori sono
        pari merito solo se coincidono entrambi i criteri. È la regola che il
        driver dei test e2e fa rispettare variando i margini delle partite —
        con tutte le partite allo stesso margine la differenza rack diventa una
        funzione delle vittorie e il secondo criterio non discrimina più.
        """
        gara = _gara(db_session)
        primo, secondo = _utente(db_session), _utente(db_session)
        terzo, quarto = _utente(db_session), _utente(db_session)
        for casa, fuori, in_casa, fuori_casa in (
            (primo, secondo, 4, 1),  # 1 vittoria, +3
            (terzo, quarto, 3, 2),  # 1 vittoria, +1
        ):
            db_session.add(
                Match(
                    gara_id=gara.id,
                    round_number=1,
                    player1_id=casa.id,
                    player2_id=fuori.id,
                    player1_score=in_casa,
                    player2_score=fuori_casa,
                    winner_id=casa.id,
                    status=MatchStatus.CLOSED_UNILATERALLY.value,
                )
            )
        db_session.commit()

        punteggi = _punteggi(gara.id)

        # Stesse vittorie, differenza diversa: non sono pari merito.
        assert punteggi[primo.id].matches_won == punteggi[terzo.id].matches_won == 1
        assert punteggi[primo.id].rack_difference == 3
        assert punteggi[terzo.id].rack_difference == 1

    def test_la_chiave_di_pari_merito_wins_e_la_coppia(self, db_session):
        """`SPECIFICHE.md` riga 168, dal lato dello spareggio.

        Lo spareggio deve raggruppare su `(match vinti, differenza rack)`, non
        sulla sola differenza: raggruppare su un criterio solo genererebbe
        pari merito che non esistono.
        """
        gara = _gara(db_session)
        db_session.commit()

        assert SpareggioService.tiebreakers_apply_to(gara) is True


# ══ Classifica: come si risolvono i pari merito ══════════════════════════


def _partita(db_session, gara, vince, perde, persi: int, turno: int = 1) -> None:
    db_session.add(
        Match(
            gara_id=gara.id,
            round_number=turno,
            player1_id=vince.id,
            player2_id=perde.id,
            player1_score=gara.distance,
            player2_score=persi,
            winner_id=vince.id,
            status=MatchStatus.CLOSED_UNILATERALLY.value,
        )
    )


@pytest.mark.unit
class TestCateneDegliSpareggi:
    """`SPECIFICHE.md`, «Classifica», «Come si risolvono i pari merito»."""

    @pytest.mark.parametrize(
        "livello, sistema, attesa",
        [
            ("turno", "WINS", ["differenza_rack", "posizione_precedente", "sorteggio"]),
            ("turno", "RACK", ["posizione_precedente", "sorteggio"]),
            ("gara", "WINS", ["differenza_rack", "ssr:3"]),
            ("gara", "RACK", ["ssr:3"]),
            (
                "campionato",
                "WINS",
                ["differenza_rack", "ssr", "posizione_precedente", "sorteggio"],
            ),
            ("campionato", "RACK", ["ssr", "posizione_precedente", "sorteggio"]),
        ],
    )
    def test_la_tabella_delle_catene(self, livello, sistema, attesa):
        """La tabella: una catena per classifica e per sistema."""
        from models.classification.ordinamento import (
            Livello,
            catena_di_default,
            serializza_catena,
        )
        from models.status_enum import ClassificationSystem

        assert (
            serializza_catena(
                catena_di_default(Livello(livello), ClassificationSystem(sistema))
            )
            == attesa
        )

    def test_nel_turno_a_rack_non_contano_ne_lo_ssr_ne_la_differenza(self, db_session):
        """> rack vinti → posizione al turno precedente → sorteggio

        Stessi rack, differenze diverse: decide la classifica di partenza.
        """
        from models.classification.models import RoundClassification
        from models.classification.seeding_service import SeedingService

        gara = _gara(db_session, sistema="RACK")
        a, b, c, d = (_utente(db_session) for _ in range(4))
        SeedingService.ensure_seeding(gara.id, [b.id, a.id, d.id, c.id])
        _partita(db_session, gara, a, c, 0)  # a: 5 rack, +5
        _partita(db_session, gara, b, d, 4)  # b: 5 rack, +1
        db_session.commit()

        RoundClassification.calculate_classification_after_round(gara.id, 1)
        primo = RoundClassification.query.filter_by(
            gara_id=gara.id, round_number=1, position=1
        ).one()
        assert primo.user_id == b.id, "b era davanti nella classifica di partenza"

    def test_nel_campionato_decide_la_gara_precedente(self, db_session):
        """> SSR (somma) → posizione dopo la gara precedente → sorteggio

        A e B chiudono pari in tutto. Dopo la gara 1 era davanti A, dopo la
        gara 2 B: decide la gara **precedente**, cioè la 2. Fino al
        2026-10-07 restava davanti A, perché compariva prima nei dati.
        """
        from models.campionato.models import Campionato
        from models.campionato.statistics_service import TournamentStatisticsService
        from models.classification.models import RoundClassification

        camp = Campionato(name=f"Spec {uuid.uuid4().hex[:6]}", planned_gare_count=3)
        db_session.add(camp)
        db_session.flush()
        a, b, c, d = (_utente(db_session) for _ in range(4))
        for numero, coppie in (
            (1, ((a, c, 0), (b, d, 1))),  # dopo la gara 1: A +5, B +4
            (2, ((b, c, 0), (a, d, 2))),  # dopo la gara 2: B +9, A +8
            (3, ((a, c, 0), (b, d, 1))),  # alla fine: A +13, B +13
        ):
            gara = _gara(db_session)
            gara.campionato_id = camp.id
            gara.number = numero
            gara.date = date(2026, 1, 10 + numero)
            gara.status = GaraStatus.COMPLETED.value
            gara.rounds_count = 1
            for vince, perde, persi in coppie:
                _partita(db_session, gara, vince, perde, persi)
            db_session.flush()
            RoundClassification.calculate_classification_after_round(gara.id, 1)
        db_session.commit()

        classifica = TournamentStatisticsService().classifica_generale(camp.id)
        ordine = [dati["user_id"] for _pos, dati in classifica]
        assert ordine[:2] == [b.id, a.id]
        assert [pos for pos, _ in classifica] == [1, 2, 3, 4], "ordine completo"


@pytest.mark.unit
class TestLeCateneSiConfigurano:
    """`SPECIFICHE.md`, «Classifica», «Le catene si configurano»."""

    def test_il_principale_non_entra_nella_catena(self):
        """> il **criterio principale** non entra nella catena"""
        from models.classification.catene import testo_dal_modulo
        from models.classification.ordinamento import Livello
        from models.status_enum import ClassificationSystem

        assert (
            testo_dal_modulo(
                "vittorie,scontri_diretti", Livello.GARA, ClassificationSystem.WINS
            )
            == '["scontri_diretti"]'
        )
        assert (
            testo_dal_modulo(
                "rack_vinti,scontri_diretti", Livello.GARA, ClassificationSystem.RACK
            )
            == '["scontri_diretti"]'
        )

    def test_il_sorteggio_e_l_ultimo_e_nel_turno_c_e_sempre(self):
        """> il **sorteggio** è sempre l'ultimo; nel turno e nel campionato c'è
        sempre"""
        from models.classification.catene import testo_dal_modulo
        from models.classification.ordinamento import Livello
        from models.status_enum import ClassificationSystem

        wins = ClassificationSystem.WINS
        assert (
            testo_dal_modulo("sorteggio,scontri_diretti", Livello.GARA, wins)
            == '["scontri_diretti", "sorteggio"]'
        )
        assert testo_dal_modulo("", Livello.TURNO, wins) == '["sorteggio"]'
        assert testo_dal_modulo("", Livello.CAMPIONATO, wins) == '["sorteggio"]'

    def test_lo_ssr_una_volta_e_mai_nel_turno(self):
        """> lo **spareggio SSR** compare al massimo una volta e mai nella
        catena di turno"""
        from models.classification.catene import testo_dal_modulo
        from models.classification.ordinamento import Livello
        from models.status_enum import ClassificationSystem

        wins = ClassificationSystem.WINS
        assert testo_dal_modulo("ssr:2,ssr:3", Livello.GARA, wins) == '["ssr:2"]'
        assert testo_dal_modulo("ssr:2", Livello.TURNO, wins) == '["sorteggio"]'
        assert testo_dal_modulo("ssr:2", Livello.CAMPIONATO, wins) == (
            '["ssr", "sorteggio"]'
        )

    def test_la_catena_di_gara_vuota_lascia_i_pari(self):
        """> una catena di gara **vuota** è ammessa: chi è pari sul principale
        resta pari"""
        from models.classification.ordinamento import (
            Concorrente,
            Criterio,
            normalizza_catena,
            ordina,
            Livello,
        )
        from models.status_enum import ClassificationSystem

        catena = normalizza_catena((), Livello.GARA, ClassificationSystem.WINS)
        assert catena == ()
        fasce = ordina(
            [Concorrente(1, vittorie=2, differenza_rack=3), Concorrente(2, vittorie=2)],
            Criterio.VITTORIE,
            catena,
        )
        assert [f.posizione for f in fasce] == [1]

    def test_la_catena_di_turno_vale_dal_turno_successivo(self, db_session):
        """> la catena di turno è una regola di gioco e, a gara avviata, vale
        **dal turno successivo**: la classifica di un turno già cominciato si
        fa con la catena di allora"""
        from datetime import date

        from models.base import db
        from models.classification.catene import catena_di_turno
        from models.classification.ordinamento import Criterio
        from models.competition.models import Gara
        from models.competition.services import GaraService
        from models.status_enum import GaraStatus

        gara = Gara(
            number=1,
            name="Dal turno dopo",
            date=date(2026, 1, 1),
            discipline="8_ball",
            distance=3,
            rounds_count=4,
            current_round=2,
            matchmaking_strategy="amalfi",
            status=GaraStatus.PLAYING.value,
            catena_turno='["differenza_rack", "posizione_precedente", "sorteggio"]',
        )
        db.session.add(gara)
        db.session.commit()
        GaraService.update_gara(
            gara.id, catena_turno='["scontri_diretti", "sorteggio"]'
        )
        gara = db.session.get(Gara, gara.id)
        assert catena_di_turno(gara, 2)[0].criterio is Criterio.DIFFERENZA_RACK
        assert catena_di_turno(gara, 3)[0].criterio is Criterio.SCONTRI_DIRETTI

    def test_le_gare_di_prima_tengono_il_loro_spareggio(self, tmp_path):
        """> Ogni gara esistente ha ricevuto la catena di gara che riproduce il
        suo interruttore"""
        import importlib.util
        import json
        import sqlite3

        percorso = tmp_path / "prima.db"
        conn = sqlite3.connect(percorso)
        conn.executescript("""
            CREATE TABLE campionato (id INTEGER PRIMARY KEY,
                default_classification_system TEXT);
            CREATE TABLE gara (id INTEGER PRIMARY KEY, classification_system TEXT,
                tiebreaker_enabled BOOLEAN, tiebreaker_until_position INTEGER);
            INSERT INTO gara VALUES (1, 'WINS', 1, 2), (2, 'RACK', 0, 3);
            """)
        conn.commit()
        conn.close()
        spec = importlib.util.spec_from_file_location(
            "m", "migrations/20261007_catene_degli_spareggi.py"
        )
        assert spec and spec.loader
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        modulo.upgrade_sqlite(str(percorso))
        conn = sqlite3.connect(percorso)
        catene = [
            json.loads(r[0])
            for r in conn.execute("SELECT catena_gara FROM gara ORDER BY id")
        ]
        conn.close()
        assert catene == [["differenza_rack", "ssr:2"], []]


@pytest.mark.unit
class TestLoScontroDiretto:
    """`SPECIFICHE.md`, «Classifica», «Lo scontro diretto» (2026-10-07)."""

    @staticmethod
    def _ordina(concorrenti, scontri, *criteri):
        from models.classification.ordinamento import Criterio, Voce, ordina

        catena = (Voce(Criterio.SCONTRI_DIRETTI),) + tuple(Voce(c) for c in criteri)
        return ordina(concorrenti, Criterio.VITTORIE, catena, scontri=scontri)

    def test_fra_due_vince_chi_ha_vinto_lo_scontro(self):
        """> se si sono affrontati sta davanti chi ha vinto lo scontro,
        altrimenti decide il criterio successivo"""
        from models.classification.ordinamento import (
            Concorrente,
            Criterio,
            Scontro,
        )

        a = Concorrente(1, vittorie=2, differenza_rack=0)
        b = Concorrente(2, vittorie=2, differenza_rack=5)
        vinto = self._ordina([a, b], [Scontro(1, 2, 5, 3, 1)], Criterio.DIFFERENZA_RACK)
        assert [g.player_id for f in vinto for g in f.giocatori] == [1, 2]
        mai = self._ordina([a, b], [], Criterio.DIFFERENZA_RACK)
        assert [g.player_id for f in mai for g in f.giocatori] == [2, 1]

    def test_conta_chi_ha_vinto_piu_scontri_e_la_parita_non_decide(self):
        """> sta davanti chi ne ha vinti di più; a parità, o con un pareggio,
        lo scontro non decide"""
        from models.classification.ordinamento import (
            Concorrente,
            Criterio,
            Scontro,
        )

        a = Concorrente(1, vittorie=2, differenza_rack=0)
        b = Concorrente(2, vittorie=2, differenza_rack=5)
        uno_a_uno = [Scontro(1, 2, 5, 3, 1), Scontro(2, 1, 5, 3, 2)]
        fasce = self._ordina([a, b], uno_a_uno, Criterio.DIFFERENZA_RACK)
        assert [g.player_id for f in fasce for g in f.giocatori] == [2, 1]
        pareggio = [Scontro(1, 2, 2, 2, None)]
        fasce = self._ordina([a, b], pareggio, Criterio.DIFFERENZA_RACK)
        assert [g.player_id for f in fasce for g in f.giocatori] == [2, 1]

    def test_fra_chi_non_si_e_incontrato_decide_il_criterio_dopo(self):
        """> nessun risultato diretto viene contraddetto, e fra chi non si è
        incontrato decide il criterio successivo

        A ha battuto B, C non ha incontrato nessuno e ha la differenza
        migliore di A ma peggiore di B: C, A, B. Fino al 2026-10-07 lo
        scontro diretto fra tre non decideva se non si erano incontrati
        tutti, e la differenza dava B, C, A.
        """
        from models.classification.ordinamento import (
            Concorrente,
            Criterio,
            Scontro,
        )

        fasce = self._ordina(
            [
                Concorrente(1, vittorie=2, differenza_rack=1),
                Concorrente(2, vittorie=2, differenza_rack=9),
                Concorrente(3, vittorie=2, differenza_rack=5),
            ],
            [Scontro(1, 2, 5, 3, 1)],
            Criterio.DIFFERENZA_RACK,
        )
        assert [g.player_id for f in fasce for g in f.giocatori] == [3, 1, 2]

    def test_chi_si_e_battuto_in_giro_resta_pari(self):
        """> chi si è battuto a vicenda in giro resta pari sullo scontro"""
        from models.classification.ordinamento import (
            Concorrente,
            Scontro,
        )

        fasce = self._ordina(
            [Concorrente(p, vittorie=3) for p in (1, 2, 3, 4)],
            [
                Scontro(1, 2, 5, 3, 1),
                Scontro(2, 3, 5, 3, 2),
                Scontro(3, 1, 5, 3, 3),
                Scontro(1, 4, 5, 3, 1),
                Scontro(2, 4, 5, 3, 2),
                Scontro(3, 4, 5, 3, 3),
            ],
        )
        assert [len(f.giocatori) for f in fasce] == [3, 1]
        assert [g.player_id for g in fasce[1].giocatori] == [4]

    def _campionato(self, db_session, giornate):
        """Un campionato con la catena generale «scontri, differenza»."""
        from models.campionato.models import Campionato
        from models.classification.models import RoundClassification

        camp = Campionato(
            name=f"Spec {uuid.uuid4().hex[:6]}",
            planned_gare_count=len(giornate),
            catena_generale='["scontri_diretti", "differenza_rack", "sorteggio"]',
        )
        db_session.add(camp)
        db_session.flush()
        for numero, (peso, partite) in enumerate(giornate, start=1):
            gara = _gara(db_session)
            gara.campionato_id = camp.id
            gara.number = numero
            gara.date = date(2026, 1, 10 + numero)
            gara.status = GaraStatus.COMPLETED.value
            gara.rounds_count = 1
            gara.weight = peso
            for vince, perde, persi in partite:
                _partita(db_session, gara, vince, perde, persi)
            db_session.flush()
            RoundClassification.calculate_classification_after_round(gara.id, 1)
        db_session.commit()
        return camp

    def test_nel_campionato_gli_scontri_si_sommano_fra_le_gare(self, db_session):
        """> più partite fra gli stessi due, anche in gare diverse del
        campionato, si contano tutte

        A batte B nella gara 1 e nella 3, B batte A nella 2: A davanti, anche
        con la differenza peggiore.
        """
        from models.campionato.statistics_service import TournamentStatisticsService

        a, b, c, d = (_utente(db_session) for _ in range(4))
        camp = self._campionato(
            db_session,
            [
                (1, ((a, b, 4), (c, d, 0))),
                (1, ((b, a, 0), (d, c, 0))),
                (1, ((a, b, 4), (c, d, 0))),
            ],
        )
        classifica = TournamentStatisticsService().classifica_generale(camp.id)
        ordine = [dati["user_id"] for _pos, dati in classifica]
        assert ordine.index(a.id) < ordine.index(b.id)

    def test_una_gara_che_pesa_zero_non_conta_negli_scontri(self, db_session):
        """> nel campionato non contano le gare con peso 0"""
        from models.campionato.statistics_service import TournamentStatisticsService

        a, b, c, d = (_utente(db_session) for _ in range(4))
        camp = self._campionato(
            db_session,
            [
                # A e B una vittoria a testa, B con la differenza migliore.
                (1, ((a, c, 4), (b, d, 0))),
                # A batte B, ma la gara pesa zero.
                (0, ((a, b, 4), (c, d, 4))),
            ],
        )
        classifica = TournamentStatisticsService().classifica_generale(camp.id)
        ordine = [dati["user_id"] for _pos, dati in classifica]
        assert ordine.index(b.id) < ordine.index(a.id)


@pytest.mark.unit
class TestAChiToccaLaXNelPrimoTurno:
    """`SPECIFICHE.md` riga 67.

    > all'avvio il direttore può assegnare la X **all'ultimo iscritto** invece
    > di lasciarla al caso [...] Il resto degli abbinamenti resta casuale: chi
    > riceve la X viene scambiato di posto con chi l'aveva sorteggiata, e
    > nient'altro si muove.

    Qui si verifica *quando* la domanda si pone e *chi* è "l'ultimo iscritto".
    Che lo scambio conservi le garanzie del sorteggio (una X a testa, nessun
    reincontro) lo verifica
    `tests/new/integration/test_x_al_ultimo_iscritto.py`, che ha bisogno di
    generare i turni veri.
    """

    @staticmethod
    def _iscrivi(db_session, gara: Gara, quanti: int) -> list[User]:
        giocatori = []
        for _ in range(quanti):
            giocatore = _utente(db_session)
            db_session.add(Inscription(gara_id=gara.id, user_id=giocatore.id))
            giocatori.append(giocatore)
        db_session.flush()
        return giocatori

    def test_si_pone_solo_con_amalfi_o_casuale_dispari_e_la_x(self, db_session):
        gara = _gara(db_session)
        self._iscrivi(db_session, gara, 5)

        assert bye_preference.choice_applies(gara) is True

        gara.matchmaking_strategy = "random"
        assert bye_preference.choice_applies(gara) is True

        # Fuori dalle due strategie la X non è una sola e la domanda decade.
        gara.matchmaking_strategy = "round_robin"
        assert bye_preference.choice_applies(gara) is False

    def test_col_trio_non_ci_sono_x_da_assegnare(self, db_session):
        gara = _gara(db_session)
        self._iscrivi(db_session, gara, 5)
        gara.odd_number_policy = "trio"

        assert bye_preference.choice_applies(gara) is False

    def test_con_giocatori_pari_non_ci_sono_x_da_assegnare(self, db_session):
        gara = _gara(db_session)
        self._iscrivi(db_session, gara, 6)

        assert bye_preference.choice_applies(gara) is False

    def test_l_ultimo_iscritto_e_l_ultimo_arrivato_fra_chi_gioca(self, db_session):
        gara = _gara(db_session)
        giocatori = self._iscrivi(db_session, gara, 5)

        assert bye_preference.last_inscribed_user_id(gara) == giocatori[-1].id

    def test_senza_la_scelta_la_x_resta_al_sorteggio(self, db_session):
        """Il default è il comportamento storico, non la novità."""
        gara = _gara(db_session)
        self._iscrivi(db_session, gara, 5)

        assert gara.bye_to_last_inscribed in (False, None)
        assert bye_preference.preferred_bye_player(gara) is None


# ══ La X (bye) ═══════════════════════════════════════════════════════════


@pytest.mark.unit
class TestQuantoValeLaX:
    """`SPECIFICHE.md` righe 64 e 71."""

    @staticmethod
    def _con_la_x(db_session, gara: Gara, giocatore: User, punteggio: int) -> Match:
        partita = Match(
            gara_id=gara.id,
            round_number=1,
            player1_id=giocatore.id,
            player2_id=None,
            is_bye=True,
            player1_score=punteggio,
            player2_score=0,
            winner_id=giocatore.id,
            status=MatchStatus.CLOSED_UNILATERALLY.value,
        )
        db_session.add(partita)
        db_session.commit()
        return partita

    def test_la_x_vale_una_vittoria(self, db_session):
        """`SPECIFICHE.md` riga 71.

        > **Bye**: un giocatore salta il turno (solo per sistema WINS: ottiene
        > 1 vittoria, 0 diff rack)

        Questa metà la regge: la vittoria c'è.
        """
        gara = _gara(db_session)
        giocatore = _utente(db_session)
        self._con_la_x(db_session, gara, giocatore, gara.distance)

        assert _punteggi(gara.id)[giocatore.id].matches_won == 1

    def test_la_x_nasce_senza_triangoli(self, db_session):
        """`SPECIFICHE.md` righe 64 e 71, **alla fonte**.

        > abbina un giocatore alla X assegnando il match vinto, ma con **zero
        > differenza punti**

        Questo test passa dal vero punto di creazione, non da un `Match`
        costruito a mano: è lì che stava la divergenza (`round_creation.py`
        assegnava `player1_score = round_distance`), ed è lì che va presidiata.
        Un test che costruisce da sé la partita con il punteggio che vuole non
        può accorgersi di come la produzione la crea davvero.
        """
        from models.competition.round_creation import create_matches_from_pairings
        from models.matchmaking.strategies.base import Pairing

        gara = _gara(db_session)
        giocatore = _utente(db_session)

        create_matches_from_pairings(
            gara=gara,
            pairings=[Pairing(players=(giocatore.id,), is_bye=True, round_number=1)],
            round_number=1,
            round_distance=gara.distance,
        )
        db_session.flush()

        partita = db_session.query(Match).filter_by(gara_id=gara.id).one()
        assert partita.is_bye
        assert partita.player1_score == 0

    def test_la_x_da_zero_differenza_rack(self, db_session):
        """`SPECIFICHE.md` righe 64 e 71, **in classifica**.

        La conseguenza del test precedente sul punteggio aggregato: con zero
        triangoli vinti e nessuno perso, la differenza resta ferma e chi riposa
        si piazza sotto chiunque abbia vinto giocando — che è l'intento
        dichiarato dalla riga 64.
        """
        gara = _gara(db_session)
        giocatore = _utente(db_session)
        self._con_la_x(db_session, gara, giocatore, 0)

        voce = _punteggi(gara.id)[giocatore.id]
        assert voce.matches_won == 1
        assert voce.rack_difference == 0

    def test_la_x_con_challenge_da_differenza_pari_al_punteggio(self, db_session):
        """`SPECIFICHE.md` riga 65.

        > il giocatore abbinato con la X, invece di stare fermo il turno, gioca
        > la challenge e in classifica ottiene il match vinto e una differenza
        > rack pari al punteggio nella challenge

        È la regola che impedisce di correggere la X azzerando l'aggregatore:
        l'aggregatore deve continuare a leggere `player1_score`, perché per la
        X-con-challenge quel campo **è** il punteggio della prova.
        """
        gara = _gara(db_session)
        gara.odd_number_policy = "bye_with_challenge"
        giocatore = _utente(db_session)
        self._con_la_x(db_session, gara, giocatore, 3)

        voce = _punteggi(gara.id)[giocatore.id]
        assert voce.matches_won == 1
        assert voce.rack_difference == 3

    def test_la_x_vale_una_vittoria_anche_nella_classifica_generale(self, db_session):
        """`SPECIFICHE.md` righe 147 e 154, **sul campionato** (riga 292).

        > abbina un giocatore alla X assegnando il match vinto, ma con zero
        > differenza punti

        I test sopra guardano la classifica della gara. Quella del campionato
        è la somma delle classifiche delle gare (riga 292), e deve portarsi
        dietro la X: le righe da cui partono gli inviti ai playoff la
        scartavano (campionato 5, 24/09/2026 — `test_x_negli_inviti_playoff.py`).
        """
        from models.campionato.models import Campionato
        from models.campionato.statistics_service import TournamentStatisticsService
        from models.classification.gara_classification import (
            RoundClassificationService,
        )

        campionato = Campionato(name=f"Spec {uuid.uuid4().hex[:6]}")
        db_session.add(campionato)
        db_session.flush()
        gara = _gara(db_session)
        gara.campionato_id = campionato.id
        gara.rounds_count = 1
        gara.status = GaraStatus.COMPLETED.value
        giocatore = _utente(db_session)
        self._con_la_x(db_session, gara, giocatore, 0)
        RoundClassificationService.calculate_and_save_round_classification(gara.id, 1)
        db_session.commit()

        voce = {
            dati["user_id"]: dati
            for _pos, dati in TournamentStatisticsService().classifica_generale(
                campionato.id
            )
        }[giocatore.id]
        assert voce["total_matches_won"] == 1
        assert voce["total_rack_difference"] == 0


# ══ Pareggio a distanza pari ═════════════════════════════════════════════


@pytest.mark.unit
class TestPareggio:
    def test_a_rack_esatti_pari_il_pareggio_da_zero_e_zero(self, db_session):
        """`SPECIFICHE.md` riga 141.

        > **"Exactly N"** (esatto numero): si giocano esattamente N rack, vince
        > chi ne ha vinti di più. Se N è pari, sono possibili pareggi (gestiti
        > con 0 vittorie e 0 diff rack per entrambi nel sistema WINS).
        """
        gara = _gara(db_session, distanza=6)
        uno, due = _utente(db_session), _utente(db_session)
        db_session.add(
            Match(
                gara_id=gara.id,
                round_number=1,
                player1_id=uno.id,
                player2_id=due.id,
                player1_score=3,
                player2_score=3,
                winner_id=None,
                status=MatchStatus.CLOSED_UNILATERALLY.value,
            )
        )
        db_session.commit()

        punteggi = _punteggi(gara.id)

        for giocatore in (uno, due):
            voce = punteggi[giocatore.id]
            assert voce.matches_won == 0, "il pareggio non è una vittoria"
            assert voce.rack_difference == 0


# ══ Playoff: la cascata dei rifiuti ══════════════════════════════════════


@pytest.mark.unit
class TestCascataDeiRifiutiAiPlayoff:
    """`SPECIFICHE.md` riga 286."""

    @staticmethod
    def _campionato_con_playoff(db_session, posti: int, iscritti: int):
        from models.campionato.models import Campionato
        from models.classification.models import Classification
        from models.base import utc_now

        campionato = Campionato(
            name=f"Camp spec {uuid.uuid4().hex[:6]}",
            campionato_type="amalfi",
            is_active=True,
        )
        db_session.add(campionato)
        db_session.flush()
        campionato.terminated_at = utc_now()

        gara = _gara(db_session)
        gara.campionato_id = campionato.id
        gara.status = GaraStatus.COMPLETED.value

        configurazione = PlayoffConfiguration(
            campionato_id=campionato.id,
            name="Elite",
            playoff_type=PlayoffType.TOP_N,
            max_participants=posti,
            positions_from=1,
            positions_to=posti,
            is_active=True,
            auto_generate=True,
        )
        db_session.add(configurazione)
        db_session.flush()

        giocatori = []
        for posizione in range(1, iscritti + 1):
            giocatore = _utente(db_session)
            db_session.add(Inscription(user_id=giocatore.id, gara_id=gara.id))
            db_session.add(
                Classification(
                    campionato_id=campionato.id,
                    user_id=giocatore.id,
                    position=posizione,
                    total_matches_won=iscritti - posizione,
                    gare_played=1,
                )
            )
            giocatori.append(giocatore)
        db_session.commit()
        return campionato, configurazione, giocatori

    def test_chi_rifiuta_lascia_il_posto_al_primo_degli_esclusi(self, db_session):
        """`SPECIFICHE.md` riga 286.

        > Nei playoff con un numero limitato di partecipanti (ad esempio i
        > primi 6), se un giocatore rifiuta, la notifica passa al primo degli
        > esclusi e così via fino a quando un numero di giocatori pari ai posti
        > disponibili ha dato l'ok oppure sono finiti i giocatori.
        """
        _campionato, configurazione, giocatori = self._campionato_con_playoff(
            db_session, posti=4, iscritti=8
        )
        PlayoffService.start_playoff(_campionato.id)
        db_session.commit()

        qualificazioni = PlayoffQualification.query.filter_by(
            configuration_id=configurazione.id
        ).all()
        assert len(qualificazioni) == 4
        rinuncia = min(qualificazioni, key=lambda q: q.qualifying_position)

        PlayoffService.decline_qualification(rinuncia.id, rinuncia.user_id)
        db_session.commit()

        invitati = PlayoffQualification.query.filter_by(
            configuration_id=configurazione.id
        ).all()
        vivi = [
            q
            for q in invitati
            if q.status in (QualificationStatus.PENDING, QualificationStatus.CONFIRMED)
        ]
        assert len(vivi) == 4, (
            "dopo un rifiuto i posti vivi devono tornare a quattro: "
            f"invitati={len(invitati)}, vivi={len(vivi)}"
        )
        # Il sostituto è il quinto della classifica, cioè il primo escluso.
        quinto = giocatori[4]
        assert quinto.id in {q.user_id for q in invitati}

    @staticmethod
    def _verifica_invito_ricevuto(sostituto: PlayoffQualification) -> None:
        """Il sostituto è invitato come gli altri: data, scadenza, notifica."""
        from models.base import utc_now
        from models.notification.models import Notification, NotificationType

        assert sostituto.invited_at is not None, "il sostituto non risulta invitato"
        assert sostituto.expires_at is not None, "l'invito del sostituto non scade"
        assert sostituto.expires_at > utc_now(), "l'invito del sostituto è già scaduto"
        notifica = Notification.query.filter_by(
            user_id=sostituto.user_id,
            notification_type=NotificationType.PLAYOFF_INVITATION,
        ).first()
        assert notifica is not None, "al primo degli esclusi non arriva nessun invito"
        assert notifica.action_url == f"/player/playoff/invitation/{sostituto.id}"

    def test_il_primo_degli_esclusi_riceve_la_notifica_d_invito(self, db_session):
        """`SPECIFICHE.md` riga 286.

        > se un giocatore rifiuta, la notifica passa al primo degli esclusi

        Non basta creargli la qualificazione: fino al 2026-09-13 il sostituto
        compariva in lista senza che nessuno glielo dicesse, e senza scadenza.
        """
        campionato, configurazione, giocatori = self._campionato_con_playoff(
            db_session, posti=4, iscritti=8
        )
        PlayoffService.start_playoff(campionato.id)
        db_session.commit()
        rinuncia = PlayoffQualification.query.filter_by(
            configuration_id=configurazione.id, user_id=giocatori[0].id
        ).one()

        sostituto = PlayoffService.decline_qualification(rinuncia.id, rinuncia.user_id)
        db_session.commit()

        assert sostituto is not None
        assert sostituto.user_id == giocatori[4].id
        self._verifica_invito_ricevuto(
            db_session.get(PlayoffQualification, sostituto.id)
        )

    def test_anche_il_rifiuto_detto_al_direttore_avvisa_il_sostituto(self, db_session):
        """`SPECIFICHE.md` riga 286, rifiuto registrato dal direttore.

        Il giocatore che dice no a voce passa dalla stessa cascata: il primo
        degli esclusi va avvisato anche lì.
        """
        campionato, configurazione, giocatori = self._campionato_con_playoff(
            db_session, posti=4, iscritti=8
        )
        direttore = _utente(db_session)
        PlayoffService.start_playoff(campionato.id)
        db_session.commit()
        rinuncia = PlayoffQualification.query.filter_by(
            configuration_id=configurazione.id, user_id=giocatori[1].id
        ).one()

        sostituto = PlayoffService.respond_on_behalf(
            rinuncia.id, accept=False, responded_by_id=direttore.id
        )
        db_session.commit()

        assert sostituto is not None
        assert sostituto.user_id == giocatori[4].id
        self._verifica_invito_ricevuto(
            db_session.get(PlayoffQualification, sostituto.id)
        )


class TestIlPlayoffSiGiocaConChiHaAccettato:
    """`SPECIFICHE.md`, sezione «Playoff», righe 286 e 288.

    > […] fino a quando un numero di giocatori pari ai posti disponibili ha
    > dato l'ok oppure sono finiti i giocatori.

    > Il playoff si gioca con chi ha accettato, anche se sono meno dei posti
    > […] chi accetta dopo la creazione […] entra fra gli iscritti fino
    > all'avvio del primo turno […]. All'avvio gli inviti ancora senza
    > risposta scadono e nessun altro viene chiamato.
    """

    @staticmethod
    def _avvia(gara_id: int):
        """Dalla preparazione: la gara di playoff non ha iscrizioni da aprire."""
        from models.competition.round_service import RoundService

        return RoundService.start_first_round(gara_id)

    @staticmethod
    def _invito(configurazione, giocatore):
        return PlayoffQualification.query.filter_by(
            configuration_id=configurazione.id, user_id=giocatore.id
        ).first()

    def test_con_meno_si_dei_posti_la_finale_parte(self, db_session):
        campionato, configurazione, giocatori = (
            TestCascataDeiRifiutiAiPlayoff._campionato_con_playoff(
                db_session, posti=4, iscritti=4
            )
        )
        PlayoffService.start_playoff(campionato.id)
        for giocatore in giocatori[:3]:
            PlayoffService.confirm_qualification(
                self._invito(configurazione, giocatore).id, giocatore.id
            )
        ultimo = giocatori[3]
        # Sono finiti i giocatori: il rifiuto non chiama nessuno.
        assert (
            PlayoffService.decline_qualification(
                self._invito(configurazione, ultimo).id, ultimo.id
            )
            is None
        )

        gara = PlayoffService.create_playoff_gara(configurazione.id)

        assert self._avvia(gara.id).current_round == 1

    def test_chi_accetta_prima_dell_avvio_entra_e_all_avvio_gli_inviti_scadono(
        self, db_session
    ):
        campionato, configurazione, giocatori = (
            TestCascataDeiRifiutiAiPlayoff._campionato_con_playoff(
                db_session, posti=4, iscritti=8
            )
        )
        PlayoffService.start_playoff(campionato.id)
        for giocatore in giocatori[:2]:
            PlayoffService.confirm_qualification(
                self._invito(configurazione, giocatore).id, giocatore.id
            )
        gara = PlayoffService.create_playoff_gara(configurazione.id)

        tardivo = giocatori[2]
        PlayoffService.confirm_qualification(
            self._invito(configurazione, tardivo).id, tardivo.id
        )
        assert Inscription.query.filter_by(gara_id=gara.id, user_id=tardivo.id).first()

        self._avvia(gara.id)

        silenzioso = self._invito(configurazione, giocatori[3])
        assert silenzioso.status == QualificationStatus.EXPIRED
        assert (
            PlayoffQualification.query.filter_by(
                configuration_id=configurazione.id
            ).count()
            == 4
        )

    def test_annullato_l_avvio_gli_inviti_chiusi_dall_avvio_si_riaprono(
        self, db_session
    ):
        """Riga 288: «Se il direttore annulla l'avvio, gli inviti chiusi
        proprio da quell'avvio tornano in attesa, purché la loro scadenza non
        sia ancora passata»."""
        from models.competition.round_cancellation import RoundCancellationService

        campionato, configurazione, giocatori = (
            TestCascataDeiRifiutiAiPlayoff._campionato_con_playoff(
                db_session, posti=5, iscritti=8
            )
        )
        PlayoffService.start_playoff(campionato.id)
        for giocatore in giocatori[:4]:
            PlayoffService.confirm_qualification(
                self._invito(configurazione, giocatore).id, giocatore.id
            )
        gara = PlayoffService.create_playoff_gara(configurazione.id)
        self._avvia(gara.id)
        assert (
            self._invito(configurazione, giocatori[4]).status
            == QualificationStatus.EXPIRED
        )

        RoundCancellationService.cancel_first_round_startup(gara.id)

        assert (
            self._invito(configurazione, giocatori[4]).status
            == QualificationStatus.PENDING
        )

    def test_il_giocatore_aggiunto_dal_direttore_entra_oltre_i_posti(self, db_session):
        """Riga 288: «Un giocatore aggiunto a mano dal direttore entra invece
        sempre […] anche oltre i posti, e il massimo della gara non ne blocca
        l'avvio»."""
        campionato, configurazione, giocatori = (
            TestCascataDeiRifiutiAiPlayoff._campionato_con_playoff(
                db_session, posti=4, iscritti=6
            )
        )
        PlayoffService.start_playoff(campionato.id)
        for giocatore in giocatori[:4]:
            PlayoffService.confirm_qualification(
                self._invito(configurazione, giocatore).id, giocatore.id
            )
        gara = PlayoffService.create_playoff_gara(configurazione.id)

        PlayoffService.admin_add_player(configurazione.id, giocatori[5].id, "direttore")

        attivi = Inscription.query.filter_by(
            gara_id=gara.id, is_waitlist=False, is_withdrawn=False
        ).count()
        assert attivi == 5
        assert self._avvia(gara.id).current_round == 1

    def test_l_aggiunta_del_direttore_rispetta_la_parita(self, db_session):
        """Riga 288: «La parità invece vale anche per lui: se la gara non
        ammette un numero dispari di giocatori […] chi renderebbe dispari gli
        iscritti aspetta in lista d'attesa come gli altri, finché non arriva
        un secondo giocatore»."""
        campionato, configurazione, giocatori = (
            TestCascataDeiRifiutiAiPlayoff._campionato_con_playoff(
                db_session, posti=4, iscritti=7
            )
        )
        configurazione.odd_number_policy = "no"
        db_session.commit()
        PlayoffService.start_playoff(campionato.id)
        for giocatore in giocatori[:4]:
            PlayoffService.confirm_qualification(
                self._invito(configurazione, giocatore).id, giocatore.id
            )
        gara = PlayoffService.create_playoff_gara(configurazione.id)

        PlayoffService.admin_add_player(configurazione.id, giocatori[5].id, "direttore")
        primo = Inscription.query.filter_by(
            gara_id=gara.id, user_id=giocatori[5].id
        ).first()
        assert primo is not None and primo.is_waitlist

        PlayoffService.admin_add_player(configurazione.id, giocatori[6].id, "direttore")
        attivi = Inscription.query.filter_by(
            gara_id=gara.id, is_waitlist=False, is_withdrawn=False
        ).count()
        assert attivi == 6


# ──────────────────────────────────────────────────────────────────────────────
# APERTURA E RUNOUT (SPECIFICHE.md, sezione «Match», righe 131-144 — ADR-056)
# ──────────────────────────────────────────────────────────────────────────────


class TestRegoleDiApertura:
    """«Il match ha una regola di inizio e una regola di apertura, entrambe
    ereditate dalla gara a cui appartiene: sul singolo match non si scelgono.»
    (SPECIFICHE.md riga 131)
    """

    def test_le_quattro_modalita_di_apertura_sono_quelle_della_specifica(self):
        """SPECIFICHE.md righe 137-141: quattro, e con questi valori.

        Fino al 2026-08-28 la specifica ne prevedeva **due** e il codice ne
        aveva **tre**, sulle sole sfide individuali. I valori contano quanto il
        numero: finiscono in colonna, e rinominarne uno rende illeggibili le
        righe gia' scritte.
        """
        from models.match.break_rules import BreakRule

        assert [r.value for r in BreakRule] == [
            "winner_breaks",
            "alternate",
            "alternate_two",
            "loser_breaks",
        ]

    def test_le_due_regole_di_inizio_sono_quelle_della_specifica(self):
        """SPECIFICHE.md righe 133-135: primo giocatore, oppure acchito."""
        from models.match.break_rules import StartRule

        assert [r.value for r in StartRule] == ["first_player", "lag"]

    def test_l_acchito_e_il_default(self):
        """SPECIFICHE.md riga 218: «acchito […] È il default» (nota del 2026-09-24).

        Il default è quello che i moduli propongono; le gare nate prima della
        regola, senza una regola scritta, restano al primo giocatore.
        """
        from models.match.break_rules import (
            DEFAULT_START_RULE,
            LEGACY_START_RULE,
            StartRule,
        )

        assert DEFAULT_START_RULE is StartRule.LAG
        assert LEGACY_START_RULE is StartRule.FIRST_PLAYER

    def test_a_turno_e_il_default(self):
        """SPECIFICHE.md riga 139: «È il default».

        E' anche quello che le sfide individuali avevano gia' dal 2026-02:
        cambiarlo riscriverebbe il passato di quelle partite.
        """
        from models.match.break_rules import DEFAULT_BREAK_RULE, BreakRule

        assert DEFAULT_BREAK_RULE is BreakRule.ALTERNATE

    def test_a_turno_alterna_a_ogni_rack(self):
        """SPECIFICHE.md riga 139: «tiri di apertura alternati»."""
        from models.match.break_rules import BreakRule, break_player_for_rack

        apre = [
            break_player_for_rack(BreakRule.ALTERNATE, n, 1, 2, []) for n in range(4)
        ]
        assert apre == [1, 2, 1, 2]

    def test_a_turno_ogni_due_cambia_ogni_due_rack(self):
        """SPECIFICHE.md riga 140: «due rack a testa, poi si cambia»."""
        from models.match.break_rules import BreakRule, break_player_for_rack

        apre = [
            break_player_for_rack(BreakRule.ALTERNATE_TWO, n, 1, 2, [])
            for n in range(6)
        ]
        assert apre == [1, 1, 2, 2, 1, 1]

    def test_spacca_chi_ha_vinto_e_chi_ha_perso_guardano_il_rack_prima(self):
        """SPECIFICHE.md righe 138 e 141."""
        from models.match.break_rules import BreakRule, break_player_for_rack

        # Rack 0 vinto da 2: al rack 1 apre 2 (winner) oppure 1 (loser).
        assert break_player_for_rack(BreakRule.WINNER_BREAKS, 1, 1, 2, [2]) == 2
        assert break_player_for_rack(BreakRule.LOSER_BREAKS, 1, 1, 2, [2]) == 1

    def test_l_acchito_e_due_domande_non_una(self):
        """SPECIFICHE.md riga 135: chi vince l'acchito **sceglie chi** apre.

        Quindi chi ha vinto e chi apre sono due fatti indipendenti, e il
        secondo puo' essere l'avversario del primo. Se fossero lo stesso dato,
        `first_break_player_id` non esisterebbe.
        """
        from models.match.models import Match

        assert hasattr(Match, "lag_winner_id")
        assert hasattr(Match, "first_break_player_id")

    def test_break_and_run_si_deduce_da_chi_apriva(self):
        """SPECIFICHE.md riga 143: «Non si scelgono: si deduce da chi apriva.»

        Un solo flag sul rack (`is_run_out`) piu' chi ha aperto: il break and
        run non e' un secondo flag che qualcuno potrebbe dimenticare di
        alzare — e quindi non puo' contraddire il primo.
        """
        from models.match.models import Rack

        vinto_da_chi_apriva = Rack(winner_id=7, break_player_id=7, is_run_out=True)
        vinto_rispondendo = Rack(winner_id=7, break_player_id=9, is_run_out=True)
        non_runout = Rack(winner_id=7, break_player_id=7, is_run_out=False)

        assert vinto_da_chi_apriva.is_break_and_run is True
        assert vinto_rispondendo.is_break_and_run is False
        assert non_runout.is_break_and_run is False

    def test_le_regole_si_ereditano_dalla_gara_non_dal_match(self, app):
        """SPECIFICHE.md riga 131: «sul singolo match non si scelgono».

        Il match non ha un override: `effective_*_rule` legge **sempre** la
        gara. Se un domani qualcuno aggiungesse una colonna sul match, questo
        test resterebbe verde — ma la catena la descrive la riga 131, ed e'
        quella che il codice deve continuare a seguire.
        """
        from models.campionato.models import Campionato
        from models.competition.models import Gara
        from models.match.break_rules import BreakRule
        from models.match.models import Match

        campionato = Campionato(default_break_rule=BreakRule.LOSER_BREAKS.value)
        gara = Gara(break_rule=None)
        gara.campionato = campionato
        match = Match()
        match.gara = gara

        # NULL sulla gara = eredita dal campionato.
        assert match.effective_break_rule is BreakRule.LOSER_BREAKS

        # Un valore sulla gara vince sul campionato.
        gara.break_rule = BreakRule.ALTERNATE_TWO.value
        assert match.effective_break_rule is BreakRule.ALTERNATE_TWO


class TestCompetizioneDiProva:
    """`SPECIFICHE.md` righe 419-431: la competizione di prova (ADR-058)."""

    def test_al_massimo_tre_prove_aperte(self):
        """Riga 424: «al massimo **3 prove aperte** contemporaneamente»."""
        from models.prova.service import LIMITE_PROVE_ATTIVE

        assert LIMITE_PROVE_ATTIVE == 3

    def test_scade_a_quattordici_giorni_con_avviso_tre_giorni_prima(self):
        """Riga 431: «**14 giorni** dopo la creazione ... **3 giorni** prima»."""
        from datetime import timedelta

        from models.prova.service import DURATA_PROVA, PREAVVISO_SCADENZA

        assert DURATA_PROVA == timedelta(days=14)
        assert PREAVVISO_SCADENZA == timedelta(days=3)

    def test_la_simulazione_chiude_le_pari_dai_giocatori_e_le_dispari_dal_direttore(
        self,
    ):
        """Riga 426: «le **pari** con la doppia conferma dei giocatori, le
        **dispari** restano ... in attesa che il direttore le validi»."""
        from types import SimpleNamespace

        from models.prova.simulation_service import SimulationService

        assert SimulationService.chiusa_dai_giocatori(SimpleNamespace(id=2))
        assert not SimulationService.chiusa_dai_giocatori(SimpleNamespace(id=3))

    def test_nel_campionato_di_prova_le_date_sono_nei_prossimi_giorni(self, db_session):
        """Riga 427: «domani la prima, il giorno dopo l'ultima le altre»."""
        from datetime import date, timedelta

        from models.campionato.tournament_service import TournamentService
        from models.prova.service import ProvaService
        from models.prova.visibility import prova_visibili

        with prova_visibili():
            campionato = TournamentService().create_campionato_with_director(
                name="Prova",
                creator_user_id=_utente(db_session).id,
                **ProvaService.campi_di_creazione(),
            )
            db_session.commit()
            assert TournamentService.data_proposta_gara(
                campionato.id
            ) == date.today() + timedelta(days=1)

    def test_i_fittizi_hanno_rating_fissi_e_diversi(self):
        """Riga 425: «rating iniziali fissi e diversi fra loro»."""
        from models.prova.nomi import NOMI_FITTIZI

        rating = [r for _, _, r in NOMI_FITTIZI]
        assert len(set(rating)) == len(rating)

    def test_una_partita_di_prova_non_muove_il_rating(self, db_session):
        """Riga 428: «non muovono alcun rating»."""
        from models.prova.service import ProvaService
        from models.rating.eligibility import RatingEligibility, RatingExclusion

        gara = _gara(db_session)
        gara.director_id = _utente(db_session).id
        for chiave, valore in ProvaService.campi_di_creazione().items():
            setattr(gara, chiave, valore)
        db_session.flush()
        a, b = _utente(db_session), _utente(db_session)
        match = Match(
            gara_id=gara.id,
            round_number=1,
            player1_id=a.id,
            player2_id=b.id,
            player1_score=5,
            player2_score=1,
            winner_id=a.id,
            status=MatchStatus.CONFIRMED_BY_BOTH.value,
        )
        db_session.add(match)
        db_session.flush()

        assert RatingEligibility.exclusion_reason(match) is RatingExclusion.PROVA


# ══ Il trio in classifica ════════════════════════════════════════════════


@pytest.mark.unit
class TestIlTrioInClassifica:
    """`SPECIFICHE.md` riga 164.

    > Per il sistema WINS, nel trio vince chi ha il punteggio più alto (1
    > vittoria), gli altri ottengono 0 vittorie. Se il punteggio più alto è di
    > due o tre giocatori, nessuno prende la vittoria.

    Il pari in testa è stato una divergenza fino al 2026-09-13: lo scioglieva lo
    scontro diretto, e con 4-4-1 alla distanza 6 la vittoria andava a uno dei
    due a quattro. La regola vale su ogni strada che chiude un trio, quindi
    ognuna ha il suo caso qui sotto.
    """

    @staticmethod
    def _nuovo_trio(db_session, distanza: int):
        from models.match.models import TrioMatch

        gara = _gara(db_session, distanza=distanza)
        gara.odd_number_policy = "trio"
        giocatori = [_utente(db_session) for _ in range(3)]
        partita = Match(
            gara_id=gara.id,
            round_number=1,
            player1_id=giocatori[0].id,
            player2_id=giocatori[1].id,
            is_trio=True,
            status=MatchStatus.PLAYING.value,
        )
        db_session.add(partita)
        db_session.flush()
        trio = TrioMatch(
            match_id=partita.id,
            player1_id=giocatori[0].id,
            player2_id=giocatori[1].id,
            player3_id=giocatori[2].id,
        )
        db_session.add(trio)
        db_session.flush()
        return gara, giocatori, trio

    @staticmethod
    def _vittorie(gara, giocatori) -> list[int]:
        voci = _punteggi(gara.id)
        return [voci[g.id].matches_won for g in giocatori]

    def _trio(self, db_session, distanza: int, punti: tuple[int, int, int]):
        from models.match.trio_scoring_service import TrioScoringService

        gara, giocatori, trio = self._nuovo_trio(db_session, distanza)
        TrioScoringService.set_result_direct(trio.id, *punti)
        db_session.commit()
        return self._vittorie(gara, giocatori)

    def test_vince_solo_il_punteggio_piu_alto(self, db_session):
        assert self._trio(db_session, 4, (4, 1, 1)) == [1, 0, 0]

    def test_il_pareggio_a_tre_non_da_vittorie(self, db_session):
        assert self._trio(db_session, 6, (3, 3, 3)) == [0, 0, 0]

    def test_il_pareggio_in_testa_non_da_vittorie(self, db_session):
        """Il risultato secco del direttore."""
        assert self._trio(db_session, 6, (4, 4, 1)) == [0, 0, 0]

    def test_il_pareggio_in_testa_segnato_triangolo_per_triangolo(self, db_session):
        """Il segnapunti. Nell'ordine del girone — 1–2, 1–3, 2–3 — il primo
        batte il secondo 2-1 e il terzo 2-1: per lo scontro diretto vinceva
        lui. Per la specifica, a 4-4-1, nessuno."""
        from models.match.trio_scoring_service import TrioScoringService

        gara, giocatori, trio = self._nuovo_trio(db_session, 6)
        sequenza = [0, 0, 1, 0, 0, 1, 1, 2, 1]
        for numero, indice in enumerate(sequenza, start=1):
            TrioScoringService.add_rack_win(
                trio.id,
                giocatori[indice].id,
                authoritative=numero == len(sequenza),
            )
        db_session.commit()

        assert trio.player_racks_list == [4, 4, 1]
        assert self._vittorie(gara, giocatori) == [0, 0, 0]

    def test_il_pareggio_in_testa_dalla_card_del_direttore(self, db_session):
        """Gli stepper della card, che segnano a totali."""
        from models.match.trio_scoring_service import TrioScoringService

        gara, giocatori, trio = self._nuovo_trio(db_session, 6)
        TrioScoringService.set_racks_won(trio.id, (4, 4, 1), giocatori[0].id)
        db_session.commit()

        assert self._vittorie(gara, giocatori) == [0, 0, 0]

    @pytest.mark.parametrize(
        "sequenza, totali, vittorie",
        [
            ([0, 2, 1, 0, 2, 2, 1], [3, 3, 3], [0, 0, 0]),
            ([0, 2, 2, 0, 2, 2, 1], [3, 2, 4], [1, 0, 0]),
        ],
        ids=["tre-tre-tre-nessuno-vince", "tre-due-quattro-vince-marco"],
    )
    def test_chi_si_ritira_non_vince_e_il_pari_resta_fra_gli_altri_due(
        self, db_session, sequenza, totali, vittorie
    ):
        """`SPECIFICHE.md` riga 164, la regola del ritiro (decisa il 2026-09-13).

        > Chi si ritira dal trio non vince mai, nemmeno col totale più alto, e
        > il pari si guarda solo fra gli altri due. Esempi alla distanza 6,
        > nove triangoli: Marco 3, Luca 3 e Gianni ritirato con 3, nessuno
        > vince; Marco 3, Luca 2 e Gianni ritirato con 4, vince Marco, anche se
        > Gianni ha il totale più alto.

        Una partita vera, passando dal ritiro nel trio. I gironi sono tre, in
        ordine fisso Marco–Luca, Marco–Gianni, Luca–Gianni: si giocano sette
        triangoli, poi Gianni si ritira e gli ultimi due, entrambi contro di
        lui, vanno uno a Marco e uno a Luca.
        """
        from models.match.trio_scoring_service import TrioScoringService

        gara, giocatori, trio = self._nuovo_trio(db_session, 6)
        marco, luca, gianni = giocatori
        for indice in sequenza:
            TrioScoringService.add_rack_win(trio.id, giocatori[indice].id)
        db_session.commit()
        assert trio.handle_forfeit(gianni.id)
        trio.confirm_result_by_admin()
        db_session.commit()

        assert trio.player_racks_list == totali
        assert trio.winner_id == (marco.id if vittorie[0] else None)
        assert self._vittorie(gara, [marco, luca, gianni]) == vittorie

    def test_il_pareggio_in_testa_dopo_un_ritiro(self, db_session):
        """Il ritiro nel trio: chi si ritira non vince, e fra gli altri due vale
        la stessa regola. Qui il primo batte il secondo 2-0, ma a totali sono
        2 e 2; e i due triangoli di chi si ritira non contano."""
        from models.match.trio_scoring_service import TrioScoringService

        gara, giocatori, trio = self._nuovo_trio(db_session, 4)
        for indice in (0, 2, 1, 0, 2):
            TrioScoringService.add_rack_win(trio.id, giocatori[indice].id)
        db_session.commit()
        assert trio.handle_forfeit(giocatori[2].id)
        trio.confirm_result_by_admin()
        db_session.commit()

        assert trio.player_racks_list == [2, 2, 2]
        assert trio.winner_id is None
        assert self._vittorie(gara, giocatori) == [0, 0, 0]


class TestCosaChiudeIlTurno:
    """`SPECIFICHE.md` righe 102 e 104 (2026-09-13).

    > Il turno successivo si avvia solo quando il turno precedente è chiuso
    > davvero: tutte le sue partite concluse, la prova giocata al posto della X
    > convalidata dal direttore [...] e ogni esercizio fra i turni agganciato a
    > quel turno registrato, con almeno un tentativo, per ogni iscritto ancora
    > in gara. [...] con la strategia _casuale_ [...] né la prova della X né gli
    > esercizi bloccano qualcosa.

    > Un tentativo di esercizio fra i turni registrato per sbaglio si può
    > togliere, a gara in corso e finché il turno successivo non è partito.
    """

    @staticmethod
    def _turno_chiuso_con_esercizio(db_session, strategia="amalfi"):
        from models.challenge.models import Challenge
        from models.competition.gara_challenge import GaraChallenge

        gara = _gara(db_session)
        gara.matchmaking_strategy = strategia
        a, b = _utente(db_session), _utente(db_session)
        for u in (a, b):
            db_session.add(Inscription(user_id=u.id, gara_id=gara.id))
        db_session.add(
            Match(
                gara_id=gara.id,
                round_number=1,
                player1_id=a.id,
                player2_id=b.id,
                player1_score=5,
                player2_score=1,
                winner_id=a.id,
                status=MatchStatus.CLOSED_UNILATERALLY.value,
            )
        )
        sfida = Challenge(
            description="Esercizio",
            image_path="/x.png",
            is_active=True,
            created_by_id=a.id,
        )
        db_session.add(sfida)
        db_session.flush()
        gc = GaraChallenge(
            gara_id=gara.id,
            challenge_id=sfida.id,
            round_number=1,
            max_attempts=1,
            added_by_id=a.id,
        )
        db_session.add(gc)
        db_session.commit()
        return gara, gc, a, b

    def test_un_esercizio_non_registrato_blocca_il_turno_dopo(self, db_session):
        from models.competition.pendenze_turno import pendenze_del_turno

        gara, _gc, _a, _b = self._turno_chiuso_con_esercizio(db_session)
        assert pendenze_del_turno(gara, 1).esercizi == 2
        assert pendenze_del_turno(gara, 1).bloccano

    def test_col_casuale_non_blocca(self, db_session):
        from models.competition.pendenze_turno import pendenze_del_turno

        gara, _gc, _a, _b = self._turno_chiuso_con_esercizio(
            db_session, strategia="random"
        )
        assert not pendenze_del_turno(gara, 1).bloccano

    def test_il_tentativo_si_toglie_finche_il_turno_dopo_non_parte(self, db_session):
        from models.competition.gara_challenge_service import GaraChallengeService
        from models.exceptions import ConflictError

        gara, gc, a, b = self._turno_chiuso_con_esercizio(db_session)
        primo = GaraChallengeService.record_challenge_attempt(gc.id, a.id, score=3)
        GaraChallengeService.remove_challenge_attempt(primo.id)
        secondo = GaraChallengeService.record_challenge_attempt(gc.id, a.id, score=3)
        db_session.add(
            Match(
                gara_id=gara.id,
                round_number=2,
                player1_id=a.id,
                player2_id=b.id,
                status=MatchStatus.PLAYING.value,
            )
        )
        db_session.commit()
        with pytest.raises(ConflictError):
            GaraChallengeService.remove_challenge_attempt(secondo.id)

    def test_anche_la_chiusura_aspetta_l_ultimo_turno(self, db_session):
        """Riga 102: «Termina la gara» e lo spareggio non partono finché
        l'ultimo turno ha esercizi da registrare."""
        from models.competition.pendenze_turno import pendenze_della_chiusura
        from models.competition.state_service import StateService
        from models.exceptions import ConflictError

        gara, _gc, _a, _b = self._turno_chiuso_con_esercizio(db_session)
        assert pendenze_della_chiusura(gara).esercizi == 2
        with pytest.raises(ConflictError):
            StateService.complete(gara)

    def test_l_xp_segue_i_tentativi_rimasti(self, db_session):
        """Riga 104: finché resta un tentativo l'esercizio è fatto, senza
        tentativi l'XP torna indietro, in qualunque ordine si tolgano."""
        import json

        from models.competition.gara_challenge_service import GaraChallengeService
        from models.gamification.models import XPTransaction, XPTransactionType

        gara, gc, a, _b = self._turno_chiuso_con_esercizio(db_session)
        gc.max_attempts = 2
        db_session.commit()

        def xp():
            return sum(
                m.xp_amount
                for m in XPTransaction.query.filter_by(
                    user_id=a.id,
                    transaction_type=XPTransactionType.CHALLENGE_COMPLETION,
                )
                if json.loads(m.related_entities or "{}").get("gara_id") == gara.id
            )

        primo = GaraChallengeService.record_challenge_attempt(gc.id, a.id, score=1)
        secondo = GaraChallengeService.record_challenge_attempt(gc.id, a.id, score=2)
        db_session.commit()
        tariffa = xp()
        GaraChallengeService.remove_challenge_attempt(primo.id)
        db_session.commit()
        assert xp() == tariffa
        GaraChallengeService.remove_challenge_attempt(secondo.id)
        db_session.commit()
        assert xp() == 0


# ══ Un solo sistema di classifica per campionato ═════════════════════════


def _campionato(db_session, sistema: str):
    from models import Campionato

    campionato = Campionato(
        name=f"Campionato spec {uuid.uuid4().hex[:8]}",
        campionato_type="amalfi",
        is_active=True,
        default_classification_system=sistema,
    )
    db_session.add(campionato)
    db_session.flush()
    return campionato


def _gara_del_campionato(db_session, campionato, *, numero: int, stato: str) -> Gara:
    gara = Gara(
        campionato_id=campionato.id,
        name=f"Gara {numero}",
        number=numero,
        date=date(2026, 1, numero),
        discipline=Discipline.NINE_BALL.value,
        distance=5,
        is_race_to=False,
        status=stato,
        rounds_count=3,
        classification_system=campionato.default_classification_system,
        matchmaking_strategy="amalfi",
        # La X semplice è vietata a triangoli totali, quella con prova no: così
        # la stessa gara è valida con entrambi i sistemi.
        odd_number_policy="bye_with_challenge",
    )
    db_session.add(gara)
    db_session.flush()
    return gara


@pytest.mark.unit
class TestUnSoloSistemaDiClassificaPerCampionato:
    """`SPECIFICHE.md`, sezione del sistema di classifica del campionato.

    > Tutte le gare di un campionato devono usare lo stesso sistema di
    > classifica, compresa la gara di playoff […]. Il sistema del campionato si
    > può cambiare finché nessuna gara del campionato è stata **avviata**, anche
    > se ha già degli iscritti *(modificato il 2026-09-29, ADR-075: prima
    > bastava una gara con le iscrizioni aperte)* […]
    """

    def test_la_gara_di_playoff_eredita_il_sistema_del_campionato(self, db_session):
        """Fino al 2026-09-14 la gara di playoff non riceveva il sistema e
        prendeva il default della colonna, WINS: un campionato a triangoli
        totali si chiudeva con una finale a vittorie. Con WINS il difetto non si
        vede, perché il default coincide."""
        campionato = _campionato(db_session, "RACK")
        _gara_del_campionato(
            db_session, campionato, numero=1, stato=GaraStatus.COMPLETED.value
        )
        configurazione = PlayoffConfiguration(
            campionato_id=campionato.id,
            name="Finale",
            playoff_type=PlayoffType.TOP_N,
            max_participants=4,
            positions_from=1,
            positions_to=4,
            is_active=True,
            auto_generate=True,
            min_garas_played=0,
        )
        db_session.add(configurazione)
        db_session.commit()

        gara = PlayoffService.create_playoff_gara(configurazione.id)

        assert gara.classification_system == "RACK"

    @pytest.mark.parametrize(
        "stato",
        [
            GaraStatus.PLAYING.value,
            GaraStatus.AWAITING_SSR.value,
            GaraStatus.COMPLETED.value,
        ],
    )
    def test_avviata_una_gara_il_sistema_non_si_cambia(self, db_session, stato):
        from models import Campionato
        from models.campionato.tournament_service import TournamentService
        from models.exceptions import ValidationError

        campionato = _campionato(db_session, "WINS")
        _gara_del_campionato(db_session, campionato, numero=1, stato=stato)
        _gara_del_campionato(
            db_session, campionato, numero=2, stato=GaraStatus.SETUP.value
        )
        db_session.commit()
        campionato_id = campionato.id

        with pytest.raises(ValidationError):
            TournamentService().update_campionato(
                campionato_id=campionato_id, default_classification_system="RACK"
            )

        db_session.expire_all()
        rimasto = db_session.get(Campionato, campionato_id)
        assert rimasto.default_classification_system == "WINS"
        assert {g.classification_system for g in rimasto.gare} == {"WINS"}

    def test_con_iscritti_ma_senza_avvio_il_cambio_arriva_alla_gara(self, db_session):
        """Emendata il 2026-09-29 (ADR-075): gli iscritti non bloccano più il
        cambio, lo blocca il primo avvio. Il cambio arriva alla gara e resta
        nella sua storia."""
        from models.campionato.tournament_service import TournamentService

        campionato = _campionato(db_session, "WINS")
        gara = _gara_del_campionato(
            db_session, campionato, numero=1, stato=GaraStatus.INSCRIPTION.value
        )
        db_session.add(Inscription(user_id=_utente(db_session).id, gara_id=gara.id))
        db_session.commit()

        TournamentService().update_campionato(
            campionato_id=campionato.id, default_classification_system="RACK"
        )
        db_session.expire_all()
        assert db_session.get(type(gara), gara.id).classification_system in (
            "RACK",
            "RACKS",
        )

    def test_prima_delle_iscrizioni_il_cambio_arriva_a_tutte_le_gare(self, db_session):
        from models import Campionato
        from models.campionato.tournament_service import TournamentService

        campionato = _campionato(db_session, "WINS")
        for numero in (1, 2):
            _gara_del_campionato(
                db_session, campionato, numero=numero, stato=GaraStatus.SETUP.value
            )
        db_session.commit()
        campionato_id = campionato.id

        TournamentService().update_campionato(
            campionato_id=campionato_id, default_classification_system="RACK"
        )

        db_session.expire_all()
        aggiornato = db_session.get(Campionato, campionato_id)
        assert aggiornato.default_classification_system == "RACK"
        assert {g.classification_system for g in aggiornato.gare} == {"RACK"}


def _configurazione(db_session, campionato, **campi) -> PlayoffConfiguration:
    configurazione = PlayoffConfiguration(
        campionato_id=campionato.id,
        name="Finale",
        playoff_type=PlayoffType.TOP_N,
        max_participants=8,
        positions_from=1,
        positions_to=8,
        is_active=True,
        auto_generate=True,
        min_garas_played=0,
        **campi,
    )
    db_session.add(configurazione)
    db_session.flush()
    return configurazione


def _finale(db_session, campionato, configurazione, *, sistema: str) -> Gara:
    gara = _gara_del_campionato(
        db_session, campionato, numero=9, stato=GaraStatus.SETUP.value
    )
    gara.playoff_config_id = configurazione.id
    gara.classification_system = sistema
    db_session.flush()
    return gara


@pytest.mark.unit
class TestLaFinaleSecondoLaModalita:
    """`SPECIFICHE.md` riga 289.

    > La gara di playoff lo segue quando il suo punteggio **si somma** a quello
    > del campionato […] e per questo in quella modalità non può essere a
    > tabellone se il campionato non lo è; quando invece la classifica finale
    > è **solo quella dei playoff** della finale conta soltanto l'ordine
    > d'arrivo […]. Per questo
    > non si passa alla modalità sommata se la finale ha già un sistema diverso
    > da quello del campionato, o una strategia a tabellone.
    """

    def test_in_modalita_sommata_la_finale_a_tabellone_e_rifiutata(self, db_session):
        from models.exceptions import ValidationError

        campionato = _campionato(db_session, "WINS")
        _gara_del_campionato(
            db_session, campionato, numero=1, stato=GaraStatus.COMPLETED.value
        )
        configurazione = _configurazione(
            db_session, campionato, strategy_type="direct_elimination"
        )
        db_session.commit()

        with pytest.raises(ValidationError):
            PlayoffService.create_playoff_gara(configurazione.id)

    def test_non_si_passa_alla_somma_con_una_finale_di_altro_sistema(self, db_session):
        from models.exceptions import ValidationError

        campionato = _campionato(db_session, "RACK")
        configurazione = _configurazione(
            db_session, campionato, final_ranking_mode="playoff_only"
        )
        _finale(db_session, campionato, configurazione, sistema="WINS")
        db_session.commit()
        configurazione_id = configurazione.id

        with pytest.raises(ValidationError):
            PlayoffService.update_scoring(
                configurazione_id, final_ranking_mode="campionato_plus_playoff"
            )

        db_session.expire_all()
        rimasta = db_session.get(PlayoffConfiguration, configurazione_id)
        assert rimasta.final_ranking_mode == "playoff_only"

    def test_non_si_passa_alla_somma_con_la_strategia_a_tabellone(self, db_session):
        from models.exceptions import ValidationError

        campionato = _campionato(db_session, "WINS")
        configurazione = _configurazione(
            db_session,
            campionato,
            final_ranking_mode="playoff_only",
            strategy_type="double_knockout",
        )
        db_session.commit()

        with pytest.raises(ValidationError):
            PlayoffService.update_scoring(
                configurazione.id, final_ranking_mode="campionato_plus_playoff"
            )

    def test_con_lo_stesso_sistema_si_passa_alla_somma(self, db_session):
        campionato = _campionato(db_session, "RACK")
        configurazione = _configurazione(
            db_session, campionato, final_ranking_mode="playoff_only"
        )
        _finale(db_session, campionato, configurazione, sistema="RACK")
        db_session.commit()
        configurazione_id = configurazione.id

        PlayoffService.update_scoring(
            configurazione_id, final_ranking_mode="campionato_plus_playoff"
        )

        db_session.expire_all()
        aggiornata = db_session.get(PlayoffConfiguration, configurazione_id)
        assert aggiornata.final_ranking_mode == "campionato_plus_playoff"

    def test_salvare_il_peso_senza_cambiare_modalita_non_si_blocca(self, db_session):
        """Il form del punteggio rimanda la modalità a ogni salvataggio. Una
        finale già incoerente — nata a vittorie in un campionato a triangoli,
        prima del 2026-09-14 — non deve impedire al direttore di cambiare il
        peso: il controllo scatta sul **passaggio** alla somma, non sullo stato."""
        campionato = _campionato(db_session, "RACK")
        configurazione = _configurazione(
            db_session, campionato, final_ranking_mode="campionato_plus_playoff"
        )
        _finale(db_session, campionato, configurazione, sistema="WINS")
        db_session.commit()
        configurazione_id = configurazione.id

        PlayoffService.update_scoring(
            configurazione_id,
            final_ranking_mode="campionato_plus_playoff",
            playoff_weight=2,
        )

        db_session.expire_all()
        aggiornata = db_session.get(PlayoffConfiguration, configurazione_id)
        assert aggiornata.playoff_weight == 2


# ────────────────────────────────────────────────────────────────────────
# Il profilo dell'esercizio (ADR-065)
# ────────────────────────────────────────────────────────────────────────


def _esercizio_per_il_profilo(db_session):
    from models.challenge.models import Challenge

    esercizio = Challenge(
        title=f"Profilo {uuid.uuid4().hex[:6]}",
        description="Dieci tiri dalla stessa posizione",
        image_path="test.jpg",
        pass_fail_only=False,
        is_active=True,
    )
    db_session.add(esercizio)
    db_session.flush()
    return esercizio


@pytest.mark.unit
class TestIlProfiloDellEsercizio:
    """`SPECIFICHE.md` riga 318, nota del 2026-09-19.

    > Ha zero, una o più abilità […], al più tre, e zero, uno o più gesti […],
    > senza tetto […]. Ha un livello dichiarato da 1 a 5, facoltativo; una
    > famiglia con un passo (da 1 in su) […]
    """

    def test_i_due_vocabolari_sono_quelli_della_specifica(self):
        from models.challenge.vocabulary import Abilita, Gesto

        assert len(Abilita) == 7
        assert len(Gesto) == 10

    def test_tre_abilita_passano_la_quarta_no(self, db_session):
        from models.challenge.profile_service import ChallengeProfileService
        from models.exceptions import ValidationError

        esercizio = _esercizio_per_il_profilo(db_session)
        ChallengeProfileService.set_profile(
            esercizio.id, abilita=["tiro", "posizione", "sponde"]
        )
        with pytest.raises(ValidationError):
            ChallengeProfileService.set_profile(
                esercizio.id, abilita=["tiro", "posizione", "sponde", "difesa"]
            )

    def test_i_gesti_non_hanno_tetto(self, db_session):
        from models.challenge.profile_service import ChallengeProfileService
        from models.challenge.vocabulary import Gesto

        esercizio = _esercizio_per_il_profilo(db_session)
        ChallengeProfileService.set_profile(
            esercizio.id, gesti=[g.value for g in Gesto]
        )

    @pytest.mark.parametrize("livello", [1, 5])
    def test_gli_estremi_del_livello_sono_ammessi(self, db_session, livello):
        from models.challenge.profile_service import ChallengeProfileService

        esercizio = _esercizio_per_il_profilo(db_session)
        salvato = ChallengeProfileService.set_profile(
            esercizio.id, declared_level=livello
        )
        assert salvato.declared_level == livello

    @pytest.mark.parametrize("livello", [0, 6])
    def test_fuori_da_uno_cinque_il_livello_si_rifiuta(self, db_session, livello):
        from models.challenge.profile_service import ChallengeProfileService
        from models.exceptions import ValidationError

        esercizio = _esercizio_per_il_profilo(db_session)
        with pytest.raises(ValidationError):
            ChallengeProfileService.set_profile(esercizio.id, declared_level=livello)

    def test_il_livello_e_facoltativo(self, db_session):
        esercizio = _esercizio_per_il_profilo(db_session)
        assert esercizio.declared_level is None

    def test_il_passo_parte_da_uno(self, db_session):
        from models.challenge.profile_service import ChallengeProfileService
        from models.exceptions import ValidationError

        esercizio = _esercizio_per_il_profilo(db_session)
        with pytest.raises(ValidationError):
            ChallengeProfileService.set_profile(
                esercizio.id, family="stop shot", family_step=0
            )


@pytest.mark.unit
class TestIlVotoDegliEsercizi:
    """`SPECIFICHE.md`, nota del 2026-09-19 sul profilo dell'esercizio.

    > Un giocatore può dare a un esercizio un voto da 1 a 5, uno solo, che può
    > cambiare; vota solo chi l'ha provato, cioè chi ha almeno una prova
    > conclusa, dal catalogo o in gara.
    """

    def _chi_ha_provato(self, db_session, esercizio):
        from models.challenge.models import ChallengeAttempt
        from models.user.models import User
        from models.user.role_enum import UserRole

        giocatore = User(
            username=f"v_{uuid.uuid4().hex[:8]}",
            email=f"v_{uuid.uuid4().hex[:8]}@test.com",
            role=UserRole.PLAYER.value,
        )
        giocatore.set_password("test1234")
        db_session.add(giocatore)
        db_session.flush()
        db_session.add(
            ChallengeAttempt(
                user_id=giocatore.id,
                challenge_id=esercizio.id,
                score=1,
                completed=True,
            )
        )
        db_session.flush()
        return giocatore

    @pytest.mark.parametrize("voto", [1, 5])
    def test_gli_estremi_sono_ammessi(self, db_session, voto):
        from models.challenge.rating_service import ChallengeRatingService

        esercizio = _esercizio_per_il_profilo(db_session)
        giocatore = self._chi_ha_provato(db_session, esercizio)
        numeri = ChallengeRatingService.rate(giocatore.id, esercizio.id, voto)
        assert numeri.rating_average == voto

    @pytest.mark.parametrize("voto", [0, 6])
    def test_fuori_scala_si_rifiuta(self, db_session, voto):
        from models.challenge.rating_service import ChallengeRatingService
        from models.exceptions import ValidationError

        esercizio = _esercizio_per_il_profilo(db_session)
        giocatore = self._chi_ha_provato(db_session, esercizio)
        with pytest.raises(ValidationError):
            ChallengeRatingService.rate(giocatore.id, esercizio.id, voto)

    def test_uno_solo_che_puo_cambiare(self, db_session):
        from models.challenge.rating_service import ChallengeRatingService

        esercizio = _esercizio_per_il_profilo(db_session)
        giocatore = self._chi_ha_provato(db_session, esercizio)
        ChallengeRatingService.rate(giocatore.id, esercizio.id, 2)
        numeri = ChallengeRatingService.rate(giocatore.id, esercizio.id, 5)
        assert (numeri.rating_count, numeri.rating_average) == (1, 5)

    def test_vota_solo_chi_ha_provato(self, db_session):
        """Chi vota e chi è contato fra i giocatori sono lo stesso insieme."""
        from models.challenge.popularity import popularity_for
        from models.challenge.rating_service import ChallengeRatingService
        from models.exceptions import PermissionDeniedError

        esercizio = _esercizio_per_il_profilo(db_session)
        contato = self._chi_ha_provato(db_session, esercizio)
        assert popularity_for([esercizio.id])[esercizio.id].players == 1
        ChallengeRatingService.rate(contato.id, esercizio.id, 4)

        altro = _esercizio_per_il_profilo(db_session)
        with pytest.raises(PermissionDeniedError):
            ChallengeRatingService.rate(contato.id, altro.id, 4)


@pytest.mark.unit
class TestLaProvaFattaDiColpi:
    """`SPECIFICHE.md`, sezione «Challenge», nota del 2026-09-20.

    > […] da uno a cinque anelli concentrici di uguale spessore — lo spessore si
    > misura in quarti di diamante — ciascuno col suo valore in punti, dal
    > centro verso l'esterno. Il colpo imbucato vale i punti dell'anello in cui
    > si ferma la battente; sul confine fra due anelli vale quello esterno;
    > fuori dall'ultimo anello vale zero. […] Imbucate = colpi imbucati su colpi
    > tirati. Posizione = media, sui soli colpi imbucati, di 1 − distanza dal
    > centro ÷ raggio esterno del bersaglio, mai sotto zero.

    Le formule sono riderivate qui a mano, su un bersaglio di cui si sanno le
    misure: un test che chiamasse `points_at` per sapere quanto deve valere
    `points_at` confronterebbe il codice con sé stesso.
    """

    @staticmethod
    def _bersaglio():
        from models.challenge.target import Target

        # Centro a 6 diamanti e 2, anelli da mezzo diamante: 3, 2, 1 punti.
        return Target(x=600, y=200, step=50, values=(3, 2, 1))

    @pytest.mark.parametrize(
        "distanza,punti",
        [
            (0, 3),
            (49, 3),
            (50, 2),  # sul confine vale l'anello esterno
            (99, 2),
            (100, 1),
            (149, 1),
            (150, 0),  # l'orlo dell'ultimo anello è già fuori
            (400, 0),
        ],
    )
    def test_i_punti_dell_anello(self, distanza, punti):
        assert self._bersaglio().points_at(600 + distanza, 200) == punti

    def test_la_distanza_e_in_ogni_direzione(self):
        # 30-40-50: a 50 unità dal centro, in diagonale, si è sul confine.
        assert self._bersaglio().points_at(630, 240) == 2

    @pytest.mark.parametrize("anelli,ammesso", [(1, True), (5, True), (6, False)])
    def test_da_uno_a_cinque_anelli(self, anelli, ammesso):
        import json

        from models.challenge.diagram import parse_scene
        from models.exceptions import ValidationError

        scena = json.dumps(
            {
                "v": 4,
                "items": [
                    {
                        "type": "target",
                        "x": 400,
                        "y": 200,
                        "step": 25,
                        "values": [1] * anelli,
                    }
                ],
            }
        )
        if ammesso:
            assert parse_scene(scena)
        else:
            with pytest.raises(ValidationError):
                parse_scene(scena)

    @pytest.mark.parametrize(
        "spessore,ammesso",
        [(25, True), (50, True), (75, True), (10, False), (60, False)],
    )
    def test_lo_spessore_e_in_quarti_di_diamante(self, spessore, ammesso):
        import json

        from models.challenge.diagram import parse_scene
        from models.exceptions import ValidationError

        scena = json.dumps(
            {
                "v": 4,
                "items": [
                    {"type": "target", "x": 1, "y": 1, "step": spessore, "values": [1]}
                ],
            }
        )
        if ammesso:
            assert parse_scene(scena)
        else:
            with pytest.raises(ValidationError):
                parse_scene(scena)

    def test_imbucate_e_posizione_sono_due_conti_diversi(self):
        from types import SimpleNamespace as Colpo

        from models.challenge.shot_stats import pocketing_pct, position_pct

        colpi = [
            Colpo(made=True, x=600, y=200),  # sul centro: 1
            Colpo(made=True, x=675, y=200),  # a metà raggio: 0,5
            Colpo(made=True, x=790, y=200),  # fuori dal bersaglio: 0, mai sotto
            Colpo(made=False, x=None, y=None),  # non ha un punto: non entra
        ]
        assert pocketing_pct(colpi) == 75  # tre su quattro
        assert position_pct(colpi, self._bersaglio()) == 50  # (1 + 0,5 + 0) / 3

    def test_senza_imbucate_la_posizione_non_c_e(self):
        from types import SimpleNamespace as Colpo

        from models.challenge.shot_stats import pocketing_pct, position_pct

        colpi = [Colpo(made=False, x=None, y=None)]
        assert pocketing_pct(colpi) == 0
        assert position_pct(colpi, self._bersaglio()) is None

    def test_il_punteggio_e_la_somma_dei_colpi(self, db_session):
        import json

        from models.challenge.models import Challenge
        from models.challenge.recording import RecordingMode
        from models.challenge.shot_service import ShotRunService

        esercizio = Challenge(
            description="x",
            image_path="t.png",
            diagram_scene=json.dumps(
                {
                    "v": 4,
                    "items": [
                        {
                            "type": "target",
                            "x": 600,
                            "y": 200,
                            "step": 50,
                            "values": [3, 2, 1],
                        }
                    ],
                }
            ),
            pass_fail_only=False,
            recording_mode=RecordingMode.SHOTS.value,
            shots_count=4,
            max_score=12,
            is_active=True,
        )
        from models.user.models import User
        from models.user.role_enum import UserRole

        giocatore = User(
            username=f"c_{uuid.uuid4().hex[:8]}",
            email=f"c_{uuid.uuid4().hex[:8]}@test.com",
            role=UserRole.PLAYER.value,
        )
        giocatore.set_password("test1234")
        db_session.add_all([esercizio, giocatore])
        db_session.flush()

        for x in (600, 660, 720):  # 3 + 2 + 1
            ShotRunService.record_shot(
                giocatore.id, esercizio.id, made=True, x=x, y=200
            )
        ShotRunService.record_shot(giocatore.id, esercizio.id, made=False)  # 0
        assert ShotRunService.close(giocatore.id, esercizio.id).score == 6


@pytest.mark.unit
class TestLEsercizioConEstrazione:
    """`SPECIFICHE.md`, sezione «Challenge», nota del 2026-09-20.

    > […] l'app pesca una voce da ogni lista, indipendentemente […]. Il
    > punteggio della prova è la somma dei colpi e il massimo è i colpi per il
    > valore più alto della scala. […] In esami e gare un esercizio con
    > estrazione non si può mettere.
    """

    @staticmethod
    def _spec():
        from models.challenge.draw_spec import build_spec

        return build_spec(
            [
                {"label": "sponde", "options": ["1 sponda", "2 sponde"]},
                {"label": "bilia", "options": ["bilia 1", "bilia 2", "bilia 3"]},
            ],
            [
                {"label": "Mancata", "points": 0},
                {"label": "Imbucata", "points": 4},
            ],
        )

    def test_una_voce_da_ogni_lista(self):
        """Il conto è riderivato: due liste da 2 e 3 voci fanno sei consegne."""
        import random

        rng = random.Random(3)
        viste = {self._spec().draw(rng) for _ in range(500)}

        assert len(viste) == 2 * 3
        for consegna in viste:
            sponde, bilia = consegna.split(", ")
            assert sponde in ("1 sponda", "2 sponde")
            assert bilia in ("bilia 1", "bilia 2", "bilia 3")

    def test_il_massimo_e_i_colpi_per_l_esito_piu_alto(self):
        spec = self._spec()
        colpi = 12

        assert spec.max_points == 4
        assert colpi * spec.max_points == 48

    @pytest.mark.parametrize(
        "quante,ammesse", [(0, False), (1, True), (3, True), (4, False)]
    )
    def test_le_liste_vanno_da_una_a_tre(self, quante, ammesse):
        from models.challenge.draw_spec import build_spec
        from models.exceptions import ValidationError

        liste = [{"label": f"l{i}", "options": ["a", "b"]} for i in range(quante)]
        scala = [{"label": "no", "points": 0}, {"label": "sì", "points": 1}]
        if ammesse:
            assert len(build_spec(liste, scala).sources) == quante
        else:
            with pytest.raises(ValidationError):
                build_spec(liste, scala)

    def test_fuori_dall_allenamento_si_rifiuta(self, db_session):
        from types import SimpleNamespace

        from models.challenge.recording import refuse_if_drawn
        from models.exceptions import ValidationError

        with pytest.raises(ValidationError):
            refuse_if_drawn(SimpleNamespace(recording_mode="draw"))
        refuse_if_drawn(SimpleNamespace(recording_mode="shots"))


# ══ Il girone all'italiana ═══════════════════════════════════════════════


@pytest.mark.unit
class TestIlGironeAllItaliana:
    """`SPECIFICHE.md` riga 112.

    > Con `N` giocatori servono `N-1` turni se `N` è pari e `N` turni se `N`
    > è dispari: nel dispari ogni giocatore riposa una volta. **Il riposo nel
    > girone non vale niente**: zero vittorie, zero punti, zero rack, e non è
    > un match giocato

    Fino al 2026-10-11 il riposo era «con la X», che vale una vittoria: la
    regola l'ha cambiata l'utente (nota datata nella specifica).
    """

    @pytest.mark.parametrize("n", [3, 4, 5, 6, 7, 8, 11, 12])
    def test_numero_di_turni(self, n):
        from models.matchmaking.configuration import (
            MatchmakingStrategy,
            calculate_rounds_for_strategy,
        )
        from models.matchmaking.strategies.round_robin import RoundRobinStrategy

        atteso = n - 1 if n % 2 == 0 else n
        assert (
            calculate_rounds_for_strategy(MatchmakingStrategy.ROUND_ROBIN, n) == atteso
        )
        calendario = RoundRobinStrategy()._generate_round_robin_schedule(
            list(range(1, n + 1))
        )
        assert len(calendario) == atteso

    @pytest.mark.parametrize("n", [5, 7])
    def test_nel_dispari_ognuno_riposa_una_volta(self, n):
        from models.matchmaking.strategies.round_robin import RoundRobinStrategy

        calendario = RoundRobinStrategy()._generate_round_robin_schedule(
            list(range(1, n + 1))
        )
        riposi = [p[0] for turno in calendario for p in turno if len(p) == 1]
        assert sorted(riposi) == list(range(1, n + 1))

    @staticmethod
    def _riposo(db_session, sistema: str):
        from models.competition.round_creation import create_matches_from_pairings
        from models.matchmaking.strategies.base import Pairing

        gara = _gara(db_session, sistema=sistema)
        gara.matchmaking_strategy = "round_robin"
        giocatore = _utente(db_session)
        create_matches_from_pairings(
            gara=gara,
            pairings=[Pairing(players=(giocatore.id,), is_bye=True, riposo=True)],
            round_number=1,
            round_distance=gara.distance,
        )
        db_session.commit()
        return gara, giocatore

    @pytest.mark.parametrize("sistema", ["WINS", "RACK", "POINTS"])
    def test_il_riposo_non_vale_niente(self, db_session, sistema):
        """> zero vittorie, zero punti, zero rack, e non è un match giocato;
        > chi riposa resta in classifica"""
        gara, giocatore = self._riposo(db_session, sistema)
        voce = _punteggi(gara.id)[giocatore.id]
        assert (voce.matches_won, voce.matches_lost, voce.matches_drawn) == (0, 0, 0)
        assert (voce.points, voce.racks_won, voce.racks_lost) == (0, 0, 0)

    def test_nel_girone_il_dispari_solo_col_riposo(self):
        """> Nel girone il dispari si gestisce **solo col riposo**: la X con
        > esercizio non si può scegliere, e se il campionato la propone a una
        > gara a girone, la gara ripiega sul riposo."""
        from models.matchmaking.configuration import (
            STRATEGY_CONSTRAINTS,
            MatchmakingStrategy,
            OddNumberPolicy,
            odd_policy_for_strategy,
        )

        assert STRATEGY_CONSTRAINTS[MatchmakingStrategy.ROUND_ROBIN][
            "odd_policies"
        ] == [OddNumberPolicy.BYE.value]
        assert (
            odd_policy_for_strategy(
                MatchmakingStrategy.ROUND_ROBIN, OddNumberPolicy.BYE_WITH_CHALLENGE
            )
            == OddNumberPolicy.BYE.value
        )

    def test_col_sistema_rack_il_riposo_e_ammesso(self):
        """> nel girone il riposo è ammesso anche col sistema RACK"""
        from models.competition import validators as v

        errori, _avvisi = v.validate_gara_configuration(
            classification_system=v.ClassificationSystem.RACK,
            distance_type=v.DistanceType.EXACTLY,
            distance=4,
            multi_set=False,
            odd_handling=v.OddHandling.BYE,
            forfeit_policy=v.ForfeitPolicy.EXCLUDE,
            matchmaking=v.MatchmakingStrategy.ROUND_ROBIN,
        )
        assert errori == []

    def test_l_avversario_dell_escluso_vince_a_tavolino(self, db_session):
        """`SPECIFICHE.md` riga 104.

        > Nel **girone all'italiana** invece chi viene escluso resta al suo
        > posto nel calendario, e il suo avversario dei turni successivi
        > **vince a tavolino**, come contro un forfait: vittoria e rack pieni
        > fino alla distanza di quel turno.

        Il turno si gioca «al 3» in una gara «al 5»: il tavolino vale 3.
        """
        from models.competition.round_creation import create_matches_from_pairings
        from models.matchmaking.strategies.base import Pairing

        gara = _gara(db_session)
        gara.matchmaking_strategy = "round_robin"
        gara.is_race_to = True
        avversario, escluso = _utente(db_session), _utente(db_session)
        create_matches_from_pairings(
            gara=gara,
            pairings=[
                Pairing(
                    players=(escluso.id, avversario.id), forfeit_players=(escluso.id,)
                )
            ],
            round_number=1,
            round_distance=3,
        )
        db_session.commit()
        partita = db_session.query(Match).filter_by(gara_id=gara.id).one()
        assert partita.winner_id == avversario.id
        assert (partita.player1_score, partita.player2_score) == (0, 3)
        assert _punteggi(gara.id)[avversario.id].matches_won == 1


# ══ I gironi multipli ════════════════════════════════════════════════════


@pytest.mark.unit
class TestIGironi:
    """`SPECIFICHE.md` righe 114-122 («Turno», «Gironi multipli») e 372-377
    («Classifica», «La classifica a gironi»), 2026-10-11, ADR-076."""

    def test_vuoto_o_uno_e_il_girone_unico(self, db_session):
        """> La gara dice un **tetto**, «gironi: fino a N», da 1 a 8; vuoto o 1
        > vuol dire **girone unico** […] Le altre strategie non hanno gironi."""
        from models.matchmaking.gironi import tetto_di_gironi

        assert [tetto_di_gironi(v) for v in (None, 0, 1, 2, 8, 9)] == [
            1,
            1,
            1,
            2,
            8,
            8,
        ]
        gara = _gara(db_session)
        gara.max_groups = 4
        assert gara.effective_max_groups == 1  # amalfi: niente gironi
        gara.matchmaking_strategy = "round_robin"
        assert gara.effective_max_groups == 4
        gara.max_groups = None
        assert gara.effective_max_groups == 1  # gara singola: girone unico

    def test_il_numero_esatto_e_la_proposta(self):
        """> da 1 al tetto, con almeno **3 giocatori per girone**. La proposta
        > è **un girone ogni 6 iscritti, arrotondato per eccesso** […] con 11
        > iscritti e tetto 2, due gironi. […] (8 iscritti: al più 2 gironi)."""
        from models.matchmaking.gironi import (
            gironi_possibili,
            proposta_di_gironi,
            verifica_numero_di_gironi,
        )

        assert proposta_di_gironi(11, 2) == 2
        assert proposta_di_gironi(12, 8) == 2
        assert proposta_di_gironi(13, 8) == 3
        assert proposta_di_gironi(5, 2) == 1
        assert gironi_possibili(8, 3) == 2
        assert verifica_numero_di_gironi(8, 3, 3) == "giocatori"
        assert verifica_numero_di_gironi(9, 3, 3) is None
        assert verifica_numero_di_gironi(12, 3, 2) == "tetto"

    def test_le_taglie(self):
        """> 11 iscritti in 2 gironi fanno 6 e 5, in 3 gironi 4, 4 e 3."""
        from models.matchmaking.gironi import taglie_dei_gironi

        assert taglie_dei_gironi(11, 2) == [6, 5]
        assert taglie_dei_gironi(11, 3) == [4, 4, 3]

    def test_uno_per_girone_andata_e_ritorno(self):
        """> con due gironi il 1° va in A, il 2° e il 3° in B, il 4° e il 5°
        > in A, e così via."""
        from models.matchmaking.gironi import (
            ComposizioneGironi,
            Iscritto,
            componi_gironi,
        )

        iscritti = [Iscritto(player_id=p, elo=2000 - p) for p in range(1, 9)]
        a, b = componi_gironi(iscritti, 2, ComposizioneGironi.ELO, seme="x")
        assert sorted(a) == [1, 4, 5, 8]
        assert sorted(b) == [2, 3, 6, 7]

    def test_per_elo_e_per_categoria(self):
        """> **per ELO** (dal più alto; chi non ha ELO in fondo), **per
        > categoria** (nell'ordine […]; chi non ha categoria in fondo; dentro
        > la categoria per ELO)."""
        from models.matchmaking.gironi import (
            ComposizioneGironi,
            Iscritto,
            ordine_di_composizione,
        )

        iscritti = [
            Iscritto(1, elo=None, categoria=0),
            Iscritto(2, elo=1500, categoria=1),
            Iscritto(3, elo=1800, categoria=None),
            Iscritto(4, elo=1600, categoria=0),
        ]
        assert ordine_di_composizione(iscritti, ComposizioneGironi.ELO, "s") == [
            3,
            4,
            2,
            1,
        ]
        assert ordine_di_composizione(iscritti, ComposizioneGironi.CATEGORIA, "s") == [
            4,
            1,
            2,
            3,
        ]

    def test_turni_paralleli(self):
        """> I turni della gara sono quelli del **girone più numeroso** […]
        > 11 iscritti in 6 e 5: entrambi i gironi giocano 5 turni […] 13
        > iscritti in 7 e 6: 7 turni, e il girone da 6 si ferma dopo il
        > quinto."""
        from models.matchmaking.gironi import turni_dei_gironi, turni_del_girone

        assert turni_dei_gironi([6, 5]) == 5
        assert turni_dei_gironi([7, 6]) == 7
        assert turni_del_girone(6) == 5

    def test_il_riposo_e_il_tavolino_valgono_anche_nei_gironi(self):
        """> con le regole del paragrafo qui sopra (riposo che non vale niente,
        > avversario dell'escluso che vince a tavolino)."""
        from models.matchmaking.strategies.round_robin import RoundRobinStrategy

        riga = [(1, 2), (3,), (4, 5)]
        pairings = RoundRobinStrategy._pairings_della_riga(
            riga, {1, 2, 3, 4}, round_number=2, bracket_group=1
        )
        riposo = next(p for p in pairings if p.players == (3,))
        assert riposo.is_bye and riposo.riposo
        tavolino = next(p for p in pairings if 5 in p.players)
        assert tavolino.players == (4, 5) and tavolino.forfeit_players == (5,)
        assert not tavolino.is_bye
        assert {p.bracket_group for p in pairings} == {1}

    def test_nella_gara_per_partita_giocata(self):
        """> il primo del girone da 6 con 4 vittorie su 5 (12 punti, 2,4 a
        > partita) viene **dopo** il primo del girone da 5 con 4 su 4 (12
        > punti, 3 a partita), e **prima** di quello con 3 su 4 (9 punti, 2,25
        > a partita)."""
        from models.classification.gironi import Giocate, ordina_a_gironi
        from models.classification.ordinamento import Concorrente, Criterio

        girone = {1: 0, 2: 1}
        sei = Giocate(partite=5, vittorie=4, punti=12)
        for cinque, atteso in (
            (Giocate(partite=4, vittorie=4, punti=12), [2, 1]),
            (Giocate(partite=4, vittorie=3, punti=9), [1, 2]),
        ):
            esito = ordina_a_gironi(
                [Concorrente(1, punti=12), Concorrente(2, punti=cinque.punti)],
                girone,
                {1: sei, 2: cinque},
                Criterio.PUNTI,
                (),
            )
            assert [c.player_id for f in esito.fasce for c in f.giocatori] == atteso

    def test_prima_i_primi_poi_i_secondi(self):
        """> vengono prima tutti i **primi** dei gironi, ordinati fra loro, poi
        > tutti i **secondi**, e così via."""
        from models.classification.gironi import Giocate, ordina_a_gironi
        from models.classification.ordinamento import Concorrente, Criterio

        girone = {1: 0, 2: 0, 3: 1, 4: 1}
        punti = {1: 9, 2: 6, 3: 3, 4: 0}
        esito = ordina_a_gironi(
            [Concorrente(p, punti=v) for p, v in punti.items()],
            girone,
            {p: Giocate(partite=3, punti=v) for p, v in punti.items()},
            Criterio.PUNTI,
            (),
        )
        assert [[c.player_id for c in f.giocatori] for f in esito.fasce] == [
            [1],
            [3],
            [2],
            [4],
        ]
        assert esito.posizione_nel_girone == {1: 1, 2: 2, 3: 1, 4: 2}

    def test_fra_gironi_lo_scontro_diretto_non_decide(self):
        """> Fra gironi diversi lo **scontro diretto non decide** — non si sono
        > incontrati — e si passa al criterio dopo; chi resta pari condivide
        > la posizione."""
        from models.classification.gironi import Giocate, ordina_a_gironi
        from models.classification.ordinamento import (
            Concorrente,
            Criterio,
            Voce,
        )

        girone = {1: 0, 2: 1}
        giocate = {p: Giocate(partite=2, punti=6) for p in (1, 2)}
        concorrenti = [Concorrente(p, punti=6) for p in (1, 2)]
        esito = ordina_a_gironi(
            concorrenti,
            girone,
            giocate,
            Criterio.PUNTI,
            (Voce(Criterio.SCONTRI_DIRETTI),),
        )
        assert [[c.player_id for c in f.giocatori] for f in esito.fasce] == [[1, 2]]


# ══ Il limite di tempo ═══════════════════════════════════════════════════


@pytest.mark.unit
class TestIlLimiteDiTempo:
    """`SPECIFICHE.md` riga 265 e riga 271 (sezione «Limite di tempo»).

    > lo **propone il campionato**, lo **decide la gara** (anche una gara
    > singola), si **fissa sul match quando nasce**.

    > **A tempo scaduto non succede niente da sé**: il match resta in corso
    """

    def _gara_e_partita(self, minuti):
        from datetime import time

        from models.base import db
        from models.competition.models import Gara
        from models.match.models import Match
        from models.status_enum import GaraStatus, MatchStatus

        gara = Gara(
            number=1,
            name=f"G {uuid.uuid4().hex[:6]}",
            date=date(2026, 1, 1),
            time=time(20, 0),
            discipline="8_ball",
            distance=3,
            rounds_count=3,
            current_round=1,
            min_participants=2,
            matchmaking_strategy="round_robin",
            status=GaraStatus.PLAYING.value,
            time_limit_minutes=minuti,
        )
        db.session.add(gara)
        db.session.flush()
        match = Match(
            gara_id=gara.id,
            round_number=1,
            status=MatchStatus.PLAYING.value,
            match_distance=3,
        )
        db.session.add(match)
        db.session.commit()
        return gara, match

    def test_trenta_minuti_si_fissano_sul_match(self, db_session):
        from models.base import db

        gara, match = self._gara_e_partita(30)
        assert match.time_limit_minutes == 30
        gara.time_limit_minutes = 45
        db.session.commit()
        assert match.time_limit_minutes == 30

    def test_a_tempo_scaduto_il_match_resta_in_corso(self, db_session):
        from datetime import datetime, timedelta

        from models.match import tempo
        from models.status_enum import MatchStatus

        _, match = self._gara_e_partita(30)
        inizio = datetime(2026, 10, 6, 20, 0)
        tempo.avvia_conto_alla_rovescia(match, adesso=inizio)
        dopo = inizio + timedelta(minutes=31)
        assert tempo.tempo_scaduto(match, adesso=dopo)
        assert match.status == MatchStatus.PLAYING.value
        assert not match.is_awaiting_validation

    def test_un_turno_con_limite_diverso(self, db_session):
        """`SPECIFICHE.md` riga 265: «anche **per un singolo turno**, con tre
        scelte: come la gara, senza limite, oppure un numero di minuti
        diverso»."""
        from models.base import db
        from models.competition.round_configuration import RoundConfiguration
        from models.match.models import Match
        from models.status_enum import MatchStatus

        gara, _ = self._gara_e_partita(30)
        RoundConfiguration.create_or_update(gara.id, 2, time_limit_minutes=45)
        RoundConfiguration.create_or_update(gara.id, 3, time_limit_minutes=0)
        db.session.commit()
        minuti = {}
        for turno in (2, 3):
            m = Match(
                gara_id=gara.id,
                round_number=turno,
                status=MatchStatus.PLAYING.value,
                match_distance=3,
            )
            db.session.add(m)
            db.session.commit()
            minuti[turno] = m.time_limit_minutes
        assert minuti == {2: 45, 3: None}


@pytest.mark.unit
class TestInterrompereAtempo:
    """`SPECIFICHE.md` righe 273–278 (sezione «Limite di tempo»).

    > chi è avanti **vince**; a parità è **pareggio** dove il pareggio è
    > ammesso, cioè fuori dal tabellone [...] nel **tabellone** il pareggio
    > non esiste: a parità il direttore indica chi passa il turno.

    > un match che a tempo scaduto arriva comunque alla distanza si chiude
    > come sempre, **senza** il segno.
    """

    def _partita(self, strategia, p1, p2, **kw):
        from datetime import time

        from models.base import db
        from models.competition.models import Gara
        from models.match.models import Match
        from models.status_enum import GaraStatus, MatchStatus

        gara = Gara(
            number=1,
            name=f"G {uuid.uuid4().hex[:6]}",
            date=date(2026, 1, 1),
            time=time(20, 0),
            discipline="8_ball",
            distance=3,
            is_race_to=True,
            rounds_count=3,
            current_round=1,
            min_participants=2,
            matchmaking_strategy=strategia,
            status=GaraStatus.PLAYING.value,
            time_limit_minutes=30,
        )
        db.session.add(gara)
        from models.user.models import User

        giocatori = [
            User(
                username=f"sp{i}_{uuid.uuid4().hex[:6]}",
                email=f"sp{i}_{uuid.uuid4().hex[:6]}@t.it",
            )
            for i in (1, 2)
        ]
        for giocatore in giocatori:
            giocatore.set_password("pwd")
        db.session.add_all(giocatori)
        db.session.flush()
        match = Match(
            gara_id=gara.id,
            round_number=1,
            player1_id=giocatori[0].id,
            player2_id=giocatori[1].id,
            status=MatchStatus.PLAYING.value,
            match_distance=3,
            player1_score=p1,
            player2_score=p2,
            table_assignment="1",
            **kw,
        )
        db.session.add(match)
        db.session.commit()
        return match

    def test_chi_e_avanti_vince(self, db_session):
        from models.match import chiusura

        match = self._partita("round_robin", 2, 1)
        esito = chiusura.esito(match)
        assert esito.vincitore_id == match.player1_id
        assert not esito.pareggio and not esito.serve_chi_passa

    def test_pari_fuori_e_dentro_il_tabellone(self, db_session):
        from models.match import chiusura

        assert chiusura.esito(self._partita("round_robin", 1, 1)).pareggio
        assert chiusura.esito(self._partita("amalfi", 1, 1)).pareggio
        nel_tabellone = chiusura.esito(self._partita("direct_elimination", 1, 1))
        assert nel_tabellone.serve_chi_passa and not nel_tabellone.pareggio

    def test_alla_distanza_a_tempo_scaduto_nessun_segno(self, db_session):
        from datetime import datetime

        from models.base import db
        from models.match.models import Match
        from models.match.validation_service import MatchValidationService

        match = self._partita(
            "round_robin", 3, 1, timer_started_at=datetime(2000, 1, 1, 20, 0)
        )
        MatchValidationService.validate_and_complete(match.id)
        assert db.session.get(Match, match.id).closed_on_time is False


class TestIlListinoDelleQuote:
    """`SPECIFICHE.md` riga 92 (nota del 2026-10-06, ADR-079).

    > ordinato dalla quota più alta alla più bassa e, a parità di quota, in
    > ordine alfabetico [...] la categoria pesa sull'ELO solo nelle gare con
    > handicap.
    """

    def test_dalla_quota_piu_alta_poi_alfabetico(self, db_session):
        from models.categoria.listino import ListinoService, VoceListino, listino_di

        gara = _gara(db_session)
        ListinoService.salva(
            gara_id=gara.id,
            voci=[
                VoceListino("Amatori", 15),
                VoceListino("Serie C", 20),
                VoceListino("Serie A", 30),
                VoceListino("Serie B", 20),
            ],
        )
        assert [(c.name, c.entry_fee) for c in listino_di(gara)] == [
            ("Serie A", 30),
            ("Serie B", 20),
            ("Serie C", 20),
            ("Amatori", 15),
        ]

    def test_senza_handicap_la_categoria_non_pesa_sull_elo(self, db_session):
        from models.categoria.listino import ListinoService, VoceListino
        from models.categoria.models import Categoria
        from models.rating.eligibility import RatingEligibility

        gara = _gara(db_session)
        ListinoService.salva(
            gara_id=gara.id, voci=[VoceListino("A", 30), VoceListino("C", 15)]
        )
        a, c = (
            Categoria.query.filter_by(gara_id=gara.id, name=nome).one()
            for nome in ("A", "C")
        )
        uno, due = _utente(db_session), _utente(db_session)
        db_session.add_all(
            [
                Inscription(gara_id=gara.id, user_id=uno.id, categoria_id=a.id),
                Inscription(gara_id=gara.id, user_id=due.id, categoria_id=c.id),
            ]
        )
        partita = Match(
            gara_id=gara.id, round_number=1, player1_id=uno.id, player2_id=due.id
        )
        db_session.add(partita)
        db_session.flush()
        assert RatingEligibility.exclusion_reason(partita, is_walkover=False) is None


# ══ La classifica a punti ════════════════════════════════════════════════


@pytest.mark.unit
class TestLaClassificaAPunti:
    """`SPECIFICHE.md`, «Classifica», «La classifica a punti» (2026-10-07).

    > Il criterio principale sono **solo i punti** […] Di norma 3, 1 e 0.
    """

    @staticmethod
    def _gara_a_punti(db_session, **campi) -> Gara:
        gara = _gara(db_session, sistema="POINTS")
        for nome, valore in campi.items():
            setattr(gara, nome, valore)
        db_session.flush()
        return gara

    @staticmethod
    def _punti(gara, giocatori) -> list[int]:
        voci = _punteggi(gara.id)
        return [voci[g.id].points for g in giocatori]

    def test_di_norma_tre_uno_zero(self):
        """> Di norma 3, 1 e 0."""
        from models.classification.punti import punti_della_gara

        class _GaraSingola:
            points_win = points_draw = points_loss = None
            campionato = None

        assert punti_della_gara(_GaraSingola()).come_tupla() == (3, 1, 0)

    def test_vittoria_e_sconfitta(self, db_session):
        """> una **vittoria** dà i punti della vittoria, una **sconfitta**
        > quelli della sconfitta"""
        gara = self._gara_a_punti(db_session)
        uno, due = _utente(db_session), _utente(db_session)
        _partita(db_session, gara, uno, due, persi=2)
        db_session.commit()
        assert self._punti(gara, [uno, due]) == [3, 0]

    def test_il_pareggio_da_i_punti_del_pareggio_a_entrambi(self, db_session):
        """> il **pareggio** — a esattamente N rack con N pari […] — dà i punti
        > del pareggio a entrambi"""
        gara = self._gara_a_punti(db_session, distance=6)
        uno, due = _utente(db_session), _utente(db_session)
        db_session.add(
            Match(
                gara_id=gara.id,
                round_number=1,
                player1_id=uno.id,
                player2_id=due.id,
                player1_score=3,
                player2_score=3,
                winner_id=None,
                status=MatchStatus.CLOSED_UNILATERALLY.value,
            )
        )
        db_session.commit()
        assert self._punti(gara, [uno, due]) == [1, 1]

    def test_la_x_vale_i_punti_della_vittoria_e_zero_differenza(self, db_session):
        """> la **X** vale una vittoria: i punti della vittoria e zero
        > differenza rack"""
        gara = self._gara_a_punti(db_session)
        giocatore = _utente(db_session)
        TestQuantoValeLaX._con_la_x(db_session, gara, giocatore, 0)
        voce = _punteggi(gara.id)[giocatore.id]
        assert (voce.points, voce.rack_difference) == (3, 0)

    def test_la_x_con_esercizio_porta_la_differenza_della_prova(self, db_session):
        """> con l'esercizio al posto della X, i punti della vittoria e la
        > differenza pari al punteggio della prova"""
        gara = self._gara_a_punti(db_session, odd_number_policy="bye_with_challenge")
        giocatore = _utente(db_session)
        TestQuantoValeLaX._con_la_x(db_session, gara, giocatore, 3)
        voce = _punteggi(gara.id)[giocatore.id]
        assert (voce.points, voce.rack_difference) == (3, 3)

    def test_ordina_solo_sui_punti(self):
        """> Il criterio principale sono **solo i punti**: le vittorie non
        > contano da sole

        Quattro pareggi (4 punti) davanti a una vittoria e una sconfitta (3).
        """
        from models.classification.strategies.base import PlayerScore
        from models.classification.strategies.round_strategies import (
            PointsRoundClassificationStrategy,
        )

        vince_e_perde = PlayerScore(player_id=1, matches_won=1, points=3)
        pareggia = PlayerScore(player_id=2, matches_won=0, points=4)
        risultato = PointsRoundClassificationStrategy().calculate(
            [vince_e_perde, pareggia]
        )
        assert [e.player_id for e in risultato.entries] == [2, 1]

    def _trio(self, db_session, distanza, punteggi):
        from models.match.trio_scoring_service import TrioScoringService

        gara, giocatori, trio = TestIlTrioInClassifica._nuovo_trio(db_session, distanza)
        gara.classification_system = "POINTS"
        TrioScoringService.set_result_direct(trio.id, *punteggi)
        db_session.commit()
        return self._punti(gara, giocatori)

    def test_il_trio_con_un_vincitore(self, db_session):
        """> nel **trio** con un vincitore, lui prende i punti della vittoria e
        > gli altri due quelli della sconfitta"""
        assert self._trio(db_session, 4, (4, 1, 1)) == [3, 0, 0]

    def test_il_trio_senza_vincitore_pareggio_in_testa(self, db_session):
        """> a 4-4-1 due pareggi e una sconfitta"""
        assert self._trio(db_session, 6, (4, 4, 1)) == [1, 1, 0]

    def test_il_trio_senza_vincitore_a_tre(self, db_session):
        """> a 3-3-3 tre pareggi"""
        assert self._trio(db_session, 6, (3, 3, 3)) == [1, 1, 1]

    def test_chi_si_ritira_dal_trio_prende_la_sconfitta(self, db_session):
        """> Chi si ritira dal trio non è mai in testa, e prende la sconfitta.

        Marco 3, Luca 3 e Gianni ritirato con 3 (l'esempio del ritiro, più
        sopra nella specifica): nessuno vince, Marco e Luca pareggiano.
        """
        from models.match.trio_scoring_service import TrioScoringService

        gara, giocatori, trio = TestIlTrioInClassifica._nuovo_trio(db_session, 6)
        gara.classification_system = "POINTS"
        marco, luca, gianni = giocatori
        for indice in [0, 2, 1, 0, 2, 2, 1]:
            TrioScoringService.add_rack_win(trio.id, giocatori[indice].id)
        db_session.commit()
        assert trio.handle_forfeit(gianni.id)
        trio.confirm_result_by_admin()
        db_session.commit()

        assert trio.player_racks_list == [3, 3, 3]
        assert self._punti(gara, giocatori) == [1, 1, 0]

    def test_i_punti_si_scelgono_entro_i_limiti(self, app):
        """> numeri interi da 0 a 99, con la vittoria che vale almeno il
        > pareggio, il pareggio almeno la sconfitta, e la vittoria più della
        > sconfitta"""
        from models.classification.punti import valida_punti

        with app.test_request_context():
            assert valida_punti(2, 1, 0).come_tupla() == (2, 1, 0)
            for terna in ((1, 1, 1), (1, 2, 0), (100, 0, 0), (3, 1, -1)):
                with pytest.raises(ValueError):
                    valida_punti(*terna)


@pytest.mark.unit
class TestIlCampionatoAPiazzamenti:
    """`SPECIFICHE.md` righe 379-386 («Classifica», «Come una gara entra nel
    campionato») e riga 116 («Gironi multipli»), 2026-10-11, ADR-080."""

    def test_la_tabella_di_norma_e_oltre_si_prende_zero(self):
        """> con la tabella dei punti per posizione del campionato (di norma
        > 25, 18, 15, 12, poi 8 dal 5° all'8° e 4 dal 9° al 16°) […] Un posto
        > oltre l'ultimo della tabella vale **zero**."""
        from models.classification.position_points import points_for_position

        assert [points_for_position(p) for p in (1, 2, 3, 4, 5, 8, 9, 16, 17)] == [
            25,
            18,
            15,
            12,
            8,
            8,
            4,
            4,
            0,
        ]
        assert points_for_position(3, {1: 10, 2: 6}) == 0

    def test_a_piazzamenti_ogni_formato_e_il_tabellone_resta_tale(self):
        """> Le gare possono avere **formati diversi** […] Il sistema della gara
        > […] lo **propone il campionato** (vittorie, rack o punti; di norma
        > vittorie) e la gara lo può cambiare; sul tabellone è il piazzamento.
        > […] Un campionato che propone il tabellone è sempre a piazzamenti."""
        from models.campionato.piazzamenti import (
            e_a_piazzamenti,
            sistema_per_la_gara,
            strategie_per_sistema,
        )
        from models.matchmaking.configuration import MatchmakingStrategy

        class _C:
            campionato_type = "amalfi"
            default_classification_system = "POSITION"
            default_gara_classification_system = None

        assert set(strategie_per_sistema()["POSITION"]) == {
            s.value for s in MatchmakingStrategy
        }
        assert sistema_per_la_gara(_C(), "amalfi") == "WINS"
        assert sistema_per_la_gara(_C(), "round_robin", "POINTS") == "POINTS"
        assert sistema_per_la_gara(_C(), "double_knockout", "RACK") == "POSITION"
        _C.default_classification_system = "WINS"
        _C.campionato_type = "direct_elimination"
        assert e_a_piazzamenti(_C())

    def test_sommando_i_totali_stesso_sistema_e_girone_unico(self, db_session):
        """> **sommando i totali** […] Le gare usano tutte il sistema del
        > campionato e restano a **girone unico** […] una gara con più gironi
        > viene rifiutata."""
        from datetime import timedelta

        from models.campionato.piazzamenti import sistema_per_la_gara
        from models.competition.services import GaraService

        campionato = _campionato(db_session, "RACK")
        campionato.campionato_type = "round_robin"
        db_session.commit()
        assert sistema_per_la_gara(campionato, "amalfi", "POINTS") == "RACK"
        with pytest.raises(ValueError, match="girone unico"):
            GaraService.create_gara(
                campionato_id=campionato.id,
                number=1,
                name="Serata",
                date=date.today() + timedelta(days=7),
                discipline=Discipline.EIGHT_BALL.value,
                distance=3,
                matchmaking_strategy="round_robin",
                classification_system="RACK",
                odd_number_policy="bye",
                rounds_count=3,
                max_groups=2,
            )

    def test_chi_non_gioca_prende_zero_e_i_pari_condividono_i_punti(self, db_session):
        """> Chi non gioca una gara prende **zero** punti da quella gara. Chi è a
        > **pari merito** […] prende i punti del posto che condivide: due
        > secondi prendono entrambi i punti del 2°."""
        from models.campionato.tournament_service import TournamentService
        from models.classification.gara_classification import (
            RoundClassificationService,
        )
        from models.classification.models import GaraClassification

        campionato = _campionato(db_session, "POSITION")
        a, b, c, d = (_utente(db_session) for _ in range(4))
        gare = []
        for numero, giocatori in ((1, (a, b, c)), (2, (a, d))):
            gara = _gara_del_campionato(
                db_session,
                campionato,
                numero=numero,
                stato=GaraStatus.COMPLETED.value,
            )
            gara.classification_system = "WINS"
            gara.current_round = 1
            db_session.add(
                Match(
                    gara_id=gara.id,
                    round_number=1,
                    player1_id=giocatori[0].id,
                    player2_id=giocatori[1].id,
                    player1_score=5,
                    player2_score=3,
                    status=MatchStatus.CLOSED_UNILATERALLY.value,
                    winner_id=giocatori[0].id,
                )
            )
            if len(giocatori) == 3:
                db_session.add(
                    Match(
                        gara_id=gara.id,
                        round_number=1,
                        player1_id=giocatori[2].id,
                        player2_id=None,
                        player1_score=0,
                        player2_score=0,
                        status=MatchStatus.CLOSED_UNILATERALLY.value,
                        winner_id=giocatori[2].id,
                    )
                )
            db_session.flush()
            RoundClassificationService.calculate_and_save_round_classification(
                gara.id, 1
            )
            gare.append(gara)
        # Gara 1: A primo, B e C secondi a pari merito; gara 2: A, D.
        for gara, posti in (
            (gare[0], ((a, 1), (b, 2), (c, 2))),
            (gare[1], ((a, 1), (d, 2))),
        ):
            for giocatore, posto in posti:
                riga = GaraClassification.query.filter_by(
                    gara_id=gara.id, user_id=giocatore.id
                ).first() or GaraClassification(gara_id=gara.id, user_id=giocatore.id)
                riga.position = posto
                db_session.add(riga)
        db_session.flush()
        punti = {
            dati["user_id"]: dati["total_points"]
            for _, dati in TournamentService().calculate_general_classification(
                campionato.id
            )
        }
        assert punti[a.id] == 50
        assert punti[b.id] == punti[c.id] == 18  # assenti alla gara 2: zero
        assert punti[d.id] == 18


@pytest.mark.unit
class TestAPariPuntiNelCampionatoAPiazzamenti:
    """`SPECIFICHE.md` righe 382-389 («Come una gara entra nel campionato»),
    nota del 2026-10-11, ADR-080 emendamento."""

    def test_criteri_ammessi_e_catena_di_default(self):
        """> - **migliori piazzamenti** […] - **posizione dopo la gara
        > precedente**; - **scontri diretti** […] - **sorteggio**, sempre
        > ultimo. Vittorie, rack e differenza rack **non** sono criteri
        > ammessi, e nemmeno lo spareggio SSR. Di norma: migliori
        > piazzamenti, poi sorteggio."""
        from models.classification.ordinamento import (
            Criterio,
            Livello,
            catena_di_default,
            criteri_ammessi,
            normalizza_catena,
        )
        from models.status_enum import ClassificationSystem

        pos, liv = ClassificationSystem.POSITION, Livello.CAMPIONATO
        assert set(criteri_ammessi(liv, pos)) == {
            Criterio.PIAZZAMENTI,
            Criterio.POSIZIONE_PRECEDENTE,
            Criterio.SCONTRI_DIRETTI,
            Criterio.SORTEGGIO,
        }
        assert [
            v.criterio for v in normalizza_catena(catena_di_default(liv, pos), liv, pos)
        ] == [
            Criterio.PIAZZAMENTI,
            Criterio.SORTEGGIO,
        ]

    def test_piu_primi_posti_poi_piu_secondi(self):
        """> chi ha più primi posti; a pari primi posti, chi ha più secondi;
        > poi più terzi, e così via. […] L'ordine è sempre completo."""
        from models.classification.ordinamento import (
            Concorrente,
            Criterio,
            Voce,
            ordina,
        )

        # Tutti a pari punti. A: un 1º e un 5º; B: un 2º e un 3º; C e D: un
        # 2º e un 4º. A ha l'unico primo posto; B, a pari secondi, ha un
        # terzo. Le vittorie (C ne ha più di tutti) non contano.
        a = Concorrente(1, punti=33, vittorie=1, piazzamenti=(1, 0, 0, 0, 1))
        b = Concorrente(2, punti=33, vittorie=4, piazzamenti=(0, 1, 1, 0, 0))
        c = Concorrente(3, punti=33, vittorie=9, piazzamenti=(0, 1, 0, 1, 0))
        d = Concorrente(4, punti=33, vittorie=0, piazzamenti=(0, 1, 0, 1, 0))
        fasce = ordina(
            [d, c, b, a],
            Criterio.PUNTI,
            (Voce(Criterio.PIAZZAMENTI), Voce(Criterio.SORTEGGIO)),
            completa=True,
        )
        ordine = [f.giocatori[0].player_id for f in fasce]
        assert ordine[:2] == [1, 2]
        assert sorted(ordine[2:]) == [3, 4]  # stessi piazzamenti: sorteggio
        assert [f.posizione for f in fasce] == [1, 2, 3, 4]

    def test_due_secondi_a_pari_merito_e_la_gara_a_peso_zero(self, db_session):
        """> due secondi a pari merito contano entrambi come un secondo posto.
        > Un piazzamento pesa come i punti della gara: una gara a peso zero
        > non conta, una gara a peso 2 conta due volte."""
        from models.campionato.statistics_service import (
            TournamentStatisticsService,
        )
        from models.classification.gara_classification import (
            RoundClassificationService,
        )
        from models.classification.models import GaraClassification
        from models.status_enum import ClassificationSystem

        campionato = _campionato(db_session, "POSITION")
        a, b, c = (_utente(db_session) for _ in range(3))
        posti_per_gara = (
            (1, ((a, 1), (b, 2), (c, 2))),  # B e C secondi a pari merito
            (0, ((c, 1), (a, 2), (b, 3))),  # peso zero: non conta
            (2, ((a, 1), (b, 2), (c, 3))),  # peso 2: conta due volte
        )
        gare = []
        for numero, (peso, posti) in enumerate(posti_per_gara, 1):
            gara = _gara_del_campionato(
                db_session, campionato, numero=numero, stato=GaraStatus.COMPLETED.value
            )
            gara.classification_system = "WINS"
            gara.current_round = 1
            gara.weight = peso
            for giocatore, _posto in posti:
                db_session.add(
                    Match(
                        gara_id=gara.id,
                        round_number=1,
                        player1_id=giocatore.id,
                        player2_id=None,
                        player1_score=0,
                        player2_score=0,
                        status=MatchStatus.CLOSED_UNILATERALLY.value,
                        winner_id=giocatore.id,
                    )
                )
            db_session.flush()
            RoundClassificationService.calculate_and_save_round_classification(
                gara.id, 1
            )
            for giocatore, posto in posti:
                riga = GaraClassification.query.filter_by(
                    gara_id=gara.id, user_id=giocatore.id
                ).first() or GaraClassification(gara_id=gara.id, user_id=giocatore.id)
                riga.position = posto
                db_session.add(riga)
            gare.append(gara)
        db_session.flush()
        totali = TournamentStatisticsService()._aggregate_player_totals(
            gare, ClassificationSystem.POSITION, campionato
        )
        assert totali[a.id]["piazzamenti"] == {1: 3}
        assert totali[b.id]["piazzamenti"] == {2: 3}
        assert totali[c.id]["piazzamenti"] == {2: 1, 3: 2}


class TestLaFaseFinaleDopoIGironi:
    """`SPECIFICHE.md` («Turno», «Fase finale dopo i gironi»; «Limite di
    tempo»; «Classifica», «La classifica a gironi»), 2026-10-11, PR 5 del
    piano dei gironi."""

    def test_di_norma_nessuna_e_passano_due(self, db_session):
        """> fra tre: **nessuna** (la gara finisce coi gironi, ed è il
        > default) […] i primi `K` di ogni girone (di norma 2)."""
        from models.matchmaking.fase_finale import FaseFinale

        gara = _gara(db_session)
        gara.matchmaking_strategy = "round_robin"
        assert gara.effective_final_phase_mode is FaseFinale.NESSUNA
        assert gara.effective_qualifiers_per_group == 2
        gara.final_phase_mode = "tabellone"
        assert gara.ha_tabellone_finale
        gara.matchmaking_strategy = "amalfi"
        assert not gara.ha_tabellone_finale  # solo il girone all'italiana

    def test_il_campionato_a_piazzamenti_propone_e_chi_somma_la_toglie(
        self, db_session
    ):
        """> Il campionato a piazzamenti **propone** alle sue gare a girone la
        > fase finale […] una gara che nasce a girone unico non riceve il
        > tabellone. Un campionato che passa a **sommare i totali** toglie la
        > fase finale alle gare non ancora avviate (nota del 2026-10-12)."""
        from datetime import date, timedelta

        from models.campionato.models import Campionato
        from models.campionato.tournament_service import TournamentService
        from models.competition.services import GaraService

        camp = Campionato(
            name="Lunedì al 74 conformità",
            campionato_type="round_robin",
            default_classification_system="POSITION",
            is_active=True,
            default_max_groups=2,
            default_final_phase_mode="tabellone",
        )
        db_session.add(camp)
        db_session.commit()

        def nuova(numero, **extra):
            return GaraService.create_gara(
                campionato_id=camp.id,
                number=numero,
                name=f"Serata {numero}",
                date=date.today() + timedelta(days=7 * numero),
                discipline="8_ball",
                distance=3,
                is_race_to=True,
                matchmaking_strategy="round_robin",
                first_round_policy="random",
                odd_number_policy="bye",
                rounds_count=3,
                **extra,
            )

        con_gironi = nuova(1)
        girone_unico = nuova(2, max_groups=1)
        assert con_gironi.ha_tabellone_finale
        assert not girone_unico.ha_tabellone_finale
        TournamentService().update_campionato(
            camp.id, default_classification_system="WINS"
        )
        db_session.refresh(con_gironi)
        assert not con_gironi.ha_tabellone_finale

    def test_chi_passa_e_quanti(self):
        """> `K` va da 1 al numero di giocatori del girone più piccolo, e i
        > qualificati devono essere almeno due […] chi si è ritirato lascia il
        > posto al successivo del suo girone."""
        from models.matchmaking.fase_finale import (
            qualificati_dei_gironi,
            verifica_qualificati,
        )

        assert verifica_qualificati([4, 3], 4) == "girone"
        assert verifica_qualificati([4, 3], 3) is None
        assert qualificati_dei_gironi({0: [1, 2, 3]}, 2, {1, 3}) == {0: [1, 3]}

    def test_taglia_e_turni(self):
        """> la potenza di 2 subito sopra i qualificati (da 2 in su: con due
        > gironi e un qualificato si gioca la sola finale) […] due gironi da 4
        > con `K` = 2 fanno 3 + 2 turni."""
        from models.matchmaking.fase_finale import (
            taglia_del_tabellone,
            turni_del_tabellone,
        )
        from models.matchmaking.gironi import turni_dei_gironi

        assert taglia_del_tabellone(2) == 2
        assert taglia_del_tabellone(6) == 8
        assert turni_dei_gironi([4, 4]) + turni_del_tabellone(4) == 3 + 2

    def test_teste_di_serie_per_colonne_e_bye_ai_migliori_primi(self):
        """> prima tutti i primi dei gironi, poi tutti i secondi […] dentro
        > una colonna i migliori nell'ordine della classifica a gironi […] con
        > tre gironi e `K` = 2, ai due migliori primi."""
        from models.matchmaking.bracket import standard_bracket_order
        from models.matchmaking.fase_finale import semina_del_tabellone

        # Classifica a gironi: C1, A1, B1, A2, C2, B2.
        seme = semina_del_tabellone(
            {0: [11, 12], 1: [21, 22], 2: [31, 32]}, [31, 11, 21, 12, 32, 22]
        )
        assert seme == [31, 11, 21, 12, 32, 22]
        # Tabellone da 8: le teste di serie 7 e 8 non ci sono, e i loro
        # avversari — le teste di serie 2 e 1 — passano il turno.
        ordine = standard_bracket_order(8)
        coppie = [ordine[i : i + 2] for i in range(0, 8, 2)]
        con_bye = sorted(min(c) for c in coppie if max(c) > len(seme))
        assert [seme[s - 1] for s in con_bye] == [31, 11]

    def test_finalina_o_due_terzi_poi_piazzamento_nel_girone(self):
        """> 1° e 2° dalla finale, 3° e 4° dalla finalina; **senza finalina**
        > i due semifinalisti sconfitti sono **terzi a pari merito** […] chi
        > esce allo stesso turno prima della semifinale […] si ordina per
        > **piazzamento nel girone** […] poi i **non qualificati**."""
        from models.classification.fase_finale import classifica_con_tabellone

        gironi = [(1, [11]), (2, [21]), (3, [12]), (4, [22]), (5, [13]), (6, [23])]
        con_finalina = classifica_con_tabellone([[11], [21], [22], [12]], gironi)
        assert [ids for _p, ids in con_finalina] == [[11], [21], [22], [12], [13], [23]]
        senza = classifica_con_tabellone(
            [[11], [21], [12, 22]], gironi, pari_merito={12, 22}
        )
        assert senza[2] == (3, [12, 22])
        quarti = classifica_con_tabellone(
            [[11], [21], [13, 23], [12, 22]],
            gironi,
            pari_merito={13, 23},
        )
        assert quarti[3:] == [(5, [12]), (6, [22])]

    def test_limite_della_fase_finale_a_tre_stati(self, db_session):
        """> **come i gironi** (il default), **senza limite**, oppure un
        > numero di minuti diverso. L'ordine è: l'override del singolo turno,
        > poi il limite della fase finale, poi quello della gara."""
        gara = _gara(db_session)
        gara.matchmaking_strategy = "round_robin"
        gara.time_limit_minutes = 30
        assert gara.effective_final_phase_time_limit_minutes == 30
        gara.final_phase_time_limit_minutes = 0
        assert gara.effective_final_phase_time_limit_minutes is None
        gara.final_phase_time_limit_minutes = 45
        assert gara.effective_final_phase_time_limit_minutes == 45

    def test_regole_della_finale_per_fase(self, db_session):
        """SPECIFICHE.md, «Fase finale dopo i gironi» → «Regole del tabellone,
        per fase» (nota del 2026-10-12):

        > La **finalina** segue la fase finale, non la finale. [...] L'ordine
        > è: l'override del singolo turno (se c'è), poi la finale, poi la
        > fase finale, poi la gara."""
        from types import SimpleNamespace

        from models.matchmaking.bracket import BRACKET_THIRD_PLACE, BRACKET_WINNERS
        from models.matchmaking.fase_finale import la_finale_del_turno

        gara = _gara(db_session)
        gara.matchmaking_strategy = "round_robin"
        gara.distance = 3
        gara.time_limit_minutes = 30
        assert (gara.effective_final_phase_distance, gara.effective_final_distance) == (
            3,
            3,
        )
        assert gara.effective_final_time_limit_minutes == 30
        gara.final_phase_distance = 4
        gara.final_phase_time_limit_minutes = 45
        assert gara.effective_final_distance == 4
        assert gara.effective_final_time_limit_minutes == 45
        gara.final_distance = 7
        gara.final_time_limit_minutes = 0
        assert gara.effective_final_distance == 7
        assert gara.effective_final_time_limit_minutes is None
        # La finalina sta nel turno della finale ma non è la finale.
        finale = SimpleNamespace(bracket_type=BRACKET_WINNERS, bracket_group=None)
        finalina = SimpleNamespace(bracket_type=BRACKET_THIRD_PLACE, bracket_group=None)
        assert la_finale_del_turno([finalina, finale]) is finale

    def test_nel_tabellone_si_gioca_al_n(self, db_session):
        """> le partite si giocano «al N» (con «esattamente N» la gara col
        > tabellone viene rifiutata, come ogni tabellone)."""
        from models.competition.services import GaraService

        gara = _gara(db_session)
        gara.matchmaking_strategy = "round_robin"
        gara.final_phase_mode = "tabellone"
        gara.max_groups = 2
        gara.is_race_to = False
        with pytest.raises(ValueError):
            GaraService._verifica_fase_finale(gara)
        gara.is_race_to = True
        GaraService._verifica_fase_finale(gara)

    def test_solo_con_piu_gironi(self, db_session):
        """> Il **tabellone** esiste solo nelle gare che possono avere **più
        > gironi** […] con il girone unico non si sceglie."""
        from models.competition.services import GaraService

        gara = _gara(db_session)
        gara.matchmaking_strategy = "round_robin"
        gara.final_phase_mode = "tabellone"
        gara.is_race_to = True
        gara.max_groups = 1
        with pytest.raises(ValueError):
            GaraService._verifica_fase_finale(gara)
        gara.max_groups = 2
        GaraService._verifica_fase_finale(gara)

    def test_il_taglio_e_una_classifica_di_turno(self):
        """> chi passa fra il `K`-esimo e il `K+1`-esimo di un girone si decide
        > **come in una classifica di turno**: con la **catena di turno** […]
        > Niente spareggio SSR a metà gara."""
        import inspect

        from models.competition import fase_finale_service

        sorgente = inspect.getsource(fase_finale_service.semina)
        assert "per_il_taglio=True" in sorgente
        sorgente = inspect.getsource(fase_finale_service.ordine_dei_gironi)
        assert "catena_di_turno(gara, g)" in sorgente


class TestComeSiMostraIlPariMerito:
    """`SPECIFICHE.md` riga 366 («Classifica», «Come si mostra il pari
    merito»), nota del 2026-10-11."""

    def test_separati_solo_dal_sorteggio_sono_mostrati_al_posto_piu_alto(self):
        """> Due giocatori con 2 vittorie e +6 che il sorteggio ha messo 1° e
        > 2° sono mostrati entrambi al 1° posto, e il terzo al 3° (1, 1, 3)
        > […] L'ordine delle righe resta quello della catena, e dove la
        > posizione decide qualcosa decide quella col sorteggio."""
        from models.classification.ordinamento import (
            Concorrente,
            Criterio,
            Livello,
            catena_di_default,
            normalizza_catena,
            ordina,
        )
        from models.status_enum import ClassificationSystem

        wins, turno = ClassificationSystem.WINS, Livello.TURNO
        catena = normalizza_catena(
            [
                v
                for v in catena_di_default(turno, wins)
                if v.criterio is not Criterio.POSIZIONE_PRECEDENTE
            ],
            turno,
            wins,
        )
        fasce = ordina(
            [
                Concorrente(1, vittorie=2, differenza_rack=6, sorteggio=5),
                Concorrente(2, vittorie=2, differenza_rack=6, sorteggio=1),
                Concorrente(3, vittorie=1, differenza_rack=0, sorteggio=3),
            ],
            Criterio.VITTORIE,
            catena,
        )
        assert [f.posizione for f in fasce] == [1, 2, 3]
        assert [f.posizione_mostrata for f in fasce] == [1, 1, 3]

    def test_chi_la_catena_lascia_pari_condivide_gia_la_posizione(self):
        """> Chi la catena lascia pari senza sorteggio condivide già la
        > posizione che decide (1, 2, 2, 4), e lì niente cambia."""
        from models.classification.ordinamento import Concorrente, Criterio, ordina

        fasce = ordina(
            [
                Concorrente(1, vittorie=3),
                Concorrente(2, vittorie=2),
                Concorrente(3, vittorie=2),
                Concorrente(4, vittorie=0),
            ],
            Criterio.VITTORIE,
            (),
        )
        posizioni = [(f.posizione, f.posizione_mostrata) for f in fasce]
        assert posizioni == [(1, 1), (2, 2), (4, 4)]
        assert [len(f.giocatori) for f in fasce] == [1, 2, 1]

    def test_le_bande_del_tabellone_al_posto_piu_alto_con_gli_stessi_punti(self):
        """> Lo stesso per le **bande del tabellone** […]: i quattro
        > quartifinalisti si mostrano «5° pari merito» e i due semifinalisti
        > sconfitti senza finalina «3° pari merito», con gli stessi punti del
        > posto condiviso."""
        from models.classification.bracket_standings import positions_from_bands
        from models.classification.position_points import points_for_position

        posizioni = positions_from_bands([[1], [2], [3, 4], [5, 6, 7, 8]])
        assert [posizioni[p] for p in range(1, 9)] == [1, 2, 3, 3, 5, 5, 5, 5]
        assert {points_for_position(posizioni[p]) for p in (5, 6, 7, 8)} == {
            points_for_position(5)
        }
        assert {points_for_position(posizioni[p]) for p in (3, 4)} == {
            points_for_position(3)
        }


class TestLeFinaliPerPiazzamento:
    """`SPECIFICHE.md` («Turno», «Finali per piazzamento»; «Classifica», «La
    classifica a gironi»), 2026-10-12, PR 6 del piano dei gironi."""

    def test_il_p_esimo_contro_il_p_esimo_e_l_ultimo_diretto(self):
        """> **1ºA–1ºB** per il 1°/2° posto, **2ºA–2ºB** per il 3°/4° […]
        > Con 5 + 4 iscritti il 5º del girone da cinque è 9º."""
        from models.matchmaking.fase_finale import incroci_per_piazzamento

        a = ["1A", "2A", "3A", "4A", "5A"]
        b = ["1B", "2B", "3B", "4B"]
        coppie, diretti = incroci_per_piazzamento({0: a, 1: b})
        assert coppie == [("1A", "1B"), ("2A", "2B"), ("3A", "3B"), ("4A", "4B")]
        assert diretti == ["5A"]

    def test_solo_con_due_gironi(self):
        """> **Solo con due gironi** […] con «fino a 3» o più la formula non si
        > sceglie."""
        from models.matchmaking.fase_finale import verifica_piazzamento

        assert verifica_piazzamento(2) is None
        assert verifica_piazzamento(3) is not None

    def test_il_modulo_non_le_accetta_con_tre_gironi(self, app):
        """> con «fino a 3» o più la formula non si sceglie (il modulo della
        > gara e quello del campionato, 2026-10-12)."""
        from routes.admin.competition.form_parser import leggi_la_fase_finale

        modulo = {"final_phase_mode": "piazzamento"}
        with app.test_request_context():
            assert leggi_la_fase_finale(modulo, "", 2)["final_phase_mode"] == (
                "piazzamento"
            )
            with pytest.raises(ValueError):
                leggi_la_fase_finale(modulo, "", 3)

    def test_un_turno_solo(self):
        """> due gironi da 4 fanno 3 + 1 turni, 5 + 4 ne fanno 5 + 1."""
        from models.competition.gironi_service import Anteprima

        anteprima = Anteprima(
            iscritti=9,
            tetto=2,
            massimo=2,
            proposta=2,
            taglie={2: [5, 4]},
            finali_per_piazzamento=True,
        )
        assert anteprima.turni == {2: 6}
        otto = Anteprima(
            iscritti=8,
            tetto=2,
            massimo=2,
            proposta=2,
            taglie={2: [4, 4]},
            finali_per_piazzamento=True,
        )
        assert otto.turni == {2: 4}

    def test_la_finale_e_quella_del_primo_posto(self):
        """> la **finale**, per le regole della sola finale, è la partita per il
        > 1°/2° posto; le altre seguono la fase finale."""
        from types import SimpleNamespace

        from models.matchmaking.bracket import BRACKET_PLACEMENT
        from models.matchmaking.fase_finale import la_finale_del_turno

        nodi = [
            SimpleNamespace(bracket_type=BRACKET_PLACEMENT, bracket_slot=s)
            for s in (1, 0, 2, 3)
        ]
        assert la_finale_del_turno(nodi) is nodi[1]

    def test_ogni_finale_assegna_due_posti(self):
        """> Esempio: due gironi, 5 + 4. 1ºA–1ºB la vince 1ºB, 2ºA–2ºB la vince
        > 2ºA, 3ºA–3ºB la vince 3ºB, 4ºA–4ºB la vince 4ºA: 1º 1ºB, 2º 1ºA, 3º
        > 2ºA, 4º 2ºB, 5º 3ºB, 6º 3ºA, 7º 4ºA, 8º 4ºB, 9º 5ºA."""
        from models.classification.fase_finale import (
            bande_delle_finali,
            classifica_con_tabellone,
        )

        # 1A=1, 2A=2, 3A=3, 4A=4, 5A=5; 1B=11, 2B=12, 3B=13, 4B=14
        coppie = [(1, 11), (2, 12), (3, 13), (4, 14)]
        bande, pari = bande_delle_finali(coppie, {0: 11, 1: 2, 2: 13, 3: 4}, [5])
        gironi = [(1, [1, 11]), (3, [2, 12]), (5, [3, 13]), (7, [4, 14]), (9, [5])]
        fasce = classifica_con_tabellone(bande, gironi, pari_merito=pari)
        assert [ids for _pos, ids in fasce] == [
            [11],
            [1],
            [2],
            [12],
            [13],
            [3],
            [4],
            [14],
            [5],
        ]
        assert [pos for pos, _ids in fasce] == list(range(1, 10))

    def test_ritirati_tutti_e_due_restano_pari(self):
        """> se si sono ritirati tutti e due, la finale non si gioca e i due
        > restano a pari merito sui loro posti."""
        from models.classification.fase_finale import (
            bande_delle_finali,
            classifica_con_tabellone,
        )

        bande, pari = bande_delle_finali(
            [(1, 11), (2, 12)], {0: 1}, [], senza_partita={1}
        )
        fasce = classifica_con_tabellone(
            bande, [(1, [1, 11]), (3, [2, 12])], pari_merito=pari
        )
        assert fasce == [(1, [1]), (2, [11]), (3, [2, 12])]


class TestLivelliDiCertificazione:
    """SPECIFICHE.md, «Livelli di certificazione» (ADR-083)."""

    @staticmethod
    def _sfida(status, p1=False, p2=False, s1=3, s2=1, winner_id=None):
        from models.individual_match.match_models import IndividualMatch

        return IndividualMatch(
            player1_id=1,
            player2_id=2,
            status=status,
            player1_confirmed=p1,
            player2_confirmed=p2,
            player1_score=s1,
            player2_score=s2,
            winner_id=winner_id,
        )

    def test_il_forfait_e_confermato_ma_non_conta_per_l_elo(self):
        """«Sfida chiusa con un forfait | Confermata … | no, come il walkover
        nei tornei»."""
        from models.certificazione import Livello, livello_di_sfida, sfida_conta_per_elo

        forfait = self._sfida(MatchStatus.CLOSED_UNILATERALLY, winner_id=2)

        assert livello_di_sfida(forfait) is Livello.CONFERMATA
        assert sfida_conta_per_elo(forfait) is False

    def test_la_sfida_in_attesa_conta_per_l_elo(self):
        """«Sfida firmata da un solo giocatore, in attesa dell'altro | In attesa
        | sì, se non è un pareggio»."""
        from models.certificazione import Livello, livello_di_sfida, sfida_conta_per_elo

        in_attesa = self._sfida(MatchStatus.IN_PROGRESS, p1=True)

        assert livello_di_sfida(in_attesa) is Livello.IN_ATTESA
        assert sfida_conta_per_elo(in_attesa) is True

    def test_il_pareggio_non_conta_per_l_elo(self):
        """«sì, se non è un pareggio»."""
        from models.certificazione import sfida_conta_per_elo

        pari = self._sfida(MatchStatus.CONFIRMED_BY_BOTH, True, True, s1=2, s2=2)

        assert sfida_conta_per_elo(pari) is False

    def test_senza_firme_nessun_livello(self):
        """«Sfida senza firme, programmata o annullata | nessuno»."""
        from models.certificazione import livello_di_sfida

        for status in (
            MatchStatus.IN_PROGRESS,
            MatchStatus.SCHEDULED,
            MatchStatus.CANCELLED,
        ):
            assert livello_di_sfida(self._sfida(status)) is None

    def test_tre_viste_cumulative_e_la_predefinita(self):
        """«tre viste cumulative: Tornei; Confermate, … la vista predefinita;
        Tutte»."""
        from models.certificazione import VISTA_PREDEFINITA, Livello, Vista

        assert [sorted(v.value for v in vista.livelli) for vista in Vista] == [
            ["torneo"],
            ["confermata", "torneo"],
            sorted(livello.value for livello in Livello),
        ]
        assert VISTA_PREDEFINITA is Vista.CONFERMATE


class TestPartitaDiUnTerzo:
    """SPECIFICHE.md, «Ciclo di vita dei Match» («La partita di altri due») e
    «Livelli di certificazione», note del 2026-10-17 (ADR-084) e del
    2026-10-18 (emendamento dell'ADR-084).

    La regola del 2026-10-17 era per giocatore anche nel rifiuto: «chi conferma
    se la tiene, chi rifiuta la toglie solo a sé». La specifica emendata il
    2026-10-18, per decisione dell'utente, dice il contrario: «Un rifiuto
    basta: se uno dei due rifiuta, prima o dopo la conferma dell'altro, la
    partita è rifiutata per tutti e due». Questi test difendono la regola
    nuova; quelli di prima difendevano la vecchia, e con una conferma e un
    rifiuto la partita restava in corso per sempre."""

    @staticmethod
    def _sfida(p1=False, p2=False, r1=False, r2=False, status=None):
        from models.base import utc_now
        from models.individual_match.match_models import IndividualMatch
        from models.tpa.models import TpaReferto

        sfida = IndividualMatch(
            player1_id=1,
            player2_id=2,
            scorer_id=3,
            status=status or MatchStatus.IN_PROGRESS,
            player1_confirmed=p1,
            player2_confirmed=p2,
            player1_rejected_at=utc_now() if r1 else None,
            player2_rejected_at=utc_now() if r2 else None,
            player1_score=3,
            player2_score=1,
            distance=3,
            is_race_to=True,
        )
        sfida.tpa_referto = TpaReferto(compiler_id=3, game_type=9, closed_at=utc_now())
        return sfida

    def test_il_livello_e_per_giocatore_finche_nessuno_rifiuta(self):
        """«Sfida di un terzo, per il giocatore che l'ha confermata |
        Confermata»; «… dichiarata, per il giocatore che non ha ancora deciso
        | In attesa»."""
        from models.certificazione import Livello, livello_di_sfida_per

        sfida = self._sfida(p1=True)
        assert livello_di_sfida_per(sfida, 1) is Livello.CONFERMATA
        assert livello_di_sfida_per(sfida, 2) is Livello.IN_ATTESA

    @pytest.mark.parametrize("prima_conferma", [True, False])
    def test_un_rifiuto_basta(self, prima_conferma):
        """«Un rifiuto basta: se uno dei due rifiuta, prima o dopo la conferma
        dell'altro, la partita è rifiutata per tutti e due»; «Sfida di un
        terzo rifiutata da uno dei due | nessuno, per tutti e due | no»."""
        from models.certificazione import (
            livello_di_sfida,
            livello_di_sfida_per,
            sfida_conta_per_elo,
        )

        sfida = self._sfida(p1=prima_conferma)
        sfida.reject_as_player(2)
        assert sfida.status == MatchStatus.REJECTED
        assert livello_di_sfida_per(sfida, 1) is None
        assert livello_di_sfida_per(sfida, 2) is None
        assert livello_di_sfida(sfida) is None
        assert sfida_conta_per_elo(sfida) is False

    def test_la_rifiutata_non_compare_ai_giocatori(self):
        """«non compare più ai due giocatori»; «Chi l'ha segnata la vede
        ancora, marcata rifiutata»."""
        sfida = self._sfida()
        sfida.reject_as_player(1)
        assert sfida.is_hidden_from(1) and sfida.is_hidden_from(2)
        assert not sfida.is_hidden_from(3)

    def test_chi_l_ha_segnata_la_corregge_o_la_cancella(self):
        """«può correggerla — il referto si riapre, conferme e rifiuti si
        azzerano …— oppure cancellarla»."""
        corretta = self._sfida(p1=True)
        corretta.reject_as_player(2)
        corretta.reopen_by_scorer(3)
        assert corretta.status == MatchStatus.IN_PROGRESS
        assert not corretta.is_declared_by_scorer
        assert corretta.decision_of(1) is None and corretta.decision_of(2) is None

        cancellata = self._sfida(p1=True)
        cancellata.reject_as_player(2)
        cancellata.cancel_by_scorer(3)
        assert cancellata.status == MatchStatus.CANCELLED

    def test_l_admin_non_segna(self):
        """«Un istruttore o un direttore — non l'admin — può segnare la sfida
        fra due altri giocatori»."""
        from types import SimpleNamespace

        from models.individual_match.scored_match_service import ScoredMatchService

        def utente(**ruoli):
            base = dict(is_admin=False, is_director=False, is_instructor=False)
            return SimpleNamespace(is_authenticated=True, **{**base, **ruoli})

        assert ScoredMatchService.can_score(utente(is_instructor=True))
        assert ScoredMatchService.can_score(utente(is_director=True))
        assert not ScoredMatchService.can_score(utente(is_admin=True))
        assert not ScoredMatchService.can_score(
            utente(is_admin=True, is_instructor=True)
        )

    def test_l_elo_e_per_coppia(self):
        """«conferma di entrambi → ELO di Confermate; dichiarata e nessun
        rifiuto → ELO di Tutte»."""
        from models.certificazione import Livello, livello_di_sfida, sfida_conta_per_elo

        entrambi = self._sfida(True, True, status=MatchStatus.CONFIRMED_BY_BOTH)
        entrambi.winner_id = 1
        assert livello_di_sfida(entrambi) is Livello.CONFERMATA
        nessun_rifiuto = self._sfida()
        assert livello_di_sfida(nessun_rifiuto) is Livello.IN_ATTESA
        assert sfida_conta_per_elo(nessun_rifiuto) is True

    def test_nessuna_firma_d_ufficio_e_nessun_blocco(self):
        """«Nessuna firma d'ufficio»; «non blocca i due giocatori … e non si
        ritira»."""
        sfida = self._sfida()
        assert sfida.awaiting_confirmation_from_id is None
        assert not sfida.signed_and_waiting(1)


class TestGiocatoriNonRegistrati:
    """SPECIFICHE.md, «Tipologie di utenti» → «Giocatori non ancora
    registrati», regola del 2026-10-17 (ADR-085)."""

    @staticmethod
    def _direttore(db_session):
        s = uuid.uuid4().hex[:8]
        u = User(
            username=f"dir_{s}", email=f"dir_{s}@test.com", role=UserRole.DIRECTOR.value
        )
        u.set_password("test1234")
        db_session.add(u)
        db_session.flush()
        return u

    def test_lo_username_e_nome_e_cognome_poi_un_numero(self, db_session):
        """«Lo username è il nome e cognome; se è già preso si aggiunge un
        numero: «Mario Rossi (2)»»."""
        from models.user.services import UserService

        direttore = self._direttore(db_session)
        cognome = f"Rossi{uuid.uuid4().hex[:4]}"
        primo = UserService.create_placeholder("Mario", cognome, direttore)
        secondo = UserService.create_placeholder("Mario", cognome, direttore)
        assert primo.username == f"Mario {cognome}"
        assert secondo.username == f"Mario {cognome} (2)"

    def test_non_entra_nell_app(self, db_session):
        """«Non entra nell'app: non ha email né password, e il login lo
        rifiuta comunque»."""
        from models.user.services import UserService

        giocatore = UserService.create_placeholder(
            "Anna", f"Verdi{uuid.uuid4().hex[:4]}", self._direttore(db_session)
        )
        assert giocatore.email is None
        giocatore.set_password("test1234")
        assert UserService.authenticate_user(giocatore.username, "test1234") is None
        assert User.from_session_id(giocatore.get_id()) is None

    def test_non_riceve_notifiche(self, db_session):
        """«Non riceve niente: né notifiche, né proposte di sfida»."""
        from models.notification.models import NotificationType
        from models.notification.services import NotificationService
        from models.user.services import UserService

        giocatore = UserService.create_placeholder(
            "Luca", f"Neri{uuid.uuid4().hex[:4]}", self._direttore(db_session)
        )
        assert (
            NotificationService.create_notification(
                user_id=giocatore.id,
                notification_type=NotificationType.SYSTEM_ANNOUNCEMENT,
                title="x",
                message="x",
            )
            is None
        )

    def test_non_e_un_avversario_delle_sfide(self, db_session):
        """«non compare fra gli avversari delle sfide individuali e non si
        sfida con l'avvio rapido»: il permesso delle sfide gli è negato."""
        from models.user.services import UserService

        giocatore = UserService.create_placeholder(
            "Sara", f"Gialli{uuid.uuid4().hex[:4]}", self._direttore(db_session)
        )
        giocatore.gamification_override = True
        assert giocatore.can_access("create_match_direct") is False


class TestRiscattoDeiNonRegistrati:
    """SPECIFICHE.md, «Tipologie di utenti» → «Giocatori non ancora
    registrati» → «Il riscatto», regola del 2026-10-17 (ADR-086)."""

    @staticmethod
    def _utente(db_session, role=UserRole.PLAYER.value):
        s = uuid.uuid4().hex[:8]
        u = User(username=f"ris_{s}", email=f"ris_{s}@test.com", role=role)
        u.set_password("test1234")
        db_session.add(u)
        db_session.flush()
        return u

    def _giocatore(self, db_session, creatore=None):
        from models.user.services import UserService

        creatore = creatore or self._utente(db_session, UserRole.DIRECTOR.value)
        return UserService.create_placeholder(
            "Gino", f"Riscatto{uuid.uuid4().hex[:4]}", creatore
        )

    def test_decide_chi_l_ha_creato(self, db_session):
        """«Decide chi ha creato il giocatore»."""
        from models.user.claim_service import ClaimService

        direttore = self._utente(db_session, UserRole.DIRECTOR.value)
        giocatore = self._giocatore(db_session, direttore)
        assert [u.id for u in ClaimService.destinatari(giocatore)] == [direttore.id]

    def test_senza_creatore_decide_solo_l_admin(self, db_session):
        """«Per un giocatore senza creatore […] decide solo l'amministratore»."""
        from models.user.claim_service import ClaimService

        admin = User.query.filter_by(role=UserRole.ADMIN.value).first() or (
            self._utente(db_session, UserRole.ADMIN.value)
        )
        storico = self._utente(db_session)
        storico.is_placeholder = True
        db_session.flush()
        destinatari = ClaimService.destinatari(storico)
        assert destinatari and all(u.is_admin for u in destinatari)
        assert admin.id in {u.id for u in destinatari}

    def test_una_sola_richiesta_in_attesa(self, db_session):
        """«C'è una sola richiesta in attesa per giocatore»."""
        from models.exceptions import ConflictError
        from models.user.claim_service import ClaimService

        giocatore = self._giocatore(db_session)
        ClaimService.richiedi(giocatore.id, self._utente(db_session))
        with pytest.raises(ConflictError):
            ClaimService.richiedi(giocatore.id, self._utente(db_session))

    def test_non_lo_riscatta_chi_l_ha_creato_ne_l_admin(self, db_session):
        """«Non lo riscatta chi l'ha creato, né l'amministratore»."""
        from models.exceptions import ValidationError
        from models.user.claim_service import ClaimService

        direttore = self._utente(db_session, UserRole.DIRECTOR.value)
        giocatore = self._giocatore(db_session, direttore)
        admin = self._utente(db_session, UserRole.ADMIN.value)
        for chi in (direttore, admin):
            with pytest.raises(ValidationError):
                ClaimService.richiedi(giocatore.id, chi)

    def test_non_serve_l_email_verificata(self, db_session):
        """«Non serve l'email verificata»."""
        from models.user.claim_service import ClaimService

        chi = self._utente(db_session)
        assert chi.is_verified is False
        richiesta = ClaimService.richiedi(self._giocatore(db_session).id, chi)
        assert richiesta.is_pending

    def test_il_pulsante_non_lo_vede_il_creatore(self, db_session):
        """«Lo vede chiunque, anche senza account, tranne il giocatore stesso e
        chi l'ha creato; sparisce quando una richiesta è già in attesa»."""
        from models.user.claim_service import ClaimService

        direttore = self._utente(db_session, UserRole.DIRECTOR.value)
        giocatore = self._giocatore(db_session, direttore)
        assert ClaimService.puo_proporre_riscatto(None, giocatore)
        assert not ClaimService.puo_proporre_riscatto(direttore, giocatore)
        ClaimService.richiedi(giocatore.id, self._utente(db_session))
        # Un'altra pagina: la memoria della richiesta HTTP non vale più.
        from flask import g

        g.pop("_riscatto_proponibile", None)
        assert not ClaimService.puo_proporre_riscatto(None, giocatore)

    def test_nell_onboarding_omonimi_senza_accenti_e_maiuscole(self, db_session):
        """«chi scrive nome e cognome vede i giocatori non registrati che si
        chiamano come lui, accenti e maiuscole a parte»."""
        from models.user.claim_service import ClaimService
        from models.user.services import UserService

        cognome = f"Nicolò{uuid.uuid4().hex[:4]}"
        giocatore = UserService.create_placeholder(
            "Niccolò", cognome, self._utente(db_session, UserRole.DIRECTOR.value)
        )
        nuovo = self._utente(db_session)
        nuovo.first_name = "niccolo"
        nuovo.last_name = cognome.upper().replace("Ò", "O")
        db_session.flush()
        assert giocatore.id in {u.id for u in ClaimService.omonimi(nuovo)}
