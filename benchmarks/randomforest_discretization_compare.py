"""Compare RandomForest discretization benchmark runs and generate HTML reports.

Reads the JSONL produced by ``randomforest_discretization_benchmark.py`` and:

* Prints a textual summary: per-dataset best configs, Pareto-optimal points,
  and a verdict addressing the three headline questions from the framing.
* With ``--plots`` writes three interactive HTML reports to ``.benchmarks/reports/``:
  - ``rf_quality_vs_bins.html``       — quality vs n_bins, one line per variant
  - ``rf_speed_vs_bins.html``         — speed metric vs n_bins per variant
  - ``rf_speed_quality_pareto.html``  — scatter with Pareto frontier marked
"""

from __future__ import annotations

import argparse
import json
import operator
import sys
from pathlib import Path
from typing import Any

DEFAULT_INPUT = Path(".benchmarks/randomforest_discretization_runs.jsonl")
DEFAULT_PLOT_DIR = Path(".benchmarks/reports")
DEFAULT_SPEED_METRIC = "total_time"

SPEED_METRIC_CHOICES = [
    "total_time",
    "rf_fit_time",
    "disc_fit_time",
    "disc_transform_time",
    "rf_predict_time",
]

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
    go = None  # type: ignore[assignment]
    make_subplots = None  # type: ignore[assignment]


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
                payload = json.loads(line)
            except json.JSONDecodeError as err:
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


def primary_quality_key(task: str) -> str:
    """Return the primary quality metric key for a given task.

    Parameters
    ----------
    task : str
        Either ``"classification"`` or ``"regression"``.

    Returns
    -------
    str
        Key name in the aggregated records.
    """
    if task == "classification":
        return "roc_auc_mean"
    return "r2_mean"


def quality_higher_better(task: str) -> bool:  # noqa: ARG001
    """Return True iff the primary quality metric is higher-is-better.

    Parameters
    ----------
    task : str
        Either ``"classification"`` or ``"regression"``.

    Returns
    -------
    bool
        True for classification (ROC-AUC) and regression R².
    """
    return True  # both roc_auc and r2 are higher-better


# ---------------------------------------------------------------------------
# Textual summary
# ---------------------------------------------------------------------------


