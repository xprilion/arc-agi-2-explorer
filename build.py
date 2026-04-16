#!/usr/bin/env python3
"""
Static Site Generator for ARC-AGI Explorer.

Generates a static site in the 'docs/' folder for GitHub Pages hosting.
Supports both ARC-AGI v1 and v2 datasets.
All evaluation logic is handled client-side via JavaScript.

Run with:
    python build.py
"""

import json
import os
import shutil
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

# ---------------------------------------------------------------------------
# Paths & Config
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
TEMPLATES_DIR = BASE_DIR / "templates"
OUTPUT_DIR = BASE_DIR / "docs"

# Base URL path for the deployed site (no trailing slash).
# For GitHub Pages at https://xprilion.com/arc-agi-2-explorer/ set this to "/arc-agi-2-explorer".
# For serving at the root of a domain, set this to "".
BASE_URL = os.environ.get("BASE_URL", "/arc-agi-2-explorer")

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------


def _load_json(filepath: Path) -> dict:
    """Load a JSON file, returning {} if it doesn't exist."""
    if not filepath.exists():
        return {}
    with open(filepath, "r") as f:
        return json.load(f)


def _load_v1_data(split_dir: Path) -> tuple[dict, dict]:
    """
    Load ARC-AGI v1 data from a directory of individual puzzle JSON files.

    Returns:
        (challenges, solutions) where:
        - challenges: {puzzle_id: {"train": [...], "test": [{"input": ...}]}}
        - solutions: {puzzle_id: [output_grid, ...]}
    """
    challenges = {}
    solutions = {}

    if not split_dir.exists():
        return challenges, solutions

    for fp in sorted(split_dir.glob("*.json")):
        puzzle_id = fp.stem
        with open(fp, "r") as f:
            data = json.load(f)

        train = data.get("train", [])
        test_raw = data.get("test", [])

        # Separate test inputs from outputs (solutions)
        test_inputs = []
        sol_grids = []
        for t in test_raw:
            test_inputs.append({"input": t["input"]})
            if "output" in t:
                sol_grids.append(t["output"])

        challenges[puzzle_id] = {"train": train, "test": test_inputs}
        if sol_grids:
            solutions[puzzle_id] = sol_grids

    return challenges, solutions


def _load_v2_json(filename: str) -> dict:
    """Load a JSON file from data/2/."""
    return _load_json(DATA_DIR / "2" / filename)


# ---- ARC-AGI v1 data ----
V1_TRAINING_CHALLENGES, V1_TRAINING_SOLUTIONS = _load_v1_data(DATA_DIR / "1" / "training")
V1_EVALUATION_CHALLENGES, V1_EVALUATION_SOLUTIONS = _load_v1_data(DATA_DIR / "1" / "evaluation")

# ---- ARC-AGI v2 data ----
V2_TRAINING_CHALLENGES = _load_v2_json("arc-agi_training_challenges.json")
V2_EVALUATION_CHALLENGES = _load_v2_json("arc-agi_evaluation_challenges.json")
V2_TEST_CHALLENGES = _load_v2_json("arc-agi_test_challenges.json")
V2_TRAINING_SOLUTIONS = _load_v2_json("arc-agi_training_solutions.json")
V2_EVALUATION_SOLUTIONS = _load_v2_json("arc-agi_evaluation_solutions.json")

# ---------------------------------------------------------------------------
# Unified data structure
# ---------------------------------------------------------------------------

