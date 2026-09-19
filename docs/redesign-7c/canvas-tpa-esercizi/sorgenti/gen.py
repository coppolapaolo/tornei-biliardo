#!/usr/bin/env python3
"""Genera il canvas «TPA ed esercizi» — primo giro: direzioni a confronto.

python3 gen.py            scrive root/project/*.dc.html e canvas.json
"""

import json
import pathlib

import decisioni as DEC
import esercizi as E
import tpa as T
from boards_extra import EXTRA_BOARDS, EXTRA_PAGES
from kit import doc

ROOT = pathlib.Path(__file__).resolve().parent / "root" / "project"

P, PH = 390, 844
GAP = 80

# (pagina, file, titolo, funzione, w, h, colore bigliettino, bigliettino)
BOARDS = [
    (
        "tpa",
        "Main.dc.html",
        "A · Ordine",
        T.tpa_a,
        P,
        976,
        "blue",
        "A · ORDINE\nLa pagina di oggi messa in ordine, con la nav in basso. Col tastierino "
        "intero dell'app originale la pagina NON sta in uno schermo: si scorre per arrivare "
        "a «Indietro / Avanti» e al referto. È il suo limite. Stesse regole di B: niente "
        "pulsante per passare il tavolo, due annulla, TPA alla pari.",
    ),
    (
        "tpa",
        "TpaTavolo.dc.html",
        "B · Tavolo",
        T.tpa_b,
        P,
        PH,
        "green",
        "B · TAVOLO — la direzione scelta (D1)\nPASSARE IL TAVOLO = toccare il riquadro di Sara. "
        "DUE ANNULLA: «cancella» toglie l'annotazione del turno; «Indietro / Avanti» scorre il "
        "referto. TRIANGOLI e TPA alla pari, TPA da 0 a 1000. NOTAZIONE, tutta in una schermata: "
        "il ① piccolo sopra è il PRIMO TIRO DI CALCIO (numero di chi tira, cerchiato — come "
        "l'originale, non una freccia); «3 Mⁿ» ha la n in apice; la P nella casella ombreggiata "
        "è il FALLO. Dopo il fallo il motore non ammette altro: tasti tutti spenti, resta passare.",
    ),
    (
        "tpa",
        "TpaIndietro.dc.html",
        "B · Indietro nel referto",
        T.tpa_indietro,
        P,
        PH,
        "orange",
        "IL SECONDO ANNULLA · nuovo\nCome nell'originale: «Indietro» porta a rileggere un turno "
        "passato, in sola lettura — il tastierino si spegne tutto, l'avviso dice dove sei. "
        "«Avanti» riporta al presente senza perdere niente. Per riscrivere la storia c'è un "
        "passo esplicito: «Riparti da questo turno…». Oggi nell'app `undo` CANCELLA l'ultimo "
        "comando: serve un cursore sul registro (emendamento ADR-044, fase 2c).",
    ),
    (
        "tpa",
        "TpaRiparti.dc.html",
        "B · Ripartire dal passato",
        T.tpa_riparti,
        P,
        PH,
        "orange",
        "RIPARTIRE · nuovo\nL'originale chiede con un confirm() «Questo eliminerà 2 turni "
        "successivi». Qui è un foglio 7c che li nomina uno per uno. ALTERNATIVA (D16): niente "
        "conferma, il primo tasto premuto nel passato tronca da sé — più veloce, ma un tocco "
        "per sbaglio mentre si rilegge butta via dei turni.",
    ),
    (
        "tpa",
        "TpaFoglio.dc.html",
        "C · Foglio vivo",
        T.tpa_c,
        P,
        PH,
        "gray",
        "C · FOGLIO VIVO — da scartare se confermi B (D1)\nIl turno in corso è l'ultima riga "
        "del referto. Ma col tastierino intero del referto resta una riga e mezza: su telefono "
        "non regge, e TPA e punteggio qui restano piccoli. L'idea buona — il referto sempre "
        "in vista — sopravvive su desktop, dove ha la sua colonna.",
    ),
    (
        "tpa",
        "TpaDesktop.dc.html",
        "Desktop",
        T.tpa_desktop,
        1440,
        900,
        "gray",
        "DESKTOP\nOggi la colonna destra resta vuota (380px) e il tastierino si stira su 6 "
        "colonne, rompendo la disposizione del cartaceo. Qui il referto riempie la colonna e "
        "il tastierino resta a 3 colonne, con «cancella» e «Indietro / Avanti». Il tavolo si "
        "passa cliccando il riquadro di Sara. Vale per qualunque direzione.",
    ),
    (
        "tpa",
        "TpaChiuso.dc.html",
        "Referto chiuso",
        T.tpa_chiuso,
        P,
        1098,
        "orange",
        "REFERTO CHIUSO · nuovo\nOggi un referto chiuso è la stessa pagina senza tastierino. "
        "Qui diventa il racconto della partita: TPA dei due, da dove vengono gli errori "
        "(le cinque famiglie del motore), i riconoscimenti, il referto triangolo per "
        "triangolo. Tutti dati che `describe` già calcola: nessun modello nuovo. "
        "Recepito: «Chiuse in un turno» (non «visita») e «Referto» (non «Il foglio»).",
    ),
    (
        "trovare",
        "TrovareCatalogo.dc.html",
        "A · Catalogo che si filtra",
        E.trovare_a,
        P,
        PH,
        "blue",
        "A · CATALOGO  (#168)\nSi filtra per ABILITÀ (cosa alleni: posizione, tiro…), per GESTO "
        "(come colpisci: stop, stun, follow, draw — è la categorizzazione di Bullseye), per "
        "livello e per voto. Sono vocabolari distinti e un esercizio ha zero, una o più voci "
        "su ciascuno: il terzo qui sotto non ha nessuna abilità. La «classe» di Ronin li "
        "mescola. Su ogni card il voto e quanti l'hanno provato, che si leggono insieme. "
        "Richiede tabelle di associazione, non colonne.",
    ),
    (
        "trovare",
        "TrovareOggi.dc.html",
        "B · Oggi",
        E.trovare_b,
        P,
        1024,
        "blue",
        "B · OGGI  (#175 #172 #316)\nLa porta è un consiglio: un esercizio per oggi col motivo "
        "scritto, la scheda da riprendere, gli obiettivi; il catalogo sta dietro «Apri il "
        "catalogo».\nÈ la direzione più ricca e la più costosa: presuppone scheda, obiettivi e "
        "la regola di raccomandazione. Può essere l'arrivo, con A come prima tappa.",
    ),
    (
        "trovare",
        "SchedaEsercizio.dc.html",
        "La scheda di un esercizio",
        E.scheda,
        P,
        1196,
        "gray",
        "LA SCHEDA  (#181 #174 #252 #253)\nMedia, ultime tre con tendenza, record; il grafico "
        "delle prove (esiste già nello storico: qui viene portato dove serve); «quelli come "
        "te» per fascia di Elo e il livello misurato accanto a quello dichiarato. "
        "«Modifica» e «Duplica» compaiono per chi può: oggi la modifica è una route senza link.",
    ),
    (
        "eseguire",
        "EseguiPunteggio.dc.html",
        "1 · A punteggio",
        E.esegui_punteggio,
        P,
        PH,
        "gray",
        "A PUNTEGGIO · c'è già\nIl gesto di oggi, con i comandi ancorati in basso. NUOVO, dal tuo "
        "commento: l'AVANZAMENTO DAL VIVO — una barra per prova, la tua media tratteggiata, i "
        "posti ancora vuoti. È un pezzo della cornice comune: lo riusano tutte le modalità.",
    ),
    (
        "eseguire",
        "EseguiColpo.dc.html",
        "2 · Colpo per colpo",
        E.esegui_colpo,
        P,
        PH,
        "green",
        "COLPO PER COLPO · rifatto (#183)\nEra troppo Bullseye. Ora: tavolo orizzontale come nel "
        "resto dell'app; anelli che valgono PUNTI (3·2·1) in una sola tinta oro, non verde e "
        "rosso; un gesto solo — il tocco sul panno è già «imbucata» — e un tasto per l'errore, "
        "non la coppia rosso/nero; i colpi sono caselle col punteggio. In alto la corsa dal "
        "vivo contro il tuo solito, con la proiezione a fine serie.",
    ),
    (
        "eseguire",
        "EseguiZoom.dc.html",
        "3 · Il punto preciso",
        E.esegui_zoom,
        P,
        PH,
        "orange",
        "IL PUNTO PRECISO · nuovo (#183)\nCol dito, su un tavolo grande come un telefono, "
        "un punto a pochi centimetri dal centro non si indica: dopo il tocco si apre "
        "l'ingrandimento, si trascina, si conferma. Qui gli anelli portano scritto il valore.",
    ),
    (
        "eseguire",
        "EseguiCasuale.dc.html",
        "4 · Con estrazione",
        E.esegui_casuale,
        P,
        PH,
        "orange",
        "CON ESTRAZIONE · nuovo (#452)\nL'app estrae e scrive la consegna a parole — «3 o più "
        "sponde, bilia 7» — invece di stampare 37. L'esito è una scala con un nome per voce "
        "(0 1 2 4 8). Stessa cornice: anche qui la corsa dal vivo, contro la serie del record. "
        "L'estrazione si persiste, così l'annulla sa dire cosa toglie.",
    ),
    (
        "eseguire",
        "EseguiFine.dc.html",
        "5 · Fine sessione",
        E.esegui_fine,
        P,
        PH,
        "orange",
        "FINE SESSIONE · nuovo (#172 #181 #184)\nLa sessione si chiude davvero. La nuvola dei "
        "punti d'arrivo è l'unica rappresentazione che dice COME correggere; i tre numeri "
        "hanno una parola accanto; la serie di colpi (non la streak settimanale) dà il "
        "traguardo; le note spiegano fra tre mesi un crollo isolato.",
    ),
    (
        "dopo",
        "Andamento.dc.html",
        "Il tuo allenamento",
        E.andamento,
        P,
        1320,
        "orange",
        "ANDAMENTO · nuovo (#181 #316)\nIl confronto che conta è con sé stessi un mese fa. Le "
        "categorizzazioni sono DUE, quindi i radar sono due (tuo commento): «Per abilità» e "
        "«Per gesto», con un interruttore. Ogni asse vuole abbastanza prove per dire qualcosa, "
        "e quando non le ha la pagina lo dice. Gli obiettivi sono al massimo tre.",
    ),
    (
        "dopo",
        "AndamentoGesto.dc.html",
        "Il tuo allenamento · per gesto",
        E.andamento_gesto,
        P,
        1320,
        "orange",
        "PER GESTO\nLa stessa pagina sull'altro asse: qui si vede che il draw cresce e lo spin è "
        "fermo — una lettura che le abilità non danno. Otto assi e non dieci: jump e massé "
        "entrano quando hanno abbastanza prove.",
    ),
    (
        "dopo",
        "Obiettivo.dc.html",
        "Imposta un obiettivo",
        E.obiettivo,
        P,
        980,
        "orange",
        "IMPOSTA UN OBIETTIVO · nuovo (#316 #175)\nRisposta a «come si impostano?»: da "
        "«Aggiungi un obiettivo» nell'andamento, o da «Punta a…» sulla scheda di un esercizio. "
        "Tre forme: un RISULTATO su un esercizio (qui), un'ABILITÀ che sale di fascia, la "
        "COSTANZA. Si dichiara quando vale raggiunto (media delle ultime 5, o una volta) ed "
        "entro quando. Il grafico dice da dove parti: un obiettivo irraggiungibile si vede "
        "prima di salvarlo. Massimo tre. La costanza può appoggiarsi alle quest che esistono già.",
    ),
    (
        "dopo",
        "CreaModulo.dc.html",
        "Crea, modifica, duplica",
        E.crea_form,
        P,
        1640,
        "gray",
        "UN MODULO SOLO  (#168 #252 #253)\nCreare, modificare e duplicare sono lo stesso modulo, "
        "precompilato. Abilità come pastiglie (fino a tre), livello 1–5, «come si registra» "
        "con le due modalità nuove. Dal catalogo «Kata» di Ronin: famiglia e passo (stop shot "
        "1·2·3), la bianca che si rimette o resta, le varianti (dx/sx, A/B). Oggi la modifica "
        "apre il modulo vuoto e chiede di ricaricare la foto.",
    ),
    (
        "dopo",
        "CreaCopia.dc.html",
        "Ha già delle prove",
        E.crea_copia,
        P,
        PH,
        "gray",
        "HA GIÀ DELLE PROVE  (#252)\nLa domanda scatta solo se cambia il significato dei "
        "punteggi (massimo, tipo, istruzioni), non per un refuso nel titolo. La copia è la "
        "scelta proposta; «modifica comunque» resta, e dice quante prove tocca.",
    ),
]

