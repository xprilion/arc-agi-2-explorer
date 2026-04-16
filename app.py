"""
ARC-AGI Data Explorer — FastAPI + Jinja2 web application.

Run with:
    PORT=8000 uvicorn app:app --reload --host 0.0.0.0 --port $PORT
"""

import json
import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, Query, UploadFile, File, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

# ---------------------------------------------------------------------------
# Load data once at startup
# ---------------------------------------------------------------------------

def _load_json(filename: str) -> dict:
    filepath = DATA_DIR / filename
    if not filepath.exists():
        return {}
    with open(filepath, "r") as f:
        return json.load(f)


# Challenges: dict[puzzle_id] -> {"train": [...], "test": [...]}
TRAINING_CHALLENGES = _load_json("arc-agi_training_challenges.json")
EVALUATION_CHALLENGES = _load_json("arc-agi_evaluation_challenges.json")
TEST_CHALLENGES = _load_json("arc-agi_test_challenges.json")

# Solutions: dict[puzzle_id] -> list[grid]
TRAINING_SOLUTIONS = _load_json("arc-agi_training_solutions.json")
EVALUATION_SOLUTIONS = _load_json("arc-agi_evaluation_solutions.json")

# Sample submission (for reference)
SAMPLE_SUBMISSION = _load_json("sample_submission.json")

DATASETS = {
    "training": {
        "label": "Training",
        "challenges": TRAINING_CHALLENGES,
        "solutions": TRAINING_SOLUTIONS,
        "description": "1,000 puzzles with full solutions. The primary dataset for learning ARC-AGI patterns.",
    },
    "evaluation": {
        "label": "Evaluation",
        "challenges": EVALUATION_CHALLENGES,
        "solutions": EVALUATION_SOLUTIONS,
        "description": "120 held-out puzzles with solutions. Used for local evaluation.",
    },
    "test": {
        "label": "Test",
        "challenges": TEST_CHALLENGES,
        "solutions": TRAINING_SOLUTIONS,  # test puzzles are a subset of training
        "description": "240 puzzles (subset of training) to submit predictions for. Solutions sourced from training.",
    },
}

# Pre-sorted puzzle ID lists for next/previous navigation
SORTED_IDS = {name: sorted(ds["challenges"].keys()) for name, ds in DATASETS.items()}

# In-memory store for uploaded submissions (reset on server restart)
CURRENT_SUBMISSION: dict = {}
CURRENT_SUBMISSION_NAME: str = ""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def grid_dims(grid: list[list[int]]) -> tuple[int, int]:
    """Return (rows, cols) for a 2D grid."""
    if not grid:
        return (0, 0)
    return (len(grid), len(grid[0]) if grid[0] else 0)


def grid_colors(grid: list[list[int]]) -> set[int]:
    """Return set of unique color values in a grid."""
    colors = set()
    for row in grid:
        colors.update(row)
    return colors


def puzzle_summary(puzzle_id: str, challenge: dict, solutions: dict) -> dict:
    """Build a summary dict for a puzzle."""
    train_examples = challenge.get("train", [])
    test_examples = challenge.get("test", [])

    # Collect all grid dimensions
    all_dims = []
    all_colors = set()
    for ex in train_examples:
        for key in ("input", "output"):
            g = ex.get(key, [])
            all_dims.append(grid_dims(g))
            all_colors |= grid_colors(g)
    for ex in test_examples:
        g = ex.get("input", [])
        all_dims.append(grid_dims(g))
        all_colors |= grid_colors(g)

    # Solutions
    sol = solutions.get(puzzle_id, [])
    for g in sol:
        all_dims.append(grid_dims(g))
        all_colors |= grid_colors(g)

    max_rows = max((d[0] for d in all_dims), default=0)
    max_cols = max((d[1] for d in all_dims), default=0)
    min_rows = min((d[0] for d in all_dims), default=0)
    min_cols = min((d[1] for d in all_dims), default=0)

    return {
        "id": puzzle_id,
        "num_train": len(train_examples),
        "num_test": len(test_examples),
        "has_solution": puzzle_id in solutions and len(solutions[puzzle_id]) > 0,
        "max_rows": max_rows,
        "max_cols": max_cols,
        "min_rows": min_rows,
        "min_cols": min_cols,
        "num_colors": len(all_colors),
        "colors": sorted(all_colors),
    }


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="ARC-AGI Data Explorer")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# --- Home page ---
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    dataset_stats = []
    for key, ds in DATASETS.items():
        challenges = ds["challenges"]
        solutions = ds["solutions"]
        total_train = sum(len(c.get("train", [])) for c in challenges.values())
        total_test = sum(len(c.get("test", [])) for c in challenges.values())
        total_solved = sum(1 for pid in challenges if pid in solutions and solutions[pid])
        dataset_stats.append({
            "key": key,
            "label": ds["label"],
            "description": ds["description"],
            "num_puzzles": len(challenges),
            "total_train_examples": total_train,
            "total_test_examples": total_test,
            "num_with_solutions": total_solved,
        })
    return templates.TemplateResponse(request, "index.html", {
        "datasets": dataset_stats,
    })


