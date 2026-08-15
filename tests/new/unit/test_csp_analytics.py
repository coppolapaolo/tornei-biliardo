"""Test per la Content-Security-Policy in presenza di Google Analytics.

Regressione: la CSP dell'applicazione elencava solo cdn.jsdelivr.net e
code.jquery.com in `script-src`, e `connect-src 'self'`. Il browser bloccava
quindi gtag.js e le chiamate di raccolta, e GA restava a zero visite **in
ogni browser** — senza alcun errore lato server e senza che il tag mancasse
dall'HTML, il che rende il guasto particolarmente difficile da attribuire.

I test verificano entrambe le direzioni: che i domini ci siano quando GA è
configurato, e che NON ci siano quando non lo è (una CSP più larga del
necessario è superficie di attacco gratuita).
"""

GA_TEST_ID = "G-TEST12345"


def _csp(client) -> str:
    return client.get("/privacy").headers["Content-Security-Policy"]


class TestCspSenzaAnalytics:
    """Senza GA la policy non deve allargarsi."""

    def test_googletagmanager_assente_da_script_src(self, client):
        assert "googletagmanager" not in _csp(client)

    def test_connect_src_resta_ristretto(self, client):
        assert "connect-src 'self'" in _csp(client)
        assert "google-analytics" not in _csp(client)


class TestCspConAnalytics:
    """Con GA configurato devono esserci i domini che il tag usa davvero."""

    def test_script_src_consente_gtag(self, app, client, monkeypatch):
        monkeypatch.setitem(app.config, "GA_MEASUREMENT_ID", GA_TEST_ID)
        csp = _csp(client)

        script_src = [d for d in csp.split(";") if d.strip().startswith("script-src")]
        assert script_src, "direttiva script-src assente"
        assert "https://www.googletagmanager.com" in script_src[0]

    def test_connect_src_consente_la_raccolta(self, app, client, monkeypatch):
        """Senza questo, gtag.js carica ma gli hit non partono: il caso
        peggiore, perché tutto sembra a posto e i dati non arrivano."""
        monkeypatch.setitem(app.config, "GA_MEASUREMENT_ID", GA_TEST_ID)
        csp = _csp(client)

        connect_src = [d for d in csp.split(";") if d.strip().startswith("connect-src")]
        assert connect_src, "direttiva connect-src assente"
        assert "https://*.google-analytics.com" in connect_src[0]
        assert "https://*.analytics.google.com" in connect_src[0]

    def test_img_src_consente_i_pixel(self, app, client, monkeypatch):
        """GA4 ricade su richieste immagine quando fetch non è disponibile."""
        monkeypatch.setitem(app.config, "GA_MEASUREMENT_ID", GA_TEST_ID)
        csp = _csp(client)

        img_src = [d for d in csp.split(";") if d.strip().startswith("img-src")]
        assert img_src, "direttiva img-src assente"
        assert "https://*.google-analytics.com" in img_src[0]

    def test_le_direttive_preesistenti_restano(self, app, client, monkeypatch):
        """L'aggiunta non deve sostituire i domini già consentiti."""
        monkeypatch.setitem(app.config, "GA_MEASUREMENT_ID", GA_TEST_ID)
        csp = _csp(client)

        assert "cdn.jsdelivr.net" in csp
        assert "code.jquery.com" in csp
        assert "cdnjs.cloudflare.com" in csp
        assert "default-src 'self'" in csp


class TestCspFontDelTema:
    """I font del design system 7c devono poter essere caricati.

    Stessa classe di guasto di GA: `base.html` chiede Manrope e JetBrains
    Mono a Google Fonts, ma la CSP elencava solo i due CDN storici. Il
    browser bloccava il foglio e i woff2, la tipografia cadeva sul fallback
    di sistema su **ogni** pagina e nulla lo segnalava lato server — il
    sintomo somiglia a un design sbagliato, non a un header.

    La CSP è impostata in un `after_request` non condizionato all'ambiente,
    quindi il blocco vale anche in sviluppo.
    """

    def test_style_src_consente_il_foglio_dei_font(self, client):
        assert "fonts.googleapis.com" in _csp(client)

    def test_font_src_consente_i_woff2(self, client):
        font_src = [d for d in _csp(client).split(";") if "font-src" in d]
        assert font_src, "direttiva font-src assente"
        assert "fonts.gstatic.com" in font_src[0]
