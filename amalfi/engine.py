# amalfi/engine.py - Core algoritmi Sistema Amalfi

from models import db, Match, Prova, Inscription, User, PlayerEncounter, RoundClassification, TrioMatch
import random
from typing import List, Tuple, Optional, Dict


class AmalfiEngine:
    """Engine principale per gestione abbinamenti Sistema Amalfi"""
    
    def __init__(self, prova: Prova):
        self.prova = prova
        self.tournament = prova.tournament
    
    def create_round_matches(self, round_number: int) -> List[Match]:
        """
        Crea abbinamenti per un turno specifico secondo algoritmo Amalfi
        
        Args:
            round_number: Numero del turno (1, 2, 3...)
            
        Returns:
            Lista dei match creati
        """
        if round_number == 1:
            return self._create_first_round()
        else:
            return self._create_amalfi_round(round_number)
    
    def _create_first_round(self) -> List[Match]:
        """Primo turno: sorteggio casuale"""
        inscriptions = Inscription.query.filter_by(prova_id=self.prova.id).all()
        
        if len(inscriptions) < self.prova.min_participants:
            raise ValueError(f"Servono almeno {self.prova.min_participants} iscritti")
        
        # Sorteggio casuale
        random.shuffle(inscriptions)
        
        # Assegna ordine iniziale
        for i, inscription in enumerate(inscriptions, 1):
            inscription.initial_order = i
        
        # Crea abbinamenti primo turno (logica esistente adattata)
        matches = self._create_first_round_matches(inscriptions)
        
        # Registra incontri per anti-reincontro
        for match in matches:
            if not match.is_bye:
                PlayerEncounter.record_encounter(
                    match.player1_id, match.player2_id, 
                    self.prova.id, 1
                )
        
        return matches
    
    def _create_first_round_matches(self, inscriptions: List) -> List[Match]:
        """Crea abbinamenti primo turno (logica esistente adattata)"""
        players = [insc.user for insc in inscriptions]
        matches = []
        
        if len(players) % 2 == 1:
            # Numero dispari: ultimo giocatore ha un bye
            bye_player = players[-1]
            
            # Usa la nuova logica per il punteggio bye
            if self.prova.best_of:
                bye_score = self.prova.get_winning_score()
            else:
                bye_score = self.prova.distance
                
            match = Match(
                prova_id=self.prova.id,
                round_number=1,
                player1_id=bye_player.id,
                is_bye=True,
                player1_score=bye_score,
                winner_id=bye_player.id,
                status='completed',
                amalfi_round=1
            )
            matches.append(match)
            players = players[:-1]
        
        # Crea abbinamenti per giocatori pari
        for i in range(0, len(players), 2):
            match = Match(
                prova_id=self.prova.id,
                round_number=1,
                player1_id=players[i].id,
                player2_id=players[i+1].id,
                amalfi_round=1
            )
            matches.append(match)
        
        db.session.add_all(matches)
        return matches
    
    def _create_amalfi_round(self, round_number: int) -> List[Match]:
        """Turni 2+: algoritmo Amalfi con formula salto"""
        
        # 1. Calcola classifica turno precedente
        classification = RoundClassification.calculate_classification_after_round(
            self.prova.id, round_number - 1
        )
        
        # 2. Calcola salto secondo formula Amalfi
        salto = self.prova.rounds_count - round_number
        
        # 3. Crea abbinamenti con algoritmo Amalfi
        matches = self._apply_amalfi_algorithm(classification, round_number, salto)
        
        # 4. Registra incontri
        for match in matches:
            if not match.is_bye and not match.is_trio:
                PlayerEncounter.record_encounter(
                    match.player1_id, match.player2_id,
                    self.prova.id, round_number
                )
            elif match.is_trio:
                # Registra tutte le combinazioni del trio
                trio = match.trio_match
                PlayerEncounter.record_encounter(
                    trio.player1_id, trio.player2_id, 
                    self.prova.id, round_number
                )
                PlayerEncounter.record_encounter(
                    trio.player1_id, trio.player3_id,
                    self.prova.id, round_number
                )
                PlayerEncounter.record_encounter(
                    trio.player2_id, trio.player3_id,
                    self.prova.id, round_number
                )
        
        return matches
    
    def _apply_amalfi_algorithm(self, classification: List[RoundClassification], 
                               round_number: int, salto: int) -> List[Match]:
        """Applica algoritmo Amalfi per abbinamenti"""
        
        matched_players = set()
        matches = []
        
        print(f"🎯 AMALFI R{round_number}: Salto={salto}, Players={len(classification)}")
        
        for current_player_class in classification:
            if current_player_class.user_id in matched_players:
                continue
            
            print(f"🔍 Abbino {current_player_class.position}° {current_player_class.user.username}")
            
            # Trova target applicando salto
            target_class = self._find_amalfi_target(
                current_player_class, classification, matched_players, salto
            )
            
            if target_class:
                # Abbinamento trovato
                match = Match(
                    prova_id=self.prova.id,
                    round_number=round_number,
                    player1_id=current_player_class.user_id,
                    player2_id=target_class.user_id,
                    amalfi_round=round_number,
                    salto_applied=salto
                )
                
                db.session.add(match)
                matches.append(match)
                matched_players.add(current_player_class.user_id)
                matched_players.add(target_class.user_id)
                
                print(f"✅ Abbinato: {current_player_class.user.username} vs {target_class.user.username}")
            
            else:
                print(f"❌ Nessun target valido per {current_player_class.user.username}")
        
        # Gestisci giocatore rimasto (se dispari)
        unmatched = [c for c in classification if c.user_id not in matched_players]
        if unmatched:
            self._handle_unmatched_player(unmatched[0], matches, round_number)
        
        return matches
    
    def _find_amalfi_target(self, current_class: RoundClassification, 
                           classification: List[RoundClassification],
                           matched_players: set, salto: int) -> Optional[RoundClassification]:
        """Trova target per abbinamento secondo algoritmo Amalfi"""
        
        players_count = len(classification)
        current_position = current_class.position
        
        # Calcola posizione target iniziale
        target_position = current_position + salto
        attempts = 0
        max_attempts = players_count * 2  # Massimo 2 giri completi
        
        while attempts < max_attempts:
            # Wrap around se supera il numero di giocatori
            if target_position > players_count:
                target_position = target_position - players_count
            
            # Trova giocatore in questa posizione
            target_class = next(
                (c for c in classification if c.position == target_position), 
                None
            )
            
            if target_class and self._is_valid_pairing(
                current_class.user_id, target_class.user_id, matched_players
            ):
                return target_class
            
            # Prova posizione successiva
            target_position += 1
            attempts += 1
        
        return None
    
    def _is_valid_pairing(self, player1_id: int, player2_id: int, 
                         matched_players: set) -> bool:
        """Verifica se un abbinamento è valido"""
        
        # 1. Entrambi non devono essere già abbinati
        if player1_id in matched_players or player2_id in matched_players:
            return False
        
        # 2. Non devono aver già giocato insieme (anti-reincontro)
        if PlayerEncounter.have_played_together(player1_id, player2_id, self.prova.id):
            print(f"    ❌ {player1_id} e {player2_id} hanno già giocato insieme")
            return False
        
        # 3. Non devono essere lo stesso giocatore
        if player1_id == player2_id:
            return False
        
        return True
    
    def _handle_unmatched_player(self, unmatched_class: RoundClassification,
                                matches: List[Match], round_number: int):
        """Gestisce giocatore rimasto senza abbinamento"""
        
        if self.tournament.without_x:
            # Modalità "Senza X": converti ultimo match in trio
            if matches:
                last_match = matches[-1]
                self._convert_to_trio(last_match, unmatched_class.user_id)
                print(f"🔄 Convertito in trio: +{unmatched_class.user.username}")
            else:
                raise ValueError("Impossibile creare trio: nessun match disponibile")
        else:
            # Modalità "Con X": controlla se ha già giocato con X
            if self._has_played_with_X(unmatched_class.user_id):
                # Tenta sostituzione
                if not self._attempt_X_substitution(unmatched_class, matches):
                    raise ValueError("Impossibile trovare sostituzione per X")
            else:
                # Crea match vs X
                self._create_X_match(unmatched_class.user_id, round_number)
                print(f"❌ {unmatched_class.user.username} vs X")
    
    def _convert_to_trio(self, match: Match, third_player_id: int):
        """Converte un match normale in trio"""
        match.is_trio = True
        
        trio = TrioMatch(
            match_id=match.id,
            player1_id=match.player1_id,
            player2_id=match.player2_id,
            player3_id=third_player_id,
            current_player1_id=match.player1_id,
            current_player2_id=match.player2_id,
            waiting_player_id=third_player_id
        )
        
        db.session.add(trio)
    
    def _has_played_with_X(self, player_id: int) -> bool:
        """Verifica se il giocatore ha già giocato con X in questa prova"""
        x_matches = Match.query.filter(
            Match.prova_id == self.prova.id,
            Match.is_bye == True,
            Match.player1_id == player_id
        ).first()
        
        return x_matches is not None
    
    def _create_X_match(self, player_id: int, round_number: int):
        """Crea match vs X (bye)"""
        winning_score = self.prova.get_winning_score() if self.prova.best_of else self.prova.distance
        
        match = Match(
            prova_id=self.prova.id,
            round_number=round_number,
            player1_id=player_id,
            is_bye=True,
            player1_score=winning_score,
            winner_id=player_id,
            status='completed',
            amalfi_round=round_number
        )
        
        db.session.add(match)
    
    def _attempt_X_substitution(self, unmatched_class: RoundClassification,
                               matches: List[Match]) -> bool:
        """Tenta sostituzione per evitare secondo X"""
        
        # Logica sostituzione complessa - implementazione base
        # TODO: Implementare logica completa secondo documentazione
        
        for match in reversed(matches):  # Dalla fine
            if match.is_bye or match.is_trio:
                continue
                
            # Prova sostituzioni
            for current_player_id in [match.player1_id, match.player2_id]:
                other_player_id = match.player2_id if current_player_id == match.player1_id else match.player1_id
                
                # Verifica sostituzione valida
                if (not PlayerEncounter.have_played_together(
                        unmatched_class.user_id, current_player_id, self.prova.id) and
                    not self._has_played_with_X(other_player_id)):
                    
                    # Esegui sostituzione
                    if current_player_id == match.player1_id:
                        match.player1_id = unmatched_class.user_id
                    else:
                        match.player2_id = unmatched_class.user_id
                    
                    # Crea X match per l'altro giocatore
                    self._create_X_match(other_player_id, match.round_number)
                    
                    print(f"🔄 Sostituzione: {unmatched_class.user.username} ↔ {current_player_id}")
                    return True
        
        return False
    
    def get_classification_preview(self, round_number: int) -> List[RoundClassification]:
        """Ottieni anteprima classifica per un turno"""
        return RoundClassification.query.filter_by(
            prova_id=self.prova.id,
            round_number=round_number
        ).order_by(RoundClassification.position).all()
    
    def preview_next_round_matches(self, next_round: int) -> List[Dict]:
        """Anteprima abbinamenti prossimo turno senza salvarli"""
        
        if next_round == 1:
            return self._preview_first_round()
        
        # Simula algoritmo senza salvare
        classification = RoundClassification.calculate_classification_after_round(
            self.prova.id, next_round - 1
        )
        
        salto = self.prova.rounds_count - next_round
        matched_players = set()
        preview_matches = []
        
        for current_class in classification:
            if current_class.user_id in matched_players:
                continue
                
            target_class = self._find_amalfi_target(
                current_class, classification, matched_players, salto
            )
            
            if target_class:
                preview_matches.append({
                    'player1': current_class.user,
                    'player2': target_class.user,
                    'type': 'normal',
                    'salto_applied': salto
                })
                matched_players.add(current_class.user_id)
                matched_players.add(target_class.user_id)
        
        # Gestisci eventuale giocatore rimasto
        unmatched = [c for c in classification if c.user_id not in matched_players]
        if unmatched:
            if self.tournament.without_x and preview_matches:
                # Trio
                last_match = preview_matches[-1]
                last_match['type'] = 'trio'
                last_match['player3'] = unmatched[0].user
            else:
                # X match
                preview_matches.append({
                    'player1': unmatched[0].user,
                    'player2': None,
                    'type': 'bye'
                })
        
        return preview_matches
    
    def _preview_first_round(self) -> List[Dict]:
        """Anteprima primo turno"""
        inscriptions = Inscription.query.filter_by(prova_id=self.prova.id).all()
        users = [insc.user for insc in inscriptions]
        
        # Simula sorteggio
        users_copy = users.copy()
        random.shuffle(users_copy)
        
        preview_matches = []
        for i in range(0, len(users_copy), 2):
            if i + 1 < len(users_copy):
                preview_matches.append({
                    'player1': users_copy[i],
                    'player2': users_copy[i + 1],
                    'type': 'normal'
                })
            else:
                # Giocatore dispari
                if self.tournament.without_x and preview_matches:
                    last_match = preview_matches[-1]
                    last_match['type'] = 'trio'
                    last_match['player3'] = users_copy[i]
                else:
                    preview_matches.append({
                        'player1': users_copy[i],
                        'player2': None,
                        'type': 'bye'
                    })
        
        return preview_matches


