# Bug Registry — TechConf

Registro dei bug trovati durante lo sviluppo e il collaudo, con classificazione,
requisito coinvolto, causa radice, test di regressione e commit di fix.

Minimo richiesto (§6.4): 2 bug chiusi, di cui almeno 1 di implementazione.

> **Verifica finale:** i riferimenti `#1` e `#2` sotto sono placeholder storici locali:
> il repository GitHub non contiene ancora issue. Per soddisfare formalmente §6.4 occorre
> creare e chiudere due issue reali, quindi sostituire questi placeholder con i relativi link.

| ID | Issue | Trovato da | Tipo | Requisito | Causa radice | Test di regressione | Commit |
|---|---|---|---|---|---|---|---|
| BUG-01 | #1 | unit test event-service | impl | REQ-EVT-B05 | Il client HTTP catturava solo `requests.exceptions.RequestException`, ma la libreria `responses` propaga un `ConnectionError` nativo Python quando si simula un servizio spento: l'eccezione sfuggiva e il servizio restituiva 500 invece di 503 `DEPENDENCY_UNAVAILABLE` | `test_create_event_user_service_down_returns_503` | `cd74697` |
| BUG-02 | #2 | unit test user-service | impl | REQ-USR-01 | Il `contracts/validator.py` invoca `response.json()` come metodo e legge `response.text`, ma la response del Flask test client espone `.json` come proprietà e usa `.data` (bytes): la validazione contro il contratto falliva con `'dict' object is not callable` | test suite `test_user_service.py` (adapter `_FlaskResponseAdapter`) | `22e319b` |

---

## Dettaglio bug

### BUG-01 — 503 non restituito quando la dipendenza è spenta

**Servizio:** event-service
**Test fallito:** `test_create_event_user_service_down_returns_503`
**Comportamento atteso:** quando user-service non è raggiungibile, event-service deve rispondere `503 DEPENDENCY_UNAVAILABLE` (REQ-EVT-B05).
**Comportamento ottenuto:** l'eccezione `ConnectionError` non veniva catturata dal blocco `except requests.exceptions.RequestException`, quindi risaliva fino a Flask che restituiva 500.

**Causa radice:** la libreria di mock `responses`, quando le si passa `body=ConnectionError(...)`, solleva l'eccezione nativa Python, non la sottoclasse `requests.exceptions.ConnectionError`. Il gestore la ignorava.

**Fix:** ampliato il catch in `clients.py` a `except (requests.exceptions.RequestException, ConnectionError)`.

**Classificazione:** bug di implementazione (la spec era corretta, il codice no) → fix diretto.

---

### BUG-02 — Validazione contratto fallisce con Flask test client

**Servizio:** user-service (poi replicato su event e registration)
**Test fallito:** tutti i test con `assert_matches_contract` sul Flask test client.
**Comportamento atteso:** la risposta del servizio deve validare contro il contratto OpenAPI.
**Comportamento ottenuto:** `ContractError: Response body is not valid JSON: 'dict' object is not callable`.

**Causa radice:** `contracts/validator.py` (non modificabile) si aspetta un oggetto stile `requests.Response` con `.json()` callable e `.text` stringa. Il Flask test client espone invece `.json` come attributo e `.data` come bytes.

**Fix:** introdotto un piccolo adapter `_FlaskResponseAdapter` nei test che espone `.status_code`, `.headers`, `.text` (da `.data`) e `.json()` come metodo. Nessuna modifica ai file protetti.

**Classificazione:** bug di implementazione (nell'harness di test del candidato) → fix diretto.