VERSIONS = {
    "1": {
        "label": "ARC-AGI 1",
        "datasets": {
            "training": {
                "label": "Training",
                "challenges": V1_TRAINING_CHALLENGES,
                "solutions": V1_TRAINING_SOLUTIONS,
                "description": f"{len(V1_TRAINING_CHALLENGES)} puzzles with full solutions. The original ARC-AGI training set.",
            },
            "evaluation": {
                "label": "Evaluation",
                "challenges": V1_EVALUATION_CHALLENGES,
                "solutions": V1_EVALUATION_SOLUTIONS,
                "description": f"{len(V1_EVALUATION_CHALLENGES)} puzzles with full solutions. The original ARC-AGI evaluation set.",
            },
        },
    },
    "2": {
        "label": "ARC-AGI 2",
        "datasets": {
            "training": {
                "label": "Training",
                "challenges": V2_TRAINING_CHALLENGES,
                "solutions": V2_TRAINING_SOLUTIONS,
                "description": f"{len(V2_TRAINING_CHALLENGES)} puzzles with full solutions. The primary dataset for learning ARC-AGI patterns.",
            },
            "evaluation": {
                "label": "Evaluation",
                "challenges": V2_EVALUATION_CHALLENGES,
                "solutions": V2_EVALUATION_SOLUTIONS,
                "description": f"{len(V2_EVALUATION_CHALLENGES)} held-out puzzles with solutions. Used for local evaluation.",
            },
            "test": {
                "label": "Test",
                "challenges": V2_TEST_CHALLENGES,
                "solutions": V2_TRAINING_SOLUTIONS,  # test puzzles are a subset of training
                "description": f"{len(V2_TEST_CHALLENGES)} puzzles (subset of training) to submit predictions for.",
            },
        },
    },
}

# Pre-sorted puzzle ID lists
SORTED_IDS = {}
for ver_key, ver in VERSIONS.items():
    SORTED_IDS[ver_key] = {}
    for ds_key, ds in ver["datasets"].items():
        SORTED_IDS[ver_key][ds_key] = sorted(ds["challenges"].keys())

# ---------------------------------------------------------------------------
# Helpers (shared with app.py)
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
# Build functions
# ---------------------------------------------------------------------------


def ensure_dir(path: Path):
    """Create directory if it doesn't exist."""
    path.mkdir(parents=True, exist_ok=True)


def write_file(path: Path, content: str):
    """Write content to file."""
    ensure_dir(path.parent)
    with open(path, "w") as f:
        f.write(content)
    print(f"  Generated: {path.relative_to(BASE_DIR)}")


def build_home(env: Environment):
    """Build the home page."""
    template = env.get_template("index.html")

    versions_data = []
    for ver_key, ver in VERSIONS.items():
        ver_datasets = []
        for ds_key, ds in ver["datasets"].items():
            challenges = ds["challenges"]
            solutions = ds["solutions"]
            total_train = sum(len(c.get("train", [])) for c in challenges.values())
            total_test = sum(len(c.get("test", [])) for c in challenges.values())
            total_solved = sum(1 for pid in challenges if pid in solutions and solutions[pid])
            ver_datasets.append({
                "key": ds_key,
                "label": ds["label"],
                "description": ds["description"],
                "num_puzzles": len(challenges),
                "total_train_examples": total_train,
                "total_test_examples": total_test,
                "num_with_solutions": total_solved,
            })
        versions_data.append({
            "key": ver_key,
            "label": ver["label"],
            "datasets": ver_datasets,
        })

    html = template.render(versions=versions_data)
    write_file(OUTPUT_DIR / "index.html", html)


def build_dataset_pages(env: Environment):
    """Build dataset listing pages."""
    template = env.get_template("dataset.html")

    for ver_key, ver in VERSIONS.items():
        for dataset_name, ds in ver["datasets"].items():
            challenges = ds["challenges"]
            solutions = ds["solutions"]

            # Build summaries for all puzzles
            summaries = []
            for pid, challenge in challenges.items():
                s = puzzle_summary(pid, challenge, solutions)
                summaries.append(s)

            # Sort by ID for initial display
            summaries.sort(key=lambda s: s["id"])

            html = template.render(
                version=ver_key,
                version_label=ver["label"],
                dataset_name=dataset_name,
                dataset_label=ds["label"],
                dataset_description=ds["description"],
                puzzles=summaries,
                total=len(summaries),
                page=1,
                per_page=50,
                total_pages=1,  # JS handles pagination
                q="",
                min_size=None,
                max_size=None,
                min_examples=None,
                sort="id",
                static_mode=True,
            )
            write_file(OUTPUT_DIR / "v" / ver_key / "dataset" / dataset_name / "index.html", html)


