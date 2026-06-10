"""Spec catalog for the additional topics to harmonize (extends the original 8).

Naming convention identical to other_binned_data.ipynb: base names carry the
10km suffix; levelize() swaps the suffix per level. Each topic keeps its OWN
total chain (universes differ; see the plan's Background section).

Default scope = MID_CONTROLLABLE_DEFAULT: the only topics that are directly
controllable via MiD household data collected for ALL households
(haustyp = geocoded building type; HP_ALTER_1..6 = member ages)."""
from harmonization import TopicSpec, levelize, BLEND_STD

# tier -> list of (name, total_col_10km, [category_cols_10km], alpha)
RAW_TOPICS = {
    1: [
        ("Geb_Gebaeudetyp",
         "Insgesamt_Gebaeude_Geb_Gebaeudetyp_Groesse_10km-Gitter",
         ["FreiEFH_Geb_Gebaeudetyp_Groesse_10km-Gitter",
          "EFH_DHH_Geb_Gebaeudetyp_Groesse_10km-Gitter",
          "EFH_Reihenhaus_Geb_Gebaeudetyp_Groesse_10km-Gitter",
          "Freist_ZFH_Geb_Gebaeudetyp_Groesse_10km-Gitter",
          "ZFH_DHH_Geb_Gebaeudetyp_Groesse_10km-Gitter",
          "ZFH_Reihenhaus_Geb_Gebaeudetyp_Groesse_10km-Gitter",
          "MFH_3bis6Wohnungen_Geb_Gebaeudetyp_Groesse_10km-Gitter",
          "MFH_7bis12Wohnungen_Geb_Gebaeudetyp_Groesse_10km-Gitter",
          "MFH_13undmehrWohnungen_Geb_Gebaeudetyp_Groesse_10km-Gitter",
          "AndererGebaeudetyp_Geb_Gebaeudetyp_Groesse_10km-Gitter"], 0.85),
        ("Geb_AnzahlWohnungen",
         "Insgesamt_Gebaeude_Gebaeude_nach_Anzahl_der_Wohnungen_10km-Gitter",
         ["1_Wohnung_Gebaeude_nach_Anzahl_der_Wohnungen_10km-Gitter",
          "2_Wohnungen_Gebaeude_nach_Anzahl_der_Wohnungen_10km-Gitter",
          "3bis6_Wohnungen_Gebaeude_nach_Anzahl_der_Wohnungen_10km-Gitter",
          "7bis12_Wohnungen_Gebaeude_nach_Anzahl_der_Wohnungen_10km-Gitter",
          "13undmehr_Wohnungen_Gebaeude_nach_Anzahl_der_Wohnungen_10km-Gitter"], 0.85),
        ("Geb_Baujahr",
         "Insgesamt_Gebaeude_Gebaeude_nach_Baujahr_in_MZ_Klassen_10km-Gitter",
         ["Vor1919_Gebaeude_nach_Baujahr_in_MZ_Klassen_10km-Gitter",
          "a1919bis1948_Gebaeude_nach_Baujahr_in_MZ_Klassen_10km-Gitter",
          "a1949bis1978_Gebaeude_nach_Baujahr_in_MZ_Klassen_10km-Gitter",
          "a1979bis1990_Gebaeude_nach_Baujahr_in_MZ_Klassen_10km-Gitter",
          "a1991bis2000_Gebaeude_nach_Baujahr_in_MZ_Klassen_10km-Gitter",
          "a2001bis2010_Gebaeude_nach_Baujahr_in_MZ_Klassen_10km-Gitter",
          "a2011bis2019_Gebaeude_nach_Baujahr_in_MZ_Klassen_10km-Gitter",
          "a2020undspaeter_Gebaeude_nach_Baujahr_in_MZ_Klassen_10km-Gitter"], 0.85),
        ("Geb_Energietraeger",
         "Insgesamt_Energietraeger_Gebaeude_nach_Energietraeger_der_Heizung_10km-Gitter",
         ["Gas_Gebaeude_nach_Energietraeger_der_Heizung_10km-Gitter",
          "Heizoel_Gebaeude_nach_Energietraeger_der_Heizung_10km-Gitter",
          "Holz_Holzpellets_Gebaeude_nach_Energietraeger_der_Heizung_10km-Gitter",
          "Biomasse_Biogas_Gebaeude_nach_Energietraeger_der_Heizung_10km-Gitter",
          "Solar_Geothermie_Waermepumpen_Gebaeude_nach_Energietraeger_der_Heizung_10km-Gitter",
          "Strom_Gebaeude_nach_Energietraeger_der_Heizung_10km-Gitter",
          "Kohle_Gebaeude_nach_Energietraeger_der_Heizung_10km-Gitter",
          "Fernwaerme_Gebaeude_nach_Energietraeger_der_Heizung_10km-Gitter",
          "kein_Energietraeger_Gebaeude_nach_Energietraeger_der_Heizung_10km-Gitter"], 0.85),
        ("Whg_Gebaeudetyp",
         "Insgesamt_Wohnungen_Wohnung_Gebaeudetyp_Groesse_10km-Gitter",
         ["FreiEFH_Wohnung_Gebaeudetyp_Groesse_10km-Gitter",
          "EFH_DHH_Wohnung_Gebaeudetyp_Groesse_10km-Gitter",
          "EFH_Reihenhaus_Wohnung_Gebaeudetyp_Groesse_10km-Gitter",
          "Freist_ZFH_Wohnung_Gebaeudetyp_Groesse_10km-Gitter",
          "ZFH_DHH_Wohnung_Gebaeudetyp_Groesse_10km-Gitter",
          "ZFH_Reihenhaus_Wohnung_Gebaeudetyp_Groesse_10km-Gitter",
          "MFH_3bis6Wohnungen_Wohnung_Gebaeudetyp_Groesse_10km-Gitter",
          "MFH_7bis12Wohnungen_Wohnung_Gebaeudetyp_Groesse_10km-Gitter",
          "MFH_13undmehrWohnungen_Wohnung_Gebaeudetyp_Groesse_10km-Gitter",
          "AndererGebaeudetyp_Wohnung_Gebaeudetyp_Groesse_10km-Gitter"], 0.85),
        ("Whg_Heizungsart",
         "Insgesamt_Heizungsart_Heizungsart_10km-Gitter",
         ["Fernheizung_Heizungsart_10km-Gitter",
          "Etagenheizung_Heizungsart_10km-Gitter",
          "Blockheizung_Heizungsart_10km-Gitter",
          "Zentralheizung_Heizungsart_10km-Gitter",
          "Einzel_Mehrraumoefen_Heizungsart_10km-Gitter",
          "keine_Heizung_Heizungsart_10km-Gitter"], 0.85),
    ],
    2: [
        ("HH_Seniorenstatus",
         "Insgesamt_Haushalte_Seniorenstatus_eines_privaten_Haushalts_10km-Gitter",
         ["HH_nurSenioren_Seniorenstatus_eines_privaten_Haushalts_10km-Gitter",
          "HH_mitSenioren_Seniorenstatus_eines_privaten_Haushalts_10km-Gitter",
          "HH_ohneSenioren_Seniorenstatus_eines_privaten_Haushalts_10km-Gitter"], 0.90),
        ("HH_Familientyp",
         "Insgesamt_Haushalte_Typ_priv_HH_Familie_10km-Gitter",
         ["EinpersHH_SingleHH_Typ_priv_HH_Familie_10km-Gitter",
          "Paare_ohneKind_Typ_priv_HH_Familie_10km-Gitter",
          "Paare_mitKind_Typ_priv_HH_Familie_10km-Gitter",
          "Alleinerziehende_Typ_priv_HH_Familie_10km-Gitter",
          "MehrpersHHohneKernfam_Typ_priv_HH_Familie_10km-Gitter"], 0.90),
        ("Pers_Staatsangehoerigkeit",
         "Insgesamt_Bevoelkerung_Staatsangehoerigkeit_10km-Gitter",
         ["Deutschland_Staatsangehoerigkeit_10km-Gitter",
          "Ausland_Sonstige_Staatsangehoerigkeit_10km-Gitter"], 0.90),
    ],
    3: [
        ("Pers_StaatsangGruppen",
         "Insgesamt_Bevoelkerung_Staatsangehoerigkeit_Gruppen_10km-Gitter",
         ["Deutschland_Staatsangehoerigkeit_Gruppen_10km-Gitter",
          "Ausland_Sonstige_Staatsangehoerigkeit_Gruppen_10km-Gitter",
          "EU27_Land_Staatsangehoerigkeit_Gruppen_10km-Gitter",
          "Sonstiges_Europa_Staatsangehoerigkeit_Gruppen_10km-Gitter",
          "Sonstige_Welt_Staatsangehoerigkeit_Gruppen_10km-Gitter",
          "Sonstige_Staatsangehoerigkeit_Gruppen_10km-Gitter"], 0.85),
        ("Pers_ZahlStaatsang",
         "Insgesamt_Bevoelkerung_Zahl_der_Staatsangehoerigkeiten_10km-Gitter",
         ["EineStaatsang_Zahl_der_Staatsangehoerigkeiten_10km-Gitter",
          "Mehrere_deutsch_und_auslaendisch_Zahl_der_Staatsangehoerigkeiten_10km-Gitter",
          "Mehrere_nur_auslaendisch_Zahl_der_Staatsangehoerigkeiten_10km-Gitter",
          "Nicht_bekannt_Zahl_der_Staatsangehoerigkeiten_10km-Gitter"], 0.85),
        ("Pers_Religion",
         "Insgesamt_Bevoelkerung_Religion_10km-Gitter",
         ["Roemisch_katholisch_Religion_10km-Gitter",
          "Evangelisch_Religion_10km-Gitter",
          "Sonstige_keine_ohneAngabe_Religion_10km-Gitter"], 0.85),
        ("Fam_Groesse",
         "Insgesamt_Familien_Grosse_Kernfamilie_bis6undmehrPers_10km-Gitter",
         ["a2Personen_Grosse_Kernfamilie_bis6undmehrPers_10km-Gitter",
          "a3Personen_Grosse_Kernfamilie_bis6undmehrPers_10km-Gitter",
          "a4Personen_Grosse_Kernfamilie_bis6undmehrPers_10km-Gitter",
          "a5Personen_Grosse_Kernfamilie_bis6undmehrPers_10km-Gitter",
          "a6Pers_und_mehr_Grosse_Kernfamilie_bis6undmehrPers_10km-Gitter"], 0.85),
        ("Fam_TypNachKindern",
         "Insgesamt_Familie_Typ_der_Kernfamilie_nach_Kindern_10km-Gitter",
         ["Ehep_ohneKind_Typ_der_Kernfamilie_nach_Kindern_10km-Gitter",
          "Ehep_mind_1Kind_unter18_Typ_der_Kernfamilie_nach_Kindern_10km-Gitter",
          "Ehep_Kinder_ab18_Typ_der_Kernfamilie_nach_Kindern_10km-Gitter",
          "EingetrLP_ohneKind_Typ_der_Kernfamilie_nach_Kindern_10km-Gitter",
          "EingetrLP_mind_1Kind_unter18_Typ_der_Kernfamilie_nach_Kindern_10km-Gitter",
          "EingetrLP_Kinder_ab18_Typ_der_Kernfamilie_nach_Kindern_10km-Gitter",
          "NichtehelLG_ohneKind_Typ_der_Kernfamilie_nach_Kindern_10km-Gitter",
          "NichtehelLG_mind_1Kind_unter18_Typ_der_Kernfamilie_nach_Kindern_10km-Gitter",
          "NichtehelLG_Kinder_ab18_Typ_der_Kernfamilie_nach_Kindern_10km-Gitter",
          "Vater_mind_1Kind_unter18_Typ_der_Kernfamilie_nach_Kindern_10km-Gitter",
          "Vater_Kinder_ab18_Typ_der_Kernfamilie_nach_Kindern_10km-Gitter",
          "Mutter_mind_1Kind_unter18_Typ_der_Kernfamilie_nach_Kindern_10km-Gitter",
          "Mutter_Kinder_ab18_Typ_der_Kernfamilie_nach_Kindern_10km-Gitter"], 0.85),
    ],
}