# --- Dataset listing ---
@app.get("/dataset/{dataset_name}", response_class=HTMLResponse)
async def dataset_view(
    request: Request,
    dataset_name: str,
    q: Optional[str] = Query(None, description="Search puzzle ID"),
    min_size: Optional[int] = Query(None, description="Min grid dimension"),
    max_size: Optional[int] = Query(None, description="Max grid dimension"),
    min_examples: Optional[int] = Query(None, description="Min train examples"),
    sort: Optional[str] = Query("id", description="Sort by: id, train, test, size"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=10, le=200),
):
    ds = DATASETS.get(dataset_name)
    if not ds:
        return HTMLResponse("<h1>Dataset not found</h1>", status_code=404)

    challenges = ds["challenges"]
    solutions = ds["solutions"]

    # Build summaries
    summaries = []
    for pid, challenge in challenges.items():
        s = puzzle_summary(pid, challenge, solutions)
        summaries.append(s)

    # Filter
    if q:
        q_lower = q.lower()
        summaries = [s for s in summaries if q_lower in s["id"].lower()]
    if min_size is not None:
        summaries = [s for s in summaries if s["max_rows"] >= min_size or s["max_cols"] >= min_size]
    if max_size is not None:
        summaries = [s for s in summaries if s["max_rows"] <= max_size and s["max_cols"] <= max_size]
    if min_examples is not None:
        summaries = [s for s in summaries if s["num_train"] >= min_examples]

    # Sort
    sort_keys = {
        "id": lambda s: s["id"],
        "train": lambda s: -s["num_train"],
        "test": lambda s: -s["num_test"],
        "size": lambda s: -(s["max_rows"] * s["max_cols"]),
        "colors": lambda s: -s["num_colors"],
    }
    sort_fn = sort_keys.get(sort, sort_keys["id"])
    summaries.sort(key=sort_fn)

    # Paginate
    total = len(summaries)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, total_pages)
    start = (page - 1) * per_page
    page_summaries = summaries[start : start + per_page]

    return templates.TemplateResponse(request, "dataset.html", {
        "dataset_name": dataset_name,
        "dataset_label": ds["label"],
        "dataset_description": ds["description"],
        "puzzles": page_summaries,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
        "q": q or "",
        "min_size": min_size,
        "max_size": max_size,
        "min_examples": min_examples,
        "sort": sort,
    })


