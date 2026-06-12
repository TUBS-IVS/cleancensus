import pyarrow as pa
import pyarrow.parquet as pq

from cleancensus.stages import ensure_no_dup_columns


def test_clean_file_returned_unchanged(tmp_path):
    p = tmp_path / "clean.parquet"
    pq.write_table(pa.table({"a": [1, 2], "b": [3, 4]}), p)
    assert ensure_no_dup_columns(p) == p


def test_duplicate_columns_deduplicated(tmp_path):
    p = tmp_path / "dup.parquet"
    t = pa.Table.from_arrays([pa.array([1, 2]), pa.array([9, 9]), pa.array([3, 4])],
                             names=["x", "M_TOTAL", "M_TOTAL"])
    pq.write_table(t, p)
    out = ensure_no_dup_columns(p)
    assert out != p
    names = pq.ParquetFile(out).schema_arrow.names
    assert names == ["x", "M_TOTAL"]  # first occurrence kept
    # kept-first values preserved
    import pandas as pd
    df = pd.read_parquet(out)
    assert df["M_TOTAL"].tolist() == [9, 9]
