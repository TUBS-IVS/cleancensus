import os
import pytest

from new_topics import RAW_TOPICS, build_new_topic_specs
from paths import PATH_10, PATH_1, PATH_100


def test_spec_shapes_consistent():
    for tier, topics in RAW_TOPICS.items():
        for name, tot, cats, alpha in topics:
            assert tot.endswith("_10km-Gitter"), name
            assert all(c.endswith("_10km-Gitter") for c in cats), name
            assert len(set(cats)) == len(cats), f"dup cats in {name}"
    s1 = build_new_topic_specs("1km", tiers=(1, 2, 3))
    s100 = build_new_topic_specs("100m", tiers=(1, 2, 3))
    assert len(s1) == len(s100) == sum(len(v) for v in RAW_TOPICS.values())
    for a, b in zip(s1, s100):
        assert len(a.parent_cat_cols) == len(a.child_cat_cols)
        assert len(b.parent_cat_cols) == len(b.child_cat_cols)


@pytest.mark.skipif(not os.path.exists(PATH_100), reason="prepared 100m parquet not present")
def test_specs_exist_in_100m_schema():
    import pyarrow.parquet as pq
    cols = set(f.name for f in pq.ParquetFile(PATH_100).schema_arrow)
    for spec in build_new_topic_specs("100m", tiers=(1, 2, 3)):
        assert spec.child_row_total_col in cols, spec.name
        missing = [c for c in spec.child_cat_cols if c not in cols]
        assert not missing, f"{spec.name}: {missing}"


@pytest.mark.skipif(not os.path.exists(PATH_1), reason="1km parquet not present")
def test_specs_exist_in_1km_schema():
    import pyarrow.parquet as pq
    cols = set(f.name for f in pq.ParquetFile(PATH_1).schema_arrow)
    for spec in build_new_topic_specs("100m", tiers=(1, 2, 3)):  # 100m specs -> parents are 1km cols
        missing = [c for c in spec.parent_cat_cols if c not in cols]
        assert not missing, f"{spec.name}: {missing}"
        # the 1km total needed by apply_adj at the 100m stage:
        assert spec.child_row_total_col.replace("_100m-Gitter", "_1km-Gitter") in cols, spec.name


@pytest.mark.skipif(not os.path.exists(PATH_10), reason="10km pickle not present")
def test_specs_exist_in_10km_frame():
    import pandas as pd
    cols = set(pd.read_pickle(PATH_10).reset_index().columns)
    for spec in build_new_topic_specs("1km", tiers=(1, 2, 3)):
        assert spec.child_row_total_col.replace("_1km-Gitter", "_10km-Gitter") in cols, spec.name
        missing = [c for c in spec.parent_cat_cols if c not in cols]
        assert not missing, f"{spec.name}: {missing}"
