# 🎱 Sistema Amalfi - Logica Abbinamenti Completa

> **Documentazione tecnica** per lo sviluppo del sistema di abbinamenti automatici nei tornei di biliardo secondo il protocollo Amalfi.

## 📋 Panoramica Sistema

Il **Sistema Amalfi** è un protocollo di abbinamenti automatici per tornei di biliardo che garantisce:
- Equità degli abbinamenti basata su classifica
- Anti-reincontro (evita che giocatori si scontrino più volte)
- Gestione dinamica del numero dispari di partecipanti
- Adattabilità al numero di turni della prova

## 🎯 Terminologia

- **X**: Giocatore virtuale (non "bye") 
- **Senza X**: Modalità che usa trii invece di X
- **Con X**: Modalità che abbina giocatori singoli con X
- **Salto**: Numero di posizioni da saltare negli abbinamenti = `Turni_Totali - Turno_Attuale`
- **Trio**: Partita a 3 giocatori (solo in modalità "Senza X")

## 🎲 Turno 1 - Sorteggio Casuale

### Meccanica
1. **Estrazione casuale** dell'ordine dei giocatori iscritti
2. **Abbinamenti sequenziali**: (1°-2°), (3°-4°), (5°-6°), (7°-8°)...
3. **Gestione dispari**:
   - **Con X**: Ultimo giocatore vs X (vince automaticamente)
   - **Senza X**: Ultimo abbinamento diventa trio

### Esempio
```
Iscritti: mario, pino, gino, lino, rino, mino
Estrazione: mario, pino, gino, lino, rino, mino
Abbinamenti: mario-pino, gino-lino, rino-mino
```

## 📊 Sistema Classifiche

### Criteri Ordinamento
**Priorità gerarchica:**
1. **Partite vinte** (desc)
2. **Differenza rack** = rack_vinti - rack_persi (desc)  
3. **Ordine precedente** (asc)
   - Turno 1: ordine estrazione casuale
   - Turni 2+: posizione classifica turno precedente

### Esempio Classifica Post-Turno 1
```
Estrazione: mario(1°), pino(2°), gino(3°), lino(4°), rino(5°), mino(6°)
Risultati: mario-pino 3-2, gino-lino 4-1, mino-rino 3-2

Classifica Turno 1:
1° gino   (1 vittoria, +3 rack, 3° estratto)
2° mario  (1 vittoria, +1 rack, 1° estratto)
3° mino   (1 vittoria, +1 rack, 6° estratto)  
4° pino   (0 vittorie, -1 rack, 2° estratto)
5° rino   (0 vittorie, -1 rack, 5° estratto)
6° lino   (0 vittorie, -3 rack, 4° estratto)
```

## 🔄 Algoritmo Abbinamenti Turni 2+

### Formula Salto
**`Salto = Turni_Totali - Turno_Attuale`**

Esempi:
- Prova 3 turni, turno 2: `salto = 3-2 = 1`
- Prova 4 turni, turno 2: `salto = 4-2 = 2`  
- Prova 4 turni, turno 3: `salto = 4-3 = 1`

### Algoritmo Dettagliato

```python
def create_amalfi_round_matches(prova, round_number):
    classification = get_classification_after_round(prova.id, round_number-1)
    salto = prova.rounds_count - round_number
    matched_players = set()
    matches = []
    
    for player in classification:
        if player.id in matched_players:
            continue
            
        # Cerca target saltando N posizioni SUCCESSIVE
        target_position = player.position + salto
        attempts = 0
        
        while attempts < len(classification) * 2:  # Max 2 cicli completi
            if target_position > len(classification):
                target_position = 1  # Wrap around
                
            target = classification[target_position - 1]  # -1 per index 0-based
            
            if (target.id not in matched_players and 
                not have_played_together(player.id, target.id, prova.id)):
                # Abbinamento valido
                matches.append(create_match(player, target))
                matched_players.add(player.id)
                matched_players.add(target.id)
                break
                
            target_position += 1
            attempts += 1
            
        if attempts >= len(classification) * 2:
            raise Exception("Impossibile trovare abbinamenti validi")
    
    # Gestisci ultimo giocatore se dispari
    handle_odd_player(classification, matched_players, matches, prova)
```

### Esempio Pratico: 6 Giocatori, 3 Turni

#### Turno 2 (salto = 1)
```
Classifica: gino(1°), mario(2°), mino(3°), pino(4°), rino(5°), lino(6°)

Step 1: gino(1°) → target = 1°+1 = 2° mario
        Ma deve saltare posizioni successive → 3° mino
        ✅ Abbina: gino-mino

Step 2: mario(2°) → target = 2°+1 = 3° mino (già abbinato)
        Scorre → 4° pino → 5° rino (primo disponibile)
        ✅ Abbina: mario-rino

Step 3: pino(4°) → target = 4°+1 = 5° rino (già abbinato)  
        Scorre → 6° lino
        ✅ Abbina: pino-lino

Risultato: gino-mino, mario-rino, pino-lino
```

## 🎮 Gestione Trii (Senza X)

### Meccanica Trio
- **Modalità**: Sempre "al meglio di" (indipendente da `prova.best_of`)
- **Svolgimento**:
  1. Iniziano primi due giocatori del trio
  2. Vincitore continua, perdente viene sostituito dal terzo
  3. Vince chi raggiunge per primo il punteggio "al meglio di"
- **Statistiche**: `differenza_rack = rack_vinti - rack_persi` per ogni giocatore

