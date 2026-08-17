"""Un'email non consegnata al primo colpo non e' un'email persa.

Dal registro GlitchTip di produzione (aprile-agosto 2026), sette invii falliti
su quattro destinatari reali, tutti con lo stesso profilo: la connessione SMTP
cade a meta'. `EOF occurred in violation of protocol`,
`Connection unexpectedly closed`, `please run connect() first` — tre modi di
dire la stessa cosa, tutti transitori.

Il guasto non era il singolo errore, era cosa succedeva dopo: niente.
`send_email` risponde `True` *prima* che l'invio parta (l'invio e' in un thread
di sfondo), quindi la route ha gia' detto «Controlla la tua casella di posta»
quando il tentativo fallisce. Un utente ha chiesto la verifica dell'indirizzo
tre volte in un'ora e mezza senza ricevere niente, leggendo ogni volta una
conferma. Per il recupero password e' peggio ancora: quel percorso e'
volutamente muto anche a utente inesistente (anti-enumerazione degli account),
quindi non c'e' nessun segnale per nessuno.

I test provano `_invia_con_ritentativi` e non `send_email`: il primo e' la
logica, il secondo e' un thread — e un thread non si interroga.
"""

from __future__ import annotations

import logging

import pytest

from models.shared import email_service as modulo
from models.shared.email_service import RITENTATIVI_ATTESE, EmailService


class _PostaFinta:
    """Un `mail` che fallisce le prime `fallimenti` volte, poi consegna."""

    def __init__(self, fallimenti: int, errore: Exception | None = None):
        self.fallimenti = fallimenti
        self.errore = errore or OSError("Connection unexpectedly closed")
        self.tentativi = 0

    def send(self, msg):  # noqa: D401 - firma di flask_mail.Mail
        self.tentativi += 1
        if self.tentativi <= self.fallimenti:
            raise self.errore


@pytest.fixture
def attese_registrate(monkeypatch):
    """Sostituisce l'attesa reale, e registra quanto si sarebbe dormito."""
    dormite: list[float] = []
    return dormite


def _invia(posta, monkeypatch, dormite: list[float]) -> bool:
    monkeypatch.setattr(modulo, "mail", posta)
    return EmailService._invia_con_ritentativi(
        msg=object(),
        to_email="tizio@example.test",
        subject="Verifica il tuo indirizzo",
        pausa=dormite.append,
    )


def test_al_primo_colpo_non_si_aspetta_nessuno(monkeypatch, attese_registrate):
    posta = _PostaFinta(fallimenti=0)
    assert _invia(posta, monkeypatch, attese_registrate) is True
    assert posta.tentativi == 1
    assert attese_registrate == [], "Nessuna attesa quando l'invio riesce subito."


def test_una_connessione_caduta_non_perde_l_email(monkeypatch, attese_registrate):
    """Il caso reale: il primo tentativo cade, il secondo consegna."""
    posta = _PostaFinta(fallimenti=1)
    assert _invia(posta, monkeypatch, attese_registrate) is True
    assert posta.tentativi == 2
    assert attese_registrate == [RITENTATIVI_ATTESE[0]]


def test_si_arrende_dopo_l_ultimo_tentativo(monkeypatch, attese_registrate):
    """Tre invii tentati in tutto: quello iniziale piu' due ripetizioni."""
    posta = _PostaFinta(fallimenti=99)
    assert _invia(posta, monkeypatch, attese_registrate) is False
    assert posta.tentativi == len(RITENTATIVI_ATTESE) + 1
    assert attese_registrate == list(RITENTATIVI_ATTESE), (
        "Ogni attesa dichiarata deve essere usata: una sequenza con un valore "
        "in piu' di quelli consumati e' un'attesa che non aspetta nessuno."
    )


def test_il_fallimento_intermedio_non_e_un_errore(
    monkeypatch, attese_registrate, caplog
):
    """Se il tentativo dopo riesce, non c'e' niente da guardare."""
    posta = _PostaFinta(fallimenti=1)
    with caplog.at_level(logging.DEBUG, logger=modulo.logger.name):
        _invia(posta, monkeypatch, attese_registrate)

    livelli = {r.levelno for r in caplog.records}
    assert logging.ERROR not in livelli, (
        "Un tentativo fallito seguito da uno riuscito non deve produrre un "
        "error: finirebbe su GlitchTip a consumare quota per un'email che e' "
        "arrivata."
    )
    assert logging.WARNING in livelli, "Il ritentativo deve restare tracciato."


def test_la_resa_definitiva_resta_un_errore_riconoscibile(
    monkeypatch, attese_registrate, caplog
):
    """È l'unico caso in cui qualcuno non ricevera' mai la sua email.

    Il prefisso «Failed to send email to» e' quello con cui queste issue
    esistono gia' su GlitchTip: cambiarlo ne aprirebbe di nuove, scollegate
    dalla storia precedente.
    """
    posta = _PostaFinta(fallimenti=99)
    with caplog.at_level(logging.DEBUG, logger=modulo.logger.name):
        _invia(posta, monkeypatch, attese_registrate)

    errori = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errori) == 1, "Una resa, un solo error."
    messaggio = errori[0].getMessage()
    assert messaggio.startswith("Failed to send email to tizio@example.test")
    assert "3 tentativi" in messaggio


def test_le_attese_crescono(monkeypatch):
    """Un ritentativo immediato ricadrebbe nello stesso guasto di rete."""
    assert list(RITENTATIVI_ATTESE) == sorted(RITENTATIVI_ATTESE)
    assert RITENTATIVI_ATTESE[0] > 0
