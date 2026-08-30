"""Le segnalazioni degli utenti: le regole che decidono cosa legge chi scrive.

Tre gruppi, e sono i tre punti in cui la issue #255 diceva che si può
sbagliare:

* **salvare prima, spedire poi**: una segnalazione non si perde perché GitHub
  è irraggiungibile — è il difetto che farebbe smettere di segnalare;
* **cosa vuol dire «presa in considerazione»**: è ciò che l'utente legge, e
  l'etichetta che ci mette l'app aprendo la issue non conta come lettura
  umana;
* **cosa dell'issue arriva all'utente**: solo un commento marcato. Sulla issue
  si deve poter ragionare senza pubblicare.
"""

from __future__ import annotations

import json

import pytest

from models.base import db
from models.exceptions import ValidationError
from models.feedback.github_client import GitHubClient, IssueRemota, Risposta
from models.feedback.models import FeedbackReport, FeedbackStatus, FeedbackType
from models.feedback.service import FeedbackService


def _issue(**campi) -> IssueRemota:
    base = dict(
        numero=1,
        stato="open",
        motivo_chiusura=None,
        etichette=["segnalazione", "bug"],
        ha_assegnatario=False,
        ha_milestone=False,
    )
    base.update(campi)
    return IssueRemota(**base)


@pytest.fixture
def utente(isolated_players):
    return isolated_players[0]


# ══ Salvare prima, spedire poi ═══════════════════════════════════════════════


@pytest.mark.unit
class TestLaSegnalazioneNonSiPerde:
    def test_si_salva_anche_senza_token_github(self, db_session, utente, monkeypatch):
        """Il caso che conta: token assente, e il testo resta.

        Se qui la segnalazione andasse persa, l'utente riscriverebbe tutto —
        o, più probabilmente, non riscriverebbe affatto.
        """
        monkeypatch.setattr(
            GitHubClient, "dalla_configurazione", classmethod(lambda cls: cls(None, ""))
        )

        segnalazione = FeedbackService.registra(
            user_id=utente.id,
            tipo=FeedbackType.BUG.value,
            titolo="Non riesco a segnare",
            corpo="Premo il triangolo e non succede niente.",
        )
        spedita = FeedbackService.spedisci(segnalazione.id)

        assert spedita is False
        riletta = db.session.get(FeedbackReport, segnalazione.id)
        assert riletta is not None
        assert riletta.corpo == "Premo il triangolo e non succede niente."
        assert riletta.stato == FeedbackStatus.RICEVUTA.value
        assert riletta.issue_number is None
        assert riletta.tentativi_invio == 1
        assert "token" in (riletta.ultimo_errore or "")

    def test_una_spedizione_riuscita_azzera_l_errore_precedente(
        self, db_session, utente, monkeypatch
    ):
        """Un errore vecchio accanto a una issue creata racconterebbe un
        guasto che non c'è più — e manderebbe l'admin a cercarlo."""
        monkeypatch.setattr(
            GitHubClient, "dalla_configurazione", classmethod(lambda cls: cls(None, ""))
        )
        segnalazione = FeedbackService.registra(
            user_id=utente.id, tipo="bug", titolo="T", corpo="C"
        )
        FeedbackService.spedisci(segnalazione.id)
        assert db.session.get(FeedbackReport, segnalazione.id).ultimo_errore

        monkeypatch.setattr(
            GitHubClient,
            "dalla_configurazione",
            classmethod(lambda cls: _ClienteFinto(numero=42)),
        )
        assert FeedbackService.spedisci(segnalazione.id) is True

        riletta = db.session.get(FeedbackReport, segnalazione.id)
        assert riletta.issue_number == 42
        assert riletta.ultimo_errore is None
        assert riletta.tentativi_invio == 2

    def test_non_si_spedisce_due_volte_la_stessa(self, db_session, utente, monkeypatch):
        """Il job ripassa ogni notte: senza questo controllo aprirebbe una
        issue nuova per la stessa segnalazione a ogni giro."""
        monkeypatch.setattr(
            GitHubClient,
            "dalla_configurazione",
            classmethod(lambda cls: _ClienteFinto(numero=7)),
        )
        segnalazione = FeedbackService.registra(
            user_id=utente.id, tipo="bug", titolo="T", corpo="C"
        )
        assert FeedbackService.spedisci(segnalazione.id) is True
        assert FeedbackService.spedisci(segnalazione.id) is False
        assert db.session.get(FeedbackReport, segnalazione.id).issue_number == 7

    @pytest.mark.parametrize(
        "campi",
        [
            {"tipo": "non-esiste"},
            {"titolo": "   "},
            {"corpo": ""},
        ],
    )
    def test_il_modulo_incompleto_lo_dice_subito(self, db_session, utente, campi):
        dati = {"tipo": "bug", "titolo": "T", "corpo": "C"}
        dati.update(campi)
        with pytest.raises(ValidationError):
            FeedbackService.registra(user_id=utente.id, **dati)


