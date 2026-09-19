# Dominio Referto TPA

## A cosa serve

Registrare una partita **visita per visita** invece che rack per rack, e
ricavarne il *Total Performance Average*:

```
TPA = bilie imbucate / (bilie imbucate + errori)
```

È il metodo Accu-Stats, quello usato nel biliardo americano professionistico.
Vive sui match individuali ed è una funzione **da sbloccare** (feature
gamification `tpa_scoresheet`).

Decisioni e alternative scartate: **`docs/adr/ADR-044-tpa-scoresheet.md`**.

---

## Le due metà, che non si toccano

| Modulo | Cosa fa | Cosa NON sa |
|---|---|---|
| `engine.py` | Le regole Accu-Stats. Python puro. | Database, Flask, chi sono i giocatori |
| `models.py` + `services.py` | Persistenza, permessi, ciclo di vita | Come si conta un errore |

Il motore ragiona per **posti** (giocatore 1 = chi spacca il primo rack).
La traduzione posto → utente la fa `TpaReferto.player_number()` /
`user_id_for()`, e sta solo lì.

---

## Riferimento rapido

```python
from models.tpa.services import TpaRefertoService

# Si puo' aprire? (e se no, perche' — frase gia' tradotta)
motivo = TpaRefertoService.blocking_reason(match, user_id)

# Apertura: chi apre diventa il compilatore
referto = TpaRefertoService.open_referto(match_id, user_id)

# Un tocco sul tastierino. Valida contro il motore e restituisce lo stato.
state = TpaRefertoService.press(referto.id, user_id, "3")
state = TpaRefertoService.press(referto.id, user_id, "M")
state = TpaRefertoService.press(referto.id, user_id, "end")   # passa il tavolo

TpaRefertoService.undo(referto.id, user_id)     # annulla l'ultimo comando (l'interfaccia non lo usa piu')
TpaRefertoService.clear_turn(referto.id, user_id)  # «cancella»: via l'annotazione del turno in corso
TpaRefertoService.restart_from_turn(referto.id, user_id, rack, turn)  # «riparti da questo turno…»
TpaRefertoService.close(referto.id, user_id)    # da qui si legge e basta

# Per la pagina: stato + nomi + se chi guarda puo' scrivere
payload = TpaRefertoService.describe(referto, viewer_id=current_user.id)
```

### Il vocabolario dei comandi

Sono le lettere del referto cartaceo, più due comandi che pulsanti non sono.

| Comando | Significato |
|---|---|
| `"0"`..`"10"` | bilie imbucate (sulla spaccata il **primo** numero sono le bilie della spaccata) |
| `"M"` `"K"` `"S"` | perché il turno è finito: miss, kick, difesa |
| `"P"` `"N"` | i falli: battente in buca, bilia designata non colpita |
| `"G"` | con questo turno si vince il rack |
| `"n"` `"x"` `"p"` | le annotazioni piccole: errore non forzato, difesa premeditata, push out |
| `"K-in"` | entrata di sponda alla prima bilia (salva la difesa avversaria) |
| `"runout"` | conferma di un run-out ambiguo |
| `"end"` | tavolo passato all'avversario |
| `"seat:1"` `"seat:2"` | chi spacca questo rack (solo prima di annotare la spaccata) |

### Il TPA di carriera

```python
from models.tpa.stats_service import TpaStatsService

# Va mostrato il TPA nel profilo di questo utente?
TpaStatsService.is_visible_for(user_id, user=user)

# Riassunto per profilo e statistiche: None se qui il TPA non ci va,
# un riassunto vuoto (`tpa: None`) se la funzione e' sbloccata ma non c'e'
# ancora nessun referto.
TpaStatsService.profile_summary(user_id, user=user)

# Tutti i numeri, referto per referto
TpaStatsService.career_stats(user_id)
```

**Il TPA di carriera non e' la media dei TPA di partita.** Si sommano bilie ed
errori di tutti i referti e si divide una volta sola: una partita da quaranta
bilie deve pesare piu' di una da quattro.

**Quando compare.** Due strade: si e' sbloccata la funzione, **oppure**
qualcuno ha gia' tenuto il referto di una tua partita. La seconda e' quella che
conta: il dato esiste e ti riguarda, e nasconderlo perche' non hai ancora
sbloccato il pulsante per compilarlo sarebbe assurdo.

---

## Le cinque famiglie di errore

| Errore | Quando |
|---|---|
| **miss** | vede la bilia, prova a imbucare, sbaglia. **Due** errori se il tiro era più facile di un tiro dal dischetto (la piccola `n`) |
| **break** | battente in buca o fuori sulla spaccata |
| **kick** | tiro di sponda obbligato che finisce in fallo |
| **safety** | gioca difesa e l'avversario poi imbuca, o sbaglia un tiro facile. Il kick-in alla prima bilia la salva |
| **position** | battente in buca fuori da kick e spaccata, **oppure** bilie imbucate senza chiudere il rack (salvo `n` o `x`) |

