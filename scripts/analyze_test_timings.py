# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Analyze pytest JUnit timing output and emit structured profiling reports.

This script is intended for maintainer-level profiling runs (major releases,
significant test-suite changes), not for default day-to-day local test runs.
"""

from __future__ import annotations

import argparse
import ast
import json
import math
import platform
import statistics
import subprocess
import sys
import tomllib
import xml.etree.ElementTree as element_tree
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any


@dataclass(frozen=True)
class TestTiming:
    """A single test timing record extracted from JUnit XML."""

    nodeid: str
    file: str
    top_level_group: str
    class_name: str | None
    test_name: str
    duration_s: float
    outcome: str
    markers_known: list[str]


@dataclass
class MarkerIndex:
    """Best-effort marker index for tests based on source AST."""

    repo_root: Path
    known_markers: set[str]

    def __post_init__(self) -> None:
        self._cache: dict[str, FileMarkerData] = {}

    def markers_for_test(self, file_path: str, class_name: str | None, test_name: str) -> list[str]:
        marker_data = self._load_marker_data(file_path)
        markers: set[str] = set(marker_data.module_markers)
        base_test_name = test_name.split("[", 1)[0]

        if class_name is not None:
            markers.update(marker_data.class_markers.get(class_name, set()))
            markers.update(marker_data.method_markers.get((class_name, base_test_name), set()))
        else:
            markers.update(marker_data.function_markers.get(base_test_name, set()))

        return sorted(markers)

    def _load_marker_data(self, file_path: str) -> FileMarkerData:
        normalized_path = file_path.replace("\\", "/")
        cached = self._cache.get(normalized_path)
        if cached is not None:
            return cached

        full_path = self.repo_root / normalized_path
        if not full_path.exists():
            marker_data = FileMarkerData()
            self._cache[normalized_path] = marker_data
            return marker_data

        try:
            source = full_path.read_text(encoding="utf-8")
            parsed_ast = ast.parse(source)
        except Exception:  # noqa: BLE001
            marker_data = FileMarkerData()
            self._cache[normalized_path] = marker_data
            return marker_data

        marker_data = parse_file_markers(parsed_ast, self.known_markers)
        self._cache[normalized_path] = marker_data
        return marker_data


@dataclass(frozen=True)
class FileMarkerData:
    """Known markers found in a single test file."""

    module_markers: set[str] = field(default_factory=set)
    class_markers: dict[str, set[str]] = field(default_factory=dict)
    function_markers: dict[str, set[str]] = field(default_factory=dict)
    method_markers: dict[tuple[str, str], set[str]] = field(default_factory=dict)


def parse_file_markers(parsed_ast: ast.AST, known_markers: set[str]) -> FileMarkerData:
    """Extract module/class/function markers from an AST."""
    module_markers: set[str] = set()
    class_markers: dict[str, set[str]] = {}
    function_markers: dict[str, set[str]] = {}
    method_markers: dict[tuple[str, str], set[str]] = {}

    module_body = getattr(parsed_ast, "body", [])
    if not isinstance(module_body, list):
        return FileMarkerData(
            module_markers=module_markers,
            class_markers=class_markers,
            function_markers=function_markers,
            method_markers=method_markers,
        )

    for node in module_body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "pytestmark":
                    module_markers.update(markers_from_expr(node.value, known_markers))

        if isinstance(node, ast.FunctionDef) and node.name.startswith("test"):
            function_markers[node.name] = markers_from_decorators(
                node.decorator_list, known_markers
            )

        if isinstance(node, ast.ClassDef):
            class_level_markers = markers_from_decorators(node.decorator_list, known_markers)
            if class_level_markers:
                class_markers[node.name] = class_level_markers
            for class_node in node.body:
                if isinstance(class_node, ast.FunctionDef) and class_node.name.startswith("test"):
                    method_markers[(node.name, class_node.name)] = markers_from_decorators(
                        class_node.decorator_list, known_markers
                    )

    return FileMarkerData(
        module_markers=module_markers,
        class_markers=class_markers,
        function_markers=function_markers,
        method_markers=method_markers,
    )


def markers_from_decorators(decorators: list[ast.expr], known_markers: set[str]) -> set[str]:
    """Extract known pytest marker names from a list of decorators."""
    markers: set[str] = set()
    for decorator in decorators:
        marker_name = marker_name_from_expr(decorator)
        if marker_name is not None and marker_name in known_markers:
            markers.add(marker_name)
    return markers


def markers_from_expr(expr: ast.AST, known_markers: set[str]) -> set[str]:
    """Extract known pytest marker names from a generic AST expression."""
    markers: set[str] = set()
    marker_name = marker_name_from_expr(expr)
    if marker_name is not None and marker_name in known_markers:
        markers.add(marker_name)

    if isinstance(expr, (ast.List, ast.Tuple, ast.Set)):
        for item in expr.elts:
            markers.update(markers_from_expr(item, known_markers))
    return markers


def marker_name_from_expr(expr: ast.AST) -> str | None:
    """Return marker name for expressions like ``pytest.mark.slow``."""
    if isinstance(expr, ast.Call):
        return marker_name_from_expr(expr.func)

    if isinstance(expr, ast.Attribute):
        parent = expr.value
        if (
            isinstance(parent, ast.Attribute)
            and isinstance(parent.value, ast.Name)
            and parent.value.id == "pytest"
            and parent.attr == "mark"
        ):
            return expr.attr
    return None


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Analyze pytest JUnit timing data and generate profiling reports.",
    )
    parser.add_argument(
        "--junit-xml",
        required=True,
        type=Path,
        help="Path to pytest JUnit XML output file.",
    )
    parser.add_argument(
        "--pytest-output",
        required=False,
        type=Path,
        default=None,
        help="Path to captured pytest stdout/stderr text output.",
    )
    parser.add_argument(
        "--output-json",
        required=True,
        type=Path,
        help="Path to write structured JSON report.",
    )
    parser.add_argument(
        "--output-summary",
        required=False,
        type=Path,
        default=None,
        help="Optional path to write markdown summary report.",
    )
    parser.add_argument(
        "--project-config",
        required=False,
        type=Path,
        default=Path("pyproject.toml"),
        help="Path to project pyproject.toml for known marker definitions.",
    )
    parser.add_argument(
        "--slow-threshold-s",
        type=float,
        default=10.0,
        help="Threshold above which unmarked tests are suggested for @pytest.mark.slow.",
    )
    parser.add_argument(
        "--benchmark-threshold-s",
        type=float,
        default=60.0,
        help="Threshold above which benchmark-like tests are suggested for @pytest.mark.benchmark.",
    )
    parser.add_argument(
        "--slow-unmark-threshold-s",
        type=float,
        default=3.0,
        help="Threshold below which slow-marked tests are suggested for review/unmark.",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=25,
        help="Number of slowest tests to include in top list.",
    )
    return parser.parse_args(argv)


def load_known_markers(config_path: Path) -> set[str]:
    """Load marker names from ``tool.pytest.ini_options.markers``."""
    if not config_path.exists():
        return {"benchmark", "integration", "milp", "slow"}

    try:
        with config_path.open("rb") as config_file:
            parsed = tomllib.load(config_file)
    except Exception:  # noqa: BLE001
        return {"benchmark", "integration", "milp", "slow"}

    marker_entries = (
        parsed.get("tool", {}).get("pytest", {}).get("ini_options", {}).get("markers", [])
    )
    markers: set[str] = set()
    if isinstance(marker_entries, list):
        for marker_entry in marker_entries:
            if not isinstance(marker_entry, str):
                continue
            marker_name = marker_entry.split(":", 1)[0].strip()
            if marker_name:
                markers.add(marker_name)

    if not markers:
        return {"benchmark", "integration", "milp", "slow"}
    return markers


def parse_junit_records(
    junit_xml_path: Path,
    marker_index: MarkerIndex,
) -> tuple[list[TestTiming], dict[str, int]]:
    """Parse test records from JUnit XML."""
    parsed_tree = element_tree.parse(junit_xml_path)
    root = parsed_tree.getroot()

    timing_records: list[TestTiming] = []
    outcome_counts = {
        "passed": 0,
        "failed": 0,
        "error": 0,
        "skipped": 0,
        "xfailed": 0,
        "xpassed": 0,
    }

    repo_root = Path.cwd().resolve()

    for testcase in root.iter("testcase"):
        test_name = testcase.get("name", "").strip()
        class_name_attr = testcase.get("classname", "").strip()
        file_attr = testcase.get("file")
        duration_s = safe_float(testcase.get("time"), default=0.0)

        outcome = testcase_outcome(testcase)
        outcome_counts[outcome] = outcome_counts.get(outcome, 0) + 1

        module_name, class_name = split_classname(class_name_attr)
        file_path = normalize_test_file_path(
            raw_file=file_attr,
            module_name=module_name,
            repo_root=repo_root,
        )
        top_level_group = infer_top_level_group(file_path)
        nodeid = build_nodeid(file_path=file_path, class_name=class_name, test_name=test_name)

        markers_known = marker_index.markers_for_test(
            file_path=file_path,
            class_name=class_name,
            test_name=test_name,
        )

        timing_records.append(
            TestTiming(
                nodeid=nodeid,
                file=file_path,
                top_level_group=top_level_group,
                class_name=class_name,
                test_name=test_name,
                duration_s=duration_s,
                outcome=outcome,
                markers_known=markers_known,
            )
        )

    return timing_records, outcome_counts


def split_classname(class_name_attr: str) -> tuple[str, str | None]:
    """Split JUnit classname into module-like path and optional class name."""
    if not class_name_attr:
        return "", None

    parts = [part for part in class_name_attr.split(".") if part]
    if not parts:
        return "", None

    last_part = parts[-1]
    if last_part.startswith("Test"):
        module_name = ".".join(parts[:-1])
        return module_name, last_part

    return ".".join(parts), None


def normalize_test_file_path(raw_file: str | None, module_name: str, repo_root: Path) -> str:
    """Normalize a test file path to repo-relative POSIX form."""
    if raw_file:
        raw_path = raw_file.replace("\\", "/")
        candidate_path = Path(raw_path)
        if candidate_path.is_absolute():
            try:
                return candidate_path.resolve().relative_to(repo_root).as_posix()
            except ValueError:
                return candidate_path.name
        return PurePosixPath(raw_path).as_posix()

    if module_name:
        inferred = f"{module_name.replace('.', '/')}.py"
        return PurePosixPath(inferred).as_posix()

    return "unknown"


def build_nodeid(file_path: str, class_name: str | None, test_name: str) -> str:
    """Build a pytest-like nodeid string for reporting."""
    if class_name:
        return f"{file_path}::{class_name}::{test_name}"
    return f"{file_path}::{test_name}"


def infer_top_level_group(file_path: str) -> str:
    """Infer top-level test grouping from a test file path."""
    if file_path == "unknown":
        return "unknown"

    parts = [part for part in PurePosixPath(file_path).parts if part]
    if not parts:
        return "unknown"

    if "tests" in parts:
        tests_index = parts.index("tests")
        if tests_index + 1 < len(parts):
            return parts[tests_index + 1]
        return "tests"

    return parts[0]


def testcase_outcome(testcase: element_tree.Element) -> str:
    """Map JUnit testcase children to a normalized outcome label."""
    error_node = testcase.find("error")
    if error_node is not None:
        return "error"

    failure_node = testcase.find("failure")
    if failure_node is not None:
        failure_text = text_from_node(failure_node).lower()
        if "xpass" in failure_text:
            return "xpassed"
        return "failed"

    skipped_node = testcase.find("skipped")
    if skipped_node is not None:
        skipped_text = text_from_node(skipped_node).lower()
        if "xfail" in skipped_text:
            return "xfailed"
        return "skipped"

    return "passed"


def text_from_node(node: element_tree.Element) -> str:
    """Collect textual content from an XML node."""
    message = node.get("message", "")
    body = "".join(node.itertext())
    return f"{message} {body}".strip()


def safe_float(raw_value: str | None, default: float) -> float:
    """Convert string to float with fallback."""
    if raw_value is None:
        return default
    try:
        return float(raw_value)
    except Exception:  # noqa: BLE001
        return default


def compute_stats(durations: list[float]) -> dict[str, float]:
    """Compute aggregate statistics for a list of durations."""
    if not durations:
        return {
            "total_s": 0.0,
            "mean_s": 0.0,
            "median_s": 0.0,
            "p95_s": 0.0,
            "min_s": 0.0,
            "max_s": 0.0,
        }

    sorted_durations = sorted(durations)
    return {
        "total_s": round(sum(sorted_durations), 6),
        "mean_s": round(statistics.fmean(sorted_durations), 6),
        "median_s": round(statistics.median(sorted_durations), 6),
        "p95_s": round(percentile(sorted_durations, 0.95), 6),
        "min_s": round(sorted_durations[0], 6),
        "max_s": round(sorted_durations[-1], 6),
    }


def percentile(sorted_values: list[float], quantile: float) -> float:
    """Return linear-interpolated percentile from a pre-sorted list."""
    if not sorted_values:
        return 0.0

    if len(sorted_values) == 1:
        return sorted_values[0]

    quantile = min(max(quantile, 0.0), 1.0)
    position = (len(sorted_values) - 1) * quantile
    lower_index = int(math.floor(position))
    upper_index = int(math.ceil(position))
    if lower_index == upper_index:
        return sorted_values[lower_index]

    lower_value = sorted_values[lower_index]
    upper_value = sorted_values[upper_index]
    fraction = position - lower_index
    return lower_value + (upper_value - lower_value) * fraction


def build_group_stats(records: list[TestTiming], total_duration_s: float) -> dict[str, Any]:
    """Build grouped timing statistics."""
    by_top_level: dict[str, list[TestTiming]] = {}
    by_file: dict[str, list[TestTiming]] = {}

    for record in records:
        by_top_level.setdefault(record.top_level_group, []).append(record)
        by_file.setdefault(record.file, []).append(record)

    top_level_stats: dict[str, Any] = {}
    for group_name, group_records in sorted(by_top_level.items()):
        group_durations = [entry.duration_s for entry in group_records]
        group_stats = compute_stats(group_durations)
        group_stats.update(
            {
                "tests": len(group_records),
                "share_of_total_pct": round(
                    (group_stats["total_s"] / total_duration_s * 100.0)
                    if total_duration_s > 0
                    else 0.0,
                    3,
                ),
                "outcomes": count_outcomes(group_records),
            }
        )
        top_level_stats[group_name] = group_stats

    file_stats: dict[str, Any] = {}
    for file_name, file_records in sorted(by_file.items()):
        file_durations = [entry.duration_s for entry in file_records]
        file_stats[file_name] = {
            **compute_stats(file_durations),
            "tests": len(file_records),
            "outcomes": count_outcomes(file_records),
        }

    return {
        "by_top_level_dir": top_level_stats,
        "by_file": file_stats,
    }


def count_outcomes(records: list[TestTiming]) -> dict[str, int]:
    """Count outcomes across records."""
    counts: dict[str, int] = {}
    for record in records:
        counts[record.outcome] = counts.get(record.outcome, 0) + 1
    return counts


def build_recommendations(
    records: list[TestTiming],
    slow_threshold_s: float,
    benchmark_threshold_s: float,
    slow_unmark_threshold_s: float,
) -> list[dict[str, Any]]:
    """Build recategorization recommendations from timing data."""
    suggestions: list[dict[str, Any]] = []
    reviewable_outcomes = {"passed", "failed", "error", "xpassed"}

    for record in records:
        if record.outcome not in reviewable_outcomes:
            continue

        markers = set(record.markers_known)
        benchmark_like_path = (
            "/goldens/" in f"/{record.file}/"
            or "benchmark" in record.file.lower()
            or "golden" in record.file.lower()
        )

        if (
            record.duration_s >= benchmark_threshold_s
            and "benchmark" not in markers
            and benchmark_like_path
        ):
            suggestions.append(
                {
                    "nodeid": record.nodeid,
                    "action": "consider_add_marker",
                    "marker": "benchmark",
                    "duration_s": round(record.duration_s, 6),
                    "reason": (
                        f"Duration >= {benchmark_threshold_s:.2f}s in benchmark-like path; "
                        "consider @pytest.mark.benchmark."
                    ),
                }
            )
        elif record.duration_s >= slow_threshold_s and "slow" not in markers:
            suggestions.append(
                {
                    "nodeid": record.nodeid,
                    "action": "consider_add_marker",
                    "marker": "slow",
                    "duration_s": round(record.duration_s, 6),
                    "reason": (
                        f"Duration >= {slow_threshold_s:.2f}s and test is not marked slow; "
                        "consider @pytest.mark.slow."
                    ),
                }
            )

        if "slow" in markers and record.duration_s < slow_unmark_threshold_s:
            suggestions.append(
                {
                    "nodeid": record.nodeid,
                    "action": "review_remove_marker",
                    "marker": "slow",
                    "duration_s": round(record.duration_s, 6),
                    "reason": (
                        f"Duration < {slow_unmark_threshold_s:.2f}s while marked slow; "
                        "review if marker is still needed."
                    ),
                }
            )

    return suggestions


def git_hash(repo_root: Path) -> str | None:
    """Return current git commit hash (best effort)."""
    try:
        output = subprocess.check_output(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except Exception:  # noqa: BLE001
        return None
    return output.strip() or None


def pytest_version() -> str | None:
    """Return pytest version if importable."""
    try:
        import pytest
    except Exception:  # noqa: BLE001
        return None
    return getattr(pytest, "__version__", None)


def write_summary_markdown(
    output_path: Path,
    report: dict[str, Any],
    top_n: int,
) -> None:
    """Write a concise markdown summary report."""
    lines: list[str] = []
    metadata = report["metadata"]
    run_summary = report["run_summary"]
    top_level_stats = report["groups"]["by_top_level_dir"]
    slowest_tests = report["slowest_tests"]
    recommendations = report["recommendations"]

    lines.append("# Test Timing Profiling Summary")
    lines.append("")
    lines.append(f"- Generated (UTC): `{metadata['generated_at_utc']}`")
    lines.append(f"- Source JUnit: `{metadata['source_junit_xml']}`")
    if metadata.get("source_pytest_output"):
        lines.append(f"- Source pytest output: `{metadata['source_pytest_output']}`")
    lines.append("")
    lines.append("## Run Summary")
    lines.append("")
    lines.append(f"- Total tests: `{run_summary['total_tests']}`")
    lines.append(f"- Total duration (s): `{run_summary['total_duration_seconds']:.3f}`")
    lines.append(
        "- Outcomes: "
        f"passed={run_summary['passed']}, "
        f"failed={run_summary['failed']}, "
        f"error={run_summary['error']}, "
        f"skipped={run_summary['skipped']}, "
        f"xfailed={run_summary['xfailed']}, "
        f"xpassed={run_summary['xpassed']}"
    )
    lines.append("")
    lines.append("## Time by Top-Level Test Group")
    lines.append("")
    lines.append("| Group | Tests | Total (s) | Share (%) | Median (s) | P95 (s) |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for group_name, stats in top_level_stats.items():
        lines.append(
            f"| `{group_name}` | {stats['tests']} | {stats['total_s']:.3f} | "
            f"{stats['share_of_total_pct']:.2f} | {stats['median_s']:.3f} | {stats['p95_s']:.3f} |"
        )
    lines.append("")
    lines.append(f"## Slowest {min(top_n, len(slowest_tests))} Tests")
    lines.append("")
    lines.append("| # | Test | Duration (s) | Outcome | Markers |")
    lines.append("|---:|---|---:|---|---|")
    for index, slow_entry in enumerate(slowest_tests[:top_n], start=1):
        markers_text = (
            ", ".join(slow_entry["markers_known"]) if slow_entry["markers_known"] else "-"
        )
        lines.append(
            f"| {index} | `{slow_entry['nodeid']}` | {slow_entry['duration_s']:.3f} | "
            f"{slow_entry['outcome']} | {markers_text} |"
        )
    lines.append("")
    lines.append("## Recategorization Recommendations")
    lines.append("")
    if not recommendations:
        lines.append("- No recategorization recommendations from current thresholds.")
    else:
        for recommendation in recommendations:
            lines.append(
                f"- `{recommendation['nodeid']}`: "
                f"`{recommendation['action']}` `{recommendation['marker']}` "
                f"({recommendation['duration_s']:.3f}s) — {recommendation['reason']}"
            )
    lines.append("")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str]) -> int:
    """Run analyzer and write JSON/markdown artifacts."""
    args = parse_args(argv)

    if not args.junit_xml.exists():
        print(f"ERROR: JUnit XML file not found: {args.junit_xml}", file=sys.stderr)
        return 2

    repo_root = Path.cwd().resolve()
    known_markers = load_known_markers(args.project_config)
    marker_index = MarkerIndex(repo_root=repo_root, known_markers=known_markers)
    records, outcome_counts = parse_junit_records(args.junit_xml, marker_index)

    total_duration_s = sum(record.duration_s for record in records)
    sorted_by_duration = sorted(records, key=lambda record: record.duration_s, reverse=True)
    top_n = max(args.top_n, 1)

    recommendations = build_recommendations(
        records=records,
        slow_threshold_s=args.slow_threshold_s,
        benchmark_threshold_s=args.benchmark_threshold_s,
        slow_unmark_threshold_s=args.slow_unmark_threshold_s,
    )

    report: dict[str, Any] = {
        "metadata": {
            "generated_at_utc": datetime.now(tz=UTC).isoformat(),
            "analyzer_version": "1",
            "source_junit_xml": str(args.junit_xml),
            "source_pytest_output": str(args.pytest_output) if args.pytest_output else None,
            "platform": platform.platform(),
            "python_version": sys.version.split()[0],
            "pytest_version": pytest_version(),
            "git_hash": git_hash(repo_root),
            "known_markers": sorted(known_markers),
            "thresholds": {
                "slow_threshold_s": args.slow_threshold_s,
                "benchmark_threshold_s": args.benchmark_threshold_s,
                "slow_unmark_threshold_s": args.slow_unmark_threshold_s,
            },
        },
        "run_summary": {
            "total_tests": len(records),
            "total_duration_seconds": round(total_duration_s, 6),
            "passed": outcome_counts.get("passed", 0),
            "failed": outcome_counts.get("failed", 0),
            "error": outcome_counts.get("error", 0),
            "skipped": outcome_counts.get("skipped", 0),
            "xfailed": outcome_counts.get("xfailed", 0),
            "xpassed": outcome_counts.get("xpassed", 0),
        },
        "tests": [
            {
                "nodeid": record.nodeid,
                "file": record.file,
                "top_level_group": record.top_level_group,
                "class_name": record.class_name,
                "test_name": record.test_name,
                "duration_s": round(record.duration_s, 6),
                "outcome": record.outcome,
                "markers_known": record.markers_known,
            }
            for record in records
        ],
        "groups": build_group_stats(records, total_duration_s),
        "slowest_tests": [
            {
                "nodeid": record.nodeid,
                "duration_s": round(record.duration_s, 6),
                "outcome": record.outcome,
                "markers_known": record.markers_known,
            }
            for record in sorted_by_duration[:top_n]
        ],
        "recommendations": recommendations,
    }

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2), encoding="utf-8")

    if args.output_summary is not None:
        write_summary_markdown(args.output_summary, report, top_n=top_n)

    print(f"Wrote timing report JSON: {args.output_json}")
    if args.output_summary is not None:
        print(f"Wrote timing summary markdown: {args.output_summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