# --- Individual puzzle view ---
@app.get("/puzzle/{dataset_name}/{puzzle_id}", response_class=HTMLResponse)
async def puzzle_view(request: Request, dataset_name: str, puzzle_id: str):
    ds = DATASETS.get(dataset_name)
    if not ds:
        return HTMLResponse("<h1>Dataset not found</h1>", status_code=404)

    challenges = ds["challenges"]
    solutions = ds["solutions"]

    challenge = challenges.get(puzzle_id)
    if not challenge:
        return HTMLResponse("<h1>Puzzle not found</h1>", status_code=404)

    train_examples = challenge.get("train", [])
    test_examples = challenge.get("test", [])
    sol = solutions.get(puzzle_id, [])

    # Build enriched train examples
    train_data = []
    for i, ex in enumerate(train_examples):
        inp = ex.get("input", [])
        out = ex.get("output", [])
        train_data.append({
            "index": i + 1,
            "input": inp,
            "input_dims": grid_dims(inp),
            "input_colors": sorted(grid_colors(inp)),
            "output": out,
            "output_dims": grid_dims(out),
            "output_colors": sorted(grid_colors(out)),
        })

    # Build enriched test examples
    test_data = []
    for i, ex in enumerate(test_examples):
        inp = ex.get("input", [])
        solution = sol[i] if i < len(sol) else None
        entry = {
            "index": i + 1,
            "input": inp,
            "input_dims": grid_dims(inp),
            "input_colors": sorted(grid_colors(inp)),
            "solution": solution,
        }
        if solution:
            entry["solution_dims"] = grid_dims(solution)
            entry["solution_colors"] = sorted(grid_colors(solution))
        test_data.append(entry)

    summary = puzzle_summary(puzzle_id, challenge, solutions)

    # Next / Previous puzzle navigation
    ids = SORTED_IDS.get(dataset_name, [])
    prev_id = None
    next_id = None
    if ids:
        try:
            idx = ids.index(puzzle_id)
            if idx > 0:
                prev_id = ids[idx - 1]
            if idx < len(ids) - 1:
                next_id = ids[idx + 1]
        except ValueError:
            pass

    return templates.TemplateResponse(request, "puzzle.html", {
        "dataset_name": dataset_name,
        "dataset_label": ds["label"],
        "puzzle_id": puzzle_id,
        "summary": summary,
        "train_data": train_data,
        "test_data": test_data,
        "prev_id": prev_id,
        "next_id": next_id,
    })


# ---------------------------------------------------------------------------
# Submission evaluation helpers
# ---------------------------------------------------------------------------

def _grids_equal(a: list, b: list) -> bool:
    """Check if two 2D grids are identical."""
    if len(a) != len(b):
        return False
    for ra, rb in zip(a, b):
        if len(ra) != len(rb):
            return False
        for ca, cb in zip(ra, rb):
            if ca != cb:
                return False
    return True


def _diff_grids(submitted: list, expected: list) -> list:
    """
    Build a diff grid: list of rows where each cell is
    {"value": int, "expected": int, "match": bool}.
    Handles mismatched dimensions by marking out-of-bounds as mismatches.
    """
    max_rows = max(len(submitted), len(expected))
    max_cols = max(
        (len(submitted[0]) if submitted and submitted[0] else 0),
        (len(expected[0]) if expected and expected[0] else 0),
    )
    diff = []
    for r in range(max_rows):
        row = []
        for c in range(max_cols):
            sv = submitted[r][c] if r < len(submitted) and c < len(submitted[r]) else -1
            ev = expected[r][c] if r < len(expected) and c < len(expected[r]) else -1
            row.append({"value": sv, "expected": ev, "match": sv == ev})
        diff.append(row)
    return diff


def evaluate_submission(submission: dict, dataset_name: str) -> dict:
    """
    Compare a submission dict against the ground-truth solutions for a dataset.
    Returns evaluation results compatible with the Kaggle scoring metric:
    - For each puzzle, score 1 if *either* attempt exactly matches the solution.
    """
    ds = DATASETS.get(dataset_name)
    if not ds:
        return {"error": f"Unknown dataset: {dataset_name}"}

    challenges = ds["challenges"]
    solutions = ds["solutions"]

    results = []
    total_correct = 0
    total_tests = 0

    puzzle_ids = sorted(submission.keys())
    for pid in puzzle_ids:
        if pid not in challenges:
            continue
        sol = solutions.get(pid, [])
        sub_entries = submission[pid]  # list of {"attempt_1": grid, "attempt_2": grid}

        puzzle_results = []
        puzzle_correct = 0

        for test_idx, sub_entry in enumerate(sub_entries):
            total_tests += 1
            expected = sol[test_idx] if test_idx < len(sol) else None

            attempt_1 = sub_entry.get("attempt_1", [])
            attempt_2 = sub_entry.get("attempt_2", [])

            a1_match = _grids_equal(attempt_1, expected) if expected else False
            a2_match = _grids_equal(attempt_2, expected) if expected else False
            correct = a1_match or a2_match

            if correct:
                puzzle_correct += 1
                total_correct += 1

            entry = {
                "test_index": test_idx + 1,
                "correct": correct,
                "a1_match": a1_match,
                "a2_match": a2_match,
                "attempt_1": attempt_1,
                "attempt_2": attempt_2,
                "expected": expected,
                "has_solution": expected is not None,
            }

            # Build diff grids for visualization
            if expected:
                entry["a1_diff"] = _diff_grids(attempt_1, expected)
                entry["a2_diff"] = _diff_grids(attempt_2, expected)

            puzzle_results.append(entry)

        all_correct = puzzle_correct == len(sub_entries) and len(sub_entries) > 0

        results.append({
            "puzzle_id": pid,
            "tests": puzzle_results,
            "num_correct": puzzle_correct,
            "num_tests": len(sub_entries),
            "all_correct": all_correct,
        })

    return {
        "results": results,
        "total_correct": total_correct,
        "total_tests": total_tests,
        "total_puzzles": len(results),
        "score": total_correct / total_tests if total_tests > 0 else 0,
    }


