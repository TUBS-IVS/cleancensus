"""Ingest path for the z22data GitHub mirror of the Zensus 2022 grid data.

Source: https://github.com/JsLth/z22data  (Jonas Lieth)
License: dl-de/by-2-0 (same as original Destatis data)

Attribution (required for any publication / data product):
  Census content: © Statistische Ämter des Bundes und der Länder, Zensus 2022
  Grid geometry: © GeoBasis-DE / BKG 2023 (https://www.bkg.bund.de)
  z22data mirror: Jonas Lieth (https://github.com/JsLth/z22)

Parquet URL pattern:
  https://raw.githubusercontent.com/JsLth/z22data/main/z22_data_{level}/{feature}_{cat}.parquet

Each parquet has columns: x:int64, y:int64, value:int64
  x, y = INSPIRE cell MIDPOINTS in EPSG:3035 metres.

GITTER_ID reconstruction (verified against T: merged CSV):
  res_str = {10km: "10000m", 1km: "1000m", 100m: "100m"}
  half    = {10km: 5000,     1km: 500,     100m: 50}
  id = f"CRS3035RES{res_str}N{y_mp - half}E{x_mp - half}"

Tested verified examples:
  10km: x_mp=4335000, y_mp=2685000  -> CRS3035RES10000mN2680000E4330000
  1km:  x_mp=4337500, y_mp=2689500  -> CRS3035RES1000mN2689000E4337000
  100m: x_mp=4337050, y_mp=2689150  -> CRS3035RES100mN2689100E4337000

FEATURE_MAP: (feature_name, category_code) -> canonical German column BASE name.
  The full column name in the output is f"{base}_{level}-Gitter".
  Category code == 0 means the parquet holds a total / average / share (no category).
  Category code == None is used only for "total" row descriptors (not downloaded).

Notes on unmapped T: features (z22data does not provide them):
  - Alter_INFR: INFR-specific age classes (z11 only; z22 uses age_short/age_long)
  - Baujahr_JZ: detailed JZ construction year (z11; z22 uses MZ classes = building_constr_year)
  - Seniorenstatus_eines_privaten_Haushalts: z11 only (household_senior)
  - Typ_priv_HH_Familie / Typ_priv_HH_Lebensform: z11 only
  - Grosse_Kernfamilie_bis6undmehrPers: family_size categories – z11 only
  - Durchschn_Nettokaltmiete_Anzahl_der_Wohnungen: auxiliary count – not published in z22data

Note on building_size vs dwelling_building_size (upstream swap, FIXED 2026-06-12):
  z22data issue #4 (reported by us) confirmed the two feature names were swapped
  relative to their contents. The MFH_13undmehrWohnungen discriminator pins the
  ground truth (buildings with 13+ dwellings are FEW, dwellings in such buildings
  are MANY); T: merged CSVs were always labelled CORRECTLY: Geb_* MFH_13+ = 237,542
  (buildings), Wohnung_* MFH_13+ = 5,224,648 (dwellings).

  The upstream "re-process 2022 data" commit (2026-06-12) corrected the swap, so the
  z22data feature names now match their contents literally. VERIFIED 2026-06-13 against
  the OFFICIAL Destatis Insgesamt totals (current upstream, 10km):
    z22 'building_size'          grand total = 19,957,238 ≈ Destatis GEBAEUDE  19,957,289
                                 cat 1 (FreiEFH) = 8,665,451 == T: FreiEFH_Geb_*, exact
    z22 'dwelling_building_size' grand total = 43,107,077 ≈ Destatis WOHNUNGEN 43,106,536
                                 cat 1 (FreiEFH) = 8,665,582 == T: FreiEFH_Wohnung_*, exact
    (Destatis "Gebaeude...nach Gebaeudetyp" Insgesamt_Gebaeude = 19,957,289;
     "Wohnungen...nach Gebaeudetyp" Insgesamt_Wohnungen = 43,106,536.)
  The FEATURE_MAP below therefore now maps z22 'building_size' -> Geb_* columns and
  'dwelling_building_size' -> Wohnung_* columns, matching the corrected upstream names.
  Pre-2026-06-12 cached parquets carry the OLD (swapped) contents — delete and
  re-download them so they agree with this mapping (guarded by a regression test).
"""
from __future__ import annotations

import os
import time
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING

