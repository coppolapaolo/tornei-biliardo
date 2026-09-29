# Regolamento di gara: modifiche tracciate invece che impedite

Specifica nata dall'intervista del 2026-09-29, a partire dalla issue #549 e
dal caso della finale dei playoff che, nata già con gli iscritti, non si
poteva più modificare (né la sala né chi spacca).

## Problema

Oggi una gara diventa immodificabile appena ha **un** iscritto
(`Gara.can_be_modified()`), e la configurazione dei playoff appena partono gli
inviti. Il direttore resta senza strumenti proprio quando servono: una gara da
rimandare perché mancano iscritti, una sala che cambia, la finale dei playoff
che nasce già con gli iscritti. D'altra parte, una modifica fatta in silenzio
a gara in corso è una fonte di contestazioni.

La scelta è di **non impedire, ma tracciare**: la modifica si fa e resta
scritta, visibile a tutti, con chi, quando, cosa e perché.

## User story

Come **direttore** voglio poter correggere le impostazioni di una gara, di un
campionato o dei playoff anche con iscritti e a gara in corso, in modo da
gestire gli imprevisti della serata.

Come **giocatore** voglio vedere le regole in vigore e ogni loro modifica, in
modo da sapere con che regole ho giocato e avere su cosa basare un'eventuale
contestazione.

## Ambito

Gara (tutti i formati: Amalfi, casuale, girone all'italiana, eliminazione
diretta, doppio KO, FISBB), campionato, configurazione dei playoff.

## Il turno, in generale

Una modifica alle regole di gioco vale per i **turni non ancora cominciati**.
Un turno è **cominciato** quando almeno una sua partita è partita; da quel
momento **tutte** le sue partite, anche quelle non ancora iniziate, si giocano
con le regole che aveva all'inizio. Dentro un turno le regole non si mescolano
mai.

Il turno lo definisce il formato:

| Formato | Turno |
|---|---|
| Amalfi, casuale, girone all'italiana | numero di turno |
| Tabellone (eliminazione diretta, doppio KO) | lato + turno interno (`bracket_type`, `bracket_round`, ADR-038) |
| FISBB | come il tabellone, più il girone (`bracket_group`) |

Nel doppio KO più turni si giocano in parallelo: la modifica si accetta
sempre, e vale per quelli fra loro che non sono ancora cominciati.

Quando un turno comincia, le sue regole effettive — con la loro provenienza —
si **fissano sul turno** e non si ricalcolano più a ogni lettura (stesso
schema di `break_player_id`, ADR-056).

## Le tre fasce di campi

| Fascia | Esempi | Quando si modifica | Cosa succede |
|---|---|---|---|
| **Logistica** | sala, data, ora, tavoli, quota, nome | sempre, fino alla fine della gara | registro + avviso agli iscritti |
| **Regole di gioco** | distanza, disciplina, chi spacca, chi apre, prova della X | sempre; vale per i turni non cominciati | registro + avviso |
| **Struttura** | strategia di abbinamento, sistema di classifica, numero di turni, capienza; per i playoff posti e criteri | liberamente fino al sorteggio | dopo il sorteggio: vedi sotto |

**Struttura dopo il sorteggio.** Si cambia solo con il gesto esplicito
**«Annulla il sorteggio e rifallo»**, possibile finché nessuna partita è
cominciata; il gesto va nel registro e gli iscritti ricevono l'avviso. Due
eccezioni che non passano dal gesto, perché non toccano le partite già
generate:

- **aggiungere turni** a un Amalfi in corso;
- **alzare la capienza** a iscrizioni ancora aperte.

## Ereditarietà: campionato e playoff

- Una modifica al campionato o alla configurazione dei playoff vale per le
  gare che **ereditano** quel campo, e solo per i loro turni non cominciati.
  Le gare concluse e i turni già cominciati tengono la regola fissata.
