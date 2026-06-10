from pathlib import Path

REPO = Path(__file__).resolve().parent
DATA_IN = REPO / "data" / "inputs"
DATA_OUT = REPO / "data" / "outputs"

PATH_10 = DATA_IN / "df10_with_single_years.pickle"
PATH_1 = DATA_IN / "cells_1km_with_binneds.parquet"
PATH_100 = DATA_IN / "cells_100m_with_gender_backf_binneds_happyorphans_with_aggs_regiostar.parquet"
OUT_1_V2 = DATA_OUT / "cells_1km_with_binneds_v2.parquet"
OUT_100_V2 = DATA_OUT / "cells_100m_with_gender_backf_binneds_happyorphans_with_aggs_regiostar_v2.parquet"
OUT_1_V3 = DATA_OUT / "cells_1km_with_binneds_v3.parquet"
OUT_100_V3 = DATA_OUT / "cells_100m_with_gender_backf_binneds_happyorphans_with_aggs_regiostar_v3.parquet"
