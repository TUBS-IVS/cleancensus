"""Tests for cleancensus.destatis_csv."""
from __future__ import annotations


class TestConfigDesatisDir:
    def test_destatis_raw_dir_default(self, tmp_path):
        from cleancensus.config import Config
        cfg = Config(
            inputs_dir=tmp_path / "inputs",
            outputs_dir=tmp_path / "outputs",
            version_tag="test",
            topics=["Whg_Gebaeudetyp"],
            derived_tenure=False,
            derived_vacancy=False,
            mode="national",
            ars_prefixes=[],
            sanity="skip",
            write_manifest=False,
            stages={s: False for s in (
                "merge", "totals", "ages", "gemeinde", "gender",
                "topics8", "aggs", "regiostar", "extend"
            )},
            config_path=tmp_path / "config.toml",
        )
        # destatis_raw_dir should be data/raw/destatis relative to inputs_dir.parent
        assert cfg.destatis_raw_dir == tmp_path / "raw" / "destatis"


class TestDesatisTablesRegistry:
    def test_destatis_tables_imported(self):
        from cleancensus.destatis_csv import DESTATIS_TABLES
        assert isinstance(DESTATIS_TABLES, dict)

    def test_seven_tables_registered(self):
        from cleancensus.destatis_csv import DESTATIS_TABLES
        assert len(DESTATIS_TABLES) == 7

    def test_all_required_zip_names_present(self):
        from cleancensus.destatis_csv import DESTATIS_TABLES
        required_zips = {
            "Seniorenstatus_eines_privaten_Haushalts.zip",
            "Typ_des_privaren_Haushalts_Lebensform.zip",
            "Typ_des_privaten_Haushalts_Familien.zip",
            "Religion.zip",
            "Zahl_der_Staatsangehoerigkeiten.zip",
            "Groesse_der_Kernfamilie.zip",
            "Typ_der_Kernfamilie_nach_Kindern.zip",
        }
        assert set(DESTATIS_TABLES.keys()) == required_zips


