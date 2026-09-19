#!/usr/bin/env python3
"""Pagina 8 del canvas: le decisioni. Una riga per decisione presunta, con
cosa cambia se si sceglie diversamente; poi le tre domande ancora aperte e
quello che la verifica nel codice del 19/09 ha trovato."""

import kit

W = 1280

# (sigla, area, decisione, presunta, se scegli diversamente)
PRESUNTE = [
    (
        "D1",
        "TPA",
        "Quale direzione per il referto",
        "<b>B · Tavolo</b>: schermata a fuoco, tutto il tastierino sotto il pollice.",
        "A scorre per arrivare ai comandi; C su telefono lascia una riga di referto. Cambia solo la PR 2b.",
    ),
    (
        "D2",
        "TPA",
        "La parola sotto ogni lettera del tastierino",
        "<b>Sì, spegnibile</b> dalle impostazioni del referto.",
        "Senza: tasti più ariosi, ma chi non conosce Accu-Stats non sa cosa vuol dire K o N.",
    ),
    (
        "D16",
        "TPA",
        "Ripartire da un turno del passato",
        "<b>Passo esplicito</b> «Riparti da questo turno…» con foglio di conferma che nomina i turni tolti — come l'originale.",
        "Troncatura implicita al primo tasto: un gesto in meno, ma un tocco per sbaglio mentre si rilegge butta via dei turni.",
    ),
    (
        "D3",
        "Esercizi",
        "La porta d'ingresso",
        "<span class='dec__tu'>DECISA DA TE</span> <b>B · «Oggi» subito.</b> Nasce in fase 4 con ciò che c'è — riprendi l'ultimo esercizio, i preferiti, i più provati, il catalogo dietro — e si riempie da sola: la scheda in fase 6, obiettivi e consigli in fase 7.",
        "—",
    ),
    (
        "D4",
        "Esercizi",
        "I vocabolari abilità e gesto",
        "<b>Fissi di piattaforma</b>; famiglia e passo liberi dell'autore. <span class='dec__tu'>DA TE</span> i radar sono <b>due</b>, uno per asse.",
        "Estendibili da una scuola: radar e consigli non sono più confrontabili fra giocatori, serve una mappatura.",
    ),
    (
        "D5",
        "Esercizi",
        "Il livello",
        "<b>1–5 dichiarato</b> da chi crea, con quello <b>misurato</b> accanto quando ci sono abbastanza prove (#174).",
        "Tre fasce a parole: più facile da dichiarare, meno fine per i consigli.",
    ),
    (
        "D6",
        "Esercizi",
        "Il voto",
        "<b>Vota solo chi ha provato</b>, scala 1–5; nei consigli non entra subito.",
        "Voto aperto a tutti: più numeri, meno significato.",
    ),
    (
        "D9",
        "Esercizi",
        "«Giocare contro il ghost»",
        "<b>Esercizio a punteggio</b> («vinte su N»), nessun tipo suo.",
        "Tipo dedicato: un modello e una schermata in più per un caso solo.",
    ),
    (
        "D7",
        "Schede",
        "La seduta",
        "<b>Entità con inizio e fine</b>, che sopravvive alla chiusura dell'app.",
        "Lista da spuntare: lavoro piccolo, ma niente ripresa, niente durata, niente registro affidabile.",
    ),
    (
        "D8",
        "Schede",
        "Il passaggio di livello",
        "<b>Opzione a tre valori</b> della scheda: nessuno · automatico alla soglia · conferma dell'istruttore.",
        "Solo automatico: l'istruttore esce dal percorso dell'allievo.",
    ),
    (
        "D17",
        "Schede",
        "Cosa somma la soglia",
        "<b>Solo le voci «a riusciti»</b>; le altre (partite, minuti, fatto) si vedono ma restano fuori dal conto.",
        "Obbligo di voci omogenee quando la soglia è accesa: torna la «scheda a caselle» che hai scartato.",
    ),
    (
        "D10",
        "Istruttori",
        "Il ruolo, e dove si chiede",
        "<b><code>RoleGrant INSTRUCTOR</code></b>, distinto da <code>EXAMINER</code> (ADR-041). Si chiede dal <b>profilo</b>, come «Diventa esaminatore»; la scuola è un testo facoltativo.",
        "Riuso di EXAMINER: chi esamina vedrebbe allievi, chi insegna potrebbe certificare. Permessi confusi.",
    ),
    (
        "D18",
        "Istruttori",
        "Dopo che il giocatore gli apre una scheda",
        "<b>Vale subito</b>: l'istruttore riceve una notifica e può togliersi da quella scheda.",
        "Accettazione dell'istruttore: un passaggio in più e uno stato «in attesa» da gestire.",
    ),
    (
        "D11",
        "Istruttori",
        "Il legame, e cosa resta quando finisce",
        "<span class='dec__tu'>DECISA DA TE</span> Il legame è <b>allievo–scheda–istruttore</b>: ogni scheda ha i suoi n lettori, aggiunti e tolti dal giocatore. Tolto da una scheda, l'istruttore di quella non vede più niente di nuovo; nei gruppi chiusi resta chi c'era.",
        "—",
    ),
    (
        "D19",
        "Schede",
        "Quanto farne",
        "<span class='dec__tu'>DECISA DA TE</span> <b>Niente serie × ripetizioni</b>: una voce è un numero di tiri, di partite o di minuti.",
        "—",
    ),
    (
        "D20",
        "TPA",
        "La notazione",
        "<span class='dec__tu'>DECISA DA TE</span> TPA da <b>0 a 1000</b>, senza punto; le bilie in spaccata come <b>apice</b>; il triangolo vinto è un <b>cerchio</b>, non una G; il primo tiro di calcio è il <b>numero del giocatore cerchiato in piccolo, sopra</b> l'annotazione; il fallo sta nella casella ombreggiata.",
        "—",
    ),
    (
        "D12",
        "Istruttori",
        "I corsi",
        "<b>Gruppo</b> = nome + periodo + allievi + scheda, creato dall'istruttore, con storico. Niente lezioni né programma.",
        "Corsi con lezioni e programma: una funzione intera che oggi non ha né issue né una riga di codice.",
    ),
    (
        "D13",
        "Disegnatore",
        "Il lessico",
        "<b>Pannello ai token 7c</b>, tavolo scuro.",
        "Resta scuro-giallo: meno lavoro nella 9a, ma resta un corpo estraneo nell'app.",
    ),
    (
        "D14",
        "Disegnatore",
        "I bersagli",
        "<b>Dato strutturato</b>: centro, raggio, valore per anello; misure in <b>quarti di diamante</b>.",
        "Solo disegno: il colpo per colpo (#183) non può calcolare i punti.",
    ),
    (
        "D15",
        "Piano",
        "L'ordine di lavoro",
        "Quello di <code>PIANO.md</code>: TPA → esami → modello dell'esercizio → eseguire → schede → andamento → istruttori → disegnatore.",
        "Il disegnatore è indipendente: si può anticipare dopo la fase 4.",
    ),
]

