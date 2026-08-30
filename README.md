# research

Three independent applications in one repository. They share a git history and
nothing else: separate stacks, separate data, separate ports. Nothing here
imports anything from a sibling directory, and none of them has to be running
for another to work.

| directory | what it is | owner |
|---|---|---|
| `backend/`, `backend_flask/`, `frontend/` | SafeTravel LK — safety heatmap and scam analytics | udesh, irusha, chamika |
| `food-assistant/` | Sri Lankan food recommender | nihara |
| `travellens/` | LostinSriLanka — aspect-based complaint mining over 46,854 tourist reviews | thanuja |

`food-assistant/` sits in its own directory because it defines
`backend/app/main.py`, `backend/main.py`, `frontend/src/App.jsx`,
`frontend/package.json` and `frontend/vite.config.js` — the same five paths
SafeTravel LK uses. Merged at the repository root, one of the two FastAPI apps
and one of the two React apps would be unable to run, and git reports no
conflict on most of those files.

---

## One URL

```bash
python gateway.py            # http://localhost:8080
python gateway.py --check    # what is reachable, starts nothing
```

| path | what |
|---|---|
| `/` | landing page, with a card per application |
| `/safety/` | SafeTravel LK |
| `/food/` | food assistant |
| `/travellens/` | LostinSriLanka |

One origin, so no CORS and one address to share. The three are served
differently, and the differences are the design:

**travellens is mounted into the gateway process.** It is a FastAPI app in this
repository, so it costs no extra port and no proxy hop. Its API comes with it
at `/travellens/analyse`, `/travellens/docs` and so on.

**The two React apps are served as built files**, so build them first:

```bash
cd frontend && npm install && npm run build
cd food-assistant/frontend && npm install && npm run build
```

`base` is set in both vite configs, because a single-page app behind a path
prefix needs that prefix compiled into its asset URLs — otherwise the built
page asks the gateway for `/assets/...` and gets a blank screen. Both still run
under `npm run dev` exactly as before.

**Their two backends stay on their own ports and are proxied**, because they
are separate Python applications with separate dependencies. Start them
yourself:

```bash
cd backend && uvicorn app.main:app --port 8000
cd food-assistant/backend && uvicorn main:app --port 8001
```

The gateway starts nothing on your behalf. A gateway that silently spawns other
people's servers is one nobody can debug, so a service that is down returns a
502 naming the exact address it tried, and the landing page marks that card
with the command to fix it.

**The food backend takes several minutes on its first run.** It downloads a
sentence-transformer and a cross-encoder (about 1 GB together) before it binds
its port. That is its own start-up, not a gateway problem — subsequent runs use
the cached models.

---

## Ports

Everything is on a distinct port, so all three can run at once.

| port | service |
|---|---|
| 3000 | SafeTravel LK — web UI |
| 8000 | SafeTravel LK — API |
| 5000 | SafeTravel LK — Flask services (optional locally, see below) |
| 5173 | Food assistant — web UI |
| 8001 | Food assistant — API |
| 8778 | travellens — UI **and** API, one process |

The food API is on **8001**, not the 8000 its own docs mention, because
SafeTravel LK's API already holds 8000. Copy
`food-assistant/frontend/.env.example` to `.env` so its client points at 8001 —
that file is the intended way to move it, so nothing in the application code
changed.

---

## Running them individually

Each is independent, and each still runs on its own without the gateway.

### travellens — one command

```bash
cd travellens
pip install -r requirements.txt -r requirements-train.txt
python scripts/49_build_all.py     # rebuild every artefact, in order
python scripts/50_launch.py        # check it, then serve it
```

Then <http://localhost:8778/> — a three-tab app (Map, Stories & videos, Add a
review) with its API on the same port. `50_launch.py` runs a preflight first
and refuses to start if anything is stale, naming the command that fixes it.
See `travellens/README.md`.

**A fresh clone cannot rebuild this one.** `travellens/data/raw/*.csv` is
deliberately not committed — the two review corpora are third-party scrapes
this project has no right to redistribute. The built dashboard, portal and
scorecards *are* committed, so the pages open and are readable; re-deriving
anything needs the raw corpus supplied separately.

### SafeTravel LK

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

```bash
cd frontend
npm install
npm run dev            # opens http://localhost:3000
```

The Vite dev server proxies `/api` to the local API on 8000, and `/assistance`,
`/budget_planner` and `/questions` to a **deployed** Flask host. Those three
work without anything else running locally. To run that Flask side yourself
instead:

```bash
cd backend_flask
pip install -r requirements.txt
python app.py          # http://127.0.0.1:5000
```

and repoint the proxy targets in `frontend/vite.config.js` at it.

### Food assistant

```bash
cd food-assistant/backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8001
```

```bash
cd food-assistant/frontend
cp .env.example .env   # sets VITE_API_URL to 8001 -- do not skip
npm install
npm run dev            # http://localhost:5173
```

Without that `.env` the client falls back to `http://localhost:8000`
(`src/api/client.js`) and talks to SafeTravel LK's API instead. That port
answers, so the failure looks like bad results rather than a connection error.
`.env` is gitignored repository-wide, which is why the working value ships as
`.env.example`.

`GET http://localhost:8001/health` reports which optional models loaded. The
API is built to degrade rather than fail: the corpus, BM25 index, fuzzy matcher
and rule-based recommender are pure Python and answer even when the embedding
model, cross-encoder and pickled XGBoost model are missing.

---

## Branches

`main` and the per-person branches are all still live and none of them has this
layout. In particular:

- **`origin/thanuja` deletes everything outside `travellens/`.** A plain
  `git merge origin/thanuja` removes 100+ files across `backend/`,
  `backend_flask/`, `data_pipeline/`, `training/`, `dataset_exports/` and
  `docs/`, and git calls it a clean merge because `main` has not touched them
  since the fork. Integrate it additively instead:

  ```bash
  git merge -s ours --no-commit --no-ff origin/thanuja
  git checkout origin/thanuja -- travellens .claude
  ```

- **`origin/irusha` is superseded by `origin/udesh`** — the same 161 file
  paths, and udesh is six commits newer.

- **`origin/Food-AI-Assistant` still has its files at the repository root.**
  Its next merge needs the same move into `food-assistant/` that this branch
  did.
