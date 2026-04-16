# ARC-AGI 2 Explorer

A small **FastAPI** + **Jinja2** web UI to browse [ARC-AGI 2](https://arcprize.org/) challenge data: training, evaluation, and test splits, with optional submission upload for local checks.

**Repository:** [github.com/xprilion/arc-agi-2-explorer](https://github.com/xprilion/arc-agi-2-explorer)

## Setup

Requires Python 3.10+ (recommended).

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install fastapi uvicorn jinja2 python-multipart
```

JSON datasets live under `data/` (included in this repo).

## Run

From the repository root:

```bash
uvicorn app:app --reload --host 127.0.0.1 --port 8000
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000).

## License

MIT — see [LICENSE](LICENSE).