PAGES = [
    ("tpa", "1 · Referto TPA", "Referto TPA — la stessa giocata in tre direzioni"),
    ("trovare", "2 · Esercizi: trovare", "Esercizi — qual è la porta d'ingresso"),
    (
        "eseguire",
        "3 · Esercizi: eseguire",
        "Eseguire — cinque momenti, una cornice sola",
    ),
    ("dopo", "4 · Andamento e creazione", "Dopo la prova, e prima: andamento e modulo"),
]

BOARDS += EXTRA_BOARDS
PAGES += EXTRA_PAGES

BOARDS += [
    (
        "decisioni",
        "Decisioni.dc.html",
        "Le decisioni",
        DEC.presunte,
        DEC.W,
        DEC.H_PRESUNTE,
        "green",
        "CONGELATE IL 19/09\nVenti decisioni, tutte confermate. La colonna di destra resta come "
        "memoria di cosa si è scartato e perché. Stanno anche in PIANO.md, fra le prese.",
    ),
    (
        "decisioni",
        "DecisioniAperte.dc.html",
        "Le tre domande: risposte",
        DEC.aperte,
        DEC.W,
        DEC.H_APERTE,
        "orange",
        "QUESTE SERVONO A TE\nLe voci dei due vocabolari, la regola della soglia, e i corsi — "
        "con quello che la verifica nel codice ha trovato: le statistiche ci sono, i corsi no.",
    ),
]
PAGES += [
    ("decisioni", "8 · Decisioni", "Decisioni — cosa do per fatto, e cosa ti chiedo")
]


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    boards, order, notes = {}, [], {}
    x_by_page = {}
    for page, fname, title, fn, w, h, color, sticky in BOARDS:
        x = x_by_page.get(page, 0)
        (ROOT / fname).write_text(doc(title, fn(), w, h), encoding="utf-8")
        boards[fname] = {"x": x, "y": 0, "w": w, "h": h, "title": title, "page": page}
        order.append(fname)
        nid = "n-" + fname.split(".")[0]
        notes[nid] = {
            "x": x,
            "y": -340,
            "w": max(w if w < 600 else 560, 390),
            "maxH": 300,
            "text": sticky,
            "color": color,
            "page": page,
            "size": "s",
        }
        x_by_page[page] = x + w + GAP
    for pid, _name, heading in PAGES:
        notes["t-" + pid] = {
            "x": 0,
            "y": -640,
            "text": heading,
            "kind": "title1",
            "maxW": x_by_page[pid] - GAP,
            "page": pid,
        }
    index = {
        "v": 3,
        "createdOnFiles": {"v": 1, "at": "2026-09-19T08:15:53Z"},
        "title": "TPA ed esercizi",
        "launch": {"view": "canvas", "page": "tpa"},
        "pages": [{"id": pid, "name": name} for pid, name, _ in PAGES],
        "boards": boards,
        "order": order,
        "notes": notes,
        "designSystems": [],
    }
    (ROOT / "canvas.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(len(order), "artboard scritti in", ROOT)


if __name__ == "__main__":
    main()
