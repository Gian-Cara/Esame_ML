# Code Structure & Architecture Decisions

## Repository layout

Monorepo: tutti i servizi nello stesso repository, ciascuno in una cartella separata sotto `services/`.

```
techconf-exam/
├── .kiro/
│   ├── steering/          # Questo file e gli altri steering
│   ├── specs/
│   │   ├── user-service/
│   │   ├── event-service/
│   │   └── registration-service/
│   └── hooks/
├── contracts/             # NON MODIFICARE
│   └── openapi/
├── services/
│   ├── user-service/
│   ├── event-service/
│   └── registration-service/
├── tests/integration/     # NON MODIFICARE (suite del docente)
├── services.yaml
├── BUGS.md
└── README.md
```

**Perché monorepo:** la suite di collaudo è già in questo repo e usa `services.yaml` con path relativi.
Aggiungere servizi opzionali è immediato senza creare nuovi repo.

## Struttura interna di ogni servizio

```
services/<nome>-service/
├── app/
│   ├── __init__.py        # crea l'app Flask (factory pattern)
│   ├── __main__.py        # entrypoint: legge PORT da env e avvia Flask
│   ├── config.py          # legge TUTTE le variabili d'ambiente in un posto solo
│   ├── routes.py          # definisce le route Flask, delega alla logica
│   ├── service.py         # regole di business (REQ-*-B*), chiama repository e clients
│   ├── repository.py      # interfaccia storage: memory / json / sqlite
│   └── clients.py         # chiamate HTTP verso altri servizi (usa *_SERVICE_URL)
├── tests/
│   ├── unit/              # unit test con responses mock, tutti e 3 i backend
│   └── integration/       # avvia servizi reali, verifica casi +/422/503
├── requirements.txt       # flask, requests, pytest, pytest-cov, responses
└── data/                  # esclusa da git (json/sqlite files)
```

**Responsabilità separate:**
- `routes.py` gestisce solo HTTP (parsing request, serializzazione response, status code)
- `service.py` contiene TUTTE le regole `REQ-*-B*`; non importa Flask
- `repository.py` gestisce TUTTA la persistenza; espone un'interfaccia uniforme (`get`, `create`, `update`, `delete`, `list`) indipendente dal backend
- `clients.py` isola le chiamate HTTP esterne; può essere mockato con `responses` negli unit test
- `config.py` legge `PORT`, `*_SERVICE_URL`, `STORAGE_BACKEND`, `DATA_DIR` — nessun'altra parte del codice legge variabili d'ambiente direttamente

**Nessun import tra servizi:** ogni servizio è autonomo. Il codice condiviso (formato errori, paginazione) è duplicato intenzionalmente per mantenere i servizi indipendenti. Se in futuro un team separato dovesse prendere un servizio, lo porta via senza dipendenze.

## Configurazione e avvio

- `config.py` in ogni servizio legge le env var con valori di default espliciti
- Comando di avvio (in `services.yaml`): `python -m app` dalla cartella `services/<nome>-service`
- `__main__.py` fa: `app = create_app(); app.run(host="0.0.0.0", port=int(os.environ["PORT"]))`

## Test

- **Unit test:** `pytest services/<nome>-service/tests/unit --cov=app`
- **Integration test (tuoi):** `pytest services/<nome>-service/tests/integration`
- **Suite collaudo docente:** `pytest tests/integration -m mandatory -v`
- **Tutti i test:** `pytest services/ --cov`

Ogni test porta l'ID del requisito nel nome o nel marker `@pytest.mark.req("REQ-XXX-BYY")`.

## Tracciabilità requisito → codice → test

- La regola `REQ-REG-B05` vive in `services/registration-service/app/service.py` (funzione `check_capacity`)
- Il test è in `services/registration-service/tests/unit/test_service.py::test_event_full_returns_409`
- Partendo dal requisito, il percorso è immediato: `service.py` per il codice, `tests/unit/` per il test

## Git e dati

- `data/` è in `.gitignore` (già presente nel repo template)
- Commit convenzionali: `spec(…)`, `feat(…)`, `test(…)`, `fix(…)`, `docs(…)`, `chore(…)`
- Sequenza leggibile: `spec(<svc>): requirements` → `spec(<svc>): design` → `spec(<svc>): tasks` → `feat(<svc>): <task> [T-NN]`