from cleancensus import names
from cleancensus.logsetup import get_logger

if TYPE_CHECKING:
    import pandas as pd

log = get_logger("merge")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

Z22DATA_BASE_URL = "https://raw.githubusercontent.com/JsLth/z22data/main"

_LEVEL_RES_STR = {"10km": "10000m", "1km": "1000m", "100m": "100m"}
_LEVEL_HALF    = {"10km": 5000,     "1km": 500,     "100m": 50}


# ---------------------------------------------------------------------------
# FEATURE_MAP
# ---------------------------------------------------------------------------

# (feature, category_code) -> canonical German column BASE name
# Full column in merged table: f"{base}_{level}-Gitter"
# cat=0 means total/average/share parquet (no category breakdown)
FEATURE_MAP: dict[tuple[str, int], str] = {

    # ---- Population --------------------------------------------------------
    ("population",           0): "Einwohner_Bevoelkerungszahl",
    ("citizens",             0): "Deutsche_ab18_Deutsche_Staatsangehoerige_ab18",
    ("foreigners",           0): "AnteilAuslaender_Anteil_Auslaender",
    ("foreigners_from_18",   0): "AnteilAuslaenderAb18_Auslaenderanteil_ab18",

    # ---- Age ---------------------------------------------------------------
    ("age_avg",     0): "Durchschnittsalter_Durchschnittsalter",
    ("age_under_18",0): "AnteilUnter18_Anteil_unter_18",
    ("age_from_65", 0): "AnteilUeber65_Anteil_ueber_65",

    # age_short: 5 classes (Alter in 5 Altersklassen)
    ("age_short", 1): "Unter18_Alter_in_5_Altersklassen",
    ("age_short", 2): "a18bis29_Alter_in_5_Altersklassen",
    ("age_short", 3): "a30bis49_Alter_in_5_Altersklassen",
    ("age_short", 4): "a50bis64_Alter_in_5_Altersklassen",
    ("age_short", 5): "a65undaelter_Alter_in_5_Altersklassen",

    # age_long: 10-year groups (Alter in 10er-Jahresgruppen)
    ("age_long", 1): "Unter10_Alter_in_10er-Jahresgruppen",
    ("age_long", 2): "a10bis19_Alter_in_10er-Jahresgruppen",
    ("age_long", 3): "a20bis29_Alter_in_10er-Jahresgruppen",
    ("age_long", 4): "a30bis39_Alter_in_10er-Jahresgruppen",
    ("age_long", 5): "a40bis49_Alter_in_10er-Jahresgruppen",
    ("age_long", 6): "a50bis59_Alter_in_10er-Jahresgruppen",
    ("age_long", 7): "a60bis69_Alter_in_10er-Jahresgruppen",
    ("age_long", 8): "a70bis79_Alter_in_10er-Jahresgruppen",
    ("age_long", 9): "a80undaelter_Alter_in_10er-Jahresgruppen",

    # ---- Marital status (Familienstand) ------------------------------------
    ("marital_status", 1): "Ledig_Familienstand",
    ("marital_status", 2): "Verheiratet_Familienstand",
    ("marital_status", 3): "Verwitwet_Familienstand",
    ("marital_status", 4): "Geschieden_Familienstand",
    ("marital_status", 5): "EingetrLebenspartnerschaft_Familienstand",
    ("marital_status", 6): "EingetrLebenspartVerstorben_Familienstand",
    ("marital_status", 7): "EingetrLebenspartAufgehoben_Familienstand",
    ("marital_status", 8): "OhneAngabe_Familienstand",

    # ---- Birth country (Geburtsland, 2022 codes) ---------------------------
    ("birth_country",  1): "Deutschland_Geburtsland_Gruppen",
    ("birth_country", 20): "Ausland_Sonstige_Geburtsland_Gruppen",
    ("birth_country", 21): "EU27_Land_Geburtsland_Gruppen",
    ("birth_country", 22): "Sonstiges_Europa_Geburtsland_Gruppen",
    ("birth_country", 23): "Sonstige_Welt_Geburtsland_Gruppen",
    ("birth_country", 24): "Sonstige_Geburtsland_Gruppen",

    # ---- Citizenship (Staatsangehörigkeit) ---------------------------------
    ("citizenship", 1): "Deutschland_Staatsangehoerigkeit",
    ("citizenship", 2): "Ausland_Sonstige_Staatsangehoerigkeit",

    # ---- Citizenship groups (Staatsangehörigkeit Gruppen, 2022 codes) ------
    ("citizenship_group",  1): "Deutschland_Staatsangehoerigkeit_Gruppen",
    ("citizenship_group", 20): "Ausland_Sonstige_Staatsangehoerigkeit_Gruppen",
    ("citizenship_group", 21): "EU27_Land_Staatsangehoerigkeit_Gruppen",
    ("citizenship_group", 22): "Sonstiges_Europa_Staatsangehoerigkeit_Gruppen",
    ("citizenship_group", 23): "Sonstige_Welt_Staatsangehoerigkeit_Gruppen",
    ("citizenship_group", 24): "Sonstige_Staatsangehoerigkeit_Gruppen",

    # ---- Households (Privathaushalte) --------------------------------------
    ("households",         0): "Insgesamt_Haushalte_Groesse_des_privaten_Haushalts",
    ("household_size_avg", 0): "DurchschnHHGroesse_Durchschn_Haushaltsgroesse",

    # household size groups
    ("household_size_group", 1): "1_Person_Groesse_des_privaten_Haushalts",
    ("household_size_group", 2): "2_Personen_Groesse_des_privaten_Haushalts",
    ("household_size_group", 3): "3_Personen_Groesse_des_privaten_Haushalts",
    ("household_size_group", 4): "4_Personen_Groesse_des_privaten_Haushalts",
    ("household_size_group", 5): "5_Personen_Groesse_des_privaten_Haushalts",
    ("household_size_group", 6): "6_Personen_und_mehr_Groesse_des_privaten_Haushalts",

    # ---- Families ----------------------------------------------------------
    ("families", 0): "Insgesamt_Familien_Grosse_Kernfamilie_bis6undmehrPers",

    # family type (Typ der Kernfamilie nach Kindern)
    ("family_type",  1): "Ehep_ohneKind_Typ_der_Kernfamilie_nach_Kindern",
    ("family_type",  2): "Ehep_mind_1Kind_unter18_Typ_der_Kernfamilie_nach_Kindern",
    ("family_type",  3): "Ehep_Kinder_ab18_Typ_der_Kernfamilie_nach_Kindern",
    ("family_type",  4): "EingetrLP_ohneKind_Typ_der_Kernfamilie_nach_Kindern",
    ("family_type",  5): "EingetrLP_mind_1Kind_unter18_Typ_der_Kernfamilie_nach_Kindern",
    ("family_type",  6): "EingetrLP_Kinder_ab18_Typ_der_Kernfamilie_nach_Kindern",
    ("family_type",  7): "NichtehelLG_ohneKind_Typ_der_Kernfamilie_nach_Kindern",
    ("family_type",  8): "NichtehelLG_mind_1Kind_unter18_Typ_der_Kernfamilie_nach_Kindern",
    ("family_type",  9): "NichtehelLG_Kinder_ab18_Typ_der_Kernfamilie_nach_Kindern",
    ("family_type", 10): "Vater_mind_1Kind_unter18_Typ_der_Kernfamilie_nach_Kindern",
    ("family_type", 11): "Vater_Kinder_ab18_Typ_der_Kernfamilie_nach_Kindern",
    ("family_type", 12): "Mutter_mind_1Kind_unter18_Typ_der_Kernfamilie_nach_Kindern",
    ("family_type", 13): "Mutter_Kinder_ab18_Typ_der_Kernfamilie_nach_Kindern",

    # ---- Buildings (Gebäude) -----------------------------------------------
    ("buildings", 0): "Insgesamt_Gebaeude_Gebaeude_nach_Baujahr_in_MZ_Klassen",

    # z22 'building_size' contains BUILDINGS by type+size. The upstream feature-name
    # swap (z22data issue #4) was FIXED in the 2026-06-12 re-process, so the name now
    # matches its content literally — Geb_* targets are semantically correct.
    ("building_size",  1): "FreiEFH_Geb_Gebaeudetyp_Groesse",
    ("building_size",  2): "EFH_DHH_Geb_Gebaeudetyp_Groesse",
    ("building_size",  3): "EFH_Reihenhaus_Geb_Gebaeudetyp_Groesse",
    ("building_size",  4): "Freist_ZFH_Geb_Gebaeudetyp_Groesse",
    ("building_size",  5): "ZFH_DHH_Geb_Gebaeudetyp_Groesse",
    ("building_size",  6): "ZFH_Reihenhaus_Geb_Gebaeudetyp_Groesse",
    ("building_size",  7): "MFH_3bis6Wohnungen_Geb_Gebaeudetyp_Groesse",
    ("building_size",  8): "MFH_7bis12Wohnungen_Geb_Gebaeudetyp_Groesse",
    ("building_size",  9): "MFH_13undmehrWohnungen_Geb_Gebaeudetyp_Groesse",
    ("building_size", 10): "AndererGebaeudetyp_Geb_Gebaeudetyp_Groesse",

    # z22 'dwelling_building_size' contains DWELLINGS by building type. After the
    # 2026-06-12 upstream fix (issue #4) the name matches its content literally —
    # Wohnung_* targets are semantically correct.
    ("dwelling_building_size",  1): "FreiEFH_Wohnung_Gebaeudetyp_Groesse",
    ("dwelling_building_size",  2): "EFH_DHH_Wohnung_Gebaeudetyp_Groesse",
    ("dwelling_building_size",  3): "EFH_Reihenhaus_Wohnung_Gebaeudetyp_Groesse",
    ("dwelling_building_size",  4): "Freist_ZFH_Wohnung_Gebaeudetyp_Groesse",
    ("dwelling_building_size",  5): "ZFH_DHH_Wohnung_Gebaeudetyp_Groesse",
    ("dwelling_building_size",  6): "ZFH_Reihenhaus_Wohnung_Gebaeudetyp_Groesse",
    ("dwelling_building_size",  7): "MFH_3bis6Wohnungen_Wohnung_Gebaeudetyp_Groesse",
    ("dwelling_building_size",  8): "MFH_7bis12Wohnungen_Wohnung_Gebaeudetyp_Groesse",
    ("dwelling_building_size",  9): "MFH_13undmehrWohnungen_Wohnung_Gebaeudetyp_Groesse",
    ("dwelling_building_size", 10): "AndererGebaeudetyp_Wohnung_Gebaeudetyp_Groesse",

    # buildings by number of dwellings (Gebäude nach Anzahl der Wohnungen)
    ("building_dwellings", 1): "1_Wohnung_Gebaeude_nach_Anzahl_der_Wohnungen",
    ("building_dwellings", 2): "2_Wohnungen_Gebaeude_nach_Anzahl_der_Wohnungen",
    ("building_dwellings", 3): "3bis6_Wohnungen_Gebaeude_nach_Anzahl_der_Wohnungen",
    ("building_dwellings", 4): "7bis12_Wohnungen_Gebaeude_nach_Anzahl_der_Wohnungen",
    ("building_dwellings", 5): "13undmehr_Wohnungen_Gebaeude_nach_Anzahl_der_Wohnungen",

    # building construction year MZ classes (Gebäude nach Baujahr in MZ-Klassen)
    ("building_constr_year", 1): "Vor1919_Gebaeude_nach_Baujahr_in_MZ_Klassen",
    ("building_constr_year", 2): "a1919bis1948_Gebaeude_nach_Baujahr_in_MZ_Klassen",
    ("building_constr_year", 3): "a1949bis1978_Gebaeude_nach_Baujahr_in_MZ_Klassen",
    ("building_constr_year", 4): "a1979bis1990_Gebaeude_nach_Baujahr_in_MZ_Klassen",
    ("building_constr_year", 5): "a1991bis2000_Gebaeude_nach_Baujahr_in_MZ_Klassen",
    ("building_constr_year", 6): "a2001bis2010_Gebaeude_nach_Baujahr_in_MZ_Klassen",
    ("building_constr_year", 7): "a2011bis2019_Gebaeude_nach_Baujahr_in_MZ_Klassen",
    ("building_constr_year", 8): "a2020undspaeter_Gebaeude_nach_Baujahr_in_MZ_Klassen",

    # building heating type (Gebäude nach überwiegender Heizungsart)
    ("building_heat_type", 1): "Fernheizung_Gebaeude_nach_ueberwiegender_Heizungsart",
    ("building_heat_type", 2): "Etagenheizung_Gebaeude_nach_ueberwiegender_Heizungsart",
    ("building_heat_type", 3): "Blockheizung_Gebaeude_nach_ueberwiegender_Heizungsart",
    ("building_heat_type", 4): "Zentralheizung_Gebaeude_nach_ueberwiegender_Heizungsart",
    ("building_heat_type", 5): "Einzel_Mehrraumoefen_Gebaeude_nach_ueberwiegender_Heizungsart",
    ("building_heat_type", 6): "keine_Heizung_Gebaeude_nach_ueberwiegender_Heizungsart",

    # building energy source (Gebäude nach Energieträger der Heizung)
    ("building_heat_src", 1): "Gas_Gebaeude_nach_Energietraeger_der_Heizung",
    ("building_heat_src", 2): "Heizoel_Gebaeude_nach_Energietraeger_der_Heizung",
    ("building_heat_src", 3): "Holz_Holzpellets_Gebaeude_nach_Energietraeger_der_Heizung",
    ("building_heat_src", 4): "Biomasse_Biogas_Gebaeude_nach_Energietraeger_der_Heizung",
    ("building_heat_src", 5): "Solar_Geothermie_Waermepumpen_Gebaeude_nach_Energietraeger_der_Heizung",
    ("building_heat_src", 6): "Strom_Gebaeude_nach_Energietraeger_der_Heizung",
    ("building_heat_src", 7): "Kohle_Gebaeude_nach_Energietraeger_der_Heizung",
    ("building_heat_src", 8): "Fernwaerme_Gebaeude_nach_Energietraeger_der_Heizung",
    ("building_heat_src", 9): "kein_Energietraeger_Gebaeude_nach_Energietraeger_der_Heizung",

    # ---- Dwellings (Wohnungen) ---------------------------------------------
    # NOTE: dwellings_0 in z22data = 21.3M (residential dwellings subset, NOT the 41.8M total
    # in T:'s Insgesamt_Wohnungen columns which is the sum of floor_space/rooms categories).
    # We use a distinct column name so it does NOT shadow the T: totals.
    ("dwellings",        0): "Wohngebaeude_Anzahl_Wohnungen",
    ("dwelling_space",   0): "durchschnFlaechejeWohn_Durchschn_Flaeche_je_Wohnung",
    ("inhabitant_space", 0): "durchschnFlaechejeBew_Durchschn_Flaeche_je_Bewohner",
    ("rent_avg",         0): "durchschnMieteQM_Durchschn_Nettokaltmiete",

    # floor space 10 m² intervals (Fläche der Wohnung)
    ("floor_space",  1): "unter30_Flaeche_der_Wohnung_10m2_Intervalle",
    ("floor_space",  2): "30bis39_Flaeche_der_Wohnung_10m2_Intervalle",
    ("floor_space",  3): "40bis49_Flaeche_der_Wohnung_10m2_Intervalle",
    ("floor_space",  4): "50bis59_Flaeche_der_Wohnung_10m2_Intervalle",
    ("floor_space",  5): "60bis69_Flaeche_der_Wohnung_10m2_Intervalle",
    ("floor_space",  6): "70bis79_Flaeche_der_Wohnung_10m2_Intervalle",
    ("floor_space",  7): "80bis89_Flaeche_der_Wohnung_10m2_Intervalle",
    ("floor_space",  8): "90bis99_Flaeche_der_Wohnung_10m2_Intervalle",
    ("floor_space",  9): "100bis109_Flaeche_der_Wohnung_10m2_Intervalle",
    ("floor_space", 10): "110bis119_Flaeche_der_Wohnung_10m2_Intervalle",
    ("floor_space", 11): "120bis129_Flaeche_der_Wohnung_10m2_Intervalle",
    ("floor_space", 12): "130bis139_Flaeche_der_Wohnung_10m2_Intervalle",
    ("floor_space", 13): "140bis149_Flaeche_der_Wohnung_10m2_Intervalle",
    ("floor_space", 14): "150bis159_Flaeche_der_Wohnung_10m2_Intervalle",
    ("floor_space", 15): "160bis169_Flaeche_der_Wohnung_10m2_Intervalle",
    ("floor_space", 16): "170bis179_Flaeche_der_Wohnung_10m2_Intervalle",
    ("floor_space", 17): "180undmehr_Flaeche_der_Wohnung_10m2_Intervalle",

    # dwelling rooms (Wohnungen nach Zahl der Räume)
    ("dwelling_rooms", 1): "1Raum_Wohnungen_nach_Zahl_der_Raeume",
    ("dwelling_rooms", 2): "2Raeume_Wohnungen_nach_Zahl_der_Raeume",
    ("dwelling_rooms", 3): "3Raeume_Wohnungen_nach_Zahl_der_Raeume",
    ("dwelling_rooms", 4): "4Raeume_Wohnungen_nach_Zahl_der_Raeume",
    ("dwelling_rooms", 5): "5Raeume_Wohnungen_nach_Zahl_der_Raeume",
    ("dwelling_rooms", 6): "6Raeume_Wohnungen_nach_Zahl_der_Raeume",
    ("dwelling_rooms", 7): "7undmehrRaeume_Wohnungen_nach_Zahl_der_Raeume",

    # dwelling heating type (Heizungsart – Wohnungen)
    ("dwelling_heat_type", 1): "Fernheizung_Heizungsart",
    ("dwelling_heat_type", 2): "Etagenheizung_Heizungsart",
    ("dwelling_heat_type", 3): "Blockheizung_Heizungsart",
    ("dwelling_heat_type", 4): "Zentralheizung_Heizungsart",
    ("dwelling_heat_type", 5): "Einzel_Mehrraumoefen_Heizungsart",
    ("dwelling_heat_type", 6): "keine_Heizung_Heizungsart",

    # dwelling energy source (Energieträger – Wohnungen)
    ("dwelling_heat_src", 1): "Gas_Energietraeger",
    ("dwelling_heat_src", 2): "Heizoel_Energietraeger",
    ("dwelling_heat_src", 3): "Holz_Holzpellets_Energietraeger",
    ("dwelling_heat_src", 4): "Biomasse_Biogas_Energietraeger",
    ("dwelling_heat_src", 5): "Solar_Geothermie_Waermepumpen_Energietraeger",
    ("dwelling_heat_src", 6): "Strom_Energietraeger",
    ("dwelling_heat_src", 7): "Kohle_Energietraeger",
    ("dwelling_heat_src", 8): "Fernwaerme_Energietraeger",
    ("dwelling_heat_src", 9): "kein_Energietraeger_Energietraeger",

    # ---- Vacancies / owner-occupier ----------------------------------------
    ("vacancies",         0): "Leerstandsquote_Leerstandsquote",
    ("market_vacancies",  0): "marktaktive_Leerstandsquote_Marktaktive_Leerstandsquote",
    ("owner_occupier",    0): "Eigentuemerquote_Eigentuemerquote",
}


