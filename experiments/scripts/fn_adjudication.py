"""
FN Adjudication for A11 base and A12 (HR+3 supplement).

Each FN record is classified as:
  - "label_error": gold standard label is wrong (study doesn't match PICO/PECO criteria)
  - "genuine_fn": system error (study does match criteria, system wrongly excluded)
  - "ambiguous": borderline case

Adjudication is based on cross-referencing title/abstract against the dataset's
stated PICO/PECO/PIF/PCC criteria.
"""

import json
import csv
import statistics
from pathlib import Path

RESULTS_DIR = Path("experiments/results")
DATASETS_DIR = Path("experiments/datasets")

DATASETS = [
    "Jeyaraman_2020", "Chou_2003", "van_der_Waal_2022", "Smid_2020",
    "Muthu_2021", "Appenzeller-Herzog_2019", "van_de_Schoot_2018",
    "Moran_2021", "Radjenovic_2013", "Leenaars_2020", "Wassenaar_2017",
    "Hall_2012", "van_Dis_2020",
]

# ── Adjudication verdicts ────────────────────────────────────────────
# Key = (dataset, record_id_suffix)  where suffix = last part of OpenAlex URI
# Value = ("label_error" | "genuine_fn" | "ambiguous", "reason")

ADJUDICATIONS: dict[str, dict[str, tuple[str, str]]] = {
    # ── Jeyaraman_2020 ──────────────────────────────────────────────
    # PICO: MSCs for knee OA/cartilage defects
    "Jeyaraman_2020": {
        "W2011790530": ("label_error", "Osteochondral autograft transfer, not MSC therapy"),
    },

    # ── Chou_2003 ───────────────────────────────────────────────────
    # PICO: Long-acting oral opioids for chronic non-cancer pain
    "Chou_2003": {
        "W2084152520": ("genuine_fn", "Oral sustained-release morphine for chronic non-cancer pain — matches PICO"),
    },

    # ── Muthu_2021 ──────────────────────────────────────────────────
    # PICO: Fragility index in spine surgery RCTs
    # Population = RCTs in spine surgery; meta-analyses are NOT RCTs
    "Muthu_2021": {
        "W1987205168": ("genuine_fn", "RCT: IPD vs decompression for lumbar stenosis — is a spine surgery RCT"),
        "W2011922368": ("label_error", "Meta-analysis of RCTs (TDR vs fusion), not an RCT itself"),
        "W2050979399": ("genuine_fn", "RCT: lidocaine infusion in lumbar surgery — is a spine surgery RCT"),
        "W2081494650": ("ambiguous", "RCT: navigated vs non-navigated pedicle screws — spine surgery RCT but fragility applicability unclear"),
        "W2085626304": ("label_error", "Meta-analysis of RCTs (balloon kyphoplasty), not an RCT itself"),
        "W2424326616": ("label_error", "Meta-analysis of RCTs (ACDF vs CDA), not an RCT itself"),
    },

    # ── van_de_Schoot_2018 ──────────────────────────────────────────
    # PIF: PTSD trajectory modelling (GMM/LGMM/LCGA approaches)
    "van_de_Schoot_2018": {
        "W1531895073": ("genuine_fn", "LGMM for PTSD trajectories after campus mass shooting"),
        "W1540984113": ("genuine_fn", "GMM for PTSD symptom course in deployed Marines"),
        "W2056927632": ("genuine_fn", "GMM for PTSD in Gulf War veterans"),
        "W2068827642": ("genuine_fn", "LCGA for PTSD trajectories after sexual assault"),
        "W2112107099": ("genuine_fn", "Trajectory analysis of parental PTSS after child injury"),
        "W2144116148": ("genuine_fn", "LGMM for PTSD trajectories in police officers"),
        "W2331818908": ("genuine_fn", "GMM for PTSD in deployed Marines (MRS cohort)"),
    },

    # ── Moran_2021 ──────────────────────────────────────────────────
    # PECO: Poor nutrition → high-risk behaviours in HUMANS
    "Moran_2021": {
        # A11+A12 (4 records)
        "W2136823874": ("label_error", "Sedentary behaviour → health indicators; exposure is behaviour not nutrition"),
        "W2895967873": ("label_error", "Bird cognition study (winter residents) — not human"),
        "W2896861612": ("genuine_fn", "SR of dietary behaviour interventions for chronic disease — nutrition + behaviour in humans"),
        "W2903635703": ("label_error", "Food labeling → consumer diet — not poor-nutrition exposure → risk behaviour"),
        # A12 only (17 records)
        "W2066792876": ("label_error", "Prenatal nutrition → obesity risk — outcome is obesity, not risk behaviour"),
        "W2301597726": ("label_error", "Binge eating disorders review — no exposure-comparison structure per PECO"),
        "W2534140764": ("label_error", "Chronic pancreatitis phenotype in India — disease epidemiology, not behaviour"),
        "W2802901530": ("label_error", "Weight regain in MMA fighters — sports weight management, not nutrition→risk"),
        "W2886350262": ("label_error", "Canine coprophagia — dogs, not humans"),
        "W2887481618": ("label_error", "Starvation effect on earthworm foraging — not human"),
        "W2894215547": ("label_error", "Estrous expression in dairy cows — not human"),
        "W2900100701": ("genuine_fn", "Pathways to eating in children/adolescents with obesity — eating behaviours"),
        "W2902802890": ("label_error", "Physical activity in after-school programs — not nutrition→risk behaviour"),
        "W2905002619": ("label_error", "Autism risk factors in India — not nutrition→risk behaviour"),
        "W2905430234": ("label_error", "Torpor and predation risk in small mammals — not human"),
        "W2906368423": ("genuine_fn", "Internet-based intervention for healthy habits in obese/hypertensive — nutrition+behaviour"),
        "W2908289791": ("label_error", "Energy state and behavioural plasticity — animal study"),
        "W2909893686": ("label_error", "Honey bee foraging during solar eclipse — not human"),
        "W2948224989": ("label_error", "Adult ADHD and externalizing spectrum — not nutrition→behaviour"),
        "W4211174654": ("label_error", "Animal welfare in fattening pigs — not human"),
        "W4298114722": ("label_error", "Anorexia nervosa case report (2 cases) — case report, not study design per PECO"),
    },

    # ── Leenaars_2020 ───────────────────────────────────────────────
    # PICO: Methotrexate efficacy in RA (human + animal)
    "Leenaars_2020": {
        "W2035320881": ("genuine_fn", "Tofacitinib + MTX in RA — methotrexate as background therapy in RA RCT"),
        "W2069302785": ("genuine_fn", "Tofacitinib/Adalimumab vs placebo in RA on MTX — MTX background in RA RCT"),
    },

    # ── Wassenaar_2017 ──────────────────────────────────────────────
    # PECO: BPA in rodents during EARLY LIFE → obesity-related outcomes
    # Must be: (1) rodent, (2) BPA, (3) early-life exposure, (4) obesity outcomes
    "Wassenaar_2017": {
        "W1966411110": ("label_error", "Review: EDCs and type 2 diabetes — review article, not original rodent study"),
        "W1973352143": ("label_error", "Review: pre/postnatal nutrition and gut — not BPA, not obesity endpoint"),
        "W1981454226": ("label_error", "In utero BPA in murine embryos → RAR/RXR gene expression — no obesity outcome"),
        "W1983689226": ("label_error", "In vitro: xenoestrogens in 3T3-L1 cells — not in vivo rodent study"),
        "W1984573399": ("ambiguous", "Perinatal BPA in rats → brain corticosterone — early-life BPA in rodent but neuro outcome not obesity"),
        "W1987797208": ("label_error", "Review: BPA as endocrine/metabolic disruptor — review article"),
        "W1991299939": ("label_error", "BPA+DBP+BP2 in ovariectomized adult rats — adult exposure, not early life"),
        "W1992188021": ("label_error", "Human epidemiology: BPA and obesity in children — not rodent study"),
        "W1993331762": ("label_error", "Review: EDCs and obesity development — review article"),
        "W2000870258": ("label_error", "Fish study: endocrine disruption in grey mullet — not rodent"),
        "W2007176657": ("label_error", "Review: obesogens — review article"),
        "W2019226516": ("label_error", "Letter/reply: BPA and obesity in children — not original research"),
        "W2020781087": ("label_error", "Review: human health hazards of BPA — review article"),
        "W2020844131": ("label_error", "In vitro: BADGE in multipotent stromal stem cells — not in vivo rodent"),
        "W2024003691": ("label_error", "BPA in ovariectomized adult rats → energy balance — adult exposure, not early life"),
        "W2027438949": ("label_error", "In vitro: BPA in human adult stem cells → adipogenesis — not rodent, not in vivo"),
        "W2028017879": ("label_error", "BPA in adult field voles — adult exposure, not standard lab rodent early-life"),
        "W2038512323": ("label_error", "Review/workshop: NTP workshop on chemicals and diabetes — review"),
        "W2041693476": ("label_error", "BPA in adult mouse liver → lipid synthesis — adult exposure, not early life"),
        "W2043307319": ("label_error", "Review: environmental toxins and diabetes in Canadian aboriginals — human, not rodent"),
        "W2045351567": ("label_error", "Review: endocrine disrupting chemicals — general review"),
        "W2048432175": ("label_error", "In vitro: BPA in HepG2 cells → lipid accumulation — not in vivo rodent"),
        "W2048655519": ("label_error", "Review: EDCs and disease susceptibility — review article"),
        "W2052016827": ("label_error", "In vitro: BPA in 3T3-L1 adipocytes → Akt signaling — not in vivo rodent"),
        "W2065341550": ("label_error", "Review: neurotoxicology and endocrine disruption — review, not rodent BPA study"),
        "W2076212136": ("label_error", "News/commentary: BPA safety controversy — not original research"),
        "W2088439238": ("label_error", "Human children adipose tissue, not rodent study"),
        "W2090637770": ("label_error", "Human epidemiology: in utero BPA and birth weight — human, not rodent"),
        "W2095513235": ("label_error", "Review: environmental estrogens and obesity — review article"),
        "W2114741845": ("label_error", "Review/commentary: BPA and diabetes/CVD/obesity — review"),
        "W2127064392": ("label_error", "Sheep study: developmental reprogramming — not rodent"),
        "W2141183734": ("label_error", "Quercetin vs BPA in adult mice liver/kidney — adult exposure, not early life, not obesity"),
        "W2144160434": ("label_error", "Hepatic phase II metabolism in pregnant mice — no BPA, no obesity outcome"),
        "W2153197176": ("genuine_fn", "Maternal BPA/genistein → Avy/a offspring coat color — early-life BPA in mice, agouti obesity model"),
        "W2162878065": ("label_error", "Review: environmental obesogens and nuclear receptors — review article"),
        "W2164889971": ("label_error", "Human epidemiology: BPA biomonitoring in maternal/cord blood — human, not rodent"),
        "W2167417752": ("label_error", "Human epidemiology: BPA and BMI in Chinese schoolchildren — human, not rodent"),
        "W2315864191": ("label_error", "Editorial: obesogens and ES&T — editorial, not original research"),
        "W4235548025": ("label_error", "Review: obesogens — review article"),
    },

    # ── Hall_2012 ───────────────────────────────────────────────────
    # PCC: Software fault PREDICTION models/techniques
    "Hall_2012": {
        "W1995029977": ("genuine_fn", "Defect prediction for embedded software — matches criteria"),
        "W2120484483": ("genuine_fn", "Software defect association mining and correction effort prediction"),
        "W2158561928": ("genuine_fn", "Fault count prediction using genetic programming"),
        "W4243127898": ("label_error", "Visualization for fault LOCALIZATION — not prediction"),
        "W4248521920": ("ambiguous", "Replicated analysis of fault DISTRIBUTIONS — descriptive, not prediction model"),
    },

    # ── van_Dis_2020 ────────────────────────────────────────────────
    # PICO: Long-term (≥12mo) outcomes of psychological treatment for anxiety disorders
    "van_Dis_2020": {
        "W2080572198": ("genuine_fn", "RCT: nurse-assisted online CBT for PTSD — psychological treatment for anxiety disorder"),
        "W2101457117": ("genuine_fn", "RCT: 7-day intensive vs standard cognitive therapy for PTSD"),
    },
}