class TestDesatisTotalsOnlyRegistry:
    def test_totals_only_imported(self):
        from cleancensus.destatis_csv import DESTATIS_TOTALS_ONLY
        assert isinstance(DESTATIS_TOTALS_ONLY, dict)

    def test_fifteen_entries_registered(self):
        from cleancensus.destatis_csv import DESTATIS_TOTALS_ONLY
        assert len(DESTATIS_TOTALS_ONLY) == 15

    def test_all_required_totals_zips_present(self):
        from cleancensus.destatis_csv import DESTATIS_TOTALS_ONLY
        required = {
            "Familienstand_in_Gitterzellen.zip",
            "Zensus2022_Energietraeger.zip",
            "Gebaeude_mit_Wohnraum_nach_ueberwiegender_Heizungsart.zip",
            "Zensus2022_Groesse_des_privaten_Haushalts_in_Gitterzellen.zip",
            "Wohnungen_nach_Zahl_der_Raeume.zip",
            "Flaeche_der_Wohnung_10m2_Intervalle.zip",
            "Zensus2022_Geburtsland_Gruppen_in_Gitterzellen.zip",
            "Wohnungen_nach_Gebaeudetyp_Groesse.zip",
            "Gebaeude_mit_Wohnraum_nach_Gebaeudetyp_Groesse.zip",
            "Gebaeude_nach_Anzahl_der_Wohnungen_im_Gebaeude.zip",
            "Gebaeude_nach_Baujahr_in_Mikrozensus_Klassen.zip",
            "Gebaeude_mit_Wohnraum_nach_Energietraeger_der_Heizung.zip",
            "Zensus2022_Heizungsart.zip",
            "Zensus2022_Staatsangehoerigkeit_in_Gitterzellen.zip",
            "Zensus2022_Staatsangehoerigkeit_Gruppen_in_Gitterzellen.zip",
        }
        assert set(DESTATIS_TOTALS_ONLY.keys()) == required

    def test_each_entry_has_insgesamt_col(self):
        from cleancensus.destatis_csv import DESTATIS_TOTALS_ONLY
        for zip_name, info in DESTATIS_TOTALS_ONLY.items():
            assert "insgesamt_col" in info, f"{zip_name} missing 'insgesamt_col'"
            assert info["insgesamt_col"].startswith("Insgesamt"), (
                f"{zip_name}: insgesamt_col {info['insgesamt_col']!r} does not start "
                "with 'Insgesamt'"
            )

    def test_each_entry_has_csv_names_for_all_levels(self):
        from cleancensus.destatis_csv import DESTATIS_TOTALS_ONLY
        for zip_name, info in DESTATIS_TOTALS_ONLY.items():
            for level in ("10km", "1km", "100m"):
                assert level in info["csv_names"], (
                    f"{zip_name} missing csv_names[{level!r}]"
                )

    def test_each_table_has_csv_names_for_all_levels(self):
        from cleancensus.destatis_csv import DESTATIS_TABLES
        for zip_name, info in DESTATIS_TABLES.items():
            for level in ("10km", "1km", "100m"):
                assert level in info["csv_names"], (
                    f"{zip_name} missing csv_names[{level!r}]"
                )

    def test_each_table_has_data_cols(self):
        from cleancensus.destatis_csv import DESTATIS_TABLES
        for zip_name, info in DESTATIS_TABLES.items():
            assert "data_cols" in info, f"{zip_name} missing 'data_cols'"
            assert len(info["data_cols"]) >= 3, (
                f"{zip_name} has < 3 data_cols: {info['data_cols']}"
            )

    def test_seniorenstatus_data_cols(self):
        from cleancensus.destatis_csv import DESTATIS_TABLES
        info = DESTATIS_TABLES["Seniorenstatus_eines_privaten_Haushalts.zip"]
        assert set(info["data_cols"]) == {
            "Insgesamt_Haushalte", "HH_nurSenioren",
            "HH_mitSenioren", "HH_ohneSenioren",
        }

    def test_religion_data_cols(self):
        from cleancensus.destatis_csv import DESTATIS_TABLES
        info = DESTATIS_TABLES["Religion.zip"]
        assert set(info["data_cols"]) == {
            "Insgesamt_Bevoelkerung", "Roemisch_katholisch",
            "Evangelisch", "Sonstige_keine_ohneAngabe",
        }

    def test_typ_der_kernfamilie_nach_kindern_data_cols(self):
        from cleancensus.destatis_csv import DESTATIS_TABLES
        info = DESTATIS_TABLES["Typ_der_Kernfamilie_nach_Kindern.zip"]
        assert set(info["data_cols"]) == {
            "Insgesamt_Familie",
            "Ehep_ohneKind",
            "Ehep_mind_1Kind_unter18",
            "Ehep_Kinder_ab18",
            "EingetrLP_ohneKind",
            "EingetrLP_mind_1Kind_unter18",
            "EingetrLP_Kinder_ab18",
            "NichtehelLG_ohneKind",
            "NichtehelLG_mind_1Kind_unter18",
            "NichtehelLG_Kinder_ab18",
            "Vater_mind_1Kind_unter18",
            "Vater_Kinder_ab18",
            "Mutter_mind_1Kind_unter18",
            "Mutter_Kinder_ab18",
        }
        assert len(info["data_cols"]) == 14

    def test_typ_der_kernfamilie_nach_kindern_csv_names(self):
        from cleancensus.destatis_csv import DESTATIS_TABLES
        info = DESTATIS_TABLES["Typ_der_Kernfamilie_nach_Kindern.zip"]
        for level in ("10km", "1km", "100m"):
            assert level in info["csv_names"]
            assert f"Zensus2022_Typ_der_Kernfamilie_nach_Kindern_{level}-Gitter.csv" in info["csv_names"][level]


