"""Compare k-means effectiveness benchmark runs and generate HTML reports."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path

DEFAULT_INPUT = Path(".benchmarks/kmeans_effectiveness_runs.jsonl")
DEFAULT_PLOT_DIR = Path(".benchmarks/reports")
OPTIMALITY_TARGET = 100.0
MIN_RUNS_FOR_DELTA = 2

try:
    import plotly.graph_objects as go
except ModuleNotFoundError:
    go = None


@dataclass(slots=True)
class RunSummary:
    """Parsed benchmark run payload with computed convenience fields."""

    timestamp_utc: str
    timestamp: dt.datetime
    commit: str
    repeats: int
    problems: dict[str, dict[str, dict[str, float]]]

    @property
    def short_commit(self) -> str:
        """Return short commit hash for compact labels."""
        return self.commit[:7] if self.commit != "unknown" else "unknown"

    @property
    def label(self) -> str:
        """Return compact identifier for logs and plots."""
        stamp = self.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        return f"{stamp} | {self.short_commit}"

    @property
    def main_mean_ms(self) -> float:
        """Return average main mean_ms across benchmark problems."""
        values = [problem_metrics["main"]["mean_ms"] for problem_metrics in self.problems.values()]
        return statistics.fmean(values)

    @property
    def main_mean_gap_pct(self) -> float:
        """Return average main mean_gap_pct across benchmark problems."""
        values = [problem_metrics["main"]["mean_gap_pct"] for problem_metrics in self.problems.values()]
        return statistics.fmean(values)

    @property
    def main_optimality_min_pct(self) -> float:
        """Return minimum main optimality across benchmark problems."""
        values = [problem_metrics["main"]["optimality_pct"] for problem_metrics in self.problems.values()]
        return min(values)

    @property
    def lloyd_optimality_mean_pct(self) -> float:
        """Return average Lloyd optimality across benchmark problems."""
        values = [problem_metrics["lloyd"]["optimality_pct"] for problem_metrics in self.problems.values()]
        return statistics.fmean(values)


def parse_args() -> argparse.Namespace:
    """Parse command-line options for benchmark run comparison."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help="JSONL file produced by benchmarks/kmeans_effectiveness_benchmark.py.",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=5,
        help="How many top qualified runs to print in the ranking.",
    )
    parser.add_argument(
        "--plot-dir",
        type=Path,
        default=DEFAULT_PLOT_DIR,
        help="Directory where interactive HTML plots are written.",
    )
    parser.add_argument(
        "--plots",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Generate interactive HTML plots (default: true).",
    )
    return parser.parse_args()


def load_runs(path: Path) -> list[RunSummary]:
    """Load benchmark runs from JSONL and sort by timestamp."""
    if not path.exists():
        msg = f"Input file does not exist: {path}"
        raise FileNotFoundError(msg)

    loaded: list[RunSummary] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            payload = json.loads(line)
            try:
                timestamp_utc = str(payload["timestamp_utc"])
                timestamp = dt.datetime.fromisoformat(timestamp_utc)
                run = RunSummary(
                    timestamp_utc=timestamp_utc,
                    timestamp=timestamp,
                    commit=str(payload["commit"]),
                    repeats=int(payload["repeats"]),
                    problems=dict(payload["problems"]),
                )
            except (KeyError, TypeError, ValueError) as error:
                msg = f"Invalid run payload at line {line_number} in {path}: {error}"
                raise ValueError(msg) from error
            loaded.append(run)

    loaded.sort(key=lambda run: run.timestamp)
    return loaded


def is_main_fully_optimal(run: RunSummary) -> bool:
    """Return true when main is effectively 100% optimal on all problems."""
    return all(
        math.isclose(problem_metrics["main"]["optimality_pct"], OPTIMALITY_TARGET, rel_tol=0.0, abs_tol=1e-9)
        for problem_metrics in run.problems.values()
    )


def print_summary(runs: list[RunSummary], top: int) -> None:
    """Print compact ranking and regression summary."""
    qualified_runs = sorted((run for run in runs if is_main_fully_optimal(run)), key=lambda run: run.main_mean_ms)

    sys.stdout.write(f"Loaded runs: {len(runs)}\n")
    sys.stdout.write(f"Qualified (main optimality=100% on all problems): {len(qualified_runs)}\n\n")

    if not runs:
        sys.stdout.write("No runs found.\n")
        return

    if qualified_runs:
        winner = qualified_runs[0]
        sys.stdout.write("Best qualified run:\n")
        sys.stdout.write(
            "  "
            f"{winner.label} | "
            f"main_mean_ms={winner.main_mean_ms:.6f} | "
            f"main_mean_gap_pct={winner.main_mean_gap_pct:.6f} | "
            f"main_min_optimality={winner.main_optimality_min_pct:.2f}%\n\n",
        )

        sys.stdout.write("Top qualified runs (lower main_mean_ms is better):\n")
        sys.stdout.write(
            "rank | timestamp_utc | commit | main_mean_ms | main_mean_gap_pct | "
            "main_min_optimality | lloyd_mean_optimality\n",
        )
        for index, run in enumerate(qualified_runs[: max(top, 1)], start=1):
            sys.stdout.write(
                f"{index} | {run.timestamp_utc} | {run.short_commit} | "
                f"{run.main_mean_ms:.6f} | {run.main_mean_gap_pct:.6f} | "
                f"{run.main_optimality_min_pct:.2f}% | {run.lloyd_optimality_mean_pct:.2f}%\n",
            )
        sys.stdout.write("\n")
    else:
        sys.stdout.write("No qualified runs match the 'main must stay at 100% optimality' rule.\n\n")

    if len(runs) >= MIN_RUNS_FOR_DELTA:
        previous, latest = runs[-2], runs[-1]
        delta_ms = latest.main_mean_ms - previous.main_mean_ms
        delta_gap = latest.main_mean_gap_pct - previous.main_mean_gap_pct
        speed_direction = "faster" if delta_ms < 0 else "slower" if delta_ms > 0 else "equal"
        gap_direction = "better" if delta_gap < 0 else "worse" if delta_gap > 0 else "equal"

        sys.stdout.write("Latest vs previous (main mean across problems):\n")
        sys.stdout.write(f"  previous: {previous.label} | {previous.main_mean_ms:.6f} ms\n")
        sys.stdout.write(f"  latest  : {latest.label} | {latest.main_mean_ms:.6f} ms\n")
        sys.stdout.write(f"  delta   : {delta_ms:+.6f} ms ({speed_direction})\n")
        sys.stdout.write(
            "Latest vs previous (main mean gap across problems):\n"
            f"  previous: {previous.main_mean_gap_pct:.6f}%\n"
            f"  latest  : {latest.main_mean_gap_pct:.6f}%\n"
            f"  delta   : {delta_gap:+.6f}% ({gap_direction})\n",
        )


