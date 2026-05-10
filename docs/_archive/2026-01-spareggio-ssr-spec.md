# Specifiche: Spareggio (Spot Shot Rally)

## Problema
Quando una gara termina, possono esserci parimerito nei primi 3 posti della classifica. Serve un meccanismo per risolvere questi tie tramite spot shot rally (SSR), con inserimento manuale dei risultati da parte dell'admin/director.

## User Story
Come **admin o director di gara**, voglio **inserire i risultati dello spot shot rally** quando ci sono parimerito nei primi 3 posti, in modo da **determinare la classifica finale ufficiale**.

## Criteri di Accettazione
- [ ] AC1: Cliccando "Termina Gara", se ci sono parimerito nei primi 3 posti, appare un modale per inserire i punteggi SSR
- [ ] AC2: Il modale mostra i giocatori raggruppati per parimerito (es. "Pari merito 1° posto: Mario, Luigi, Paolo")
- [ ] AC3: Solo admin e director della gara possono inserire i risultati SSR
- [ ] AC4: L'input accetta solo numeri interi positivi (>0)
- [ ] AC5: I punteggi SSR all'interno di un gruppo devono essere tutti diversi (validazione)
- [ ] AC6: La gara non può essere terminata finché tutti i parimerito nei primi 3 non sono risolti
- [ ] AC7: La classifica finale ordina per: rack_totali DESC, punti_ssr DESC

## User Journey
1. Admin/Director è sulla pagina dettaglio gara in stato PLAYING
2. Tutti i turni sono completati, clicca "Termina Gara"
3. Sistema verifica se ci sono parimerito nei primi 3 posti della classifica
4. **Se ci sono parimerito**:
   - Appare modale "Risolvi Spareggi"
   - Mostra gruppi di parimerito con campi input per SSR score
   - Admin inserisce i punteggi (interi positivi, tutti diversi nel gruppo)
   - Clicca "Conferma e Termina Gara"
   - Validazione: se punteggi uguali o non validi → errore
   - Se OK → salva punteggi SSR, termina gara
5. **Se NON ci sono parimerito**: termina gara direttamente (comportamento attuale)
6. Gara passa a stato COMPLETED con classifica finale

## Edge Cases Gestiti
| Scenario | Comportamento Atteso |
|----------|---------------------|
| Nessun parimerito nei primi 3 | Termina gara normalmente (nessun modale) |
| Parimerito solo in posizione 4+ | Termina gara normalmente (non serve SSR) |
| Punteggi SSR uguali nel gruppo | Errore: "I punteggi devono essere diversi per risolvere il parimerito" |
| Punteggio SSR = 0 o negativo | Errore: "Inserire un numero intero positivo" |
| Punteggio SSR non numerico | Errore: "Inserire un numero intero positivo" |
| Utente non autorizzato | Non vede il modale, può solo vedere la classifica |
| Più gruppi di parimerito | Modale mostra tutti i gruppi, tutti devono essere risolti |

## Logica di Rilevamento Parimerito

```python
# Pseudo-codice per rilevare parimerito nei primi 3
classifications = sorted(gara.classifications, key=lambda c: -c.rack_totali)

# Raggruppa per rack_totali
groups = {}
for i, c in enumerate(classifications):
    if c.rack_totali not in groups:
        groups[c.rack_totali] = []
    groups[c.rack_totali].append(c)

# Trova gruppi che coinvolgono i primi 3 posti
position = 1
tiebreaker_groups = []
for rack_count in sorted(groups.keys(), reverse=True):
    group = groups[rack_count]
    if position <= 3 and len(group) > 1:
        # Questo gruppo di parimerito coinvolge almeno una posizione <= 3
        tiebreaker_groups.append({
            'position': position,
            'rack_totali': rack_count,
            'players': group
        })
    position += len(group)
    if position > 3:
        break
```

## Impatto Tecnico

### Database
- **Nuovo campo**: `Classification.ssr_score` (Integer, nullable)
- **Migrazione**: Aggiungere colonna `ssr_score` alla tabella `classification`

### Model: Classification
```python
class Classification(db.Model):
    # ... existing fields ...
    ssr_score = db.Column(db.Integer, nullable=True)  # Spot Shot Rally score
```

### Ordinamento Classifica
```python
# Modifica query ordinamento in ClassificationService
order_by(Classification.rack_totali.desc(),
         Classification.ssr_score.desc().nullslast())
```

### Nuovi File/Metodi
1. **`models/competition/spareggio_service.py`** - Logica SSR
   - `detect_tiebreakers(gara_id)` → lista gruppi parimerito
   - `save_ssr_scores(gara_id, scores: dict)` → salva e valida
   - `has_unresolved_tiebreakers(gara_id)` → bool

2. **`routes/admin/competition.py`** - Endpoint
   - Modifica `terminate_gara()` per verificare spareggi
   - Nuovo endpoint `POST /admin/gara/<id>/ssr-scores`

3. **`templates/admin/gara/_spareggio_modal.html`** - Modale UI

### UI Modale (Mockup)
```
┌─────────────────────────────────────────────────┐
│  ⚠️ Risolvi Spareggi                        [X] │
├─────────────────────────────────────────────────┤
│                                                 │
│  Ci sono parimerito da risolvere prima di      │
│  terminare la gara.                             │
│                                                 │
│  ── Pari merito per il 1° posto (15 rack) ──   │
│  Mario Rossi:    [___] punti SSR               │
│  Luigi Bianchi:  [___] punti SSR               │
│                                                 │
│  ── Pari merito per il 3° posto (12 rack) ──   │
│  Paolo Verdi:    [___] punti SSR               │
│  Anna Neri:      [___] punti SSR               │
│                                                 │
│  ℹ️ Inserire il punteggio finale dello spot    │
│     shot rally. Punteggi più alti = posizione  │
│     migliore.                                   │
│                                                 │
├─────────────────────────────────────────────────┤
│           [Annulla]  [Conferma e Termina Gara] │
└─────────────────────────────────────────────────┘
```

## Domande Risolte
- ✅ Solo primi 3 posti richiedono spareggio
- ✅ Input manuale libero (intero positivo)
- ✅ Ordinamento: rack_totali DESC, ssr_score DESC
- ✅ Punteggi devono essere diversi nel gruppo (validazione)
- ✅ Blocking: gara non può terminare con spareggi non risolti