CSS = """
.dec{width:%dpx;box-sizing:border-box;background:var(--c7-bg);color:var(--c7-ink);
  font-family:var(--c7-font);padding:48px 56px 56px;display:block}
.dec h1{font-size:34px;font-weight:800;letter-spacing:-.03em;margin:0}
.dec .lead{font-size:15px;line-height:1.5;color:var(--c7-ink-soft);max-width:860px;margin:10px 0 28px}
.dtab{display:grid;grid-template-columns:64px 104px 1fr 1.25fr 1.25fr;background:var(--c7-card);
  border-radius:var(--c7-r-card);overflow:hidden}
.dtab > div{padding:14px 16px;border-bottom:1px solid var(--c7-line-soft);font-size:13.5px;line-height:1.45}
.dtab .th{background:var(--c7-ink);color:#fff;font-size:10.5px;font-weight:800;letter-spacing:.08em;
  text-transform:uppercase;border:0}
.dtab .id{font-family:var(--c7-font-mono);font-weight:800}
.dtab .ar{font-size:11px;font-weight:800;letter-spacing:.04em;text-transform:uppercase;color:var(--c7-ink-muted)}
.dtab .q{font-weight:800}
.dtab .alt{color:var(--c7-ink-soft)}
.dtab code,.qa code{font-family:var(--c7-font-mono);font-size:12px;background:var(--c7-sunken);
  padding:1px 5px;border-radius:5px}
.qa{display:grid;grid-template-columns:1fr 1fr;gap:20px}
.qa section{background:var(--c7-card);border-radius:var(--c7-r-card);padding:22px 24px}
.qa h2{font-size:19px;font-weight:800;letter-spacing:-.02em;margin:0 0 4px}
.qa .k{font-size:10.5px;font-weight:800;letter-spacing:.08em;text-transform:uppercase;color:var(--c7-ink-muted)}
.qa p,.qa li{font-size:13.5px;line-height:1.5;color:var(--c7-ink-soft)}
.qa ul{margin:8px 0 0;padding-left:18px}
.qa .rec{margin-top:12px;padding:12px 14px;border-radius:var(--c7-r-control);background:var(--c7-ok-bg);
  color:var(--c7-ok-ink);font-size:13px;font-weight:700;line-height:1.45}
.voc{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}
.voc span{height:28px;padding:0 12px;border-radius:999px;display:inline-flex;align-items:center;
  font-size:12px;font-weight:800;background:var(--c7-accent-tint);color:var(--c7-accent-tint-ink)}
.voc.g span{background:transparent;box-shadow:inset 0 0 0 1.5px var(--c7-line);color:var(--c7-ink-soft)}
.dec__tu{display:inline-block;font-size:9.5px;font-weight:800;letter-spacing:.06em;padding:2px 7px;border-radius:999px;
  background:var(--c7-ok-bg);color:var(--c7-ok-ink);margin-right:4px;vertical-align:1px}
.ok{display:inline-block;font-size:10px;font-weight:800;letter-spacing:.06em;padding:3px 9px;border-radius:999px;
  background:var(--c7-ok-bg);color:var(--c7-ok-ink);margin-left:8px;vertical-align:3px}
.yes{color:var(--c7-ok-ink);font-weight:800}.no{color:var(--c7-err-ink);font-weight:800}
""" % W


