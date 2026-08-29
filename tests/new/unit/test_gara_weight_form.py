"""Il peso della prova, dal modulo fino alla colonna (issue #64).

Il motore c'era già: `Gara.weight` esiste, `Gara.classification_weight` lo
legge, e `ScoreAggregator.aggregate_campionato_scores` moltiplica per quel
valore il contributo di ogni gara prima di sommarlo (ADR-053). Mancava soltanto
il modo di **dirlo**: l'unico peso che una schermata sapesse impostare era
quello del playoff, e ogni altra gara nasceva a 1 senza che nessuno potesse
scegliere diversamente.

Due decisioni che questo file fissa, perché nessuna delle due è ovvia:

**Un peso non positivo è un errore, non un valore da correggere in silenzio.**
Il parser altrove ripiega su un default quando un numero arriva malformato, e
per i turni o la quota è la scelta giusta — nessuno *intende* «zero turni». Qui
no: lo zero ha già un significato preciso e riservato (`classification_weight`
vale 0 per la gara di playoff che decide da sola la classifica finale), e
trasformare uno zero digitato in un 1 vorrebbe dire scrivere in classifica un
peso che il direttore non ha scelto. Si rifiuta, con lo stesso messaggio di
`PlayoffService.update_scoring`, che sulla stessa colonna decide già così.

**Su una gara standalone il peso resta 1 e non si legge dal modulo.** Senza
campionato non c'è nessuna classifica generale in cui pesare, quindi il campo
non viene mostrato; e ciò che non si mostra non si legge, altrimenti un POST
costruito a mano scriverebbe un valore che nessuna schermata potrà più
rivedere. È la stessa regola che `_parse_bracket_options` applica alle opzioni
del tabellone fuori dal tabellone: azzerate, non ignorate.
"""

from __future__ import annotations

import pytest

from routes.admin.competition.form_parser import GaraFormParser


class _CampionatoFinto:
    """Il minimo che `GaraFormParser` legge da un campionato."""

    campionato_type = "amalfi"
    default_rounds_count = 3
    default_entry_fee = 0
    default_anti_rematch = True
    default_odd_policy = "bye"
    default_classification_system = "WINS"


def _gara_form(app, **extra):
    base = {
        "date": "2026-12-01",
        "time": "20:00",
        "discipline": "8_ball",
        "distance": "5",
        "rounds_count": "3",
        "min_participants": "2",
        "matchmaking_strategy": "amalfi",
        "first_round_policy": "random",
        "odd_number_policy": "bye",
    }
    base.update(extra)
    return app.test_request_context(method="POST", data=base)


@pytest.mark.unit
def test_il_peso_scelto_arriva_al_modello(app):
    with _gara_form(app, weight="3"):
        data = GaraFormParser(campionato=_CampionatoFinto()).parse()
    assert data["weight"] == 3


@pytest.mark.unit
def test_senza_campo_il_peso_vale_uno(app):
    """1 è il comportamento storico: ogni campionato esistente resta com'era."""
    with _gara_form(app):
        data = GaraFormParser(campionato=_CampionatoFinto()).parse()
    assert data["weight"] == 1


@pytest.mark.unit
def test_il_campo_vuoto_vale_uno(app):
    """Casella svuotata = «non ho scelto», non = «zero»."""
    with _gara_form(app, weight=""):
        data = GaraFormParser(campionato=_CampionatoFinto()).parse()
    assert data["weight"] == 1


@pytest.mark.unit
@pytest.mark.parametrize("valore", ["0", "-2", "due", "1.5"])
def test_un_peso_non_positivo_viene_rifiutato(app, valore):
    """Lo zero è riservato, e il resto non è un peso: si rifiuta, non si aggiusta."""
    with _gara_form(app, weight=valore):
        with pytest.raises(ValueError, match="maggiore di zero"):
            GaraFormParser(campionato=_CampionatoFinto()).parse()


@pytest.mark.unit
def test_sulla_gara_standalone_il_peso_resta_uno(app):
    """Senza campionato non c'è classifica in cui pesare: il campo non si legge."""
    with _gara_form(app, weight="5"):
        data = GaraFormParser(campionato=None).parse()
    assert data["weight"] == 1
