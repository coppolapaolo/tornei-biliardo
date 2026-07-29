"""Test per il caching dei file statici.

Su PythonAnywhere i file statici sono serviti da Flask, quindi ogni richiesta
occupa un worker Python. Col default `no-cache` il browser rivalida tutti i
CSS/JS a ogni pagina: misurato in produzione, ogni richiesta costa tra 0,4 e
2,4 secondi. La cache lunga elimina quelle richieste, ma è sicura solo se il
cache-buster negli URL cambia quando un asset viene modificato.
"""

import os
import time

import pytest

from config import Config, ProductionConfig, _compute_asset_version


class TestAssetVersion:
    """Il cache-buster deve cambiare quando cambia un asset, non prima."""

    def test_e_una_stringa_non_vuota(self):
        assert isinstance(Config.ASSET_VERSION, str)
        assert Config.ASSET_VERSION

    def test_e_stabile_tra_chiamate_successive(self):
        """Senza modifiche agli asset il valore non deve oscillare: cambiarlo
        a ogni avvio invaliderebbe la cache di tutti gli utenti a ogni deploy."""
        assert _compute_asset_version() == _compute_asset_version()

    def test_cambia_quando_un_asset_viene_modificato(self, tmp_path, monkeypatch):
        """È la proprietà che rende sicura la cache di un anno."""
        static = tmp_path / "static" / "css"
        static.mkdir(parents=True)
        asset = static / "main.css"
        asset.write_text("body {}")

        monkeypatch.setattr("config._BASE_DIR", str(tmp_path))
        prima = _compute_asset_version()

        # mtime esplicito: il filesystem ha granularità al secondo e il test
        # sarebbe altrimenti sensibile alla velocità della macchina.
        os.utime(asset, (time.time() + 60, time.time() + 60))
        dopo = _compute_asset_version()

        assert dopo != prima

    def test_ignora_gli_upload_degli_utenti(self, tmp_path, monkeypatch):
        """Le immagini caricate non sono codice: non devono invalidare i CSS
        di tutti gli utenti a ogni upload."""
        (tmp_path / "static" / "css").mkdir(parents=True)
        (tmp_path / "static" / "css" / "main.css").write_text("body {}")
        uploads = tmp_path / "static" / "uploads"
        uploads.mkdir(parents=True)

        monkeypatch.setattr("config._BASE_DIR", str(tmp_path))
        prima = _compute_asset_version()

        nuovo_upload = uploads / "foto.jpg"
        nuovo_upload.write_bytes(b"x")
        os.utime(nuovo_upload, (time.time() + 60, time.time() + 60))

        assert _compute_asset_version() == prima

    def test_non_solleva_se_le_cartelle_non_esistono(self, tmp_path, monkeypatch):
        monkeypatch.setattr("config._BASE_DIR", str(tmp_path))
        assert _compute_asset_version() == "0"


class TestCacheHeaders:
    """La cache lunga va attiva in produzione, non nei test."""

    CACHE_LUNGA = "public, max-age=31536000, immutable"

    @pytest.mark.parametrize("path", ["/static/css/main.css", "/static/js/polling.js"])
    def test_css_e_js_hanno_cache_lunga(self, client, path):
        assert client.get(path).headers.get("Cache-Control") == self.CACHE_LUNGA

    @pytest.mark.parametrize(
        "path",
        ["/static/img/chalk1.png", "/static/uploads/venues/foto.jpg"],
    )
    def test_asset_senza_cache_buster_non_hanno_cache_lunga(self, client, path):
        """Rilievo Copilot su PR #75: questi percorsi sono referenziati senza
        `?v=` (es. /static/img/chalk1.png da gamification.js), quindi una
        cache lunga li renderebbe non aggiornabili per un anno."""
        assert client.get(path).headers.get("Cache-Control") != self.CACHE_LUNGA

    def test_la_cache_non_e_impostata_globalmente_in_config(self):
        """Se SEND_FILE_MAX_AGE_DEFAULT tornasse in ProductionConfig varrebbe
        per tutto /static/, reintroducendo esattamente il problema."""
        assert getattr(ProductionConfig, "SEND_FILE_MAX_AGE_DEFAULT", None) is None

    @pytest.mark.parametrize("asset", ["css/main.css", "js/polling.js"])
    def test_asset_serviti_con_cache_buster_nel_template(self, client, asset):
        """Se un asset perde il `?v=`, la cache di un anno diventa una trappola:
        gli utenti resterebbero col file vecchio per sempre."""
        html = client.get("/privacy").get_data(as_text=True)

        assert f"{asset}?v={Config.ASSET_VERSION}" in html