- Una gara che ha **scelto esplicitamente** il proprio valore non cambia: la
  scelta esplicita vince sul predefinito.
- La modifica compare **anche nel registro di ogni gara colpita**, con la
  provenienza: «Chi spacca: alternato → vincitore · *modificato nel
  campionato* da …».
- Prima di salvare, il direttore vede l'elenco delle gare colpite e da quale
  turno: «Vale per: gara 7 (dal turno 3), gare 8–10. Non vale per: gare 1–6,
  concluse».

## Registro

- Ogni **salvataggio** è una voce, con le sue righe campo per campo (prima →
  dopo). Il registro non si accorpa mai, neanche per i passaggi che si
  annullano (sala A → B → A resta due voci).
- Ogni voce porta: quando, **nome e ruolo** di chi ha modificato (direttore,
  co-direttore, amministratore), provenienza (gara, campionato, playoff),
  motivo.
- Il **motivo è facoltativo**, sempre. Il campo sta in evidenza nel form, con
  un suggerimento («Scrivi perché: servirà in caso di contestazioni»).
- Le voci non si cancellano e non si correggono: si può solo aggiungere una
  nota successiva, anch'essa datata e firmata.
- I valori si salvano grezzi (`lag`, `alternate`, …) e si traducono in
  lettura, nella lingua di chi legge (ADR-062).
- Nessun backfill: per le modifiche avvenute prima dell'introduzione non c'è
  registro, e la pagina lo dice.

## Avvisi accorpati

Il registro è la verità; la **comunicazione** si accorpa.

- La prima modifica apre un **avviso in attesa** per quella gara (o campionato);
  le successive ci confluiscono.
- L'avviso confronta lo stato di partenza con quello attuale, non i passaggi:
  A → B → C diventa «A → C»; A → B → A svuota l'avviso, che non parte.
- L'avviso parte:
  - dopo **30 minuti di quiete** dall'ultima modifica (in produzione
    il controllo è orario: tempo effettivo 30–90 minuti);
  - **subito** se il direttore preme «Invia ora» nel banner «N modifiche non
    ancora comunicate»;
  - **subito** se la gara comincia entro poche ore (soglia proposta: 3).
- I testi si compongono per destinatario, nella sua lingua e nel suo fuso
  (ADR-043, ADR-062).

## Riconferma

Scatta solo per ciò che può cambiare la decisione di esserci:

| Modifica | Riconferma |
|---|---|
| data o ora spostate oltre una soglia (proposta: 1 ora) | sì |
| sala | sì |
| quota in aumento | sì |
| regole di gioco, formato | no, solo avviso |
| nome, tavoli, quota in diminuzione, piccoli spostamenti d'orario | no, solo registro |

- Su ogni iscrizione si salva la **versione confermata** dei campi che contano
  (data, ora, sala, quota). La riconferma serve se e solo se i valori attuali
  ne differiscono oltre soglia: più modifiche prima della risposta danno **una
  sola** richiesta; se si torna al valore accettato, la richiesta sparisce.
- Chi non riconferma resta iscritto **«da riconfermare»**: nessun ritiro
  automatico. Il direttore lo vede evidenziato e decide, al più tardi al
  sorteggio.