# ---------------------------------------------------------------------------
# GITTER_ID formula
# ---------------------------------------------------------------------------

def make_gitter_id(x_mp: int, y_mp: int, level: str) -> str:
    """Reconstruct the INSPIRE GITTER_ID from midpoint coordinates.

    Verified for all three levels against the T: notebook-era merged CSVs.

    Parameters
    ----------
    x_mp, y_mp : int
        Cell midpoint in EPSG:3035 metres (as stored in z22data parquets).
    level : str
        "10km", "1km", or "100m".

    Returns
    -------
    str
        e.g. "CRS3035RES10000mN2680000E4330000"
    """
    res_str = _LEVEL_RES_STR[level]
    half    = _LEVEL_HALF[level]
    return f"CRS3035RES{res_str}N{y_mp - half}E{x_mp - half}"


# ---------------------------------------------------------------------------
# Downloader
# ---------------------------------------------------------------------------

def download_z22(
    level: str,
    features: list[tuple[str, int]],
    dest_dir: str | Path,
    force: bool = False,
    base_url: str = Z22DATA_BASE_URL,
) -> list[Path]:
    """Download z22data parquet files for the given level and feature list.

    Parameters
    ----------
    level : str
        "10km", "1km", or "100m".
    features : list of (feature_name, category_code)
        Which parquets to download.
    dest_dir : Path
        Directory to save files; created if it does not exist.
    force : bool
        Re-download even if the file already exists.
    base_url : str
        Base URL of the z22data raw GitHub mirror.

    Returns
    -------
    list of Path
        Paths of all downloaded (or already-cached) parquet files.
    """
    from cleancensus.progress import progress_iter

    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    paths = []
    for feat, cat in progress_iter(features, f"z22/download-{level}", total=len(features)):
        fname = f"{feat}_{cat}.parquet"
        dest_path = dest_dir / fname
        if dest_path.exists() and not force:
            paths.append(dest_path)
            continue
        url = f"{base_url}/z22_data_{level}/{fname}"
        _download_file(url, dest_path)
        paths.append(dest_path)
    return paths


