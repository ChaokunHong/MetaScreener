#!/usr/bin/env bash
# run_all_validations.sh — One-command reproduction of all MetaScreener 2.0 results
#
# Usage:
#   bash scripts/run_all_validations.sh           # Full run (requires OPENROUTER_API_KEY)
#   bash scripts/run_all_validations.sh --mock     # Mock run (offline, for testing)
#
# Prerequisites:
#   uv sync --extra dev --extra viz
#   export OPENROUTER_API_KEY="your-key-here"
set -euo pipefail

MOCK_FLAG=""
if [[ "${1:-}" == "--mock" ]]; then
    MOCK_FLAG="--mock"
    echo "[INFO] Running in MOCK mode (no API calls)"
fi

echo "=== MetaScreener 2.0 Validation Suite ==="
echo ""

# Step 1: Download datasets
echo "[1/6] Downloading datasets..."
python validation/datasets/download_cohen.py
python validation/datasets/download_asreview.py

# Step 2: Run Exp2 — Cohen benchmark
echo "[2/6] Running Exp2: Cohen Benchmark..."
python validation/experiments/exp2_cohen_benchmark.py --seed 42 $MOCK_FLAG

# Step 3: Run Exp3 — ASReview benchmark
echo "[3/6] Running Exp3: ASReview Benchmark..."
python validation/experiments/exp3_asreview_benchmark.py --seed 42 $MOCK_FLAG

# Step 4: Run Exp4 — Ablation study (requires a data file; uses first Cohen topic)
echo "[4/6] Running Exp4: Ablation Study..."
FIRST_COHEN=$(ls validation/datasets/cohen/*.csv 2>/dev/null | head -1 || true)
if [[ -n "$FIRST_COHEN" ]]; then
    python validation/experiments/exp4_ablation_study.py --data "$FIRST_COHEN" --seed 42 $MOCK_FLAG
else
    echo "  [SKIP] No Cohen data found for ablation study"
fi

# Step 5: Run Exp7 — Cost/time analysis
echo "[5/6] Running Exp7: Cost and Time Analysis..."
if [[ -n "${FIRST_COHEN:-}" ]]; then
    python validation/experiments/exp7_cost_time.py --data "$FIRST_COHEN" --seed 42 --max-records 20 $MOCK_FLAG
else
    echo "  [SKIP] No data found for cost analysis"
fi

# Step 6: Generate paper outputs
echo "[6/6] Generating paper outputs..."
python validation/analysis/generate_tables.py
python validation/analysis/generate_figures.py

echo ""
echo "=== All validation experiments complete ==="
echo "Results: validation/results/"
echo "Tables:  paper/tables/paper_tables.md"
echo "Figures: paper/figures/"
