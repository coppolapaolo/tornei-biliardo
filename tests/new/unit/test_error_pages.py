"""Le pagine di errore devono essere quelle dell'applicazione.

Il 403 non aveva né template né handler: ogni permesso negato mostrava la
pagina grezza di Werkzeug — sfondo bianco, testo inglese, nessuna
navigazione — mentre 400, 404, 429 e 500 erano stati ridisegnati. Il caso
si incontra facilmente: `utils/permissions.py` fa `abort(403)` in cinque
punti, quindi basta che un direttore apra una pagina da amministratore.
"""

import pytest

from models.user.role_enum import UserRole


class TestPagina403:
    def test_permesso_negato_usa_il_template_dell_app(self, logged_in_client):
        """Un direttore su una pagina da admin vede la pagina 403 vera."""
        client, _ = logged_in_client(role=UserRole.DIRECTOR.value)

        risposta = client.get("/admin/users")

        assert risposta.status_code == 403
        corpo = risposta.get_data(as_text=True)
        # Marcatori del template dell'app, assenti dalla pagina di Werkzeug.
        assert "Tavolo riservato" in corpo
        assert "c7-empty" in corpo
        assert "You don&#39;t have the permission" not in corpo

    def test_richiesta_ajax_riceve_json(self, logged_in_client):
        """Le chiamate asincrone non devono ricevere una pagina HTML."""
        client, _ = logged_in_client(role=UserRole.DIRECTOR.value)

        risposta = client.get(
            "/admin/users", headers={"X-Requested-With": "XMLHttpRequest"}
        )

        assert risposta.status_code == 403
        assert risposta.is_json
        assert "error" in risposta.get_json()


@pytest.mark.parametrize("nome", ["400", "403", "404", "429", "500"])
def test_ogni_template_di_errore_esiste_e_compila(app, nome):
    """Un template di errore rotto si scopre solo quando serve davvero."""
    app.jinja_env.get_template(f"errors/{nome}.html")