# Utility functions per integrazione con codice esistente

def create_amalfi_round_matches(prova: Prova, round_number: int) -> List[Match]:
    """Wrapper function per integrazione con routes esistenti"""
    engine = AmalfiEngine(prova)
    return engine.create_round_matches(round_number)


def get_amalfi_classification(prova_id: int, round_number: int) -> List[RoundClassification]:
    """Ottieni classifica Amalfi per un turno"""
    return RoundClassification.query.filter_by(
        prova_id=prova_id,
        round_number=round_number
    ).order_by(RoundClassification.position).all()


def validate_amalfi_configuration(prova: Prova) -> Dict[str, any]:
    """Valida configurazione prova per algoritmo Amalfi"""
    from models import Inscription  # Import qui per evitare circular import
    
    inscriptions = Inscription.query.filter_by(prova_id=prova.id).count()
    
    validation = {
        'is_valid': True,
        'warnings': [],
        'errors': []
    }
    
    # Controlla numero minimo partecipanti
    if inscriptions < prova.min_participants:
        validation['errors'].append(
            f"Servono almeno {prova.min_participants} iscritti (attuali: {inscriptions})"
        )
        validation['is_valid'] = False
    
    # Controlla configurazione turni
    if prova.rounds_count < 2:
        validation['warnings'].append(
            "Con meno di 2 turni l'algoritmo Amalfi ha efficacia limitata"
        )
    
    # Controlla numero partecipanti vs turni
    max_encounters = (inscriptions * (inscriptions - 1)) // 2
    required_encounters = inscriptions * (prova.rounds_count - 1)
    
    if required_encounters > max_encounters:
        validation['errors'].append(
            f"Troppi turni per {inscriptions} giocatori. Massimo consigliato: {max_encounters // inscriptions + 1}"
        )
        validation['is_valid'] = False
    
    return validation