# TechConf — Microservizi per la gestione di conferenze tech

Implementazione **Spec-Driven** (Requirements-First) dei microservizi TechConf con Kiro.

## Servizi implementati

| Servizio | Porta dev | Tipo | Chiama |
|---|---|---|---|
| **user-service** | 5001 | Obbligatorio | — |
| **event-service** | 5002 | Obbligatorio | user |
| **registration-service** | 5003 | Obbligatorio | user, event |

I servizi opzionali (feedback, notification) non sono implementati.

## Struttura del repository

```
techconf-exam/
├── .kiro/
│   ├── steering/          # product, tech, structure, platform-standards
│   ├── specs/             # requirements/design/tasks per ogni servizio
│   └── hooks/             # hook: unit test su salvataggio file .py
├── contracts/             # OpenAPI + validator (NON MODIFICATI)
├── services/
│   ├── user-service/
│   ├── event-service/
│   └── registration-service/
├── tests/integration/     # suite di collaudo del docente (NON MODIFICATA)
├── services.yaml          # manifest letto dalla suite
├── collaudo.txt           # output del collaudo (27/27 passati)
├── BUGS.md
└── README.md
```

Ogni servizio segue lo stesso layout interno:

```
services/<nome>-service/
├── app/
│   ├── __init__.py        # Flask app factory (create_app)
│   ├── __main__.py        # entrypoint: legge PORT, avvia il server
│   ├── config.py          # UNICO punto di lettura delle env var
│   ├── routes.py          # layer HTTP
│   ├── service.py         # regole di business (REQ-*-B*)
│   ├── repository.py      # persistenza memory/json/sqlite
│   └── clients.py         # chiamate HTTP agli altri servizi
├── tests/unit/            # unit test (responses mock, 3 backend, contract)
├── tests/integration/     # integration test (servizi reali in subprocess)
├── requirements.txt
└── data/                  # file json/sqlite (esclusa da git)
```

## Prerequisiti

- Aprire `Exam/techconf-exam` come **root del workspace Kiro**: steering e hook sono intenzionalmente nella sua `.kiro/` e non nelle directory superiori.
- Python 3.12+
- Dipendenze runtime e test:

```bash
pip install flask requests pytest pytest-cov responses
pip install -r tests/integration/requirements.txt   # per il collaudo
```

## Variabili d'ambiente

Tutte lette in `app/config.py` di ciascun servizio.

| Variabile | Default | Servizi | Descrizione |
|---|---|---|---|
| `PORT` | 5001/5002/5003 | tutti | Porta di ascolto (obbligatoria in collaudo) |
| `STORAGE_BACKEND` | `memory` | tutti | `memory` \| `json` \| `sqlite` |
| `DATA_DIR` | `./data` | tutti | Cartella per i file json/sqlite |
| `USER_SERVICE_URL` | `http://localhost:5001` | event, registration | URL di user-service |
| `EVENT_SERVICE_URL` | `http://localhost:5002` | registration | URL di event-service |

## Avvio dei servizi

Da dentro la cartella di ciascun servizio:

```bash
# user-service
cd services/user-service
$env:PORT=5001; python -m app          # PowerShell
PORT=5001 python -m app                # bash

# event-service (richiede user-service attivo)
cd services/event-service
$env:PORT=5002; $env:USER_SERVICE_URL="http://localhost:5001"; python -m app

# registration-service (richiede user + event attivi)
cd services/registration-service
$env:PORT=5003; $env:USER_SERVICE_URL="http://localhost:5001"; $env:EVENT_SERVICE_URL="http://localhost:5002"; python -m app
```

Cambio backend di persistenza (nessuna modifica al codice):

```bash
$env:STORAGE_BACKEND="sqlite"; $env:DATA_DIR="./data"; python -m app
```

## Test

### Unit test (per servizio, con coverage)

```bash
python -m pytest services/user-service/tests/unit --cov=services/user-service/app
python -m pytest services/event-service/tests/unit --cov=services/event-service/app
python -m pytest services/registration-service/tests/unit --cov=services/registration-service/app
```

Coverage verificata con `--cov-fail-under=80`: user **83.25%**, event **80.14%**, registration **83.50%**.

### Integration test propri (dipendenze reali in subprocess; SUT tramite Flask test client)

```bash
python -m pytest services/event-service/tests/integration
python -m pytest services/registration-service/tests/integration
```

### Suite di collaudo del docente

```bash
pip install -r tests/integration/requirements.txt
python -m pytest tests/integration -m mandatory -v      # solo i 3 obbligatori
```

Ultimo run: **27 passed** (vedi `collaudo.txt`).

> Nota: se il collaudo fallisce con "port already in use", ci sono processi Python
> orfani sulle porte 15001–15003 / 15101+. Terminarli prima di rilanciare.

## Persistenza

Tre backend selezionabili via `STORAGE_BACKEND`, tutti con sole librerie standard:

- `memory` — dizionario in RAM (default, azzerato al riavvio)
- `json` — file JSON in `DATA_DIR`
- `sqlite` — database SQLite in `DATA_DIR` (modulo `sqlite3`)

La logica di business è indipendente dal backend (dependency injection del repository).

## Contratti OpenAPI

I file in `contracts/openapi/*.yaml` sono la fonte di verità delle interfacce e
**non sono stati modificati**. Ogni endpoint ha almeno un test che valida la risposta
con `contracts/validator.py` (`assert_matches_contract`).

## Bug

Vedi `BUGS.md` per i bug trovati durante lo sviluppo e la loro risoluzione.