def print_summary(rows: list[dict[str, Any]], speed_metric: str) -> None:  # noqa: C901, PLR0912, PLR0914, PLR0915
    """Print per-dataset textual summary and Pareto-optimal configurations.

    Parameters
    ----------
    rows : list of dict
        All result records loaded from the JSONL file.
    speed_metric : str
        The speed metric to use for Pareto analysis.
    """
    sys.stdout.write(f"Loaded records: {len(rows)}\n")
    if not rows:
        sys.stdout.write("No records found.\n")
        return

    datasets = sorted({r["dataset"] for r in rows})
    sys.stdout.write(f"Datasets: {', '.join(datasets)}\n\n")

    speed_key = f"{speed_metric}_mean"

    for ds_name in datasets:
        ds_rows = [r for r in rows if r["dataset"] == ds_name]
        task = ds_rows[0].get("task", "unknown")
        q_key = primary_quality_key(task)
        higher = quality_higher_better(task)
        q_label = "ROC-AUC" if task == "classification" else "R²"

        sys.stdout.write(f"═══ {ds_name} ({task}) ═══\n")

        # Aggregate over RF hyperparameter grid (mean across n_estimators x max_depth)
        agg_keys = [speed_key, q_key]
        if task == "classification":
            agg_keys += ["accuracy_mean", "macro_f1_mean"]
        else:
            agg_keys += ["rmse_mean"]

        agg = aggregate_by_key(ds_rows, ["variant", "n_bins"], agg_keys)
        agg = [a for a in agg if q_key in a and speed_key in a]

        if not agg:
            sys.stdout.write("  No aggregated data available.\n\n")
            continue

        # --- Pareto analysis ---
        is_pareto = pareto_front(agg, speed_key=speed_key, quality_key=q_key, higher_quality_better=higher)
        pareto_points = [p for p, flag in zip(agg, is_pareto, strict=True) if flag]
        pareto_points_sorted = sorted(pareto_points, key=operator.itemgetter(q_key), reverse=higher)

        sys.stdout.write(f"  Pareto-optimal configs (speed={speed_metric}, quality={q_label}):\n")
        if pareto_points_sorted:
            for pt in pareto_points_sorted:
                nb = pt.get("n_bins")
                nb_str = str(nb) if nb is not None else "N/A"
                sys.stdout.write(
                    f"    variant={pt['variant']:10s}  n_bins={nb_str:4s}  "
                    f"{q_label}={pt[q_key]:.4f}  {speed_metric}={pt[speed_key]:.4f}s\n",
                )
        else:
            sys.stdout.write("    (none found)\n")
        sys.stdout.write("\n")

        # --- Best per variant at each n_bins (aggregated across RF grid) ---
        sys.stdout.write(f"  Best {q_label} per variant (mean across RF grid):\n")
        variants_seen = sorted({r.get("variant") for r in ds_rows if r.get("variant")})
        for variant in variants_seen:
            variant_rows = [a for a in agg if a["variant"] == variant]
            if not variant_rows:
                continue
            best = (
                max(variant_rows, key=operator.itemgetter(q_key))
                if higher
                else min(variant_rows, key=operator.itemgetter(q_key))
            )
            nb = best.get("n_bins")
            nb_str = str(nb) if nb is not None else "N/A"
            sys.stdout.write(
                f"    {variant:10s}  best at n_bins={nb_str:4s}  "
                f"{q_label}={best[q_key]:.4f}  {speed_metric}={best[speed_key]:.4f}s\n",
            )
        sys.stdout.write("\n")

        # --- Verdict: three headline questions ---
        sys.stdout.write("  Verdict:\n")

        # Q1: optimal vs kmeans at equal n_bins
        opt_rows = {a["n_bins"]: a for a in agg if a["variant"] == "optimal"}
        km_rows = {a["n_bins"]: a for a in agg if a["variant"] == "kmeans"}
        common_bins = sorted(set(opt_rows) & set(km_rows))
        if common_bins:
            opt_wins_quality = sum(
                1
                for nb in common_bins
                if (
                    opt_rows[nb][q_key] > km_rows[nb][q_key]
                    if higher
                    else opt_rows[nb][q_key] < km_rows[nb][q_key]
                )
            )
            opt_wins_speed = sum(
                1 for nb in common_bins if opt_rows[nb][speed_key] < km_rows[nb][speed_key]
            )
            sys.stdout.write(
                f"    1. optimal vs kmeans: optimal wins quality in {opt_wins_quality}/{len(common_bins)} "
                f"bin-count comparisons; wins speed in {opt_wins_speed}/{len(common_bins)} comparisons.\n",
            )
        else:
            sys.stdout.write("    1. optimal vs kmeans: insufficient data for comparison.\n")

        # Q2: optimal/kmeans vs quantile at equal n_bins
        qt_rows = {a["n_bins"]: a for a in agg if a["variant"] == "quantile"}
        if qt_rows and opt_rows:
            common_bins_oq = sorted(set(opt_rows) & set(qt_rows))
            if common_bins_oq:
                opt_vs_qt_quality = sum(
                    1
                    for nb in common_bins_oq
                    if (
                        opt_rows[nb][q_key] > qt_rows[nb][q_key]
                        if higher
                        else opt_rows[nb][q_key] < qt_rows[nb][q_key]
                    )
                )
                qt_disc_cost = (
                    sum(qt_rows[nb].get("disc_fit_time_mean", 0.0) for nb in common_bins_oq)
                    / max(len(common_bins_oq), 1)
                )
                opt_disc_cost = (
                    sum(opt_rows[nb].get("disc_fit_time_mean", 0.0) for nb in common_bins_oq)
                    / max(len(common_bins_oq), 1)
                )
                sys.stdout.write(
                    f"    2. optimal vs quantile: optimal wins quality in {opt_vs_qt_quality}/{len(common_bins_oq)} "
                    f"comparisons; mean disc_fit_time: quantile={qt_disc_cost:.4f}s optimal={opt_disc_cost:.4f}s.\n",
                )
            else:
                sys.stdout.write("    2. optimal vs quantile: insufficient data.\n")
        else:
            sys.stdout.write("    2. optimal vs quantile: insufficient data.\n")

        # Q3: does any discretized variant beat none?
        none_rows = [a for a in agg if a["variant"] == "none"]
        if none_rows:
            none_q = none_rows[0][q_key]
            discretized_variants = ["quantile", "kmeans", "optimal"]
            beats_none: list[str] = []
            for dv in discretized_variants:
                dv_agg = [a for a in agg if a["variant"] == dv]
                best_dv = (
                    max(dv_agg, key=operator.itemgetter(q_key))
                    if (higher and dv_agg)
                    else (min(dv_agg, key=operator.itemgetter(q_key)) if dv_agg else None)
                )
                if best_dv is not None:
                    nb_str = str(best_dv.get("n_bins"))
                    if (higher and best_dv[q_key] > none_q) or (not higher and best_dv[q_key] < none_q):
                        beats_none.append(f"{dv}@n_bins={nb_str}({best_dv[q_key]:.4f})")
            if beats_none:
                sys.stdout.write(
                    f"    3. Discretized variants beating none ({q_label}={none_q:.4f}): "
                    + ", ".join(beats_none)
                    + "\n",
                )
            else:
                sys.stdout.write(
                    f"    3. No discretized variant beats none ({q_label}={none_q:.4f}); "
                    "pre-discretization does not help quality on this dataset.\n",
                )
        else:
            sys.stdout.write("    3. 'none' variant not present; cannot compare.\n")

        sys.stdout.write("\n")