---

## Chi guarda vede cambiare

Ogni scrittura annuncia sul canale del match (`emit_individual_match_event`)
due eventi diversi, perche' servono a due pagine diverse:

| Evento | Quando | Chi lo ascolta | Cosa fa |
|---|---|---|---|
| `tpa_updated` | a **ogni** tocco | la pagina del referto | rilegge `/tpa/state` e **ridisegna** |
| `rack_updated` | solo se il punteggio si e' mosso | la pagina del match | si **ricarica** |

La distinzione non e' un dettaglio. Chi guarda il referto sta seguendo una
partita: una pagina che si ricarica da sola ogni pochi secondi gli fa perdere
il segno. E mandare `rack_updated` a ogni tocco vorrebbe dire ricaricare la
pagina dell'avversario venti volte per rack.

L'annuncio sta nelle **route**, non nel servizio: e' la convenzione del resto
del dominio (`routes/individual_match/matches.py`).

---

## Do Not

- **Non salvare una posizione nel referto** (cursore, «turno che sto guardando»).
  Rileggere e' una vista del browser; l'unico gesto che scrive e'
  `restart_from_turn`, dopo una conferma. Con una posizione salvata, scorrere
  indietro sposterebbe il punteggio della partita (ADR-044, emendamento).

- **Non calcolare il TPA fuori da `engine.py`.** Le regole stanno lì e solo lì.
- **Non salvare totali** (TPA, errori, rack) su colonna: si ricavano rigiocando
  il registro dei comandi. Un totale salvato diverge al primo annulla.
- **Non applicare un comando senza validarlo** contro `state.available_buttons()`:
  è quello che impedisce a un client fuori sincrono di sporcare il referto.
- **Non fare polling a orologio dalla pagina.** C'e' `window.Polling` sul
  canale del match: si rilegge quando e' successo qualcosa, non ogni N secondi.
- **Non rimettere `@feature_required` sulle route di lettura o di scrittura.**
  Sta solo su `tpa_open`: prendere un referto è la funzione da sbloccare,
  leggerne uno che ti riguarda no, e il compilatore non va chiuso fuori da un
  referto a metà se le regole cambiano a partita in corso.
- **Non far segnare i rack a mano** su un match con referto aperto: il punteggio
  discende dal referto (`_sync_match_score`), e due segnapunti si
  contraddicono. Il template del match nasconde il segnapunti normale.
- **Non aprire un referto a rack già segnati**: partirebbe da 0-0 e dovrebbe
  cancellare rack veri. Da cui il secondo punto d'ingresso: l'avvio rapido
  porta dritti al segnapunti, quindi la finestra per prendere il referto sarebbe
  larga un tocco — il modulo lo chiede prima (spunta `tpa_referto`, aperta da
  `routes/individual_match/quick.py`, **fuori** dalla transazione di
  `QuickMatchService.start`: sono due `@transactional` diversi). Se lì il
  referto non si può aprire — disciplina non coperta, match a set — la partita
  parte lo stesso, senza.
- **Non allineare le regole al PDF Accu-Stats** senza migrare i referti
  esistenti: le tre divergenze note sono volute e fissate da un test.

---

## Come si verifica

```bash
pytest tests/new/unit/test_tpa_engine.py -v          # la sessione d'esempio ufficiale
pytest tests/new/unit/test_tpa_engine_corpus.py -v   # 600 partite contro l'app JS
pytest tests/new/integration/test_tpa_referto.py -n 4
cd tests/frontend && node test_tpa_referto.cjs        # la pagina: static/js/tpa-referto.js
```

Il JavaScript della pagina sta in `static/js/tpa-referto.js` e **non conosce le
regole**: disegna lo stato che riceve e rimanda ogni tocco al server. Indirizzi
e testi tradotti li legge dai `data-*` di `#tpaReferto`, lo stato iniziale dal
blocco `#tpaStato`. La suite frontend **non gira in CI**: dopo aver toccato quel
file va lanciata a mano.

Il corpus (`tests/new/fixtures/tpa_js_reference_corpus.json.gz`) è una
**fotografia del comportamento dell'app JS di riferimento**: non si rigenera
perché un test si è rotto, si rigenera solo se cambia quell'app. Un test rotto
lì significa che il motore Python ha cambiato idea su una regola.

---

## Rimandi

- `models/individual_match/CLAUDE.md` — il match su cui il referto vive
- `models/gamification/CLAUDE.md` — il gate che lo sblocca
- `docs/adr/ADR-044-tpa-scoresheet.md` — le decisioni