# ---------------------------------------------------------------------------
# Submission routes
# ---------------------------------------------------------------------------

@app.get("/submissions", response_class=HTMLResponse)
async def submissions_home(request: Request):
    """Show submission upload form and results summary."""
    return templates.TemplateResponse(request, "submissions.html", {
        "submission_name": CURRENT_SUBMISSION_NAME,
        "has_submission": bool(CURRENT_SUBMISSION),
        "evaluation": None,
        "detail": None,
        "puzzle_index": None,
    })


@app.post("/submissions/upload", response_class=HTMLResponse)
async def submissions_upload(request: Request, file: UploadFile = File(...), dataset: str = Form("evaluation")):
    """Upload a submission JSON and evaluate it."""
    global CURRENT_SUBMISSION, CURRENT_SUBMISSION_NAME

    content = await file.read()
    try:
        submission = json.loads(content)
    except json.JSONDecodeError:
        return templates.TemplateResponse(request, "submissions.html", {
            "submission_name": "",
            "has_submission": False,
            "evaluation": None,
            "detail": None,
            "puzzle_index": None,
            "error": "Invalid JSON file. Please upload a valid submission JSON.",
        })

    CURRENT_SUBMISSION = submission
    CURRENT_SUBMISSION_NAME = file.filename or "submission.json"

    evaluation = evaluate_submission(submission, dataset)

    return templates.TemplateResponse(request, "submissions.html", {
        "submission_name": CURRENT_SUBMISSION_NAME,
        "has_submission": True,
        "evaluation": evaluation,
        "dataset_name": dataset,
        "detail": None,
        "puzzle_index": None,
    })


@app.get("/submissions/detail/{dataset_name}/{puzzle_index}", response_class=HTMLResponse)
async def submissions_detail(request: Request, dataset_name: str, puzzle_index: int):
    """Show detailed diff for a single puzzle in the current submission."""
    if not CURRENT_SUBMISSION:
        return RedirectResponse("/submissions")

    evaluation = evaluate_submission(CURRENT_SUBMISSION, dataset_name)
    if "error" in evaluation:
        return RedirectResponse("/submissions")

    results = evaluation["results"]
    if puzzle_index < 0 or puzzle_index >= len(results):
        return RedirectResponse("/submissions")

    detail = results[puzzle_index]

    # Get the challenge data for rendering input grids
    ds = DATASETS.get(dataset_name, {})
    challenges = ds.get("challenges", {})
    challenge = challenges.get(detail["puzzle_id"], {})
    test_inputs = [t.get("input", []) for t in challenge.get("test", [])]

    # Next/previous navigation within submission results
    prev_index = puzzle_index - 1 if puzzle_index > 0 else None
    next_index = puzzle_index + 1 if puzzle_index < len(results) - 1 else None

    return templates.TemplateResponse(request, "submissions.html", {
        "submission_name": CURRENT_SUBMISSION_NAME,
        "has_submission": True,
        "evaluation": evaluation,
        "dataset_name": dataset_name,
        "detail": detail,
        "puzzle_index": puzzle_index,
        "test_inputs": test_inputs,
        "prev_index": prev_index,
        "next_index": next_index,
    })


# ---------------------------------------------------------------------------
# Run with: python -m explorer.app
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    try:
        port = int(os.getenv("PORT", "8000"))
    except ValueError:
        port = 8000

    uvicorn.run(
        "explorer.app:app",
        host="0.0.0.0",
        port=port,
        reload=True,
    )