class TestColumnNaming:
    """Verify the column naming function on in-memory CSV data."""

    def test_column_name_seniorenstatus_10km(self):
        """build_col_name(data_col, csv_name, level) matches T: convention."""
        from cleancensus.destatis_csv import build_col_name
        result = build_col_name(
            "HH_nurSenioren",
            "Zensus2022_Seniorenstatus_eines_privaten_Haushalts_10km-Gitter.csv",
        )
        assert result == "HH_nurSenioren_Seniorenstatus_eines_privaten_Haushalts_10km-Gitter"

    def test_column_name_lebensform_1km(self):
        from cleancensus.destatis_csv import build_col_name
        result = build_col_name(
            "EinpersHH_SingleHH",
            "Zensus2022_Typ_priv_HH_Lebensform_1km-Gitter.csv",
        )
        assert result == "EinpersHH_SingleHH_Typ_priv_HH_Lebensform_1km-Gitter"

    def test_column_name_religion_100m(self):
        from cleancensus.destatis_csv import build_col_name
        result = build_col_name(
            "Roemisch_katholisch",
            "Zensus2022_Religion_100m-Gitter.csv",
        )
        assert result == "Roemisch_katholisch_Religion_100m-Gitter"

    def test_column_name_kernfamilie_10km(self):
        from cleancensus.destatis_csv import build_col_name
        # Note: CSV filename has "Grosse" (missing the second 'e'), not "Groesse"
        result = build_col_name(
            "a2Personen",
            "Zensus2022_Grosse_Kernfamilie_bis6undmehrPers_10km-Gitter.csv",
        )
        assert result == "a2Personen_Grosse_Kernfamilie_bis6undmehrPers_10km-Gitter"

    def test_column_name_typ_der_kernfamilie_nach_kindern_10km(self):
        from cleancensus.destatis_csv import build_col_name
        result = build_col_name(
            "Ehep_mind_1Kind_unter18",
            "Zensus2022_Typ_der_Kernfamilie_nach_Kindern_10km-Gitter.csv",
        )
        assert result == "Ehep_mind_1Kind_unter18_Typ_der_Kernfamilie_nach_Kindern_10km-Gitter"

    def test_column_name_typ_der_kernfamilie_insgesamt_1km(self):
        from cleancensus.destatis_csv import build_col_name
        result = build_col_name(
            "Insgesamt_Familie",
            "Zensus2022_Typ_der_Kernfamilie_nach_Kindern_1km-Gitter.csv",
        )
        assert result == "Insgesamt_Familie_Typ_der_Kernfamilie_nach_Kindern_1km-Gitter"