@pytest.mark.unit
class TestIlCorpoDellIssue:
    def test_porta_il_contesto_ma_non_l_email(self, db_session, utente):
        """Username e id bastano a risalire a chi ha scritto: il legame vive
        nel nostro DB, e l'email su un servizio di terzi non ci va."""
        segnalazione = FeedbackService.registra(
            user_id=utente.id,
            tipo="bug",
            titolo="T",
            corpo="Il racconto dell'utente.",
            contesto={"versione": "1.5.0", "browser": "Safari"},
        )
        db.session.flush()

        corpo = FeedbackService.corpo_issue(segnalazione)

        assert "Il racconto dell'utente." in corpo
        assert utente.username in corpo
        assert "1.5.0" in corpo and "Safari" in corpo
        assert utente.email not in corpo

    def test_un_contesto_illeggibile_non_impedisce_la_spedizione(
        self, db_session, utente
    ):
        """Il testo dell'utente vale più del contesto, che è un di più
        raccolto dall'app: un JSON storto non deve bloccare niente."""
        segnalazione = FeedbackService.registra(
            user_id=utente.id, tipo="bug", titolo="T", corpo="C"
        )
        segnalazione.contesto = "{non è json"
        db.session.flush()

        assert FeedbackService.contesto_dizionario(segnalazione) == {}
        assert "C" in FeedbackService.corpo_issue(segnalazione)


# ══ Cosa vuol dire «presa in considerazione» ════════════════════════════════


@pytest.mark.unit
class TestLaRegolaDiStato:
    def test_le_etichette_dell_app_non_sono_una_lettura_umana(self):
        """`segnalazione` e `bug` le mette l'app aprendo la issue. Se
        bastassero, ogni segnalazione risulterebbe «presa in considerazione»
        un secondo dopo essere stata scritta."""
        assert FeedbackService.stato_da_issue(_issue()) == FeedbackStatus.RICEVUTA

    @pytest.mark.parametrize(
        "campi",
        [
            {"etichette": ["segnalazione", "bug", "campionati"]},
            {"ha_assegnatario": True},
            {"ha_milestone": True},
        ],
    )
    def test_un_segno_di_lettura_umana_la_prende_in_carico(self, campi):
        assert (
            FeedbackService.stato_da_issue(_issue(**campi))
            == FeedbackStatus.PRESA_IN_CARICO
        )

    def test_chiusa_come_completata_e_risolta(self):
        assert (
            FeedbackService.stato_da_issue(
                _issue(stato="closed", motivo_chiusura="completed")
            )
            == FeedbackStatus.RISOLTA
        )

    @pytest.mark.parametrize(
        "campi",
        [
            {"stato": "closed", "motivo_chiusura": "not_planned"},
            {"stato": "closed", "motivo_chiusura": None, "etichette": ["duplicate"]},
            {"etichette": ["segnalazione", "wontfix"]},
        ],
    )
    def test_non_prevista(self, campi):
        assert (
            FeedbackService.stato_da_issue(_issue(**campi))
            == FeedbackStatus.NON_PREVISTA
        )

    def test_una_chiusa_con_area_assegnata_e_risolta_non_presa_in_carico(self):
        """L'ordine dei controlli conta: una issue chiusa dice già tutto, e
        va letta prima delle etichette. Al contrario, all'utente arriverebbe
        «presa in considerazione» per una cosa già fatta."""
        assert (
            FeedbackService.stato_da_issue(
                _issue(
                    stato="closed",
                    motivo_chiusura="completed",
                    etichette=["segnalazione", "campionati"],
                    ha_assegnatario=True,
                )
            )
            == FeedbackStatus.RISOLTA
        )


# ══ Cosa dell'issue arriva all'utente ═══════════════════════════════════════