### Implementazione Database
```python
class TrioMatch(db.Model):
    match_id = db.Column(db.Integer, db.ForeignKey('match.id'))
    player1_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    player2_id = db.Column(db.Integer, db.ForeignKey('user.id')) 
    player3_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    current_player1_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    current_player2_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    waiting_player_id = db.Column(db.Integer, db.ForeignKey('user.id'))
```

## ❌ Gestione X e Sostituzioni

### Abbinamento con X
```python
if ultimo_giocatore_non_abbinato:
    if torneo.without_x:
        # Aggiungi a ultimo abbinamento come trio
        convert_last_match_to_trio(ultimo_giocatore)
    else:
        if not has_played_with_X(ultimo_giocatore, prova.id):
            create_X_match(ultimo_giocatore)
        else:
            # Logica sostituzione complessa
            attempt_substitution_in_previous_matches()
```

### Logica Sostituzione X
Quando ultimo giocatore ha già giocato con X:

1. **Prova ultimo abbinamento**: Se non ha mai giocato con uno dei due E l'altro non ha mai giocato con X → sostituisci
2. **Risali abbinamenti**: Se non va, prova penultimo abbinamento
3. **Continua**: Finché non trova sostituzione valida o esaurisce possibilità

```python
def attempt_X_substitution(remaining_player, existing_matches, prova):
    for match in reversed(existing_matches):  # Dalla fine
        for player in [match.player1, match.player2]:
            other_player = match.player2 if player == match.player1 else match.player1
            
            if (not have_played_together(remaining_player.id, player.id, prova.id) and
                not has_played_with_X(other_player.id, prova.id)):
                # Sostituzione valida
                substitute_player_in_match(match, player, remaining_player)
                create_X_match(other_player)
                return True
    return False
```

## 🚫 Sistema Anti-Reincontro

### Tracking Incontri
```python
class PlayerEncounter(db.Model):
    player1_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    player2_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    prova_id = db.Column(db.Integer, db.ForeignKey('prova.id'))
    round_number = db.Column(db.Integer)
    
    __table_args__ = (
        db.UniqueConstraint('player1_id', 'player2_id', 'prova_id', 'round_number'),
    )

def have_played_together(player1_id, player2_id, prova_id):
    return PlayerEncounter.query.filter(
        db.or_(
            db.and_(PlayerEncounter.player1_id == player1_id, 
                   PlayerEncounter.player2_id == player2_id),
            db.and_(PlayerEncounter.player1_id == player2_id, 
                   PlayerEncounter.player2_id == player1_id)
        ),
        PlayerEncounter.prova_id == prova_id
    ).first() is not None
```

## 📈 Casi Limite e Gestione Errori

### Situazioni Problematiche
1. **Tutti hanno già giocato insieme**: Impossibile in configurazione corretta
2. **Loop infinito abbinamenti**: Max 2 cicli completi della classifica
3. **Sostituzione X impossibile**: Errore configurazione torneo

### Validazioni Pre-Turno
```python
def validate_round_feasibility(prova, round_number):
    players_count = len(get_active_inscriptions(prova.id))
    max_encounters = calculate_max_encounters(players_count, round_number-1)
    
    if max_encounters > theoretical_limit:
        raise InfeasibleRoundError("Troppi giocatori per il numero di turni")
```

## 🔧 Implementazione Tecnica

### Nuove Route Admin
```python
@admin_bp.route('/prova/<int:prova_id>/start_round/<int:round_number>')
def start_round(prova_id, round_number)

@admin_bp.route('/prova/<int:prova_id>/classification/<int:round_number>')  
def view_classification(prova_id, round_number)

@admin_bp.route('/prova/<int:prova_id>/preview_round/<int:round_number>')
def preview_next_round(prova_id, round_number)
```

### Aggiornamenti Models
```python
# In models.py - aggiungi nuovi campi
class Prova(db.Model):
    # ... campi esistenti ...
    current_classification = db.relationship('Classification', backref='prova')

class Match(db.Model):
    # ... campi esistenti ...
    is_trio = db.Column(db.Boolean, default=False)
    trio_players = db.relationship('TrioMatch', backref='match')
```

### Utility Functions
```python
def calculate_classification_after_round(prova_id, round_number)
def create_amalfi_round_matches(prova, round_number)  
def handle_trio_match_logic(match_id)
def get_player_encounters_in_prova(prova_id)
def validate_amalfi_configuration(prova)
```

---

## 🎯 Esempi Completi

### Scenario A: 8 Giocatori, 4 Turni, Con X
```
Turno 1: Sorteggio casuale
Turno 2: Salto = 4-2 = 2 → (1°-4°), (2°-5°), (3°-6°), (7°-8°)
Turno 3: Salto = 4-3 = 1 → (1°-3°), (2°-4°), (5°-7°), (6°-8°)  
Turno 4: Salto = 4-4 = 0 → (1°-2°), (3°-4°), (5°-6°), (7°-8°)
```

### Scenario B: 7 Giocatori, 3 Turni, Senza X  
```
Turno 1: 3 coppie + 1 giocatore → ultimo abbinamento diventa trio
Turno 2: Salto = 3-2 = 1 → abbinamenti con gestione trio
Turno 3: Salto = 3-3 = 0 → abbinamenti finali
```

---

## ⚠️ Note Implementazione

1. **Performance**: Ottimizza query per tornei con molti partecipanti
2. **Concorrenza**: Gestisci accesso simultaneo agli abbinamenti  
3. **Backup**: Salva stato prima di ogni turno per rollback
4. **Logging**: Traccia decisioni algoritmo per debug
5. **Testing**: Crea suite test per tutti i casi limite

---

*Documentazione aggiornata: 27 luglio 2025*  
*Versione Sistema: Amalfi v1.0*