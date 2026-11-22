"""Compare RandomForest discretization benchmark runs and generate HTML reports.

Reads the JSONL produced by ``randomforest_discretization_benchmark.py`` and:

* Prints a textual summary: per-dataset best configs, Pareto-optimal points,
  and a verdict addressing the three headline questions from the framing.
* With ``--plots`` writes three interactive HTML reports to ``.benchmarks/reports/``:
  - ``rf_quality_vs_bins.html``       — quality vs n_bins, one line per variant
  - ``rf_speed_vs_bins.html``         — speed metric vs n_bins per variant
  - ``rf_speed_quality_pareto.html``  — scatter with Pareto frontier marked
"""

import operator
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, Literal, TypeAlias

import attrs
import cyclopts
import orjson

SpeedMetric: TypeAlias = Literal["total_time", "rf_fit_time", "disc_fit_time", "disc_transform_time", "rf_predict_time"]
DEFAULT_INPUT = Path(".benchmarks/randomforest_discretization_runs.jsonl")
DEFAULT_PLOT_DIR = Path(".benchmarks/reports")
DEFAULT_SPEED_METRIC: SpeedMetric = "total_time"


VARIANT_COLORS: dict[str, str] = {
    "none": "#2ca02c",
    "quantile": "#1f77b4",
    "kmeans": "#ff7f0e",
    "optimal": "#d62728",
}

