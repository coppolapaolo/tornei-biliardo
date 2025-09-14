## Use case 1
- Un admin _(variante: director)_ crea una gara standalone _(variante: all'interno di un campionato)_ con tre turni, strategia amalfi, minimo 6 giocatori, massimo 10, disciplina palla 9 al meglio di 9 _(variante: esattamente 5)_, primo abbinamento casuale, gestione dispari con X, challenge con spot shot rally in caso di parità tra i giocatori nei primi tre posti
- apre le iscrizioni, 
- si iscrivono 8 giocatori _(variante1: 9 giocatori, variante2: 11 giocatori e l'ultimo finisce in lista d'attesa)_,
- chiude le iscrizioni _(variante: scade il termine delle iscrizioni e si chiudono automaticamente)_,
- avvia il primo turno e i giocatori vengono abbinati in modo random, 
- vengono giocati tutti i match del primo turno,
- il sistema calcola la classifica del primo turno secondo l'ordinamento (match vinti, differenza rack, ordine precedente)
- avvia i secondo turno e l'abbinamento rispetta il metodo amalfi, senza rematch
- vengono giocati tutti i match,
- il sistema calcola la classifica del secondo turno
- avvia il terzo turno con abbinamento amalfi senza rematch
- vengono giocati tutti i match, 
- il sistema stila la classifica finale e risultano a pari merito il secondo e il terzo
- il secondo e il terzo disputano la challenge e vince il terzo
- la classifica finale è aggiornata con il risultato della challenge

## Use case 2
- Un admin _(variante: director)_ crea una gara standalone _(variante: all'interno di un campionato)_ con tre turni, strategia random, minimo 6 giocatori, massimo 10, disciplina palla 8 al meglio di 9 _(variante: esattamente 5)_, gestione dispari con X _(variante: con trio)_, challenge con spot shot rally in caso di parità tra i giocatori nei primi tre posti
- aggiunge due challenge dopo il primo turno, due tentativi
- cambia la disciplina del solo terzo turno in palla 9
- apre le iscrizioni, 
- si iscrivono 8 giocatori _(variante1: 9 giocatori, variante2: 11 giocatori e l'ultimo finisce in lista d'attesa)_,
- chiude le iscrizioni _(variante: scade il termine delle iscrizioni e si chiudono automaticamente)_,
- avvia il primo turno e i giocatori vengono abbinati in modo random in tutti e tre i turni, senza rematch, 
- vengono giocati tutti i match del primo turno,
- vengono giocate le challenge dopo il primo turno
- il sistema calcola la classifica del primo turno secondo l'ordinamento (numero rack vinti)
- avvia i secondo turno 
- vengono giocati tutti i match,
- il sistema calcola la classifica del secondo turno
- avvia il terzo turno 
- vengono giocati tutti i match, 
- il sistema stila la classifica finale e risultano a pari merito il secondo, il terzo e il quarto
- il secondo, il terzo e il quarto disputano la challenge dello spot shot rally e vince il secondo
- la classifica finale è aggiornata con il risultato della challenge

## Use case 3
- Un admin _(variante: director)_ crea una gara standalone _(variante: all'interno di un campionato)_, strategia round robin, minimo 6 giocatori, massimo 12, disciplina palla 8 due set al meglio di 5 _(variante: esattamente 5)_, gestione dispari con X
- cambia la disciplina del secondo turno in palla 9
- apre le iscrizioni, 
- si iscrivono 8 giocatori _(variante1: 9 giocatori, variante2: 14 giocatori e gli ultimi due in lista d'attesa)_,
- chiude le iscrizioni,
- avvia il primo turno e i giocatori vengono abbinati, 
- vengono giocati tutti i match,
- il sistema calcola e agigorna la classifica dopo ogni match secondo l'ordinamento (match vinti, differenza rack)

## Use case 4
- Un admin _(variante: director)_ crea un campionato con 3 gare amalfi _(variante: strategia di abbinamento random)_
- crea la prima gara
- apre le iscrizioni
- avvia la gara
- la gara viene giocata dal numero minimo di giocatori
- alla fine della gara viene aggiornata la classifica del campionato
- tutte le altre gare vengono create e giocate e la classifica di campionato si aggiorna di conseguenza

## Use case 5
- un utente guest non loggato vede le informazioni di un campionato in corso
- vede i risultati delle gare finite
- vede in tempo reale i risultati delle partite che si stanno giocando

## Use case 6
- un player _(variante: director)_ invita un altro player a un match individuale
- entrambi inseriscono e validano i punteggi inseriti dall'altro

## Use case 7 
- un player _(variante: direcotor)_ si rende disponibile a giocare in una determinata sala il prossimo lunedi' alle 20 _(variante: ogni mercoledi' alle 21)_
- un altro player vede nella scheda della sala che c'è la disponibilità a giocare e invia una richiesta di match
- un altro player che ha già giocato in quella sala riceve una notifica di disponibilità e invia una richiesta di match

## Use case 8
- in una gara standalone di quattro turni sono appena terminati tutti i match del secondo turno e la classifica è stata aggiornata
- l'admin _(variante: director)_ modifica un match del secondo turno e lo resetta
- la classifica torna a quella del primo turno perche' il secondo turno viene riaperto
- l'admin _(variante: director)_ cambia il risultato del match e lo conclude in modo diverso da prima
- la cassifica del secondo turno viene ricalcolata
- avvia il terzo turno
- non e' piu' possibile modificare i match del primo e del secondo turno
- annulla il terzo turno (perché nessun risultato, nemmeno parziale è stato ancora inserito)
- i pulsanti di modifica per i match del secondo turno compaiono e possono essere usati, mentre quelli del primo turno non compaiono e i match non mossono essere modificati
- resetta tutti i match del secondo turno
- la classifica torna quella del primo turno
- annulla il secondo turno
- i pulsanti per modificare i match del primo turno compaiono
- modifica il risultato di uno dei match del primo turno
- la classifica si modifica di conseguenza