def generate_plots(runs: list[RunSummary], plot_dir: Path) -> list[Path]:
    """Generate interactive HTML plots and return written paths."""
    if go is None:
        sys.stdout.write("\nSkipping plots: plotly is not installed.\n")
        return []

    if not runs:
        return []

    plot_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    labels = [run.label for run in runs]

    speed_colors = ["#1f77b4" if is_main_fully_optimal(run) else "#d62728" for run in runs]
    speed_trend = go.Figure()
    speed_trend.add_trace(
        go.Scatter(
            x=labels,
            y=[run.main_mean_ms for run in runs],
            mode="lines+markers",
            marker={"size": 10, "color": speed_colors},
            line={"width": 2, "color": "#6c757d"},
            text=["qualified" if is_main_fully_optimal(run) else "not qualified" for run in runs],
            hovertemplate="run=%{x}<br>main_mean_ms=%{y:.6f}<br>status=%{text}<extra></extra>",
            name="main_mean_ms",
        ),
    )
    speed_trend.update_layout(
        title="Main Algorithm Speed Across Runs",
        xaxis_title="run",
        yaxis_title="avg main mean_ms across problems",
    )

    speed_path = plot_dir / "kmeans_main_speed_trend.html"
    speed_trend.write_html(speed_path, include_plotlyjs="cdn")
    written.append(speed_path)

    optimality = go.Figure()
    optimality.add_trace(
        go.Scatter(
            x=labels,
            y=[run.main_optimality_min_pct for run in runs],
            mode="lines+markers",
            marker={"size": 8, "color": "#1f77b4"},
            line={"width": 2, "color": "#1f77b4"},
            name="main min optimality %",
            hovertemplate="run=%{x}<br>main_min_optimality=%{y:.2f}%<extra></extra>",
        ),
    )
    optimality.add_trace(
        go.Scatter(
            x=labels,
            y=[run.lloyd_optimality_mean_pct for run in runs],
            mode="lines+markers",
            marker={"size": 8, "color": "#ff7f0e"},
            line={"width": 2, "color": "#ff7f0e"},
            name="lloyd mean optimality %",
            hovertemplate="run=%{x}<br>lloyd_mean_optimality=%{y:.2f}%<extra></extra>",
        ),
    )
    optimality.update_layout(
        title="Optimality Trend: Main vs Lloyd",
        xaxis_title="run",
        yaxis_title="optimality %",
    )

    optimality_path = plot_dir / "kmeans_optimality_trend.html"
    optimality.write_html(optimality_path, include_plotlyjs="cdn")
    written.append(optimality_path)

    problem_names = list(runs[-1].problems)
    latest = runs[-1]
    breakdown = go.Figure()
    breakdown.add_trace(
        go.Bar(
            x=problem_names,
            y=[latest.problems[problem]["main"]["mean_gap_pct"] for problem in problem_names],
            name="main mean gap %",
            marker={"color": "#1f77b4"},
        ),
    )
    breakdown.add_trace(
        go.Bar(
            x=problem_names,
            y=[latest.problems[problem]["lloyd"]["mean_gap_pct"] for problem in problem_names],
            name="lloyd mean gap %",
            marker={"color": "#ff7f0e"},
        ),
    )
    breakdown.update_layout(
        title="Latest Run Mean Gap by Problem",
        xaxis_title="problem",
        yaxis_title="mean gap % vs brute-force optimum",
        barmode="group",
    )

    breakdown_path = plot_dir / "kmeans_latest_gap_breakdown.html"
    breakdown.write_html(breakdown_path, include_plotlyjs="cdn")
    written.append(breakdown_path)

    return written


def main() -> None:
    """Execute run comparison and optionally generate plots."""
    args = parse_args()
    runs = load_runs(args.input)
    print_summary(runs, top=args.top)

    if args.plots:
        written_plots = generate_plots(runs=runs, plot_dir=args.plot_dir)
        if written_plots:
            sys.stdout.write("\nWrote interactive plots:\n")
            for path in written_plots:
                sys.stdout.write(f"  - {path}\n")


if __name__ == "__main__":
    main()