DEFAULT_TIERS = (1, 2)

# The only topics controllable DIRECTLY via MiD household data collected for ALL
# households (haustyp = geocoded building type; HP_ALTER_1..6 = member ages).
# Everything else in RAW_TOPICS is an opt-in catalog (--topics).
MID_CONTROLLABLE_DEFAULT = ("Whg_Gebaeudetyp", "HH_Seniorenstatus")


def build_new_topic_specs(level: str, tiers=DEFAULT_TIERS, names=None):
    """Mirror of build_topic_specs_for_level for the NEW topics.

    level: "1km" (parent 10km) or "100m" (parent 1km).
    names: optional explicit topic-name subset (overrides tiers).
    """
    specs = []
    for tier, topics in RAW_TOPICS.items():
        for name, tot_10, cats_10, alpha in topics:
            if names is not None:
                if name not in names:
                    continue
            elif tier not in tiers:
                continue
            if level == "1km":
                parent_cols, child_cols = cats_10, levelize(cats_10, "1km")
                child_total = tot_10.replace("_10km-Gitter", "_1km-Gitter")
            elif level == "100m":
                parent_cols, child_cols = levelize(cats_10, "1km"), levelize(cats_10, "100m")
                child_total = tot_10.replace("_10km-Gitter", "_100m-Gitter")
            else:
                raise ValueError(f"Unknown level: {level}")
            specs.append(TopicSpec(
                name=name, parent_cat_cols=parent_cols, child_cat_cols=child_cols,
                child_row_total_col=child_total, alpha=alpha, blend=BLEND_STD,
            ))
    return specs