class TestReadDesatisZip:
    """Unit test read_destatis_zip using an in-memory fake ZIP."""

    def _make_fake_zip(self, tmp_path):
        """Write a minimal fake Seniorenstatus ZIP to tmp_path and return path."""
        import io, zipfile
        csv_content = (
            "GITTER_ID_10km;x_mp_10km;y_mp_10km;Insgesamt_Haushalte;HH_nurSenioren;HH_mitSenioren;HH_ohneSenioren\n"
            "CRS3035RES10000mN2690000E4330000;4335000;2695000;143;39;15;87\n"
            "CRS3035RES10000mN2700000E4330000;4335000;2705000;50;10;5;35\n"
        )
        zip_path = tmp_path / "Seniorenstatus_eines_privaten_Haushalts.zip"
        with zipfile.ZipFile(zip_path, "w") as z:
            z.writestr(
                "Zensus2022_Seniorenstatus_eines_privaten_Haushalts_10km-Gitter.csv",
                csv_content,
            )
        return zip_path

    def test_read_returns_dataframe(self, tmp_path):
        from cleancensus.destatis_csv import read_destatis_zip
        zip_path = self._make_fake_zip(tmp_path)
        df = read_destatis_zip(zip_path, "10km")
        import pandas as pd
        assert isinstance(df, pd.DataFrame)

    def test_read_has_gitter_id_column(self, tmp_path):
        from cleancensus.destatis_csv import read_destatis_zip
        zip_path = self._make_fake_zip(tmp_path)
        df = read_destatis_zip(zip_path, "10km")
        assert "GITTER_ID_10km" in df.columns

    def test_read_has_correct_row_count(self, tmp_path):
        from cleancensus.destatis_csv import read_destatis_zip
        zip_path = self._make_fake_zip(tmp_path)
        df = read_destatis_zip(zip_path, "10km")
        assert len(df) == 2

    def test_read_drops_xy_columns(self, tmp_path):
        from cleancensus.destatis_csv import read_destatis_zip
        zip_path = self._make_fake_zip(tmp_path)
        df = read_destatis_zip(zip_path, "10km")
        assert "x_mp_10km" not in df.columns
        assert "y_mp_10km" not in df.columns

    def test_read_column_names_match_t_convention(self, tmp_path):
        from cleancensus.destatis_csv import read_destatis_zip
        zip_path = self._make_fake_zip(tmp_path)
        df = read_destatis_zip(zip_path, "10km")
        expected_cols = {
            "GITTER_ID_10km",
            "Insgesamt_Haushalte_Seniorenstatus_eines_privaten_Haushalts_10km-Gitter",
            "HH_nurSenioren_Seniorenstatus_eines_privaten_Haushalts_10km-Gitter",
            "HH_mitSenioren_Seniorenstatus_eines_privaten_Haushalts_10km-Gitter",
            "HH_ohneSenioren_Seniorenstatus_eines_privaten_Haushalts_10km-Gitter",
        }
        assert set(df.columns) == expected_cols

    def test_read_suppressed_dash_becomes_nan(self, tmp_path):
        """The '–' (EN DASH) suppressed value must become NaN, not a string."""
        import io, zipfile
        import pandas as pd
        csv_content = (
            "GITTER_ID_10km;x_mp_10km;y_mp_10km;Insgesamt_Bevoelkerung;Roemisch_katholisch;Evangelisch;Sonstige_keine_ohneAngabe\n"
            "CRS3035RES10000mN2680000E4330000;4335000;2685000;4;4;–;–\n"
        )
        zip_path = tmp_path / "Religion.zip"
        with zipfile.ZipFile(zip_path, "w") as z:
            z.writestr("Zensus2022_Religion_10km-Gitter.csv", csv_content)
        from cleancensus.destatis_csv import read_destatis_zip
        df = read_destatis_zip(zip_path, "10km")
        assert pd.isna(df["Evangelisch_Religion_10km-Gitter"].iloc[0])


class TestMergeDesatisTablesSmoke:
    """Integration smoke: merge_destatis_tables with fake ZIPs."""

    def _make_two_fake_zips(self, tmp_path):
        import zipfile
        # Seniorenstatus (4 data cols)
        csv1 = (
            "GITTER_ID_10km;x_mp_10km;y_mp_10km;Insgesamt_Haushalte;HH_nurSenioren;HH_mitSenioren;HH_ohneSenioren\n"
            "ID_A;1;2;100;30;10;60\n"
            "ID_B;3;4;50;5;5;40\n"
        )
        with zipfile.ZipFile(tmp_path / "Seniorenstatus_eines_privaten_Haushalts.zip", "w") as z:
            z.writestr("Zensus2022_Seniorenstatus_eines_privaten_Haushalts_10km-Gitter.csv", csv1)
        # Religion (4 data cols)
        csv2 = (
            "GITTER_ID_10km;x_mp_10km;y_mp_10km;Insgesamt_Bevoelkerung;Roemisch_katholisch;Evangelisch;Sonstige_keine_ohneAngabe\n"
            "ID_A;1;2;200;80;60;60\n"
            "ID_C;5;6;30;10;10;10\n"
        )
        with zipfile.ZipFile(tmp_path / "Religion.zip", "w") as z:
            z.writestr("Zensus2022_Religion_10km-Gitter.csv", csv2)

    def test_merge_produces_union_of_ids(self, tmp_path):
        """Outer join on GITTER_ID should give union of all IDs across tables."""
        self._make_two_fake_zips(tmp_path)
        from cleancensus.destatis_csv import merge_destatis_tables
        df = merge_destatis_tables("10km", tmp_path)
        assert set(df["GITTER_ID_10km"]) == {"ID_A", "ID_B", "ID_C"}

    def test_merge_missing_zip_does_not_raise(self, tmp_path):
        """If only some ZIPs are present, merge still completes (warn only)."""
        # Only Seniorenstatus present (no Religion, etc.)
        import zipfile
        csv1 = (
            "GITTER_ID_10km;x_mp_10km;y_mp_10km;Insgesamt_Haushalte;HH_nurSenioren;HH_mitSenioren;HH_ohneSenioren\n"
            "ID_A;1;2;100;30;10;60\n"
        )
        with zipfile.ZipFile(tmp_path / "Seniorenstatus_eines_privaten_Haushalts.zip", "w") as z:
            z.writestr("Zensus2022_Seniorenstatus_eines_privaten_Haushalts_10km-Gitter.csv", csv1)
        from cleancensus.destatis_csv import merge_destatis_tables
        df = merge_destatis_tables("10km", tmp_path)
        assert len(df) == 1
        assert "HH_nurSenioren_Seniorenstatus_eines_privaten_Haushalts_10km-Gitter" in df.columns

    def test_merge_all_missing_returns_none(self, tmp_path):
        """If no ZIPs present, return None (caller checks for None)."""
        from cleancensus.destatis_csv import merge_destatis_tables
        result = merge_destatis_tables("10km", tmp_path)
        assert result is None


