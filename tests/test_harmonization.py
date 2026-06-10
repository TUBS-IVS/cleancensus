import numpy as np
import pandas as pd
import pytest

from cleancensus.harmonization import (
    TrustBlend, TopicSpec, rake_to_margins, make_child_totals_adj,
    downscale_topic, impute_orphan_rows_100m,
)


def test_rake_to_margins_hits_both_margins():
    X = np.array([[1.0, 1.0], [1.0, 1.0]])
    rows = np.array([10.0, 30.0])
    cols = np.array([15.0, 25.0])
    rake_to_margins(X, row_targets=rows, col_targets=cols)
    np.testing.assert_allclose(X.sum(axis=1), rows, atol=1e-8)
    np.testing.assert_allclose(X.sum(axis=0), cols, atol=1e-8)


def test_make_child_totals_adj_scales_group_to_parent():
    parent = pd.DataFrame({"PID": ["A"], "tot_adj": [100.0]})
    child = pd.DataFrame({"PID": ["A", "A"], "tot": [30.0, 50.0]})
    make_child_totals_adj(
        parent_df=parent, child_df=child,
        parent_id_col="PID", child_parent_id_col="PID",
        parent_adj_col="tot_adj", child_total_col="tot", out_col="tot_adj",
    )
    assert child["tot_adj"].sum() == pytest.approx(100.0)
    # shape preserved: 30/80 vs 50/80
    np.testing.assert_allclose(child["tot_adj"].values, [37.5, 62.5])


def test_make_child_totals_adj_equal_split_when_child_sum_zero():
    parent = pd.DataFrame({"PID": ["A"], "tot_adj": [10.0]})
    child = pd.DataFrame({"PID": ["A", "A"], "tot": [0.0, 0.0]})
    make_child_totals_adj(
        parent_df=parent, child_df=child,
        parent_id_col="PID", child_parent_id_col="PID",
        parent_adj_col="tot_adj", child_total_col="tot", out_col="tot_adj",
    )
    np.testing.assert_allclose(child["tot_adj"].values, [5.0, 5.0])


def _tiny_topic_frames():
    # one 1km parent with 2 categories, three 100m children
    parent = pd.DataFrame({
        "GITTER_ID_1km": ["P1"],
        "cat_a_1km": [60.0], "cat_b_1km": [40.0],
    })
    child = pd.DataFrame({
        "GITTER_ID_1km": ["P1", "P1", "P1"],
        "cat_a_100m": [10.0, 0.0, 5.0],
        "cat_b_100m": [0.0, 8.0, 5.0],
        "tot_adj":    [40.0, 30.0, 30.0],   # sums to parent total 100
    })
    spec = TopicSpec(
        name="tiny",
        parent_cat_cols=["cat_a_1km", "cat_b_1km"],
        child_cat_cols=["cat_a_100m", "cat_b_100m"],
        child_row_total_col="tot_adj",
        alpha=0.85, blend=TrustBlend(w_min=0.4, t_pc=5.0),
    )
    return parent, child, spec


def test_downscale_topic_satisfies_row_and_col_margins():
    parent, child, spec = _tiny_topic_frames()
    res = downscale_topic(
        parent_df=parent, child_df=child,
        parent_id_col="GITTER_ID_1km", child_parent_id_col="GITTER_ID_1km",
        spec=spec,
    )
    np.testing.assert_allclose(
        res[spec.child_cat_cols].sum(axis=1).values, child["tot_adj"].values, rtol=1e-6)
    np.testing.assert_allclose(
        res[spec.child_cat_cols].sum(axis=0).values, [60.0, 40.0], atol=1e-2)
    assert (res.values >= 0).all()


def test_impute_orphan_rows_scales_signal_to_total():
    df = pd.DataFrame({
        "is_orphan":  [False, False, True, True],
        "cat_a_100m": [60.0, 30.0, 1.0, 0.0],
        "cat_b_100m": [20.0, 10.0, 1.0, 0.0],
        "tot_adj":    [80.0, 40.0, 10.0, 6.0],
    })
    spec = TopicSpec(
        name="tiny", parent_cat_cols=["x", "y"],
        child_cat_cols=["cat_a_100m", "cat_b_100m"],
        child_row_total_col="tot_adj",
    )
    impute_orphan_rows_100m(df, specs=[spec], orphan_flag_col="is_orphan", verbose=False)
    # orphan with signal: scaled 1:1 -> 5/5
    np.testing.assert_allclose(df.loc[2, ["cat_a_100m", "cat_b_100m"]].values.astype(float), [5.0, 5.0])
    # orphan without signal: prior from non-orphans (90:30 = 3:1) -> 4.5/1.5
    np.testing.assert_allclose(df.loc[3, ["cat_a_100m", "cat_b_100m"]].values.astype(float), [4.5, 1.5], rtol=1e-5)
