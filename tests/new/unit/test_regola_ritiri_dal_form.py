"""La regola dei ritiri letta dal form è una di quelle che il servizio conosce.

`GaraFormParser` prendeva `withdraw_policy` dal form e lo salvava com'era. Un
valore sconosciuto — bastava la minuscola, `"forfeit"` al posto di `"Forfeit"`
— finiva sulla gara senza un lamento, e l'errore arrivava molto dopo e molto
lontano: al primo giocatore che si ritirava, con un 400 «Unknown withdraw
policy» a gara in corso. L'interfaccia manda i valori giusti, quindi in
produzione non è capitato; è capitato ai dati di prova della stagione e2e
(`tests/new/e2e/stagione.py`), e il test del forfait era rosso senza che la CI
— che esegue solo i test unitari — lo vedesse.
"""

import pytest

from models.status_enum import WithdrawPolicy
from routes.admin.competition.form_parser import GaraFormParser


def _regola(app, form):
    with app.test_request_context(method="POST", data=form):
        return GaraFormParser._parse_withdraw_policy()


@pytest.mark.unit
class TestRegolaDeiRitiri:
    def test_i_due_valori_dell_interfaccia_passano(self, app):
        for regola in WithdrawPolicy:
            assert _regola(app, {"withdraw_policy": regola.value}) == regola.value

    def test_senza_campo_vale_il_default(self, app):
        assert _regola(app, {}) == WithdrawPolicy.FORFEIT.value

    def test_la_minuscola_si_riconosce(self, app):
        """Chi scrive `forfeit` intende `Forfeit`: si salva il valore vero."""
        assert (
            _regola(app, {"withdraw_policy": "forfeit"}) == WithdrawPolicy.FORFEIT.value
        )
        assert (
            _regola(app, {"withdraw_policy": "EXCLUDE"}) == WithdrawPolicy.EXCLUDE.value
        )

    def test_un_valore_sconosciuto_si_rifiuta_subito(self, app):
        with pytest.raises(ValueError):
            _regola(app, {"withdraw_policy": "squalifica"})