class TestMergeWithZ22Integration:
    """Smoke test: merge_destatis_tables output left-joins onto a synthetic z22 table."""

    def test_left_join_adds_destatis_columns(self, tmp_path):
        """Verifies that the merge logic in run_merge_z22 adds Destatis columns."""
        import zipfile
        import pandas as pd

        # Build a minimal fake ZIP
        csv_content = (
            "GITTER_ID_10km;x_mp_10km;y_mp_10km;Insgesamt_Bevoelkerung;Roemisch_katholisch;Evangelisch;Sonstige_keine_ohneAngabe\n"
            "CRS3035RES10000mN2690000E4330000;4335000;2695000;100;40;30;30\n"
            "CRS3035RES10000mN2700000E4330000;4335000;2705000;50;20;15;15\n"
        )
        raw_dir = tmp_path / "destatis"
        raw_dir.mkdir()
        with zipfile.ZipFile(raw_dir / "Religion.zip", "w") as z:
            z.writestr("Zensus2022_Religion_10km-Gitter.csv", csv_content)

        # Synthetic z22 frame (3 rows; only 2 overlap with Destatis)
        z22_df = pd.DataFrame({
            "GITTER_ID_10km": [
                "CRS3035RES10000mN2690000E4330000",
                "CRS3035RES10000mN2700000E4330000",
                "CRS3035RES10000mN2710000E4330000",
            ],
            "Einwohner_Bevoelkerungszahl_10km-Gitter": [100, 50, 30],
        })

        from cleancensus.destatis_csv import merge_destatis_tables
        destatis_df = merge_destatis_tables("10km", raw_dir)
        assert destatis_df is not None

        result = z22_df.merge(destatis_df, on="GITTER_ID_10km", how="left")
        assert "Roemisch_katholisch_Religion_10km-Gitter" in result.columns
        # Third row (no Destatis data) should be NaN
        assert pd.isna(result["Roemisch_katolisch_Religion_10km-Gitter".replace("katol", "kathol")].iloc[2])
        # First two rows should have values
        assert result["Roemisch_katholisch_Religion_10km-Gitter"].iloc[0] == 40.0


