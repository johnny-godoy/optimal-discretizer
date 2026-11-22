"""Tests of the RandomForest discretization benchmark."""

from pathlib import Path
from typing import Any, cast

import orjson
import pytest
from benchmarks import randomforest_discretization_benchmark as benchmark


@pytest.fixture(scope="module")
def one_run(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    output = tmp_path_factory.mktemp("runs") / "runs.jsonl"
    argv = ["--repeats", "1", "--datasets", "synth_clf", "synth_reg", "unknown_name", "--n-bins", "2", "4"]
    assert benchmark.app([*argv, "--variants", "none", "optimal", "--output", str(output)]) == 0
    lines = output.read_bytes().splitlines()
    assert len(lines) == 1
    return cast(dict[str, Any], orjson.loads(lines[0]))


def test_the_run_has_its_metadata(one_run: dict[str, Any]) -> None:
    for field in ("timestamp_utc", "commit", "repeats", "seed", "n_bins_sweep", "package_version"):
        assert field in one_run
    assert one_run["n_bins_sweep"] == [2, 4]


def test_an_unknown_dataset_is_skipped(one_run: dict[str, Any]) -> None:
    assert set(one_run["results"]) == {"synth_clf", "synth_reg"}


def test_each_task_reports_its_quality(one_run: dict[str, Any]) -> None:
    assert all("roc_auc_mean" in row and "macro_f1_mean" in row for row in one_run["results"]["synth_clf"])
    assert all("r2_mean" in row and "rmse_mean" in row for row in one_run["results"]["synth_reg"])


def test_the_raw_forest_runs_once_and_has_no_bins(one_run: dict[str, Any]) -> None:
    raw_rows = [row for row in one_run["results"]["synth_clf"] if row["variant"] == "none"]
    assert len(raw_rows) == len(benchmark.DEFAULT_N_ESTIMATORS) * len(benchmark.DEFAULT_MAX_DEPTHS)
    assert all(row["n_bins"] is None and row["disc_fit_time_mean"] == pytest.approx(0.0) for row in raw_rows)


def test_a_failed_download_is_skipped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def offline(name: str) -> tuple[Any, Any, str]:
        msg = f"no network for {name}"
        raise OSError(msg)

    monkeypatch.setattr(benchmark, "load_single_dataset", offline)
    output = tmp_path / "runs.jsonl"
    assert benchmark.app(["--datasets", "california_housing", "--output", str(output)]) == 0
    assert orjson.loads(output.read_bytes())["results"] == {}


def test_the_grid_runs_the_raw_forest_once() -> None:
    configs = benchmark.grid_configs([2, 4], ["none", "kmeans"])
    raw = [config for config in configs if config.variant == "none"]
    assert {config.n_bins for config in raw} == {2}
    assert len(configs) == 3 * len(benchmark.DEFAULT_N_ESTIMATORS) * len(benchmark.DEFAULT_MAX_DEPTHS)


def test_the_seed_of_a_config_is_stable() -> None:
    config = benchmark.ForestConfig(variant="optimal", n_bins=4, n_estimators=100, max_depth=None)
    assert benchmark.config_seed("wine", config, 42) == benchmark.config_seed("wine", config, 42)
    assert 42 <= benchmark.config_seed("wine", config, 42) < 42 + 2**16


@pytest.mark.parametrize("variant", ["none", "quantile", "kmeans", "optimal"])
def test_each_variant_builds_its_pipeline(variant: benchmark.Variant) -> None:
    config = benchmark.ForestConfig(variant=variant, n_bins=3, n_estimators=10, max_depth=2)
    steps = list(benchmark.build_pipeline(config, "regression", seed=0).named_steps)
    assert steps == (["rf"] if variant == "none" else ["disc", "rf"])


def test_an_unknown_variant_is_rejected() -> None:
    config = benchmark.ForestConfig(variant="none", n_bins=3, n_estimators=10, max_depth=2)
    mystery = benchmark.attrs.evolve(config, variant="mystery")  # pyrefly: ignore[bad-argument-type] -- the test passes a variant outside the Literal on purpose
    with pytest.raises(ValueError, match="Unknown variant 'mystery'"):
        benchmark.build_pipeline(mystery, "regression", seed=0)


def test_a_multiclass_dataset_reports_the_macro_roc_auc() -> None:
    features, target, task = benchmark.load_single_dataset("wine")
    dataset = benchmark.Dataset(name="wine", features=features, target=target, task=task)
    config = benchmark.ForestConfig(variant="optimal", n_bins=3, n_estimators=10, max_depth=3)
    metrics = benchmark.evaluate_config(config, dataset, seed=0, cv_repeats=1)
    assert 0.5 < metrics["roc_auc_mean"] <= 1.0


@pytest.mark.parametrize(("name", "task"), [("breast_cancer", "classification"), ("diabetes", "regression")])
def test_a_registered_dataset_loads(name: str, task: str) -> None:
    features, target, loaded_task = benchmark.load_single_dataset(name)
    assert loaded_task == task == benchmark.DATASET_REGISTRY[name]
    assert features.shape[0] == target.shape[0]


def test_an_unknown_dataset_name_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown dataset"):
        benchmark.load_single_dataset("mystery")
