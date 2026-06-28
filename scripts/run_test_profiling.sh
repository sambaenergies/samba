#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

PYTHON_BIN="${PYTHON_BIN:-python3}"
if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  if command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
  else
    echo "[profiling] ERROR: python interpreter not found." >&2
    exit 127
  fi
fi

TIMESTAMP="$(date -u +%Y%m%d_%H%M%S)"
OUTPUT_ROOT="${PROFILE_OUTPUT_ROOT:-artifacts/test-profiling}"
RUN_DIR="${OUTPUT_ROOT}/${TIMESTAMP}"
RAW_DIR="${RUN_DIR}/raw"
REPORT_DIR="${RUN_DIR}/reports"

mkdir -p "${RAW_DIR}" "${REPORT_DIR}"

JUNIT_XML="${RAW_DIR}/junit.xml"
PYTEST_OUTPUT="${RAW_DIR}/pytest_output.txt"
REPORT_JSON="${REPORT_DIR}/test_timing_report.json"
SUMMARY_MD="${REPORT_DIR}/test_timing_summary.md"

echo "[profiling] Running full pytest suite (including benchmark tests)."
echo "[profiling] Output directory: ${RUN_DIR}"

set +e
"${PYTHON_BIN}" -m pytest -o addopts="" tests \
  --junit-xml "${JUNIT_XML}" \
  --durations=0 \
  --durations-min=0 \
  -ra \
  "$@" 2>&1 | tee "${PYTEST_OUTPUT}"
PYTEST_EXIT=${PIPESTATUS[0]}
set -e

echo "[profiling] Running timing analyzer."
set +e
"${PYTHON_BIN}" scripts/analyze_test_timings.py \
  --junit-xml "${JUNIT_XML}" \
  --pytest-output "${PYTEST_OUTPUT}" \
  --output-json "${REPORT_JSON}" \
  --output-summary "${SUMMARY_MD}"
ANALYZER_EXIT=$?
set -e

echo "[profiling] Artifacts written to: ${RUN_DIR}"
if [[ ${PYTEST_EXIT} -ne 0 ]]; then
  echo "[profiling] pytest exited with code ${PYTEST_EXIT}"
  exit "${PYTEST_EXIT}"
fi
if [[ ${ANALYZER_EXIT} -ne 0 ]]; then
  echo "[profiling] analyzer exited with code ${ANALYZER_EXIT}"
  exit "${ANALYZER_EXIT}"
fi
echo "[profiling] Completed successfully."