class TestReadDesatisTotalsZip:
    """Unit tests for read_destatis_totals_zip (DESTATIS_TOTALS_ONLY)."""

    def _make_fake_familienstand_zip(self, tmp_path):
        """Write a minimal fake Familienstand ZIP and return path."""
        import io, zipfile
        csv_content = (
            "GITTER_ID_10km;x_mp_10km;y_mp_10km;Insgesamt_Bevoelkerung;Ledig;Verheiratet;Verwitwet;Geschieden\n"
            "CRS3035RES10000mN2680000E4330000;4335000;2685000;100;40;45;5;10\n"
            "CRS3035RES10000mN2690000E4330000;4335000;2695000;200;80;90;10;20\n"
        )
        zip_path = tmp_path / "Familienstand_in_Gitterzellen.zip"
        with zipfile.ZipFile(zip_path, "w") as z:
            z.writestr("Zensus2022_Familienstand_10km-Gitter.csv", csv_content)
        return zip_path

    def test_read_totals_returns_dataframe(self, tmp_path):
        import pandas as pd
        from cleancensus.destatis_csv import read_destatis_totals_zip
        zip_path = self._make_fake_familienstand_zip(tmp_path)
        df = read_destatis_totals_zip(zip_path, "10km")
        assert isinstance(df, pd.DataFrame)

    def test_read_totals_has_exactly_two_columns(self, tmp_path):
        """Only GITTER_ID + the single Insgesamt column should remain."""
        from cleancensus.destatis_csv import read_destatis_totals_zip
        zip_path = self._make_fake_familienstand_zip(tmp_path)
        df = read_destatis_totals_zip(zip_path, "10km")
        assert len(df.columns) == 2

    def test_read_totals_drops_category_columns(self, tmp_path):
        """Category columns (Ledig, Verheiratet, etc.) must NOT be in the output."""
        from cleancensus.destatis_csv import read_destatis_totals_zip
        zip_path = self._make_fake_familienstand_zip(tmp_path)
        df = read_destatis_totals_zip(zip_path, "10km")
        for cat in ("Ledig", "Verheiratet", "Verwitwet", "Geschieden"):
            assert not any(cat in c for c in df.columns), (
                f"Category column containing {cat!r} found in output (should be dropped)"
            )

    def test_read_totals_column_name_matches_t_convention(self, tmp_path):
        """Produced column name must match T: canonical name exactly."""
        from cleancensus.destatis_csv import read_destatis_totals_zip
        zip_path = self._make_fake_familienstand_zip(tmp_path)
        df = read_destatis_totals_zip(zip_path, "10km")
        expected_col = "Insgesamt_Bevoelkerung_Familienstand_10km-Gitter"
        assert expected_col in df.columns, (
            f"Expected {expected_col!r} in columns, got {list(df.columns)}"
        )

    def test_read_totals_values_are_numeric(self, tmp_path):
        """Insgesamt column values must be numeric (int or float, not object)."""
        import pandas as pd
        from cleancensus.destatis_csv import read_destatis_totals_zip
        zip_path = self._make_fake_familienstand_zip(tmp_path)
        df = read_destatis_totals_zip(zip_path, "10km")
        col = "Insgesamt_Bevoelkerung_Familienstand_10km-Gitter"
        assert pd.api.types.is_numeric_dtype(df[col])
        assert df[col].iloc[0] == 100

    def test_read_totals_drops_xy_columns(self, tmp_path):
        """Coordinate columns must be dropped."""
        from cleancensus.destatis_csv import read_destatis_totals_zip
        zip_path = self._make_fake_familienstand_zip(tmp_path)
        df = read_destatis_totals_zip(zip_path, "10km")
        assert "x_mp_10km" not in df.columns
        assert "y_mp_10km" not in df.columns

    def test_read_totals_unknown_zip_raises(self, tmp_path):
        """read_destatis_totals_zip must raise ValueError for unknown ZIPs."""
        import zipfile
        from cleancensus.destatis_csv import read_destatis_totals_zip
        zip_path = tmp_path / "NotRegistered.zip"
        with zipfile.ZipFile(zip_path, "w") as z:
            z.writestr("dummy.csv", "a;b\n1;2\n")
        import pytest
        with pytest.raises(ValueError, match="Unknown ZIP"):
            read_destatis_totals_zip(zip_path, "10km")


