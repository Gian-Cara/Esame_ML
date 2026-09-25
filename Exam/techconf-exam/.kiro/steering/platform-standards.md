# Platform Standards (vincolanti per tutti i servizi)

## Avvio

- Il file `services.yaml` nella root dichiara `cwd` e `command` per ogni servizio
- La suite di collaudo inietta `PORT` e `*_SERVICE_URL` come variabili d'ambiente
- Ogni servizio **deve** leggere la porta da `PORT` (non usare porte hardcoded)
- In collaudo i servizi girano sulle porte **15001–15005** (e 15101+ per resilienza)

## API

- Base path: `/api/v1/<risorsa>`
- Formato: **JSON**, campi in `snake_case`
- Identificativi: `id` UUID v4, generato dal server, **mai** accettato in input
- Timestamp: ISO 8601 UTC — es. `2026-10-15T09:30:00Z`; ogni risorsa ha `created_at` e `updated_at`
- Date: `YYYY-MM-DD`
- Importi: numerici con 2 decimali (`149.00`), valuta implicita EUR

## Paginazione

Query params: `?page=1&page_size=20` (max 100)

Risposta:
```json
{"items": [...], "page": 1, "page_size": 20, "total": 57}
```

## Errori

Sempre questa struttura:
```json
{"error": {"code": "UPPER_SNAKE", "message": "...", "details": {}}}
```

## Status code

| Codice | Quando |
|---|---|
| 201 | Creazione (+ header `Location: /api/v1/<risorsa>/<id>`) |
| 200 | Lettura / modifica |
| 204 | Cancellazione |
| 400 | JSON malformato |
| 404 | `NOT_FOUND` |
| 405 | Metodo non previsto |
| 409 | Conflitto (es. duplicato) |
| 422 | `VALIDATION_ERROR` / `REFERENCE_NOT_FOUND` / regole di business |
| 503 | `DEPENDENCY_UNAVAILABLE` |

## Chiamate tra servizi

- URL letti **esclusivamente** da variabili d'ambiente: `USER_SERVICE_URL`, `EVENT_SERVICE_URL`, `REGISTRATION_SERVICE_URL`, `FEEDBACK_SERVICE_URL`, `NOTIFICATION_SERVICE_URL`
- Default se non impostata: `http://localhost:<porta_sviluppo>`
- Timeout: **2 secondi**
- Se il servizio chiamato risponde 404 → restituire **422** `REFERENCE_NOT_FOUND`
- Se timeout, connessione rifiutata o 5xx → restituire **503** `DEPENDENCY_UNAVAILABLE`

## Health check

```
GET /health → 200 {"status": "ok", "service": "<nome-servizio>"}
```

## Persistenza

- `STORAGE_BACKEND` = `memory` | `json` | `sqlite` (default: `memory`)
- Con `json`/`sqlite` i file vanno in `DATA_DIR` (default `./data`)
- Solo librerie standard: `json`, `sqlite3`
- La logica di business non deve dipendere dal backend scelto

## Dipendenze Python

- Runtime: `flask`, `requests`
- Test: `pytest`, `pytest-cov`, `responses`