kit.CSS += CSS  # nel <helmet>, come tutto il resto: niente <style> nel corpo


def _shell(h, inner):
    # `app` e `dcontent` servono solo a measure.py, che cerca quei due nomi
    return (
        f'<div class="app dec" style="width: {W}px; height: {h}px;">'
        f'<div class="dcontent" style="padding:0">{inner}</div></div>'
    )


H_PRESUNTE = 1960
H_APERTE = 1062


def presunte():
    rows = (
        '<div class="th">#</div><div class="th">Area</div><div class="th">La decisione</div>'
        '<div class="th">Decisione</div>'
        '<div class="th">Se scegli diversamente</div>'
    )
    for sig, area, q, pres, alt in PRESUNTE:
        rows += (
            f'<div class="id">{sig}</div><div class="ar">{area}</div><div class="q">{q}</div>'
            f'<div>{pres}</div><div class="alt">{alt}</div>'
        )
    inner = f"""
<h1>Le decisioni &mdash; congelate il 19/09/2026</h1>
<p class="lead">Venti scelte, tutte confermate: quelle col bollino verde le hai decise tu nei commenti, le altre valgono perch&eacute; non le hai
commentate (&laquo;se non ho commentato significa che &egrave; ok&raquo;). Da qui in poi cambiano solo con una nota datata in PIANO.md.</p>
<div class="dtab">{rows}</div>"""
    return _shell(H_PRESUNTE, inner)