def build_puzzle_pages(env: Environment):
    """Build individual puzzle pages."""
    template = env.get_template("puzzle.html")

    total_puzzles = sum(
        len(ds["challenges"])
        for ver in VERSIONS.values()
        for ds in ver["datasets"].values()
    )
    built = 0

    for ver_key, ver in VERSIONS.items():
        for dataset_name, ds in ver["datasets"].items():
            challenges = ds["challenges"]
            solutions = ds["solutions"]
            ids = SORTED_IDS[ver_key][dataset_name]

            for i, puzzle_id in enumerate(ids):
                challenge = challenges[puzzle_id]

                train_examples = challenge.get("train", [])
                test_examples = challenge.get("test", [])
                sol = solutions.get(puzzle_id, [])

                # Build enriched train examples
                train_data = []
                for j, ex in enumerate(train_examples):
                    inp = ex.get("input", [])
                    out = ex.get("output", [])
                    train_data.append({
                        "index": j + 1,
                        "input": inp,
                        "input_dims": grid_dims(inp),
                        "input_colors": sorted(grid_colors(inp)),
                        "output": out,
                        "output_dims": grid_dims(out),
                        "output_colors": sorted(grid_colors(out)),
                    })

                # Build enriched test examples
                test_data = []
                for j, ex in enumerate(test_examples):
                    inp = ex.get("input", [])
                    solution = sol[j] if j < len(sol) else None
                    entry = {
                        "index": j + 1,
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

                # Next / Previous navigation
                prev_id = ids[i - 1] if i > 0 else None
                next_id = ids[i + 1] if i < len(ids) - 1 else None

                html = template.render(
                    version=ver_key,
                    version_label=ver["label"],
                    dataset_name=dataset_name,
                    dataset_label=ds["label"],
                    puzzle_id=puzzle_id,
                    summary=summary,
                    train_data=train_data,
                    test_data=test_data,
                    prev_id=prev_id,
                    next_id=next_id,
                )
                write_file(OUTPUT_DIR / "v" / ver_key / "puzzle" / dataset_name / puzzle_id / "index.html", html)

                built += 1
                if built % 200 == 0:
                    print(f"  Progress: {built}/{total_puzzles} puzzle pages")


def build_submissions_page(env: Environment):
    """Build the submissions page (JS-powered evaluation)."""
    template = env.get_template("submissions.html")

    # Build version options for the form
    version_options = []
    for ver_key, ver in VERSIONS.items():
        ds_list = []
        for ds_key, ds in ver["datasets"].items():
            ds_list.append({
                "key": ds_key,
                "label": ds["label"],
                "num_puzzles": len(ds["challenges"]),
            })
        version_options.append({
            "key": ver_key,
            "label": ver["label"],
            "datasets": ds_list,
        })

    html = template.render(
        version_options=version_options,
        submission_name="",
        has_submission=False,
        evaluation=None,
        detail=None,
        puzzle_index=None,
        static_mode=True,
    )
    write_file(OUTPUT_DIR / "submissions" / "index.html", html)


def build_puzzle_index():
    """Build a lightweight puzzle index JSON for client-side filtering."""
    index = {}

    for ver_key, ver in VERSIONS.items():
        for dataset_name, ds in ver["datasets"].items():
            challenges = ds["challenges"]
            solutions = ds["solutions"]

            summaries = []
            for pid, challenge in challenges.items():
                s = puzzle_summary(pid, challenge, solutions)
                summaries.append(s)

            # Key format: "version/dataset"
            index_key = f"{ver_key}/{dataset_name}"
            index[index_key] = {
                "label": ds["label"],
                "version_label": ver["label"],
                "description": ds["description"],
                "puzzles": summaries,
            }

    write_file(OUTPUT_DIR / "data" / "puzzle-index.json", json.dumps(index, separators=(',', ':')))


def copy_data_files():
    """Copy and generate JSON data files to output directory."""
    ensure_dir(OUTPUT_DIR / "data" / "1")
    ensure_dir(OUTPUT_DIR / "data" / "2")

    # ---- v2: Copy existing combined JSON files ----
    v2_files = [
        "arc-agi_training_challenges.json",
        "arc-agi_training_solutions.json",
        "arc-agi_evaluation_challenges.json",
        "arc-agi_evaluation_solutions.json",
        "arc-agi_test_challenges.json",
        "sample_submission.json",
    ]
    for filename in v2_files:
        src = DATA_DIR / "2" / filename
        dst = OUTPUT_DIR / "data" / "2" / filename
        if src.exists():
            shutil.copy(src, dst)
            print(f"  Copied: data/2/{filename}")

    # ---- v1: Generate combined JSON files from individual puzzle files ----
    # These are generated on-the-fly so the client-side JS can fetch them.
    v1_data_pairs = [
        ("training", V1_TRAINING_CHALLENGES, V1_TRAINING_SOLUTIONS),
        ("evaluation", V1_EVALUATION_CHALLENGES, V1_EVALUATION_SOLUTIONS),
    ]
    for split_name, challenges, solutions in v1_data_pairs:
        chal_path = OUTPUT_DIR / "data" / "1" / f"v1_{split_name}_challenges.json"
        sol_path = OUTPUT_DIR / "data" / "1" / f"v1_{split_name}_solutions.json"

        with open(chal_path, "w") as f:
            json.dump(challenges, f, separators=(',', ':'))
        print(f"  Generated: data/1/v1_{split_name}_challenges.json ({len(challenges)} puzzles)")

        with open(sol_path, "w") as f:
            json.dump(solutions, f, separators=(',', ':'))
        print(f"  Generated: data/1/v1_{split_name}_solutions.json ({len(solutions)} solutions)")


def copy_assets():
    """Copy JavaScript assets."""
    ensure_dir(OUTPUT_DIR / "assets")
    src = BASE_DIR / "assets" / "app.js"
    dst = OUTPUT_DIR / "assets" / "app.js"
    if src.exists():
        shutil.copy(src, dst)
        print(f"  Copied: assets/app.js")
    else:
        print(f"  Warning: assets/app.js not found (will create)")


def create_nojekyll():
    """Create .nojekyll file to prevent Jekyll processing."""
    write_file(OUTPUT_DIR / ".nojekyll", "")


def main():
    print("=" * 60)
    print("ARC-AGI Explorer Static Site Generator")
    print("=" * 60)

    # Clean output directory
    if OUTPUT_DIR.exists():
        print(f"\nCleaning {OUTPUT_DIR}...")
        shutil.rmtree(OUTPUT_DIR)

    # Set up Jinja2 environment
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))
    env.globals["base_url"] = BASE_URL

    print("\nBuilding pages...")

    # Build pages
    print("\n[1/6] Home page")
    build_home(env)

    print("\n[2/6] Dataset listing pages")
    build_dataset_pages(env)

    print("\n[3/6] Puzzle pages (this may take a moment)...")
    build_puzzle_pages(env)

    print("\n[4/6] Submissions page")
    build_submissions_page(env)

    print("\n[5/6] Puzzle index JSON")
    build_puzzle_index()

    print("\n[6/6] Copying data files and assets")
    copy_data_files()
    copy_assets()
    create_nojekyll()

    # Print summary
    total_puzzles = sum(
        len(ds["challenges"])
        for ver in VERSIONS.values()
        for ds in ver["datasets"].values()
    )

    print("\n" + "=" * 60)
    print("Build complete!")
    print(f"Output directory: {OUTPUT_DIR}")
    print(f"Total puzzle pages generated: {total_puzzles}")
    for ver_key, ver in VERSIONS.items():
        for ds_key, ds in ver["datasets"].items():
            print(f"  {ver['label']} / {ds['label']}: {len(ds['challenges'])} puzzles")
    print("\nTo preview locally:")
    print(f"  python -m http.server 8000 --directory {OUTPUT_DIR}")
    print("\nTo deploy to GitHub Pages:")
    print("  1. Push to your repository")
    print("  2. Go to Settings > Pages > Source: 'Deploy from branch'")
    print("  3. Select branch 'main' and folder '/docs'")
    print("=" * 60)


if __name__ == "__main__":
    main()