def _download_file(url: str, dest: Path, retries: int = 3) -> None:
    """Download *url* to *dest* with retry logic."""
    req = urllib.request.Request(url, headers={"User-Agent": "cleancensus/z22 (+https://github.com/JsLth/z22data)"})
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = resp.read()
            dest.write_bytes(data)
            return
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt < retries - 1:
                time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"Failed to download {url} after {retries} attempts: {last_exc}") from last_exc


# ---------------------------------------------------------------------------
# Table builder
# ---------------------------------------------------------------------------

def build_merged_table(level: str, src_dir: str | Path) -> "pd.DataFrame":
    """Read all needed feature parquets and assemble the wide merged table.

    Parameters
    ----------
    level : str
        "10km", "1km", or "100m".
    src_dir : Path
        Directory containing the downloaded parquet files.

    Returns
    -------
    pd.DataFrame
        Wide frame with GITTER_ID_{level}, x_mp_{level}, y_mp_{level} and one
        column per FEATURE_MAP entry (named ``{base}_{level}-Gitter``).
        Missing cells = NaN (downstream fillna handles them).
    """
    import pandas as pd
    import pyarrow.parquet as pq

    from cleancensus.progress import progress_iter

    src_dir = Path(src_dir)
    suffix  = f"_{level}-Gitter"
    gid_col = f"GITTER_ID_{level}"
    x_col   = f"x_mp_{level}"
    y_col   = f"y_mp_{level}"

    # Phase 1: collect all (GITTER_ID, x, y) pairs from ALL parquets to get complete
    # coordinate coverage, then merge feature values on GITTER_ID.
    all_coords: dict[str, tuple[int, int]] = {}
    feature_cols: list[tuple[str, "pd.Series"]] = []

    for (feat, cat), base_name in progress_iter(
        FEATURE_MAP.items(), f"z22/build-{level}", total=len(FEATURE_MAP)
    ):
        parquet_path = src_dir / f"{feat}_{cat}.parquet"
        if not parquet_path.exists():
            # Feature not downloaded – will appear as NaN in output (silently)
            continue

        df = pq.read_table(parquet_path).to_pandas()
        # z22data parquet dtypes are inconsistent across levels (e.g. 100m
        # family_type_* carry value as STRING while 10km/1km are int64).
        # Coerce defensively; verified loss-free (the strings are plain digits).
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        col_name = base_name + suffix

        # Build GITTER_ID
        gids = [
            make_gitter_id(int(x), int(y), level)
            for x, y in zip(df["x"], df["y"])
        ]
        df[gid_col] = gids

        # Accumulate coordinate lookup (first occurrence wins)
        for gid, x, y in zip(gids, df["x"], df["y"]):
            if gid not in all_coords:
                all_coords[gid] = (int(x), int(y))

        feature_cols.append((col_name, df.set_index(gid_col)["value"]))

    if not feature_cols:
        raise FileNotFoundError(
            f"No parquet files found in {src_dir} for level={level!r}. "
            "Run download_z22() first."
        )

    # Phase 2: build the coordinate frame from the union of all seen cells
    all_ids = sorted(all_coords)
    coords_df = pd.DataFrame({
        gid_col: all_ids,
        x_col:   [all_coords[g][0] for g in all_ids],
        y_col:   [all_coords[g][1] for g in all_ids],
    }).set_index(gid_col)

    # Phase 3: build feature frame from collected series, then concat once
    series_dict: dict[str, "pd.Series"] = {}
    for col_name, series in feature_cols:
        series_dict[col_name] = series
    feat_df = pd.DataFrame(series_dict)

    merged = pd.concat([coords_df, feat_df], axis=1).reset_index()
    merged = merged.rename(columns={"index": gid_col}) if "index" in merged.columns else merged

    # Reorder: ID + coords first, then feature columns
    feat_cols_names = [c for c in merged.columns if c not in (gid_col, x_col, y_col)]
    merged = merged[[gid_col, x_col, y_col] + feat_cols_names]
    return merged


