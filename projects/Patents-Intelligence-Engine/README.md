# Patents Intelligence Engine

## `patent-reader/`

The actual working product: an end-to-end system that reads a patent's claims structure and citation lineage from real data, with an optional Claude-based scope classification. Split into:

- **`backend/`** — the agents (`ClaimsAgent`, `LineageAgent`), the FastAPI server (`api.py`), and their tests.
- **`frontend/`** — a React (Vite) UI that calls the backend and displays the results.

See `patent-reader/README.md` for the full write-up: what each agent does, how to run both pieces together, and the API's actual request/response shape.

## `chapters/`

Earlier coursework-style material — theses, evidence files, and backlog notes organized by chapter (`Chapter1`, `Chapter2`, `chapter3_chapter4`, `chapter5`, `chapter6`). This isn't part of the working product;
