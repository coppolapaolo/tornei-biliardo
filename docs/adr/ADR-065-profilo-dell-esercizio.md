# ADR-065 Il profilo dell'esercizio: due vocabolari fissi, livello dichiarato, varianti, voto

**Data**: 2026-09-19
**Stato**: Accepted
**Decisori**: Paolo Coppola

## Contesto

`Challenge` diceva **come si valuta** una prova — a punteggio o superato/non
superato, con o senza tetto — e niente su **che cosa allena** né su **quanto è
difficile**. Il catalogo era un elenco piatto: chi cercava «qualcosa sul
controllo della battente» leggeva le descrizioni una per una. La issue #168 lo
chiama il prerequisito di quasi tutto il resto: scheda di allenamento (#172),
istruttori (#173), difficoltà misurata (#174), consigli (#175), radar (#181)
presuppongono tutti queste informazioni.

Le scelte di prodotto le ha prese l'utente sul canvas «TPA ed esercizi» il
19/09/2026 (decisioni D4, D5, D6 e i commenti sui vocabolari); qui si fissa come
diventano schema.

## Decisione

### 1. Due vocabolari fissi di piattaforma, nel codice

Un esercizio si descrive su **due assi indipendenti**, con zero, una o più voci
di ciascuno:

| asse | risponde a | voci |
|---|---|---|
| **abilità** | che cosa si allena | Fondamentali, Tiro, Battente, Posizione, Sponde, Difesa, Spaccata |
| **gesto** | con quale colpo | stop, stun, follow, draw, spin, forza, bank, kick, jump, massé |

Sono due e non una lista sola perché lo stesso draw serve a un esercizio di
posizione e a uno di difesa; i radar dell'andamento saranno due, uno per asse.
«Esordienti» non è una voce: è un livello.

I vocabolari sono **enum** (`models/challenge/vocabulary.py`), come
`Discipline`: il valore va su disco, il nome mostrato passa da gettext. Una
tabella `abilita` in DB avrebbe voluto colonne di traduzione e un seed da
eseguire in produzione, per un elenco che la piattaforma cambia una volta
l'anno con una PR.

Al più **tre abilità** per esercizio (`MAX_ABILITA`): un esercizio che allena
tutto non dice niente a chi filtra. I gesti non hanno tetto — sono un fatto,
non una scelta di cosa mettere in evidenza.

### 2. Una tabella di associazione sola, `challenge_category`

`(challenge_id, axis, value)`, unica sui tre. Una tabella per i due assi perché
hanno la stessa forma e la stessa vita: due tabelle gemelle sarebbero due posti
da tenere allineati. `axis` e `value` sono colonne **`String`**, non `db.Enum`:
senza `values_callable` SQLAlchemy salverebbe il *nome* del membro, e ogni
rinomina diventerebbe una migrazione dei dati (incidente del 2026-08-17).

`Challenge.abilita` e `Challenge.gesti` restituiscono i membri **nell'ordine
del vocabolario**; una riga con un valore che l'enum non conosce più si salta,
così togliere una voce non fa esplodere il catalogo.

### 3. Livello **dichiarato**, 1–5, facoltativo

La colonna si chiama `declared_level`, non «difficoltà», di proposito: la #174
gli metterà accanto il livello *misurato* dai risultati, e due numeri con lo
stesso nome in lettura non si distinguono più.

### 4. Famiglia e passo, liberi dell'autore

`family` (testo) e `family_step` (intero): «stop shot» 1 · 2 · 3. Liberi, a
differenza dei vocabolari, perché le progressioni le inventa chi insegna. Un
passo senza famiglia si rifiuta.

### 5. La bianca

`cue_ball_reset`: `True` si rimette a ogni tiro, `False` resta dove si ferma.
Cambia che cosa misura il punteggio, quindi è un fatto dell'esercizio e non una
frase nelle istruzioni.

### 6. Le varianti sono etichette, mai un secondo esercizio

`challenge_variant (challenge_id, label, position)` e
`challenge_attempt.variant_id`. Destra e sinistra condividono disegno,
istruzioni, profilo e voto; le prove si registrano separate perché il 9 su 10 di
destra e il 4 su 10 di sinistra sono la notizia, non la loro media. Le etichette
sono N e libere.

* **Rinominare** tiene le prove (si passa l'`id`).
* **Togliere** una variante che ha prove si rifiuta (`ConflictError`): la chiave
  è `SET NULL`, i numeri resterebbero e non si saprebbe più di che lato erano.
* La variante è **facoltativa anche quando c'è**: chi non la dice registra una
  prova generica, e non gli si inventa un lato.
* `record_attempt` rifiuta la variante di un altro esercizio **prima** di creare
  la riga: la chiave esterna sarebbe soddisfatta e l'errore invisibile.

### 7. Voto e «quanti l'hanno provato»

`challenge_rating (challenge_id, user_id, rating)`, unico per giocatore ed
esercizio, con `CHECK rating BETWEEN 1 AND 5` anche nello schema. L'unicità sta
nello schema e non in un `if` perché `UserMergeService` decide dallo schema come
spostare le righe quando due account si fondono.

«Quanti l'hanno provato» **non si salva**: si conta, da
`models/challenge/popularity.py`, su chi ha almeno una prova *completata* dal
catalogo o in gara — le stesse due fonti dello storico d'allenamento. La stessa
funzione (`has_tried`) dirà chi può votare (D6): un contatore che dice «14
giocatori» e un voto rifiutato a uno di quei quattordici è un difetto che nessun
test di un lato solo vede. `popularity_for` risponde per tutti gli esercizi di
una pagina con tre query.

Gli esami restano fuori dal conto: una prova d'esame è una valutazione davanti
a un esaminatore, non un allenamento.

### 8. Il profilo si scrive da un servizio suo

`ChallengeProfileService.set_profile`, distinto da
`ChallengeService.update_challenge`: quello cambia come si valuta la prova — e
per questo il modulo chiede se farne una copia quando ci sono già risultati
(#252) — questo cambia come la prova **si trova**, e non deve far scattare
nessuna domanda. Ogni argomento ha per default `UNSET`: non inviato e vuoto sono
cose diverse.

`copy_profile` porta il profilo su una copia — quella automatica della
disattivazione (#267) e, dalla PR successiva, «Duplica» (#253). Prove e voti
non si copiano.

### 9. Nessun backfill

Gli esercizi esistenti restano senza categoria e senza livello finché l'autore
non glieli dà. «Non lo so» e un valore messo d'ufficio sono cose diverse, e il
catalogo filtrerebbe il secondo come vero.

## Alternative scartate

* **Vocabolari in tabella**, modificabili da un admin: traduzioni e seed in
  produzione per un elenco quasi immobile; e un vocabolario che cresce a
  piacere smette di essere un filtro.
* **Una colonna `category` singola**: le due app di riferimento della #168
  mostrano due o tre etichette sullo stesso esercizio.
* **Varianti come esercizi distinti legati fra loro**: due disegni, due testi e
  due voti da tenere allineati, e «Duplica» esiste già per chi vuole davvero due
  esercizi.
* **Contatore dei giocatori salvato** sulla riga dell'esercizio: andrebbe
  tenuto allineato a ogni prova registrata e cancellata, in due tabelle.

## Conseguenze

* Migration `20260919_profilo_esercizio.py`, idempotente, con `created_at` e
  `updated_at`; `test_esercizio_profilo_migration.py` la **esegue** e confronta
  le colonne con quelle dei modelli.
* Le regole numeriche (tre abilità, livello 1–5, voto 1–5) stanno in
  `SPECIFICHE.md` e in `test_specifiche_conformita.py`.
* Le relazioni `categories` e `variants` sono `selectin`: il catalogo mostra le
  etichette di decine di esercizi senza una query per card.
* Le schermate arrivano dopo: modulo (#252, #253), «Oggi» e catalogo che si
  filtra, voto.