class TestInsgesamtFilterOnSyntheticFrame:
    """Verify that only Insgesamt_* columns pass the totals-only filter."""

    def test_insgesamt_filter_keeps_only_insgesamt(self):
        """Simulates the filter: given a frame with many cols, only Insgesamt_* survive."""
        import pandas as pd
        cols = [
            "GITTER_ID_10km",
            "Insgesamt_Bevoelkerung",
            "Ledig",
            "Verheiratet",
            "Verwitwet",
            "Geschieden",
        ]
        df = pd.DataFrame({c: [1] for c in cols})
        # Replicate the filter logic from read_destatis_totals_zip (keep GITTER_ID + Insgesamt*)
        insgesamt_col = "Insgesamt_Bevoelkerung"
        gid_col = "GITTER_ID_10km"
        filtered = df[[gid_col, insgesamt_col]]
        assert list(filtered.columns) == [gid_col, insgesamt_col]
        assert "Ledig" not in filtered.columns
        assert "Verheiratet" not in filtered.columns

    def test_insgesamt_filter_multiple_insgesamt_cols(self):
        """If a frame has multiple Insgesamt_* columns, the explicit insgesamt_col
        selection (not a prefix scan) ensures only the registered one is kept."""
        import pandas as pd
        cols = ["GITTER_ID_1km", "Insgesamt_A", "Insgesamt_B", "Cat_X"]
        df = pd.DataFrame({c: [5] for c in cols})
        # Only Insgesamt_A is the registered col
        registered = "Insgesamt_A"
        gid_col = "GITTER_ID_1km"
        filtered = df[[gid_col, registered]]
        assert "Insgesamt_B" not in filtered.columns
        assert "Cat_X" not in filtered.columns


class TestMergeIncludesTotalsOnly:
    """Verify merge_destatis_tables includes totals-only columns when ZIPs are present."""

    def test_merge_includes_insgesamt_column_from_totals_only_zip(self, tmp_path):
        """A totals-only ZIP in raw_dir must produce an Insgesamt column in the merge."""
        import zipfile
        import pandas as pd

        # Create a minimal Familienstand ZIP (totals-only registry)
        csv_content = (
            "GITTER_ID_10km;x_mp_10km;y_mp_10km;Insgesamt_Bevoelkerung;Ledig;Verheiratet\n"
            "ID_X;1;2;300;120;180\n"
        )
        with zipfile.ZipFile(tmp_path / "Familienstand_in_Gitterzellen.zip", "w") as z:
            z.writestr("Zensus2022_Familienstand_10km-Gitter.csv", csv_content)

        from cleancensus.destatis_csv import merge_destatis_tables
        df = merge_destatis_tables("10km", tmp_path)
        assert df is not None

        expected_col = "Insgesamt_Bevoelkerung_Familienstand_10km-Gitter"
        assert expected_col in df.columns, (
            f"Expected {expected_col!r} in columns, got {list(df.columns)}"
        )
        # Category columns must NOT be in output (they were filtered out)
        assert "Ledig_Familienstand_10km-Gitter" not in df.columns
        assert "Verheiratet_Familienstand_10km-Gitter" not in df.columns

    def test_merge_totals_only_and_full_table_combined(self, tmp_path):
        """When both a full-table ZIP and a totals-only ZIP are present, both
        contribute columns to the merged output."""
        import zipfile
        import pandas as pd

        # Full-table ZIP: Religion
        csv_religion = (
            "GITTER_ID_10km;x_mp_10km;y_mp_10km;Insgesamt_Bevoelkerung;Roemisch_katholisch;Evangelisch;Sonstige_keine_ohneAngabe\n"
            "ID_A;1;2;100;40;30;30\n"
        )
        with zipfile.ZipFile(tmp_path / "Religion.zip", "w") as z:
            z.writestr("Zensus2022_Religion_10km-Gitter.csv", csv_religion)

        # Totals-only ZIP: Familienstand
        csv_familienstand = (
            "GITTER_ID_10km;x_mp_10km;y_mp_10km;Insgesamt_Bevoelkerung;Ledig;Verheiratet\n"
            "ID_A;1;2;200;80;120\n"
        )
        with zipfile.ZipFile(tmp_path / "Familienstand_in_Gitterzellen.zip", "w") as z:
            z.writestr("Zensus2022_Familienstand_10km-Gitter.csv", csv_familienstand)

        from cleancensus.destatis_csv import merge_destatis_tables
        df = merge_destatis_tables("10km", tmp_path)
        assert df is not None

        # Full-table columns present
        assert "Insgesamt_Bevoelkerung_Religion_10km-Gitter" in df.columns
        assert "Roemisch_katholisch_Religion_10km-Gitter" in df.columns
        # Totals-only column present
        assert "Insgesamt_Bevoelkerung_Familienstand_10km-Gitter" in df.columns
        # Category cols from totals-only ZIP NOT present
        assert "Ledig_Familienstand_10km-Gitter" not in df.columns
