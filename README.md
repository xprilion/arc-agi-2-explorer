# ARC-AGI 2 Explorer

A small **FastAPI** + **Jinja2** web UI to browse [ARC-AGI 2](https://arcprize.org/) challenge data: training, evaluation, and test splits, with optional submission upload for local checks.

**Repository:** [github.com/xprilion/arc-agi-2-explorer](https://github.com/xprilion/arc-agi-2-explorer)

## Setup

Requires Python 3.10+.

Use [Astral uv](https://docs.astral.sh/uv/) to manage the environment and install dependencies from [`requirements.txt`](requirements.txt):

```bash
# Install uv: https://docs.astral.sh/uv/getting-started/

uv venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
uv pip install -r requirements.txt
```

JSON datasets live under `data/` (included in this repo).

## Run

From the repository root (with the virtual environment activated):

```bash
PORT=8000 uvicorn app:app --reload --host 127.0.0.1 --port $PORT
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000).

## Docker

```bash
docker build -t arc-agi-2-explorer .
docker run --rm -p 8000:8000 arc-agi-2-explorer
```

Then open [http://127.0.0.1:8000](http://127.0.0.1:8000).

## License

MIT — see [LICENSE](LICENSE).
