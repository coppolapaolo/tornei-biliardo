#!/usr/bin/env python3
"""Pagine 5-7 del canvas: schede di allenamento, esami, disegnatore."""

import disegnatore as D
import esami as X
import schede as S

P, PH = 390, 844

EXTRA_BOARDS = [
    (
        "schede",
        "SchedeElenco.dc.html",
        "1 · Le tue schede",
        S.elenco,
        P,
        PH,
        "orange",
        "LE TUE SCHEDE · nuovo (#172)\nUna scheda è una scheda: niente più «da palestra» o «a "
        "caselle». Le pastiglie dicono solo ciò che QUELLA scheda ha acceso — un livello, una "
        "soglia, dei giorni — e di chi è. La prima la legge un istruttore.",
    ),
    (
        "schede",
        "SchedaComponi.dc.html",
        "2 · Comporre",
        S.componi,
        P,
        1264,
        "green",
        "COMPORRE — UNA FORMA SOLA\nOgni voce ha il SUO «quanto farne», libero: 10 tiri, 5 + 5 dx "
        "e sx, 30 tiri, 5 partite. Niente «serie × ripetizioni»: è un concetto da palestra, non "
        "da biliardo (tuo commento). LIVELLO e SOGLIA sono interruttori, accanto a giorni e "
        "durata. La soglia somma solo le voci «a riusciti» (qui 60 tiri).",
    ),
    (
        "schede",
        "SchedaVoce.dc.html",
        "3 · Quanto farne",
        S.voce_sheet,
        P,
        PH,
        "green",
        "QUANTO FARNE — SENZA SERIE (tuo commento)\nUna voce è: come si segna (fatto · riusciti · "
        "punteggio · vinte · minuti), QUANTI — tiri, partite o minuti — e le varianti. Un numero "
        "solo. Le differenze fra una scuola e l'altra stanno qui, nella voce.",
    ),
    (
        "schede",
        "SchedaInCorso.dc.html",
        "4 · La seduta · una voce con varianti",
        S.in_corso,
        P,
        PH,
        "orange",
        "LA SEDUTA — VOCE «A RIUSCITI» CON DX E SX\nUn tocco su 0–5 e il tocco salva: come la "
        "cifra scritta sulla carta. Il totale corre sotto, contro la soglia, perché questa "
        "scheda la soglia ce l'ha accesa. La seduta è un'entità con inizio e fine (D7).",
    ),
    (
        "schede",
        "SedutaPalestra.dc.html",
        "5 · La stessa seduta · una voce lunga",
        S.seduta_serie,
        P,
        PH,
        "orange",
        "LA STESSA SEDUTA, LA VOCE DOPO\nTrenta tiri non si ricordano a memoria: si contano uno "
        "alla volta, riuscito o sbagliato, e la striscia cresce. Chi preferisce scrive il totale "
        "alla fine. L'input lo decide la VOCE, non la scheda.",
    ),
    (
        "schede",
        "SchedaRegistro.dc.html",
        "6 · Il registro",
        S.il_registro,
        P,
        PH,
        "orange",
        "IL REGISTRO\nLe sedute e, voce per voce, le ultime tre: è qui che si vede «a sinistra "
        "fai meno». Il totale c'è perché la soglia è accesa; le voci non a riusciti si vedono "
        "ma restano fuori dal conto. La griglia stampabile del foglio può tornare come vista "
        "in più quando tutte le voci sono a riusciti.",
    ),
    (
        "schede",
        "SchedaFine.dc.html",
        "7 · Fine seduta",
        S.fine,
        P,
        PH,
        "orange",
        "FINE SEDUTA\nOggi contro l'ultima volta, voce per voce. Il passaggio di livello è "
        "un'OPZIONE della scheda (D8): nessuno · automatico alla soglia · conferma "
        "dell'istruttore. Qui è disegnata la terza.",
    ),
    (
        "schede",
        "SchedaLettori.dc.html",
        "8 · Chi la legge",
        S.lettori,
        P,
        PH,
        "green",
        "IL LEGAME È ALLIEVO–SCHEDA–ISTRUTTORE (tuo commento su D11)\nNon esiste «Luca mi "
        "segue»: esiste «questa scheda la legge Luca». Ogni scheda ha i suoi lettori, n "
        "istruttori diversi, aggiunti e tolti dal giocatore. Nel modello è UNA tabella "
        "(scheda, istruttore, da quando, fino a quando) e nient'altro.",
    ),
    (
        "schede",
        "IstruttoreConsenso.dc.html",
        "9 · Chi legge le mie schede",
        S.miei_istruttori,
        P,
        PH,
        "orange",
        "UNA VISTA, NON UN LEGAME\nIl riepilogo di chi legge cosa, ricavato dalle schede. Un "
        "istruttore compare perché gli hai aperto almeno una scheda. L'andamento generale NON "
        "si condivide: fuori da una scheda l'istruttore non vede niente.",
    ),
    (
        "schede",
        "IstruttoreAggiungi.dc.html",
        "10 · Aprire una scheda a un istruttore",
        S.aggiungi_istruttore,
        P,
        PH,
        "orange",
        "APRIRE\nSi parte dalla scheda. Si cerca per nome fra chi ha il ruolo di istruttore — "
        "la scuola accanto al nome aiuta a non sbagliare persona — e si conferma. Vale subito "
        "(D18): l'istruttore riceve una notifica nella SUA lingua (ADR-062).",
    ),
    (
        "schede",
        "IstruttoreDiventa.dc.html",
        "11 · Diventare istruttore",
        S.diventa_istruttore,
        P,
        860,
        "green",
        "DOVE SI CONFIGURA L'ISTRUTTORE (tua domanda)\nNel profilo, sezione Ruoli: lo stesso "
        "percorso di «Diventa esaminatore» che esiste già (`RoleRequest` → approvazione → "
        "`RoleGrant`, ADR-041). La scuola o associazione è un testo facoltativo della richiesta, "
        "mostrato accanto al nome. PROPOSTA: testo libero, non un'anagrafica delle associazioni.",
    ),
    (
        "schede",
        "IstruttoreAllievi.dc.html",
        "12 · I miei allievi",
        S.allievi,
        P,
        PH,
        "orange",
        "I MIEI ALLIEVI, PER GRUPPO · nuovo (#173, D12)\nL'istruttore organizza gli allievi in "
        "GRUPPI con un nome e un periodo («Base 1 · autunno 2026»). Chi gli apre una scheda compare in "
        "cima, da sistemare. VERIFICATO NEL CODICE: corsi, lezioni, programmi NON esistono — "
        "zero modelli, zero tabelle. Esistono invece lo storico e l'andamento per esercizio.",
    ),
    (
        "schede",
        "IstruttoreGruppo.dc.html",
        "13 · Un gruppo, e lo storico",
        S.gruppo,
        P,
        880,
        "orange",
        "LO STORICO CORSO PER CORSO · nuovo (D12)\nUn gruppo chiuso resta com'era: chi c'era, "
        "com'è andata. È il modo in cui l'istruttore ritrova «il Base 1 della primavera scorsa». "
        "PROPOSTA: gruppo = nome + periodo + allievi + scheda; niente lezioni né programma.",
    ),
    (
        "esami",
        "EsamiCatalogo.dc.html",
        "1 · Gli esami",
        X.catalogo,
        P,
        PH,
        "gray",
        "GLI ESAMI\nOggi è un elenco di nomi. Qui ogni esame dice cosa sei tu per lui — "
        "superato e da chi, provato da solo, mai provato — e l'appuntamento più vicino sta in "
        "cima. Chi somministra trova le richieste che aspettano lui. Tutti dati che esistono.",
    ),
    (
        "esami",
        "EsameDettaglio.dc.html",
        "2 · Un esame",
        X.dettaglio,
        P,
        908,
        "gray",
        "UN ESAME\nGli esercizi numerati nell'ordine in cui si fanno. «Le tue volte» al posto "
        "delle quattro statistiche globali, che oggi mostrano quasi sempre zero. I due comandi "
        "in fondo sono quelli di oggi.",
    ),
    (
        "esami",
        "EsameAppuntamento.dc.html",
        "3 · L'appuntamento",
        X.appuntamento,
        P,
        916,
        "gray",
        "L'APPUNTAMENTO\nLa proposta sul tavolo e il suo «Accetto» stanno nella stessa card: "
        "oggi la proposta è in cima e il pulsante in fondo, sotto la nav. Date leggibili "
        "(«sab 26 set») al posto di 26/09/2026. La trattativa è una linea del tempo.",
    ),
    (
        "esami",
        "EsameSessione.dc.html",
        "4 · La sessione",
        X.sessione,
        P,
        PH,
        "gray",
        "LA SESSIONE DELL'ESAMINATORE\nUn esercizio alla volta, stessa cornice e stessa "
        "striscia della scheda di allenamento. Oggi il punteggio compare due volte (la cifra e "
        "il campo) e si scrive in un input numerico. NUOVO: «Rinuncia alla terza» non esiste.",
    ),
    (
        "esami",
        "EsameChiusura.dc.html",
        "5 · L'esito",
        X.chiusura,
        P,
        PH,
        "gray",
        "L'ESITO\nIl riepilogo prima della decisione, poi i due bersagli grandi. ADR-042 non "
        "si tocca: esito netto, deciso dall'esaminatore, nessun voto.",
    ),
    (
        "esami",
        "EsameComponi.dc.html",
        "6 · Comporre un esame",
        X.componi,
        P,
        954,
        "gray",
        "COMPORRE UN ESAME\nLo stesso modulo della scheda. Oggi per aggiungere un esercizio si "
        "scrive il suo ID numerico a mano, il riordino ha la route ma nessun comando, e peso e "
        "prove non si cambiano più dopo. «Vale» e «prove» sono i due campi di ExamChallenge.",
    ),
    (
        "disegnatore",
        "DisegnatoreDesktop.dc.html",
        "Desktop",
        D.d_desktop,
        1440,
        900,
        "orange",
        "IL DISEGNATORE (#179)\nTavolo al centro, strumenti in colonna, proprietà dell'oggetto "
        "selezionato a destra. I quattro col puntino sono nuovi: Bersaglio, Posizioni, "
        "Richiamo, Marcatore. Sul tavolo la notazione di Billiard University: riquadri in "
        "diamanti (vuoti, pieno, ruotato), numeri fuori sponda, donut, richiamo legato al "
        "punto. Passa dal lessico scuro-giallo del tool ai token 7c: è una scelta (D13). "
        "RECEPITO: largo, alto e raggio dei bersagli vanno a passi da ¼ di diamante, come la "
        "griglia (qui 2½ × 1¼).",
    ),
    (
        "disegnatore",
        "DisegnatoreMobile.dc.html",
        "Telefono",
        D.d_mobile,
        P,
        PH,
        "orange",
        "SU TELEFONO\nOggi gli strumenti occupano tutto lo schermo e il tavolo finisce sotto "
        "«Salva». Qui il tavolo resta sempre in vista, gli strumenti sono una striscia e sotto "
        "c'è solo ciò che serve all'oggetto selezionato.",
    ),
    (
        "disegnatore",
        "DisegnatoreCerchi.dc.html",
        "I cerchi: il bersaglio come dato",
        D.d_cerchi,
        P,
        860,
        "orange",
        "IL BERSAGLIO COME DATO (#179 → #183, D14)\nI cerchi hanno centro, raggio e un valore per "
        "anello: è ciò che rende calcolabile «Posizione» nel colpo per colpo. Le misure sono in "
        "QUARTI di diamante (raggio 1½). Gli anelli si chiamano per VALORE, non per colore: il "
        "colore non è nel dato, ed è così che il colpo per colpo smette di somigliare a Bullseye.",
    ),
    (
        "disegnatore",
        "DisegnatoreInquadratura.dc.html",
        "L'inquadratura",
        D.d_inquadratura,
        P,
        PH,
        "green",
        "COME SI FA L'IMMAGINE DI UN SOLO PEZZO (tua domanda)\nSi disegna sempre sul tavolo "
        "intero. L'inquadratura è una cornice: tre preset (mezzo tavolo, un angolo, intero) o "
        "libera, trascinata dalle maniglie e agganciata ai diamanti. Decide solo cosa finisce "
        "nell'immagine: nel dato è un rettangolo in quarti di diamante accanto alla scena.",
    ),
    (
        "disegnatore",
        "DisegnatoreVarianti.dc.html",
        "Dal foglio di Ronin",
        D.d_varianti,
        P,
        PH,
        "orange",
        "DAL FOGLIO DI RONIN · nuovo\nTre cose che i diagrammi della scheda usano e il "
        "disegnatore non sa fare: la variante specchiata (dx/sx da un disegno solo), "
        "l'inquadratura su mezzo tavolo o su un angolo, e il bersaglio come tratto di sponda "
        "evidenziato (esercizio 1, linea tangente). Non erano nella #179.",
    ),
]

EXTRA_PAGES = [
    (
        "schede",
        "5 · Schede di allenamento",
        "Schede — una forma sola; e chi ti segue lo scegli tu",
    ),
    ("esami", "6 · Esami", "Esami — la stessa sequenza, davanti a un esaminatore"),
    ("disegnatore", "7 · Disegnatore", "Disegnatore — la notazione che manca"),
]