# ---------------------------------------------------------------------------
# Pipeline entry point
# ---------------------------------------------------------------------------

def run_merge_z22(cfg) -> None:
    """Merge stage: download z22data parquets and build per-level wide tables.

    Additionally ingests the 6 Destatis-CSV ZIP supplements (if present in
    cfg.destatis_raw_dir) and left-joins them onto the z22 table.

    Writes ``work_dir/merged_{level}_gitter.parquet`` for each level.
    Downloads go to ``inputs_dir.parent / "raw" / "z22" / {level}`` (gitignored).

    Parameters
    ----------
    cfg : cleancensus.config.Config
    """
    import pyarrow as pa
    import pyarrow.parquet as pq

    from cleancensus.destatis_csv import merge_destatis_tables

    features = list(FEATURE_MAP.keys())

    levels = ["10km", "1km", "100m"]
    for level in levels:
        raw_dir = cfg.inputs_dir.parent / "raw" / "z22" / level
        log.info(f"level={level}: downloading to {raw_dir} ...")
        download_z22(level, features, raw_dir)

        log.info(f"level={level}: building z22 merged table ...")
        df = build_merged_table(level, raw_dir)

        # ---- Destatis-CSV supplement ----------------------------------------
        destatis_dir = cfg.destatis_raw_dir
        if destatis_dir.exists():
            log.info(f"level={level}: ingesting Destatis-CSV supplement from {destatis_dir} ...")
            destatis_df = merge_destatis_tables(level, destatis_dir)
            if destatis_df is not None:
                gid_col = f"GITTER_ID_{level}"
                # NOTE: z22data's `households` grid (Insgesamt_Haushalte_Groesse_des_
                # privaten_Haushalts) was under-populated at fine resolutions (values
                # zeroed for most cells) until JsLth/z22data took the totals directly
                # from the official census totals (fixed 2026-06-13). The current upstream
                # is dense and matches the official Destatis Insgesamt_Haushalte exactly
                # (national 10km 40.24M / 1km 40.22M / 100m 39.62M, every cell populated),
                # so z22 is the primary source again and wins the overlap below. Cache
                # note: delete pre-2026-06-13 cached households_0 parquets so the corrected
                # dense version is re-downloaded.
                # collision guard: z22data already covers some supplement columns
                # (e.g. family_type == Typ_der_Kernfamilie_nach_Kindern, gated EXACT)
                # — a plain merge would produce _x/_y duplicate columns that crash
                # downstream parquet writes. z22 columns take precedence.
                overlap = [c for c in destatis_df.columns
                           if c != gid_col and c in df.columns]
                if overlap:
                    log.info(f"level={level}: dropping {len(overlap)} supplement "
                             f"columns already provided by z22data (e.g. {overlap[0]})")
                    destatis_df = destatis_df.drop(columns=overlap)
                before = df.shape[1]
                df = df.merge(destatis_df, on=gid_col, how="left")
                added = df.shape[1] - before
                log.info(f"level={level}: added {added} Destatis-CSV columns")
            else:
                log.warning(f"level={level}: no Destatis ZIPs found in {destatis_dir}, skipping supplement")
        else:
            log.warning(
                f"level={level}: {destatis_dir} not found — "
                "Destatis supplement skipped (z22-only mode). "
                "Copy the 6 ZIPs there to include the 6 missing topics."
            )
        # ----------------------------------------------------------------------

        # fail fast on non-numeric data columns (a stray object column would
        # otherwise crash much later inside pyarrow's threaded conversion)
        gid_col = f"GITTER_ID_{level}"
        bad = [c for c in df.columns
               if c != gid_col and df[c].dtype == object]
        if bad:
            raise TypeError(
                f"[merge/z22] level={level}: non-numeric data columns after merge "
                f"(first 5): {bad[:5]} — refusing to write a corrupt merged table")

        out_path = cfg.work_dir / names.work("merge", level)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(pa.Table.from_pandas(df), out_path)
        log.info(f"level={level}: wrote {out_path} ({len(df):,} rows, {df.shape[1]} cols)")


def merge_complete(cfg) -> bool:
    """Return True if all three merged parquets exist in work_dir."""
    return all(
        names.resolve(cfg.work_dir, names.work("merge", level)).exists()
        for level in ("10km", "1km", "100m")
    )