def _expand_none_variant(
    agg: list[dict[str, Any]],
    q_key: str,
    x_vals: list[Any],
) -> tuple[list[Any], list[float]]:
    """Expand the 'none' variant to cover all available n_bins values for plotting.

    Parameters
    ----------
    agg : list of dict
        Aggregated records for the current dataset.
    q_key : str
        Quality metric key.
    x_vals : list
        Current x-axis values (may be empty for none variant).

    Returns
    -------
    tuple of (list, list)
        Updated ``(x_vals, y_vals)`` spanning all discretized bin counts.
    """
    none_pts = [a for a in agg if a["variant"] == "none"]
    if not none_pts:
        return x_vals, []
    none_q = none_pts[0].get(q_key)
    if none_q is None:
        return x_vals, []
    x_none = sorted({p["n_bins"] for p in agg if p.get("n_bins") is not None})
    if x_none:
        return x_none, [none_q] * len(x_none)
    return x_vals or [min(DEFAULT_N_BINS_FOR_PLOT)], [none_q]


# ---------------------------------------------------------------------------
# Plot generation
# ---------------------------------------------------------------------------

DEFAULT_N_BINS_FOR_PLOT = [2, 4, 8, 16, 32, 64]


def generate_plots(  # noqa: C901, PLR0912, PLR0914, PLR0915
    rows: list[dict[str, Any]],
    plot_dir: Path,
    speed_metric: str,
) -> list[Path]:
    """Generate interactive HTML plots and return written paths.

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
        Paths of written HTML files.
    """
    if go is None:
        sys.stdout.write("\nSkipping plots: plotly is not installed.\n")
        return []

    if not rows:
        return []

    plot_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    speed_key = f"{speed_metric}_mean"

    datasets = sorted({r["dataset"] for r in rows})

    # --- Plot 1: quality vs n_bins ---
    fig_q = make_subplots(
        rows=max(1, len(datasets)),
        cols=1,
        subplot_titles=datasets,
        shared_xaxes=False,
    )

    for ds_idx, ds_name in enumerate(datasets, start=1):
        ds_rows = [r for r in rows if r["dataset"] == ds_name]
        task = ds_rows[0].get("task", "unknown")
        q_key = primary_quality_key(task)
        q_label = "ROC-AUC" if task == "classification" else "R²"

        agg = aggregate_by_key(ds_rows, ["variant", "n_bins"], [q_key, speed_key])

        variants_seen = sorted({a["variant"] for a in agg})
        for variant in variants_seen:
            variant_pts = sorted(
                [a for a in agg if a["variant"] == variant and a.get("n_bins") is not None],
                key=operator.itemgetter("n_bins"),
            )
            x_vals = [p["n_bins"] for p in variant_pts]
            y_vals = [p[q_key] for p in variant_pts]
            if variant == "none" and ds_rows:
                x_vals, y_vals = _expand_none_variant(agg, q_key, x_vals)
            if not x_vals:
                continue
            hover_q = (
                f"n_bins=%{{x}}<br>{q_label}=%{{y:.4f}}"
                f"<br>dataset={ds_name}<extra>{variant}</extra>"
            )
            fig_q.add_trace(
                go.Scatter(
                    x=x_vals,
                    y=y_vals,
                    mode="lines+markers",
                    name=variant,
                    line={"color": VARIANT_COLORS.get(variant)},
                    marker={"size": 7},
                    legendgroup=variant,
                    showlegend=(ds_idx == 1),
                    hovertemplate=hover_q,
                ),
                row=ds_idx,
                col=1,
            )
        fig_q.update_yaxes(title_text=q_label, row=ds_idx, col=1)
        fig_q.update_xaxes(title_text="n_bins", row=ds_idx, col=1)

    fig_q.update_layout(title="RF Quality vs n_bins by Variant", height=350 * max(1, len(datasets)))
    q_path = plot_dir / "rf_quality_vs_bins.html"
    fig_q.write_html(q_path, include_plotlyjs="cdn")
    written.append(q_path)

    # --- Plot 2: speed vs n_bins ---
    fig_s = make_subplots(
        rows=max(1, len(datasets)),
        cols=1,
        subplot_titles=datasets,
        shared_xaxes=False,
    )

    for ds_idx, ds_name in enumerate(datasets, start=1):
        ds_rows = [r for r in rows if r["dataset"] == ds_name]
        agg = aggregate_by_key(ds_rows, ["variant", "n_bins"], [speed_key])

        variants_seen = sorted({a["variant"] for a in agg})
        for variant in variants_seen:
            variant_pts = sorted(
                [a for a in agg if a["variant"] == variant and a.get("n_bins") is not None],
                key=operator.itemgetter("n_bins"),
            )
            x_vals = [p["n_bins"] for p in variant_pts]
            y_vals = [p[speed_key] for p in variant_pts]
            if not x_vals:
                continue
            hover_s = (
                f"n_bins=%{{x}}<br>{speed_metric}=%{{y:.4f}}s"
                f"<br>dataset={ds_name}<extra>{variant}</extra>"
            )
            fig_s.add_trace(
                go.Scatter(
                    x=x_vals,
                    y=y_vals,
                    mode="lines+markers",
                    name=variant,
                    line={"color": VARIANT_COLORS.get(variant)},
                    marker={"size": 7},
                    legendgroup=variant,
                    showlegend=(ds_idx == 1),
                    hovertemplate=hover_s,
                ),
                row=ds_idx,
                col=1,
            )
        fig_s.update_yaxes(title_text=f"{speed_metric} (s)", row=ds_idx, col=1)
        fig_s.update_xaxes(title_text="n_bins", row=ds_idx, col=1)

    fig_s.update_layout(title=f"RF {speed_metric} vs n_bins by Variant", height=350 * max(1, len(datasets)))
    s_path = plot_dir / "rf_speed_vs_bins.html"
    fig_s.write_html(s_path, include_plotlyjs="cdn")
    written.append(s_path)

    # --- Plot 3: speed-quality Pareto scatter ---
    fig_p = make_subplots(
        rows=max(1, len(datasets)),
        cols=1,
        subplot_titles=datasets,
        shared_xaxes=False,
    )

    for ds_idx, ds_name in enumerate(datasets, start=1):
        ds_rows = [r for r in rows if r["dataset"] == ds_name]
        task = ds_rows[0].get("task", "unknown")
        q_key = primary_quality_key(task)
        q_label = "ROC-AUC" if task == "classification" else "R²"
        higher = quality_higher_better(task)

        agg = aggregate_by_key(ds_rows, ["variant", "n_bins"], [q_key, speed_key])
        agg = [a for a in agg if q_key in a and speed_key in a]
        if not agg:
            continue

        is_pareto = pareto_front(agg, speed_key=speed_key, quality_key=q_key, higher_quality_better=higher)

        for variant in sorted(VARIANT_COLORS):
            variant_pts = [p for p in agg if p["variant"] == variant]
            if not variant_pts:
                continue
            variant_pareto = [is_pareto[agg.index(p)] for p in variant_pts]
            x_all = [p[speed_key] for p in variant_pts]
            y_all = [p[q_key] for p in variant_pts]
            nb_all = [str(p.get("n_bins", "N/A")) for p in variant_pts]
            pareto_mask = list(variant_pareto)

            # non-pareto points
            x_np = [x for x, flag in zip(x_all, pareto_mask, strict=True) if not flag]
            y_np = [y for y, flag in zip(y_all, pareto_mask, strict=True) if not flag]
            nb_np = [n for n, flag in zip(nb_all, pareto_mask, strict=True) if not flag]
            if x_np:
                hover_np = (
                    f"{speed_metric}=%{{x:.4f}}<br>{q_label}=%{{y:.4f}}"
                    f"<br>n_bins=%{{text}}<extra>{variant}</extra>"
                )
                fig_p.add_trace(
                    go.Scatter(
                        x=x_np,
                        y=y_np,
                        mode="markers",
                        name=variant,
                        marker={"color": VARIANT_COLORS[variant], "size": 8, "opacity": 0.4},
                        legendgroup=variant,
                        showlegend=(ds_idx == 1),
                        text=nb_np,
                        hovertemplate=hover_np,
                    ),
                    row=ds_idx,
                    col=1,
                )
            # pareto points (larger, solid)
            x_p = [x for x, flag in zip(x_all, pareto_mask, strict=True) if flag]
            y_p = [y for y, flag in zip(y_all, pareto_mask, strict=True) if flag]
            nb_p = [n for n, flag in zip(nb_all, pareto_mask, strict=True) if flag]
            if x_p:
                hover_p = (
                    f"★ {speed_metric}=%{{x:.4f}}<br>{q_label}=%{{y:.4f}}"
                    f"<br>n_bins=%{{text}}<extra>{variant} Pareto</extra>"
                )
                fig_p.add_trace(
                    go.Scatter(
                        x=x_p,
                        y=y_p,
                        mode="markers",
                        name=f"{variant} (Pareto)",
                        marker={
                            "color": VARIANT_COLORS[variant],
                            "size": 14,
                            "symbol": "star",
                            "line": {"width": 1, "color": "black"},
                        },
                        legendgroup=f"{variant}_pareto",
                        showlegend=(ds_idx == 1),
                        text=nb_p,
                        hovertemplate=hover_p,
                    ),
                    row=ds_idx,
                    col=1,
                )

        fig_p.update_xaxes(title_text=f"{speed_metric} (s)", row=ds_idx, col=1)
        fig_p.update_yaxes(title_text=q_label, row=ds_idx, col=1)

    fig_p.update_layout(
        title=f"RF Speed-Quality Pareto Frontier (speed={speed_metric})",
        height=450 * max(1, len(datasets)),
    )
    pareto_path = plot_dir / "rf_speed_quality_pareto.html"
    fig_p.write_html(pareto_path, include_plotlyjs="cdn")
    written.append(pareto_path)

    return written


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    """Parse command-line options for benchmark run comparison.

    Returns
    -------
    argparse.Namespace
        Parsed arguments namespace.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help="JSONL file produced by benchmarks/randomforest_discretization_benchmark.py.",
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
        default=False,
        help="Generate interactive HTML plots (default: false).",
    )
    parser.add_argument(
        "--speed-metric",
        choices=SPEED_METRIC_CHOICES,
        default=DEFAULT_SPEED_METRIC,
        help="Speed metric to use for Pareto analysis and speed plots (default: total_time).",
    )
    return parser.parse_args()


def main() -> None:
    """Execute run comparison and optionally generate plots."""
    args = parse_args()
    rows = load_runs(args.input)
    print_summary(rows, speed_metric=args.speed_metric)

    if args.plots:
        written_plots = generate_plots(rows=rows, plot_dir=args.plot_dir, speed_metric=args.speed_metric)
        if written_plots:
            sys.stdout.write("\nWrote interactive plots:\n")
            for path in written_plots:
                sys.stdout.write(f"  - {path}\n")


if __name__ == "__main__":
    main()