def aperte():
    ab = "".join(
        f"<span>{v}</span>"
        for v in [
            "Fondamentali",
            "Tiro",
            "Battente",
            "Posizione",
            "Sponde",
            "Difesa",
            "Spaccata",
        ]
    )
    ge = "".join(
        f"<span>{v}</span>"
        for v in [
            "stop",
            "stun",
            "follow",
            "draw",
            "spin",
            "forza",
            "bank",
            "kick",
            "jump",
            "mass&eacute;",
        ]
    )
    inner = f"""
<h1>Le tre domande: risposte</h1>
<p class="lead">Hai corretto i vocabolari a mano (&laquo;Spaccata&raquo;, &laquo;spin&raquo;) e detto ok alle altre due. Restano qui come promemoria di cosa &egrave; stato deciso.</p>
<div class="qa">
  <section>
    <div class="k">Domanda 1 &middot; D4</div>
    <h2>Le voci dei due vocabolari<span class='ok'>CORRETTE DA TE</span></h2>
    <p><b>Abilit&agrave;</b> &mdash; cosa alleni. Sette voci, le stesse che vedi nel catalogo e nel modulo; il radar delle abilit&agrave; ne usa sei (i fondamentali non hanno una percentuale sensata); il gesto ha il suo radar.</p>
    <div class="voc">{ab}</div>
    <p style="margin-top:14px"><b>Gesto</b> &mdash; come colpisci. &Egrave; l&rsquo;asse di Bullseye, allargato.</p>
    <div class="voc g">{ge}</div>
    <div class="rec">Un esercizio ha zero, una o pi&ugrave; voci su ciascun asse.       Gli esercizi che esistono gi&agrave; restano senza voci finch&eacute; l&rsquo;autore non le mette.</div>
  </section>
  <section>
    <div class="k">Domanda 2 &middot; vale solo se D8 non &egrave; &laquo;nessuno&raquo;</div>
    <h2>La soglia: basta raggiungerla una volta?<span class='ok'>OK</span></h2>
    <p>Sul foglio cartaceo non c&rsquo;&egrave; scritto. Una seduta fortunata a 48 su 60 non &egrave; &laquo;essere da livello 4&raquo;;
      pretendere tre sedute di fila pu&ograve; scoraggiare.</p>
    <div class="rec">Proposta: &egrave; un numero sulla scheda &mdash; &laquo;sedute di fila sopra la soglia&raquo; &mdash; con <b>1</b> per
      default (come la carta). Chi scrive la scheda lo alza se vuole.</div>
  </section>
  <section style="grid-column:1 / -1">
    <div class="k">Domanda 3 &middot; D12 &mdash; verificato nel codice il 19/09</div>
    <h2>Corsi e statistiche: cosa c&rsquo;&egrave; gi&agrave; davvero<span class='ok'>OK AI GRUPPI</span></h2>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:28px;margin-top:6px">
      <div>
        <p><span class="no">Non esiste</span> &mdash; nemmeno un abbozzo:</p>
        <ul>
          <li><b>Corsi, lezioni, programmi</b>: nessun modello, tabella, route o template; non sono citati neanche in SPECIFICHE o ROADMAP.</li>
          <li><b>Ruolo istruttore</b>: <code>GrantableRole</code> ha solo <code>EXAMINER</code> e <code>BETA_TESTER</code>.</li>
          <li><b>Legame fra un utente e chi lo segue</b>: nessuno (n&eacute; amici, n&eacute; follow).</li>
          <li><b>Schede, sedute, obiettivi del giocatore</b>: niente; la sessione di allenamento &egrave; dichiarata &laquo;solo navigazione&raquo;.</li>
          <li><b>Categoria, livello, tag sull&rsquo;esercizio</b>: <code>Challenge</code> ha 11 colonne, nessuna di queste.</li>
        </ul>
      </div>
      <div>
        <p><span class="yes">Esiste e funziona</span>:</p>
        <ul>
          <li><b>Storico d&rsquo;allenamento</b> per giocatore (<code>TrainingHistoryService</code>): prove, record, esami.</li>
          <li><b>Andamento su un esercizio</b> a punteggio, con tendenza (<code>get_drill_trend</code>, <code>trend_chart</code>).</li>
          <li><b>Statistiche di un esercizio</b> su tutti i giocatori &mdash; ma solo per i direttori.</li>
          <li><b>Visibilit&agrave; a terzi</b>: un interruttore solo, <code>show_challenge_stats</code>, spento per default: tutto o niente, a chiunque.
            Il permesso &laquo;a questo istruttore, questa scheda&raquo; &egrave; nuovo.</li>
          <li>Il meccanismo <code>RoleGrant</code> che ospiterebbe il ruolo (senza <i>scope</i>: il legame con l&rsquo;allievo &egrave; una tabella a parte).</li>
        </ul>
      </div>
    </div>
    <div class="rec">Quindi le statistiche ci sono e si riusano; i corsi no. Proposta (D12): il <b>gruppo</b> dell&rsquo;istruttore &mdash; nome,
      periodo, allievi, scheda &mdash; con lo storico dei gruppi chiusi. Lezioni, programma e valutazioni d&rsquo;ingresso restano fuori. I gruppi entrano nel piano, fase 8.</div>
  </section>
</div>"""
    return _shell(H_APERTE, inner)
