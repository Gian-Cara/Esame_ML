# Tech Stack

## Runtime

- **Python 3.12**
- **Flask** — framework HTTP per tutti i microservizi
- **requests** — client HTTP per le chiamate tra servizi (timeout fisso: 2 secondi)

## Persistenza

- Nessun DBMS esterno. Tre backend selezionabili via variabile d'ambiente `STORAGE_BACKEND`:
  - `memory` (default) — dizionario in RAM, si azzera al riavvio
  - `json` — file JSON nella cartella `DATA_DIR` (default `./data`)
  - `sqlite` — database SQLite in `DATA_DIR` usando solo la libreria standard `sqlite3`
- Il cambio di backend NON deve richiedere modifiche alla logica di business
- La cartella `data/` è esclusa da git

## Test

- **pytest** — runner per unit test e integration test
- **pytest-cov** — coverage report (`pytest --cov=app`), soglia minima **80%**
- **responses** — mock delle chiamate HTTP verso altri servizi negli unit test
- Ogni test deve essere tracciabile a un requisito via marker `@pytest.mark.req("REQ-XXX-BYY")` o ID nel nome/docstring

## Dipendenze Python

```
# runtime
flask
requests

# test
pytest
pytest-cov
responses
```

Solo librerie elencate qui. Non usare SQLAlchemy, Pydantic, marshmallow o altri ORM/validator.

## Contratti OpenAPI

I file in `contracts/openapi/*.yaml` sono la fonte di verità delle interfacce. NON modificarli.
Usa `contracts/validator.py` (`assert_matches_contract`) in almeno 1 test per endpoint per validare
le risposte contro il contratto.