- Il **direttore può riconfermare al posto del giocatore** (per esempio per chi
  l'ha detto a voce); l'azione va nel registro con il suo nome.
- Vale anche per chi ha **accettato l'invito ai playoff**. Per il campionato non
  c'è riconferma: solo registro e avviso.
- Lo stato di riconferma è **visibile come le iscrizioni**.

## Regolamento di gara (vista pubblica)

Visibile a **tutti**, dalla pagina della gara.

1. **In vigore**: ogni impostazione con la provenienza («Chi spacca: alternato ·
   dal campionato»).
2. **Per turno**, solo se ci sono differenze fra turni, con i nomi del formato
   («Quarti vincenti: al 5 · Semifinali e finale: al 7 dal 29/09 ore 21:40»).
3. **Cronologia**: le voci del registro, dalla più recente; «Annulla il
   sorteggio e rifallo» si distingue a colpo d'occhio.

Sulla pagina del campionato, lo stesso per i predefiniti del campionato e la
configurazione dei playoff.

## Criteri di accettazione

- [ ] La finale dei playoff appena creata, con gli iscritti, permette di
      cambiare sala e chi spacca; la modifica compare nel Regolamento di gara.
- [ ] In un tabellone con i quarti cominciati, portare la distanza da 5 a 7
      lascia al 5 **tutti** i quarti (anche quelli non iniziati) e mette al 7
      semifinali e finale.
- [ ] Nel doppio KO, con quarti vincenti e perdenti turno 2 in corso, la
      modifica vale per i turni successivi di entrambi i lati.
- [ ] Cambiare chi spacca nel campionato non cambia le gare concluse, i turni
      cominciati, né le gare con un valore esplicito; compare nel registro di
      ciascuna gara colpita.
- [ ] Sala A → B → C in 10 minuti: registro con due voci, **un** avviso «A → C»,
      **una** richiesta di riconferma.
- [ ] Sala A → B → A: nessun avviso, nessuna riconferma, due voci nel registro.
- [ ] Chi non riconferma resta iscritto e appare «da riconfermare»; il
      direttore può riconfermare per lui, e il registro lo dice.
- [ ] Dopo il sorteggio la strategia non si cambia senza «Annulla il sorteggio
      e rifallo»; si possono invece aggiungere turni a un Amalfi in corso.
- [ ] La promessa del form («gli iscritti ricevono una notifica») è vera.

## Casi limite

| Scenario | Comportamento |
|---|---|
| Due co-direttori modificano insieme | si applicano solo i campi che chi salva ha **cambiato** rispetto a quanto ha caricato; se uno di quei campi nel frattempo l'ha cambiato l'altro, il salvataggio si ferma e lo dice |
| Modifica verso un valore che rende invalida una partita già giocata | impossibile per costruzione: i turni cominciati hanno le regole fissate |
| Data spostata prima della gara precedente del campionato | resta il controllo di sequenza (ADR-016) |
| Gara in corso al momento del rilascio | la migration fissa le regole dei turni già cominciati sui valori effettivi di quel momento |
| Gara conclusa prima del rilascio | idem: le regole si fissano come sono, e il Regolamento dice che non c'è cronologia precedente |
| Competizione di prova (ADR-058) | registro sì, avvisi no |

## Impatto tecnico (prima stima)

- **Nuove entità**: voce del registro con le sue righe (provenienza gara,
  campionato o playoff); avviso in attesa; regole fissate per turno; versione
  confermata sull'iscrizione e sull'accettazione dell'invito ai playoff.
- **Punto unico di scrittura**: `GaraService.update_gara`,
  l'aggiornamento del campionato, `PlayoffService.update_configuration` /
  `update_scoring`. Nessuna route scrive il registro da sé.
- **Lettura delle regole**: `Match.effective_*` / `distance_config` (ADR-027)
  leggono prima le regole fissate sul turno.
- **Da rimuovere**: il blocco di `can_be_modified()` sulle iscrizioni e quello
  di `update_configuration` sulle qualificazioni, sostituiti dalle fasce.
- **Job orario**: l'invio degli avvisi accorpati, accanto a
  `send_match_reminders.py`.
- **Documenti**: ADR nuovo; `SPECIFICHE.md` (le regole di modifica); `/aiuto`
  (skill `help-docs`); traduzioni.

## Domande aperte

- [ ] Soglie: 30 minuti di quiete, 3 ore prima della gara, 1 ora di
      spostamento per la riconferma — da confermare.
- [ ] Nelle gare dentro un campionato, cambiare la **data** con le gare
      successive già fissate: si sposta solo questa (se la sequenza lo
      permette) o si propone di spostare anche le successive?