@pytest.mark.unit
class TestLaNotaPubblica:
    def test_un_commento_qualunque_non_arriva_all_utente(self):
        """È il patto: sulla issue si deve poter ragionare — «forse è lo
        stesso bug della #212», sbagliarsi, cambiare idea — senza che ogni
        parola finisca sotto gli occhi di chi ha segnalato."""
        assert (
            FeedbackService.nota_pubblica(
                [{"body": "boh, forse è lo stesso della #212"}]
            )
            is None
        )

    def test_solo_il_commento_marcato(self):
        nota = FeedbackService.nota_pubblica(
            [
                {"body": "nota interna"},
                {"body": "@utente: ci stiamo lavorando, grazie!"},
                {"body": "altra nota interna"},
            ]
        )
        assert nota == "ci stiamo lavorando, grazie!"

    def test_vince_l_ultimo_marcato(self):
        """Se si torna sulla issue e si corregge quel che si era detto,
        all'utente deve arrivare la versione buona."""
        nota = FeedbackService.nota_pubblica(
            [
                {"body": "@utente: pensavamo fosse il telefono"},
                {"body": "@utente: era un nostro errore, corretto"},
            ]
        )
        assert nota == "era un nostro errore, corretto"

    def test_un_marcatore_senza_testo_non_e_una_nota(self):
        assert FeedbackService.nota_pubblica([{"body": "@utente:   "}]) is None


# ══ L'aggiornamento e le sue conseguenze ════════════════════════════════════


@pytest.mark.unit
class TestApplicaAggiornamento:
    def test_niente_di_nuovo_niente_notifica(self, db_session, utente):
        """Senza questa distinzione, ogni giro del job manderebbe una
        notifica a tutti anche quando non è cambiato niente."""
        segnalazione = FeedbackService.registra(
            user_id=utente.id, tipo="bug", titolo="T", corpo="C"
        )
        db.session.flush()

        assert FeedbackService.applica_aggiornamento(
            segnalazione, FeedbackStatus.RICEVUTA, None
        ) == (False, False)

    def test_una_nota_nuova_e_una_novita_anche_a_stato_fermo(self, db_session, utente):
        """La sezione «Novità» ordina per `stato_cambiato_il`: senza toccarla,
        una risposta scritta a stato invariato non comparirebbe mai."""
        segnalazione = FeedbackService.registra(
            user_id=utente.id, tipo="bug", titolo="T", corpo="C"
        )
        db.session.flush()
        prima = segnalazione.stato_cambiato_il

        stato_cambiato, nota_cambiata = FeedbackService.applica_aggiornamento(
            segnalazione, FeedbackStatus.RICEVUTA, "ci stiamo lavorando"
        )

        assert (stato_cambiato, nota_cambiata) == (False, True)
        assert segnalazione.nota_pubblica == "ci stiamo lavorando"
        assert segnalazione.stato_cambiato_il >= prima


@pytest.mark.unit
class TestLeLettureDelleSchermate:
    def test_una_segnalazione_appena_nata_non_e_una_novita(self, db_session, utente):
        """«Ricevuta» è lo stato in cui nasce: mostrarla fra le novità
        riempirebbe la sezione di non-notizie."""
        FeedbackService.registra(user_id=utente.id, tipo="bug", titolo="T", corpo="C")
        db.session.flush()

        assert FeedbackService.mie_segnalazioni(utente.id)
        assert FeedbackService.novita(utente.id) == []

    def test_si_vedono_solo_le_proprie(self, db_session, isolated_players):
        uno, due = isolated_players[0], isolated_players[1]
        FeedbackService.registra(user_id=uno.id, tipo="bug", titolo="La mia", corpo="C")
        db.session.flush()

        assert [s.titolo for s in FeedbackService.mie_segnalazioni(uno.id)] == [
            "La mia"
        ]
        assert FeedbackService.mie_segnalazioni(due.id) == []


class _ClienteFinto:
    """Un GitHub che risponde sempre bene, per provare il ramo felice."""

    def __init__(self, numero: int):
        self._numero = numero
        self.configurato = True

    def crea_issue(self, titolo, corpo, etichette):
        return Risposta(ok=True, corpo={"number": self._numero})

    def issue_toccate(self, etichetta, da_quando=None, etag=None):
        return Risposta(ok=True, corpo=[])

    def commenti(self, numero_issue):
        return Risposta(ok=True, corpo=[])


@pytest.mark.unit
def test_il_json_del_contesto_sopravvive_al_giro(db_session, isolated_players):
    """Il contesto si salva come JSON e si rilegge come dizionario: se la
    serializzazione perdesse i caratteri accentati, le issue arriverebbero
    illeggibili."""
    segnalazione = FeedbackService.registra(
        user_id=isolated_players[0].id,
        tipo="bug",
        titolo="T",
        corpo="C",
        contesto={"pagina di provenienza": "/gare/1", "città": "Udine"},
    )
    db.session.flush()

    assert json.loads(segnalazione.contesto)["città"] == "Udine"
    assert FeedbackService.contesto_dizionario(segnalazione)["città"] == "Udine"