try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
except ModuleNotFoundError:
    go = None
    make_subplots = None


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def load_runs(path: Path) -> list[dict[str, Any]]:
    """Load all rows from the JSONL file and flatten into a list of result records.

    Parameters
    ----------
    path : Path
        Path to the JSONL benchmark output file.

    Returns
    -------
    list of dict
        Every individual ``(dataset, variant, n_bins, rf_params)`` result row,
        augmented with top-level metadata from the run (timestamp, commit, etc.).

    Raises
    ------
    FileNotFoundError
        If ``path`` does not exist.
    ValueError
        If any line in the file is not valid JSON.

    """
    if not path.exists():
        msg = f"Input file does not exist: {path}"
        raise FileNotFoundError(msg)

    all_rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line_number, raw_line in enumerate(fh, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = orjson.loads(line)
            except orjson.JSONDecodeError as err:
                msg = f"Invalid JSON at line {line_number} in {path}: {err}"
                raise ValueError(msg) from err

            meta_keys = {
                "timestamp_utc",
                "commit",
                "repeats",
                "cv_folds",
                "cv_repeats",
                "seed",
                "platform",
                "python_version",
                "sklearn_version",
                "numpy_version",
                "package_version",
                "timing_method",
                "n_bins_sweep",
                "n_estimators_grid",
                "max_depth_grid",
                "n_jobs",
            }
            run_meta = {k: payload.get(k) for k in meta_keys}

            results: dict[str, list[dict[str, Any]]] = payload.get("results", {})
            for ds_name, ds_rows in results.items():
                all_rows.extend({**run_meta, **row, "dataset": ds_name} for row in ds_rows)

    return all_rows


# ---------------------------------------------------------------------------
# Pareto analysis
# ---------------------------------------------------------------------------


def pareto_front(
    points: list[dict[str, Any]],
    speed_key: str,
    quality_key: str,
    *,
    higher_quality_better: bool = True,
) -> list[bool]:
    """Compute the non-dominated (Pareto-optimal) set for speed vs quality.

    A point *p* is dominated if there exists another point *q* such that
    *q* is at least as good on quality AND strictly better on speed (lower),
    or strictly better on quality and at least as good on speed.

    Parameters
    ----------
    points : list of dict
        Each dict must contain ``speed_key`` and ``quality_key``.
    speed_key : str
        Metric to minimise (lower is faster).
    quality_key : str
        Metric to potentially maximise or minimise depending on
        ``higher_quality_better``.
    higher_quality_better : bool
        When True, higher quality values are better (e.g. ROC-AUC, R²).
        When False, lower quality values are better (e.g. RMSE).

    Returns
    -------
    list of bool
        ``is_pareto[i]`` is True iff ``points[i]`` is non-dominated.

    """
    n = len(points)
    is_pareto = [True] * n

    for i in range(n):
        if not is_pareto[i]:
            continue
        si = points[i][speed_key]
        qi = points[i][quality_key]
        for j in range(n):
            if i == j or not is_pareto[j]:
                continue
            sj = points[j][speed_key]
            qj = points[j][quality_key]
            # Does j dominate i?
            if higher_quality_better:
                j_dominates_i = (sj <= si and qj >= qi) and (sj < si or qj > qi)
            else:
                j_dominates_i = (sj <= si and qj <= qi) and (sj < si or qj < qi)
            if j_dominates_i:
                is_pareto[i] = False
                break

    return is_pareto


# ---------------------------------------------------------------------------
# Aggregation helpers
# ---------------------------------------------------------------------------


def aggregate_by_key(
    rows: list[dict[str, Any]],
    group_keys: list[str],
    agg_keys: list[str],
) -> list[dict[str, Any]]:
    """Group rows and compute mean of numeric agg_keys within each group.

    Parameters
    ----------
    rows : list of dict
        Flat list of result records.
    group_keys : list of str
        Keys to group by.
    agg_keys : list of str
        Numeric keys to average within each group.

    Returns
    -------
    list of dict
        One aggregated record per unique combination of group_keys.

    """
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for row in rows:
        key = tuple(row.get(k) for k in group_keys)
        groups.setdefault(key, []).append(row)

    aggregated: list[dict[str, Any]] = []
    for key_vals, group_rows in groups.items():
        record: dict[str, Any] = dict(zip(group_keys, key_vals, strict=True))
        for agg_key in agg_keys:
            values = [r[agg_key] for r in group_rows if agg_key in r]
            if values:
                record[agg_key] = float(sum(values) / len(values))
        aggregated.append(record)

    return aggregated


QUALITY_KEYS = {"classification": "roc_auc_mean", "regression": "r2_mean"}
"""The primary quality metric of each task. Both are higher-is-better."""
QUALITY_LABELS = {"classification": "ROC-AUC", "regression": "R²"}
EXTRA_QUALITY_KEYS = {"classification": ["accuracy_mean", "macro_f1_mean"], "regression": ["rmse_mean"]}
DISCRETIZED_VARIANTS = ["quantile", "kmeans", "optimal"]
DEFAULT_N_BINS_FOR_PLOT = [2, 4, 8, 16, 32, 64]


def primary_quality_key(task: str) -> str:
    """Return the primary quality metric of a task.

    Parameters
    ----------
    task : str
        Either ``"classification"`` or ``"regression"``.

    Returns
    -------
    str
        The key of the metric in the aggregated records.

    """
    return QUALITY_KEYS.get(task, "r2_mean")


@attrs.frozen
class DatasetView:
    """The records of one dataset, aggregated over the forest grid for each variant and bin count.

    Attributes
    ----------
    name : str
        The dataset.
    task : str
        ``"classification"`` or ``"regression"``.
    quality_key : str
        The primary quality metric.
    aggregated : list of dict
        One record for each variant and bin count, with the mean of each metric.

    """

    name: str
    task: str
    quality_key: str
    aggregated: list[dict[str, Any]]

    @property
    def quality_label(self) -> str:
        """The name of the primary quality metric, for the text and the plots."""
        return QUALITY_LABELS.get(self.task, "R²")

    def variant_by_bins(self, variant: str) -> dict[Any, dict[str, Any]]:
        """Return the records of one variant, by bin count.

        Parameters
        ----------
        variant : str
            The variant.

        Returns
        -------
        dict
            The records of the variant, by bin count.

        """
        return {record["n_bins"]: record for record in self.aggregated if record["variant"] == variant}

    def best_of(self, variant: str) -> dict[str, Any] | None:
        """Return the record of a variant with the best quality.

        Parameters
        ----------
        variant : str
            The variant.

        Returns
        -------
        dict or None
            The record, or ``None`` if the variant has no record.

        """
        records = [record for record in self.aggregated if record["variant"] == variant]
        return max(records, key=operator.itemgetter(self.quality_key)) if records else None


def dataset_views(rows: Sequence[dict[str, Any]], speed_key: str) -> list[DatasetView]:
    """Aggregate the records of each dataset over the forest grid.

    Parameters
    ----------
    rows : Sequence of dict
        All result records.
    speed_key : str
        The speed metric to aggregate.

    Returns
    -------
    list of DatasetView
        One view for each dataset, sorted by name. A record without the quality or the speed metric is left out.

    """
    views: list[DatasetView] = []
    for name in sorted({row["dataset"] for row in rows}):
        dataset_rows = [row for row in rows if row["dataset"] == name]
        task = dataset_rows[0].get("task", "unknown")
        quality_key = primary_quality_key(task)
        metrics = [speed_key, quality_key, *EXTRA_QUALITY_KEYS.get(task, []), "disc_fit_time_mean"]
        aggregated = aggregate_by_key(dataset_rows, ["variant", "n_bins"], metrics)
        aggregated = [record for record in aggregated if quality_key in record and speed_key in record]
        views.append(DatasetView(name=name, task=task, quality_key=quality_key, aggregated=aggregated))
    return views


def _bins_text(record: dict[str, Any]) -> str:
    """Return the bin count of a record as text, ``N/A`` for the variant without bins.

    Returns
    -------
    str
        The text.

    """
    return "N/A" if record.get("n_bins") is None else str(record["n_bins"])


# ---------------------------------------------------------------------------
# Textual summary
# ---------------------------------------------------------------------------


def _write_pareto(view: DatasetView, speed_key: str, speed_metric: str) -> None:
    """Write the configs on the Pareto front of speed and quality."""
    flags = pareto_front(view.aggregated, speed_key=speed_key, quality_key=view.quality_key)
    front = sorted(
        (record for record, flag in zip(view.aggregated, flags, strict=True) if flag),
        key=operator.itemgetter(view.quality_key),
        reverse=True,
    )
    sys.stdout.write(f"  Pareto-optimal configs (speed={speed_metric}, quality={view.quality_label}):\n")
    for record in front:
        sys.stdout.write(
            f"    variant={record['variant']:10s}  n_bins={_bins_text(record):4s}  "
            f"{view.quality_label}={record[view.quality_key]:.4f}  {speed_metric}={record[speed_key]:.4f}s\n",
        )
    if not front:
        sys.stdout.write("    (none found)\n")
    sys.stdout.write("\n")


def _write_best_per_variant(view: DatasetView, speed_key: str, speed_metric: str) -> None:
    """Write the bin count with the best quality of each variant."""
    sys.stdout.write(f"  Best {view.quality_label} per variant (mean across RF grid):\n")
    for variant in sorted({record["variant"] for record in view.aggregated}):
        best = view.best_of(variant)
        if best is not None:
            sys.stdout.write(
                f"    {variant:10s}  best at n_bins={_bins_text(best):4s}  "
                f"{view.quality_label}={best[view.quality_key]:.4f}  {speed_metric}={best[speed_key]:.4f}s\n",
            )
    sys.stdout.write("\n")


def _wins(
    first: dict[Any, dict[str, Any]],
    second: dict[Any, dict[str, Any]],
    better: Callable[[dict[str, Any], dict[str, Any]], bool],
) -> str:
    """Count the bin counts at which the first variant is better than the second.

    Returns
    -------
    str
        ``wins/comparisons``.

    """
    common = sorted(set(first) & set(second))
    return f"{sum(1 for bins in common if better(first[bins], second[bins]))}/{len(common)}"


def _verdict_lines(view: DatasetView, speed_key: str) -> list[str]:
    """Answer the three headline questions of the benchmark for one dataset.

    Returns
    -------
    list of str
        One line for each question.

    """
    quality = view.quality_key
    optimal, kmeans, quantile = (view.variant_by_bins(name) for name in ("optimal", "kmeans", "quantile"))
    lines = []
    if set(optimal) & set(kmeans):
        quality_wins = _wins(optimal, kmeans, lambda first, second: first[quality] > second[quality])
        speed_wins = _wins(optimal, kmeans, lambda first, second: first[speed_key] < second[speed_key])
        lines.append(
            f"1. optimal vs kmeans: optimal wins quality in {quality_wins} bin-count comparisons; "
            f"wins speed in {speed_wins} comparisons.",
        )
    else:
        lines.append("1. optimal vs kmeans: insufficient data for comparison.")
    common = sorted(set(optimal) & set(quantile))
    if common:
        quality_wins = _wins(optimal, quantile, lambda first, second: first[quality] > second[quality])
        quantile_cost = sum(quantile[bins].get("disc_fit_time_mean", 0.0) for bins in common) / len(common)
        optimal_cost = sum(optimal[bins].get("disc_fit_time_mean", 0.0) for bins in common) / len(common)
        lines.append(
            f"2. optimal vs quantile: optimal wins quality in {quality_wins} comparisons; mean disc_fit_time: "
            f"quantile={quantile_cost:.4f}s optimal={optimal_cost:.4f}s.",
        )
    else:
        lines.append("2. optimal vs quantile: insufficient data.")
    lines.append(_verdict_versus_none(view))
    return lines


def _verdict_versus_none(view: DatasetView) -> str:
    """Tell whether a discretized variant beats the forest on the raw features.

    Returns
    -------
    str
        The line of the third question.

    """
    baseline = view.best_of("none")
    if baseline is None:
        return "3. 'none' variant not present; cannot compare."
    baseline_quality = baseline[view.quality_key]
    winners = [
        f"{variant}@n_bins={_bins_text(best)}({best[view.quality_key]:.4f})"
        for variant in DISCRETIZED_VARIANTS
        if (best := view.best_of(variant)) is not None and best[view.quality_key] > baseline_quality
    ]
    if winners:
        return f"3. Discretized variants beating none ({view.quality_label}={baseline_quality:.4f}): " + ", ".join(
            winners,
        )
    return (
        f"3. No discretized variant beats none ({view.quality_label}={baseline_quality:.4f}); "
        "pre-discretization does not help quality on this dataset."
    )


def print_summary(rows: list[dict[str, Any]], speed_metric: str) -> None:
    """Print the summary of each dataset: the Pareto front, the best bin counts and the verdict.

    Parameters
    ----------
    rows : list of dict
        All result records loaded from the JSONL file.
    speed_metric : str
        The speed metric of the Pareto analysis.

    """
    sys.stdout.write(f"Loaded records: {len(rows)}\n")
    if not rows:
        sys.stdout.write("No records found.\n")
        return
    speed_key = f"{speed_metric}_mean"
    views = dataset_views(rows, speed_key)
    sys.stdout.write(f"Datasets: {', '.join(view.name for view in views)}\n\n")
    for view in views:
        sys.stdout.write(f"═══ {view.name} ({view.task}) ═══\n")
        if not view.aggregated:
            sys.stdout.write("  No aggregated data available.\n\n")
            continue
        _write_pareto(view, speed_key, speed_metric)
        _write_best_per_variant(view, speed_key, speed_metric)
        sys.stdout.write("  Verdict:\n")
        for line in _verdict_lines(view, speed_key):
            sys.stdout.write(f"    {line}\n")
        sys.stdout.write("\n")


# ---------------------------------------------------------------------------
# Plot generation
# ---------------------------------------------------------------------------


def _line_points(
    view: DatasetView,
    variant: str,
    value_key: str,
    *,
    expand_none: bool,
) -> tuple[list[Any], list[float]]:
    """Return the points of the line of one variant: the bin counts and the values.

    The variant ``none`` has no bin count. With ``expand_none``, it becomes a flat line over the bin counts of the
    other variants, so that the plot compares each variant with the forest on the raw features.

    Returns
    -------
    tuple of (list, list)
        The bin counts and the values.

    """
    if variant == "none":
        baseline = view.best_of("none")
        if not expand_none or baseline is None:
            return [], []
        bins = sorted({record["n_bins"] for record in view.aggregated if record.get("n_bins") is not None})
        bins = bins or DEFAULT_N_BINS_FOR_PLOT
        return bins, [baseline[value_key]] * len(bins)
    points = sorted(view.variant_by_bins(variant).items(), key=operator.itemgetter(0))
    return [bins for bins, _ in points], [record[value_key] for _, record in points]


def _line_figure(
    views: Sequence[DatasetView],
    title: str,
    value_key: Callable[[DatasetView], str],
    value_label: Callable[[DatasetView], str],
    *,
    expand_none: bool,
) -> Any:  # ruff: ignore[any-type] -- a plotly figure; plotly is an optional dependency and is not typed
    """Build a figure with one subplot for each dataset and one line for each variant.

    Returns
    -------
    plotly.graph_objects.Figure
        The figure.

    """
    figure = make_subplots(rows=max(1, len(views)), cols=1, subplot_titles=[view.name for view in views])
    for row_index, view in enumerate(views, start=1):
        for variant in sorted({record["variant"] for record in view.aggregated}):
            bins, values = _line_points(view, variant, value_key(view), expand_none=expand_none)
            if not bins:
                continue
            figure.add_trace(
                go.Scatter(
                    x=bins,
                    y=values,
                    mode="lines+markers",
                    name=variant,
                    line={"color": VARIANT_COLORS.get(variant)},
                    marker={"size": 7},
                    legendgroup=variant,
                    showlegend=row_index == 1,
                    hovertemplate=f"n_bins=%{{x}}<br>{value_label(view)}=%{{y:.4f}}<extra>{variant}</extra>",
                ),
                row=row_index,
                col=1,
            )
        figure.update_yaxes(title_text=value_label(view), row=row_index, col=1)
        figure.update_xaxes(title_text="n_bins", row=row_index, col=1)
    figure.update_layout(title=title, height=350 * max(1, len(views)))
    return figure


def _pareto_traces(view: DatasetView, speed_key: str, speed_metric: str, *, first_row: bool) -> list[Any]:
    """Return the scatter traces of one dataset: the configs off the Pareto front, faint, and those on it, as stars.

    Returns
    -------
    list of plotly.graph_objects.Scatter
        The traces.

    """
    flags = pareto_front(view.aggregated, speed_key=speed_key, quality_key=view.quality_key)
    traces = []
    for variant in sorted(VARIANT_COLORS):
        for on_front in (False, True):
            points = [
                record
                for record, flag in zip(view.aggregated, flags, strict=True)
                if record["variant"] == variant and flag == on_front
            ]
            if not points:
                continue
            marker: dict[str, Any] = {"color": VARIANT_COLORS[variant], "size": 8, "opacity": 0.4}
            if on_front:
                marker = {"color": VARIANT_COLORS[variant], "size": 14, "symbol": "star", "line": {"width": 1}}
            name = f"{variant} (Pareto)" if on_front else variant
            traces.append(
                go.Scatter(
                    x=[record[speed_key] for record in points],
                    y=[record[view.quality_key] for record in points],
                    mode="markers",
                    name=name,
                    marker=marker,
                    legendgroup=name,
                    showlegend=first_row,
                    text=[_bins_text(record) for record in points],
                    hovertemplate=f"{speed_metric}=%{{x:.4f}}<br>{view.quality_label}=%{{y:.4f}}"
                    f"<br>n_bins=%{{text}}<extra>{name}</extra>",
                ),
            )
    return traces


def generate_plots(rows: list[dict[str, Any]], plot_dir: Path, speed_metric: str) -> list[Path]:
    """Write the interactive HTML plots: quality and speed against the bin count, and the Pareto front.

    Parameters
    ----------
    rows : list of dict
        All result records.
    plot_dir : Path
        Directory in which to write HTML files.
    speed_metric : str
        Speed metric to show on speed plots and Pareto x-axis.

    Returns
    -------
    list of Path
        Paths of written HTML files. The list is empty if plotly is not installed or there are no records.

    """
    if go is None:
        sys.stdout.write("\nSkipping plots: plotly is not installed.\n")
        return []
    if not rows:
        return []
    plot_dir.mkdir(parents=True, exist_ok=True)
    speed_key = f"{speed_metric}_mean"
    views = dataset_views(rows, speed_key)
    figures = {
        "rf_quality_vs_bins.html": _line_figure(
            views,
            "RF Quality vs n_bins by Variant",
            lambda view: view.quality_key,
            lambda view: view.quality_label,
            expand_none=True,
        ),
        "rf_speed_vs_bins.html": _line_figure(
            views,
            f"RF {speed_metric} vs n_bins by Variant",
            lambda _: speed_key,
            lambda _: f"{speed_metric} (s)",
            expand_none=False,
        ),
    }
    pareto = make_subplots(rows=max(1, len(views)), cols=1, subplot_titles=[view.name for view in views])
    for row_index, view in enumerate(views, start=1):
        for trace in _pareto_traces(view, speed_key, speed_metric, first_row=row_index == 1):
            pareto.add_trace(trace, row=row_index, col=1)
        pareto.update_xaxes(title_text=f"{speed_metric} (s)", row=row_index, col=1)
        pareto.update_yaxes(title_text=view.quality_label, row=row_index, col=1)
    pareto.update_layout(
        title=f"RF Speed-Quality Pareto Frontier (speed={speed_metric})",
        height=450 * max(1, len(views)),
    )
    figures["rf_speed_quality_pareto.html"] = pareto
    written = []
    for file_name, figure in figures.items():
        figure.write_html(plot_dir / file_name, include_plotlyjs="cdn")
        written.append(plot_dir / file_name)
    return written


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

app: cyclopts.App = cyclopts.App(
    name="randomforest_discretization_compare",
    help=__doc__.splitlines()[0] if __doc__ else None,
    result_action="return_value",
)


@app.default
def main(
    *,
    input_path: Path = DEFAULT_INPUT,
    plot_dir: Path = DEFAULT_PLOT_DIR,
    plots: bool = False,
    speed_metric: SpeedMetric = DEFAULT_SPEED_METRIC,
) -> int:
    """Compare the benchmark runs, and write interactive HTML plots.

    Parameters
    ----------
    input_path : Path
        The JSONL file that benchmarks/randomforest_discretization_benchmark.py writes.
    plot_dir : Path
        The directory for the interactive HTML plots.
    plots : bool
        Write the plots.
    speed_metric : str
        The speed metric of the Pareto analysis and of the speed plots.

    Returns
    -------
    int
        0 when the comparison is done.

    """
    rows = load_runs(input_path)
    print_summary(rows, speed_metric=speed_metric)
    if plots:
        written_plots = generate_plots(rows=rows, plot_dir=plot_dir, speed_metric=speed_metric)
        if written_plots:
            sys.stdout.write("\nWrote interactive plots:\n")
            for path in written_plots:
                sys.stdout.write(f"  - {path}\n")
    return 0


if __name__ == "__main__":
    sys.exit(app())