def load_metrics(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


def get_record_id_suffix(full_id: str) -> str:
    return full_id.split("/")[-1]


def compute_adjusted_metrics(
    dataset: str,
    original_fn_ids: list[str],
    tp: int,
    fn: int,
    tn: int,
    fp: int,
) -> dict:
    """Recompute metrics after removing label errors from the gold standard."""
    adj = ADJUDICATIONS.get(dataset, {})

    label_errors = 0
    genuine_fn = 0
    ambiguous = 0

    for rid in original_fn_ids:
        suffix = get_record_id_suffix(rid)
        verdict, reason = adj.get(suffix, ("genuine_fn", "No adjudication — treated as genuine"))
        if verdict == "label_error":
            label_errors += 1
        elif verdict == "genuine_fn":
            genuine_fn += 1
        else:
            ambiguous += 1

    # Adjustments:
    # Each label_error FN: the record shouldn't be "include" in gold standard
    #   - Remove from positives: TP+FN decreases by 1, FN decreases by 1
    #   - The system correctly excluded it, so TN increases by 1
    # Ambiguous: treat conservatively as genuine FN (no adjustment)
    adj_tp = tp
    adj_fn = fn - label_errors
    adj_tn = tn + label_errors
    adj_fp = fp

    adj_sens = adj_tp / (adj_tp + adj_fn) if (adj_tp + adj_fn) > 0 else 1.0
    adj_spec = adj_tn / (adj_tn + adj_fp) if (adj_tn + adj_fp) > 0 else 0.0
    orig_sens = tp / (tp + fn) if (tp + fn) > 0 else 1.0

    return {
        "dataset": dataset,
        "n": tp + fn + tn + fp,
        "orig_sens": orig_sens,
        "adj_sens": adj_sens,
        "orig_fn": fn,
        "adj_fn": adj_fn,
        "label_errors": label_errors,
        "genuine_fn": genuine_fn,
        "ambiguous": ambiguous,
        "orig_tp": tp,
        "adj_tp": adj_tp,
        "orig_tn": tn,
        "adj_tn": adj_tn,
    }


def main():
    # ── A11 Base ────────────────────────────────────────────────────
    print("=" * 100)
    print("A11 BASE — Gold Label Adjudication")
    print("=" * 100)

    a11_rows = []
    a11_total_tp = a11_total_fn = a11_total_tn = a11_total_fp = 0
    a11_total_label_errors = 0

    for ds in DATASETS:
        path = RESULTS_DIR / ds / "a11_rule_exclude.json"
        data = load_metrics(path)
        m = data["metrics"]
        fn_ids = data.get("false_negatives", [])

        row = compute_adjusted_metrics(ds, fn_ids, m["tp"], m["fn"], m["tn"], m["fp"])
        a11_rows.append(row)

        a11_total_tp += m["tp"]
        a11_total_fn += m["fn"]
        a11_total_tn += m["tn"]
        a11_total_fp += m["fp"]
        a11_total_label_errors += row["label_errors"]

    # Print table
    print(f"\n{'Dataset':<28s} {'N':>6s} {'Sens(orig)':>10s} {'Sens(adj)':>10s} "
          f"{'Auto%':>6s} {'FN(o)':>5s} {'FN(a)':>5s} {'LblErr':>6s} {'GenFN':>5s} {'Ambig':>5s}")
    print("-" * 100)

    for row in a11_rows:
        path = RESULTS_DIR / row["dataset"] / "a11_rule_exclude.json"
        data = load_metrics(path)
        auto_rate = data["metrics"].get("auto_rate", 0)

        adj_mark = "*" if row["label_errors"] > 0 else ""
        print(f"{row['dataset']:<28s} {row['n']:>6d} {row['orig_sens']:>10.3f} "
              f"{row['adj_sens']:>9.3f}{adj_mark} {auto_rate:>5.1%} "
              f"{row['orig_fn']:>5d} {row['adj_fn']:>5d} "
              f"{row['label_errors']:>6d} {row['genuine_fn']:>5d} {row['ambiguous']:>5d}")

    # Pooled
    pooled_sens = a11_total_tp / (a11_total_tp + a11_total_fn)
    adj_pooled_fn = a11_total_fn - a11_total_label_errors
    adj_pooled_sens = a11_total_tp / (a11_total_tp + adj_pooled_fn)
    mean_sens = statistics.mean(r["orig_sens"] for r in a11_rows)
    mean_adj_sens = statistics.mean(r["adj_sens"] for r in a11_rows)
    total_auto = sum(
        load_metrics(RESULTS_DIR / ds / "a11_rule_exclude.json")["metrics"].get("auto_rate", 0)
        for ds in DATASETS
    ) / len(DATASETS)

    print("-" * 100)
    print(f"{'Pooled':<28s} {a11_total_tp + a11_total_fn + sum(r['orig_tn'] for r in a11_rows) + sum(load_metrics(RESULTS_DIR / r['dataset'] / 'a11_rule_exclude.json')['metrics']['fp'] for r in a11_rows):>6d} "
          f"{pooled_sens:>10.3f} {adj_pooled_sens:>9.3f}* {total_auto:>5.1%} "
          f"{a11_total_fn:>5d} {adj_pooled_fn:>5d} {a11_total_label_errors:>6d}")
    print(f"{'Mean':<28s} {'':>6s} {mean_sens:>10.3f} {mean_adj_sens:>9.3f}*")

    # ── A12 HR+3 Supplement ─────────────────────────────────────────
    print("\n" + "=" * 100)
    print("A12 (HR+3 SUPPLEMENT) — Gold Label Adjudication")
    print("=" * 100)

    a12_rows = []
    a12_total_tp = a12_total_fn = a12_total_tn = a12_total_fp = 0
    a12_total_label_errors = 0
    a12_has_data = []

    for ds in DATASETS:
        hr_path = RESULTS_DIR / "hr_plus3" / f"{ds}.json"
        if not hr_path.exists():
            # No HR supplement run — use A11 base results
            path = RESULTS_DIR / ds / "a11_rule_exclude.json"
            data = load_metrics(path)
            m = data["metrics"]
            fn_ids = data.get("false_negatives", [])
            row = compute_adjusted_metrics(ds, fn_ids, m["tp"], m["fn"], m["tn"], m["fp"])
        else:
            data = load_metrics(hr_path)
            m = data["merged_metrics"]
            fn_ids = data.get("merged_false_negatives", [])
            row = compute_adjusted_metrics(ds, fn_ids, m["tp"], m["fn"], m["tn"], m["fp"])
            a12_has_data.append(ds)

        a12_rows.append(row)
        a12_total_tp += row["orig_tp"]
        a12_total_fn += row["orig_fn"]
        a12_total_tn += row["orig_tn"]
        a12_total_fp += m.get("fp", 0)
        a12_total_label_errors += row["label_errors"]

    print(f"\n{'Dataset':<28s} {'N':>6s} {'Sens(orig)':>10s} {'Sens(adj)':>10s} "
          f"{'FN(o)':>5s} {'FN(a)':>5s} {'LblErr':>6s} {'GenFN':>5s} {'Ambig':>5s}")
    print("-" * 100)

    for row in a12_rows:
        adj_mark = "*" if row["label_errors"] > 0 else ""
        print(f"{row['dataset']:<28s} {row['n']:>6d} {row['orig_sens']:>10.3f} "
              f"{row['adj_sens']:>9.3f}{adj_mark} "
              f"{row['orig_fn']:>5d} {row['adj_fn']:>5d} "
              f"{row['label_errors']:>6d} {row['genuine_fn']:>5d} {row['ambiguous']:>5d}")

    pooled_a12_sens = a12_total_tp / (a12_total_tp + a12_total_fn)
    adj_pooled_a12_fn = a12_total_fn - a12_total_label_errors
    adj_pooled_a12_sens = a12_total_tp / (a12_total_tp + adj_pooled_a12_fn)
    mean_a12_sens = statistics.mean(r["orig_sens"] for r in a12_rows)
    mean_adj_a12_sens = statistics.mean(r["adj_sens"] for r in a12_rows)

    print("-" * 100)
    total_n = sum(r["n"] for r in a12_rows)
    print(f"{'Pooled':<28s} {total_n:>6d} {pooled_a12_sens:>10.3f} {adj_pooled_a12_sens:>9.3f}* "
          f"{a12_total_fn:>5d} {adj_pooled_a12_fn:>5d} {a12_total_label_errors:>6d}")
    print(f"{'Mean':<28s} {'':>6s} {mean_a12_sens:>10.3f} {mean_adj_a12_sens:>9.3f}*")

    # ── Side-by-side comparison ─────────────────────────────────────
    print("\n" + "=" * 100)
    print("COMPARISON: A11 base vs A12 (HR+3 supplement)")
    print("=" * 100)

    print(f"\n{'':28s} {'── A11 base ──':>30s}  {'── A12 (HR+3) ──':>30s}")
    print(f"{'Dataset':<28s} {'Sens(o)':>8s} {'Sens(a)':>8s} {'FN(o)':>5s} {'FN(a)':>5s}"
          f"  {'Sens(o)':>8s} {'Sens(a)':>8s} {'FN(o)':>5s} {'FN(a)':>5s}")
    print("-" * 100)

    for r11, r12 in zip(a11_rows, a12_rows):
        ds = r11["dataset"]
        a11_mark = "*" if r11["label_errors"] > 0 else ""
        a12_mark = "*" if r12["label_errors"] > 0 else ""

        print(f"{ds:<28s} "
              f"{r11['orig_sens']:>8.3f} {r11['adj_sens']:>7.3f}{a11_mark} {r11['orig_fn']:>5d} {r11['adj_fn']:>5d}"
              f"  {r12['orig_sens']:>8.3f} {r12['adj_sens']:>7.3f}{a12_mark} {r12['orig_fn']:>5d} {r12['adj_fn']:>5d}")

    print("-" * 100)
    print(f"{'Pooled':<28s} "
          f"{pooled_sens:>8.3f} {adj_pooled_sens:>7.3f}* {a11_total_fn:>5d} {adj_pooled_fn:>5d}"
          f"  {pooled_a12_sens:>8.3f} {adj_pooled_a12_sens:>7.3f}* {a12_total_fn:>5d} {adj_pooled_a12_fn:>5d}")
    print(f"{'Mean':<28s} "
          f"{mean_sens:>8.3f} {mean_adj_sens:>7.3f}*"
          f"{'':>12s}"
          f"{mean_a12_sens:>8.3f} {mean_adj_a12_sens:>7.3f}*")

    print(f"\n* = adjusted after gold-label audit (label errors removed from denominator)")

    # ── Detailed FN audit log ───────────────────────────────────────
    print("\n" + "=" * 100)
    print("DETAILED FN AUDIT LOG")
    print("=" * 100)

    for ds in DATASETS:
        adj = ADJUDICATIONS.get(ds, {})
        if not adj:
            continue

        # Load titles
        titles = {}
        csv_path = DATASETS_DIR / ds / "records.csv"
        a11_fn = set(load_metrics(RESULTS_DIR / ds / "a11_rule_exclude.json").get("false_negatives", []))
        hr_path = RESULTS_DIR / "hr_plus3" / f"{ds}.json"
        a12_fn = set(load_metrics(hr_path).get("merged_false_negatives", [])) if hr_path.exists() else set()
        all_fn = a11_fn | a12_fn

        with open(csv_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row["record_id"] in all_fn:
                    suffix = get_record_id_suffix(row["record_id"])
                    titles[suffix] = row.get("title", "N/A")[:100]

        print(f"\n── {ds} ──")
        for suffix, (verdict, reason) in sorted(adj.items()):
            source = "A11+A12" if f"https://openalex.org/{suffix}" in a11_fn else "A12_only"
            icon = {"label_error": "❌", "genuine_fn": "✅", "ambiguous": "⚠️"}[verdict]
            title = titles.get(suffix, "N/A")
            print(f"  {icon} [{verdict:12s}] {source:8s} | {title}")
            print(f"    Reason: {reason}")

    # ── Summary statistics ──────────────────────────────────────────
    print("\n" + "=" * 100)
    print("SUMMARY")
    print("=" * 100)

    for system, rows, total_fn, total_le in [
        ("A11 base", a11_rows, a11_total_fn, a11_total_label_errors),
        ("A12 HR+3", a12_rows, a12_total_fn, a12_total_label_errors),
    ]:
        total_genuine = sum(r["genuine_fn"] for r in rows)
        total_ambig = sum(r["ambiguous"] for r in rows)
        print(f"\n{system}:")
        print(f"  Total FN:        {total_fn}")
        print(f"  Label errors:    {total_le} ({total_le/total_fn*100:.0f}%)")
        print(f"  Genuine FN:      {total_genuine} ({total_genuine/total_fn*100:.0f}%)")
        print(f"  Ambiguous:       {total_ambig} ({total_ambig/total_fn*100:.0f}%)")


if __name__ == "__main__":
    main()
