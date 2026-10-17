"""Il link al video della partita (2026-10-17).

Un modulo solo decide cosa è un link valido e in che forma si salva:
``utils.video_link.normalize_video_url``. Si accettano i link di YouTube nelle
forme che un giocatore copia davvero — dalla barra del browser, dal tasto
«Condividi», da una diretta o da uno short — compreso il punto d'inizio
(``t=``), e si salvano tutti nella stessa forma canonica. Il resto si rifiuta
con un messaggio: un link qualunque, aperto in una scheda nuova dalla pagina
della partita, sarebbe un link che il sito promuove senza sapere dove porta.
"""

import pytest

from utils.video_link import VideoLinkError, normalize_video_url

ID = "dQw4w9WgXcQ"
CANONICO = f"https://www.youtube.com/watch?v={ID}"


@pytest.mark.parametrize(
    "grezzo, atteso",
    [
        (f"https://www.youtube.com/watch?v={ID}", CANONICO),
        (f"https://youtube.com/watch?v={ID}", CANONICO),
        (f"https://m.youtube.com/watch?v={ID}", CANONICO),
        (f"http://www.youtube.com/watch?v={ID}", CANONICO),
        (f"www.youtube.com/watch?v={ID}", CANONICO),
        (f"https://www.youtube.com/watch?feature=share&v={ID}", CANONICO),
        (f"https://youtu.be/{ID}", CANONICO),
        (f"youtu.be/{ID}?si=abcdef", CANONICO),
        (f"https://www.youtube.com/live/{ID}", CANONICO),
        (f"https://www.youtube.com/live/{ID}?si=xyz", CANONICO),
        (f"https://www.youtube.com/shorts/{ID}", CANONICO),
        (f"  https://youtu.be/{ID}  ", CANONICO),
    ],
)
def test_le_forme_di_youtube_diventano_una(grezzo, atteso):
    assert normalize_video_url(grezzo) == atteso


@pytest.mark.parametrize(
    "grezzo, secondi",
    [
        (f"https://youtu.be/{ID}?t=90", 90),
        (f"https://youtu.be/{ID}?t=90s", 90),
        (f"https://www.youtube.com/watch?v={ID}&t=1m30s", 90),
        (f"https://www.youtube.com/watch?v={ID}&t=1h2m3s", 3723),
        (f"https://www.youtube.com/live/{ID}?t=600", 600),
        (f"https://www.youtube.com/watch?v={ID}&start=45", 45),
    ],
)
def test_il_punto_d_inizio_resta(grezzo, secondi):
    assert normalize_video_url(grezzo) == f"{CANONICO}&t={secondi}s"


def test_un_inizio_a_zero_non_si_scrive():
    assert normalize_video_url(f"https://youtu.be/{ID}?t=0") == CANONICO


@pytest.mark.parametrize("vuoto", [None, "", "   "])
def test_il_campo_vuoto_toglie_il_link(vuoto):
    assert normalize_video_url(vuoto) is None


@pytest.mark.parametrize(
    "cattivo",
    [
        "https://vimeo.com/123456",
        "https://www.youtube.com/",
        "https://www.youtube.com/watch?v=corto",
        "https://www.youtube.com/channel/UC1234567890",
        f"https://youtube.com.evil.example/watch?v={ID}",
        f"https://evil.example/?u=https://youtu.be/{ID}",
        f"javascript:alert(1)//youtu.be/{ID}",
        f"ftp://youtu.be/{ID}",
        f"https://youtu.be/{ID}?t=abc",
        "non è un link",
        "https://www.youtube.com/watch?v=" + "a" * 300,
    ],
)
def test_il_resto_si_rifiuta(cattivo):
    with pytest.raises(VideoLinkError):
        normalize_video_url(cattivo)


def test_l_errore_e_un_errore_di_validazione():
    """Le route lo mappano a 422 come ogni ``ValidationError`` di dominio."""
    from models.exceptions import ValidationError

    assert issubclass(VideoLinkError, ValidationError)
