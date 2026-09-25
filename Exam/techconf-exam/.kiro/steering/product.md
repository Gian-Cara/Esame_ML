# TechConf — Product Overview

## Dominio

TechConf è una piattaforma a microservizi per la gestione di conferenze tecnologiche (cloud, AI, security). Permette di registrare utenti, creare eventi, gestire iscrizioni, raccogliere feedback e inviare notifiche.

## Servizi

| Servizio | Porta | Tipo | Scopo |
|---|---|---|---|
| user-service | 5001 | Obbligatorio | Anagrafica utenti (attendee, speaker, organizer) |
| event-service | 5002 | Obbligatorio | Conferenze con ciclo di vita (draft→published→cancelled) e capienza |
| registration-service | 5003 | Obbligatorio | Iscrizioni degli utenti agli eventi pubblicati |
| feedback-service | 5004 | Opzionale | Valutazioni degli eventi da parte degli iscritti |
| notification-service | 5005 | Opzionale | Notifiche singole e broadcast agli iscritti di un evento |

## Dipendenze tra servizi

- **event-service** chiama user-service per validare l'organizzatore
- **registration-service** chiama user-service ed event-service per validare utente ed evento
- **feedback-service** chiama registration-service ed event-service
- **notification-service** chiama user-service e registration-service

## Regole di dominio principali

- Un utente con `role = organizer` può creare eventi
- Un utente può iscriversi solo a eventi con `status = published`
- Un utente non può avere due iscrizioni `confirmed` allo stesso evento
- Il numero di iscrizioni `confirmed` non può superare la `capacity` dell'evento
- Solo un utente con iscrizione `confirmed` può lasciare feedback
- Il `broadcast` crea notifiche solo per gli iscritti `confirmed`
