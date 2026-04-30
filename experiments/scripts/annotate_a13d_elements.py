"""Annotate element-level truth labels for A13d training data.

Reads titles/abstracts and criteria, applies careful heuristic rules
to determine match/mismatch/unclear for each element.

Handles both:
1. FN audit records (infer from audit verdict + title analysis)
2. New HR/TN samples (full title+abstract analysis against criteria)
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ADJ_DIR = PROJECT_ROOT / "experiments" / "adjudication"
CRITERIA_DIR = PROJECT_ROOT / "experiments" / "criteria"


def load_criteria(dataset: str) -> dict:
    path = CRITERIA_DIR / f"{dataset}_criteria_v2.json"
    if not path.exists():
        path = CRITERIA_DIR / f"{dataset}_criteria.json"
    with open(path) as f:
        return json.load(f)


def text_contains_any(text: str, keywords: list[str], threshold: int = 1) -> bool:
    """Check if text contains any of the keywords (case-insensitive)."""
    text_lower = text.lower()
    matches = 0
    for kw in keywords:
        if kw.lower() in text_lower:
            matches += 1
            if matches >= threshold:
                return True
    return False


# ── Dataset-specific annotation logic ────────────────────────────────

DATASET_RULES: dict[str, dict] = {
    "Jeyaraman_2020": {
        # PICO: MSCs for knee OA/cartilage defects
        "population": {
            "match_kw": ["knee", "osteoarthritis", "cartilage", "chondral", "osteochondral", "articular"],
            "mismatch_kw": [],
        },
        "intervention": {
            "match_kw": ["mesenchymal", "stem cell", "msc", "stromal cell", "bone marrow concentrate"],
            "mismatch_kw": ["autograft transfer", "microfracture only", "osteotomy"],
        },
        "study_design": {
            "match_kw": ["randomized", "rct", "clinical trial", "controlled trial", "cohort", "case-control",
                         "systematic review", "meta-analysis", "prospective", "retrospective"],
            "mismatch_kw": ["case report", "editorial", "letter to", "commentary", "opinion"],
        },
    },
    "Chou_2003": {
        # PICO: Long-acting oral opioids for chronic non-cancer pain
        "population": {
            "match_kw": ["chronic pain", "non-cancer pain", "noncancer pain", "chronic non-malignant",
                         "low back pain", "neuropathic pain", "fibromyalgia", "osteoarthritis pain"],
            "mismatch_kw": ["cancer pain", "acute pain", "postoperative pain", "palliative"],
        },
        "intervention": {
            "match_kw": ["opioid", "morphine", "oxycodone", "fentanyl", "methadone", "hydromorphone",
                         "tramadol", "codeine", "buprenorphine", "sustained release", "extended release",
                         "long-acting", "analgesic"],
            "mismatch_kw": [],
        },
        "study_design": {
            "match_kw": ["randomized", "rct", "controlled trial", "clinical trial", "systematic review",
                         "meta-analysis", "cohort", "prospective", "double-blind"],
            "mismatch_kw": ["case report", "editorial", "letter", "commentary"],
        },
    },
    "van_der_Waal_2022": {
        # SPIDER: Elderly cancer patients, treatment decision-making
        "sample": {
            "match_kw": ["elderly", "older", "aged", "geriatric", "65", "cancer", "malignancy",
                         "oncology", "neoplasm", "tumor", "tumour"],
            "mismatch_kw": ["child", "pediatric", "adolescent", "young adult"],
        },
        "phenomenon_of_interest": {
            "match_kw": ["decision", "decision-making", "treatment choice", "shared decision",
                         "preference", "autonomy", "informed consent"],
            "mismatch_kw": [],
        },
        "study_design": {
            "match_kw": ["qualitative", "interview", "survey", "questionnaire", "cross-sectional",
                         "observational", "systematic review", "cohort"],
            "mismatch_kw": ["case report", "editorial"],
        },
    },
    "Smid_2020": {
        # PICO: Bayesian SEM with small samples
        "population": {
            "match_kw": ["structural equation", "sem", "latent variable", "path analysis",
                         "confirmatory factor", "cfa", "small sample"],
            "mismatch_kw": [],
        },
        "intervention": {
            "match_kw": ["bayesian", "bayes", "mcmc", "markov chain", "prior distribution",
                         "posterior", "gibbs", "bayesian estimation"],
            "mismatch_kw": [],
        },
        "study_design": {
            "match_kw": ["simulation", "monte carlo", "methodological", "comparison", "empirical",
                         "applied", "review"],
            "mismatch_kw": [],
        },
    },
    "Muthu_2021": {
        # PICO: Fragility index in spine surgery RCTs
        "population": {
            "match_kw": ["spine", "spinal", "lumbar", "cervical", "thoracic", "vertebr",
                         "disc", "scoliosis", "kyphosis", "stenosis", "fusion",
                         "decompression", "laminectomy", "discectomy"],
            "mismatch_kw": [],
        },
        "intervention": {
            "match_kw": ["fragility", "fragility index", "randomized", "rct", "statistical significance",
                         "p-value", "clinical trial"],
            "mismatch_kw": [],
        },
        "study_design": {
            "match_kw": ["randomized", "rct", "controlled trial", "clinical trial"],
            "mismatch_kw": ["meta-analysis", "systematic review", "review of", "case report",
                            "case series", "editorial", "letter"],
        },
    },
    "Appenzeller-Herzog_2019": {
        # PICO: Wilson disease treatments
        "population": {
            "match_kw": ["wilson disease", "wilson's disease", "hepatolenticular", "copper metabolism",
                         "ceruloplasmin"],
            "mismatch_kw": [],
        },
        "intervention": {
            "match_kw": ["chelat", "penicillamine", "trientine", "zinc", "tetrathiomolybdate",
                         "liver transplant", "treatment", "therapy"],
            "mismatch_kw": [],
        },
        "study_design": {
            "match_kw": ["cohort", "case series", "retrospective", "prospective", "clinical",
                         "observational", "trial", "review"],
            "mismatch_kw": ["case report", "editorial", "letter"],
        },
    },
    "van_de_Schoot_2018": {
        # PIF: PTSD trajectory modelling
        "population": {
            "match_kw": ["ptsd", "post-traumatic", "posttraumatic", "trauma", "stress disorder"],
            "mismatch_kw": [],
        },
        "index_factor": {
            "match_kw": ["trajectory", "growth mixture", "latent class", "latent growth",
                         "gmm", "lgmm", "lcga", "growth curve", "longitudinal",
                         "bayesian", "bayes"],
            "mismatch_kw": [],
        },
        "study_design": {
            "match_kw": ["longitudinal", "prospective", "cohort", "panel", "repeated measure",
                         "follow-up", "wave"],
            "mismatch_kw": ["cross-sectional", "case report", "editorial"],
        },
    },
    "Moran_2021": {
        # PECO: Poor nutrition → high-risk behaviours in HUMANS
        "population": {
            "match_kw": ["human", "patient", "participant", "adult", "child", "adolescent",
                         "men", "women", "people", "individual", "subject", "population",
                         "community", "school", "college", "veteran"],
            "mismatch_kw": ["mouse", "mice", "rat", "rodent", "animal", "canine", "dog",
                            "bird", "avian", "fish", "insect", "bee", "worm", "earthworm",
                            "cow", "bovine", "pig", "porcine", "vole", "sheep", "primate",
                            "drosophila", "zebrafish", "mullet"],
        },
        "exposure": {
            "match_kw": ["nutrition", "diet", "food", "eating", "malnutrition", "undernutrition",
                         "obesity", "overweight", "bmi", "body mass", "caloric", "nutrient",
                         "vitamin", "mineral", "feeding", "hunger", "starvation", "fasting",
                         "anorexia", "bulimia", "binge eating"],
            "mismatch_kw": ["adhd", "autism", "genetic", "endocrine disrupt"],
        },
        "study_design": {
            "match_kw": ["observational", "cohort", "cross-sectional", "case-control", "survey",
                         "longitudinal", "prospective", "retrospective", "systematic review",
                         "meta-analysis", "randomized", "trial", "intervention"],
            "mismatch_kw": ["case report", "editorial", "letter", "opinion", "commentary"],
        },
    },
    "Radjenovic_2013": {
        # PCC: Software fault prediction
        "population": {
            "match_kw": ["software", "code", "program", "system", "module", "component",
                         "project", "repository", "open source"],
            "mismatch_kw": [],
        },
        "concept": {
            "match_kw": ["fault prediction", "defect prediction", "bug prediction", "error prediction",
                         "reliability", "quality prediction", "fault-prone", "defect-prone",
                         "prediction model", "classifier", "machine learning", "metric",
                         "complexity metric", "object-oriented metric"],
            "mismatch_kw": ["fault localization", "debugging", "testing only", "formal verification"],
        },
        "study_design": {
            "match_kw": ["empirical", "experiment", "case study", "replication", "comparison",
                         "evaluation", "validation", "benchmark"],
            "mismatch_kw": ["tutorial", "editorial"],
        },
    },
    "Leenaars_2020": {
        # PICO: Methotrexate efficacy in RA
        "population": {
            "match_kw": ["rheumatoid arthritis", "ra ", "arthritis"],
            "mismatch_kw": [],
        },
        "intervention": {
            "match_kw": ["methotrexate", "mtx"],
            "mismatch_kw": [],
        },
        "study_design": {
            "match_kw": ["randomized", "clinical trial", "controlled trial", "animal",
                         "in vivo", "systematic review", "meta-analysis"],
            "mismatch_kw": ["case report", "editorial"],
        },
    },
    "Wassenaar_2017": {
        # PECO: BPA in rodents during EARLY LIFE → obesity outcomes
        "population": {
            "match_kw": ["mouse", "mice", "rat", "rodent", "murine", "animal model"],
            "mismatch_kw": ["human", "patient", "children", "adolescent", "adult", "epidemiolog",
                            "fish", "mullet", "sheep", "vole", "in vitro", "cell line",
                            "3t3", "hepg2", "stem cell", "adipocyte"],
        },
        "exposure": {
            "match_kw": ["bisphenol a", "bpa", "bisphenol-a"],
            "mismatch_kw": [],
        },
        "study_design": {
            "match_kw": ["in vivo", "animal experiment", "exposure study", "developmental",
                         "prenatal", "perinatal", "postnatal", "gestational", "in utero",
                         "lactation", "neonatal", "juvenile"],
            "mismatch_kw": ["review", "in vitro", "editorial", "commentary", "letter",
                            "opinion", "workshop", "news"],
        },
    },
    "Hall_2012": {
        # PCC: Software fault prediction
        "population": {
            "match_kw": ["software", "code", "program", "system", "module", "project"],
            "mismatch_kw": [],
        },
        "concept": {
            "match_kw": ["fault prediction", "defect prediction", "bug prediction",
                         "prediction model", "fault-prone", "defect-prone", "predictor",
                         "classification", "regression model", "machine learning",
                         "neural network", "decision tree", "logistic regression",
                         "metric", "complexity"],
            "mismatch_kw": ["fault localization", "visualization", "debugging"],
        },
        "study_design": {
            "match_kw": ["empirical", "experiment", "case study", "replication", "comparison",
                         "evaluation", "validation"],
            "mismatch_kw": ["tutorial", "editorial"],
        },
    },
    "van_Dis_2020": {
        # PICO: Long-term (≥12mo) outcomes of psych treatment for anxiety disorders
        "population": {
            "match_kw": ["anxiety", "ptsd", "post-traumatic", "posttraumatic", "ocd",
                         "obsessive", "panic", "phobia", "gad", "social anxiety",
                         "generalized anxiety"],
            "mismatch_kw": [],
        },
        "intervention": {
            "match_kw": ["cbt", "cognitive", "behavioral", "behaviour", "psychotherapy",
                         "therapy", "treatment", "intervention", "exposure therapy",
                         "emdr", "mindfulness", "pharmacotherapy", "ssri", "antidepressant"],
            "mismatch_kw": [],
        },
        "study_design": {
            "match_kw": ["randomized", "rct", "controlled trial", "clinical trial",
                         "long-term", "follow-up", "longitudinal"],
            "mismatch_kw": ["case report", "editorial", "letter"],
        },
    },
}


def annotate_element(
    dataset: str,
    element_key: str,
    title: str,
    abstract: str,
    criteria: dict,
) -> str:
    """Determine element-level truth label based on title+abstract vs criteria."""
    text = f"{title} {abstract}".lower()
    rules = DATASET_RULES.get(dataset, {}).get(element_key)

    if not rules:
        return "unclear"

    match_kw = rules.get("match_kw", [])
    mismatch_kw = rules.get("mismatch_kw", [])

    has_match_signal = text_contains_any(text, match_kw)
    has_mismatch_signal = text_contains_any(text, mismatch_kw)

    # Special handling for specific datasets/elements
    if dataset == "Wassenaar_2017":
        if element_key == "study_design":
            # Check if it's a review/in-vitro (mismatch) vs original rodent study (match)
            is_review = text_contains_any(text, ["review", "systematic review", "meta-analysis",
                                                  "editorial", "commentary", "letter", "opinion",
                                                  "workshop", "news"])
            is_invitro = text_contains_any(text, ["in vitro", "cell line", "3t3", "hepg2",
                                                   "cell culture", "adipocyte culture"])
            has_early_life = text_contains_any(text, ["prenatal", "perinatal", "postnatal",
                                                       "gestational", "in utero", "lactation",
                                                       "neonatal", "juvenile", "developmental",
                                                       "early life", "offspring"])
            if is_review or is_invitro:
                return "mismatch"
            if has_early_life:
                return "match"
            # Adult exposure studies
            if text_contains_any(text, ["adult", "ovariectomized", "ovx"]):
                return "mismatch"
            return "unclear"

        if element_key == "population":
            is_rodent = text_contains_any(text, ["mouse", "mice", "rat", "rodent", "murine"])
            is_human = text_contains_any(text, ["human", "patient", "children", "adolescent",
                                                 "epidemiolog", "population-based", "cross-sectional",
                                                 "birth cohort", "school children"])
            is_other = text_contains_any(text, ["fish", "mullet", "sheep", "vole", "cell line",
                                                 "3t3", "hepg2", "stem cell", "in vitro"])
            is_review = text_contains_any(text, ["review", "editorial", "commentary"])
            if is_rodent and not is_human and not is_other:
                return "match"
            if is_human or is_other or is_review:
                return "mismatch"
            return "unclear"

    if dataset == "Moran_2021":
        if element_key == "population":
            animal_kw = ["mouse", "mice", "rat", "rodent", "canine", "dog", "bird", "avian",
                         "fish", "insect", "bee", "worm", "earthworm", "cow", "bovine",
                         "pig", "porcine", "vole", "sheep", "drosophila", "primate",
                         "honey bee", "apis", "lumbricus", "predator", "prey", "foraging",
                         "torpor", "fattening pigs"]
            if text_contains_any(text, animal_kw):
                return "mismatch"
            return "match"

    if dataset == "Muthu_2021":
        if element_key == "study_design":
            if text_contains_any(text, ["meta-analysis", "systematic review", "review of"]):
                if text_contains_any(text, ["meta-analysis of randomized", "meta-analysis of rct"]):
                    return "mismatch"  # meta-analysis, not an RCT itself
                return "mismatch"
            if text_contains_any(text, ["randomized", "rct", "clinical trial", "controlled trial"]):
                return "match"
            return "unclear"

    # ── Generic study_design fallback ──
    if element_key == "study_design":
        mismatch_sd = ["review", "editorial", "letter to the editor", "commentary",
                        "opinion", "book chapter", "erratum", "corrigendum",
                        "news", "workshop report", "conference abstract"]
        match_sd = ["study", "trial", "cohort", "survey", "experiment", "analysis",
                     "investigation", "evaluation", "assessment", "comparison",
                     "randomized", "prospective", "retrospective", "longitudinal",
                     "cross-sectional", "case-control", "observational", "simulation",
                     "empirical", "pilot", "feasibility", "open-label", "double-blind"]
        if text_contains_any(text, mismatch_sd):
            return "mismatch"
        if text_contains_any(text, match_sd):
            return "match"
        # Most research papers indexed in databases are studies, default to match
        # unless there's clear mismatch signal
        if len(text) > 100:
            return "match"
        return "unclear"

    # General logic
    if has_mismatch_signal and not has_match_signal:
        return "mismatch"
    if has_match_signal and not has_mismatch_signal:
        return "match"
    if has_match_signal and has_mismatch_signal:
        match_count = sum(1 for kw in match_kw if kw.lower() in text)
        mismatch_count = sum(1 for kw in mismatch_kw if kw.lower() in text)
        if mismatch_count > match_count:
            return "mismatch"
        if match_count > mismatch_count:
            return "match"
        return "unclear"

    # For population/intervention/exposure: if no keywords match but
    # abstract is substantial, the record likely doesn't match this element
    if element_key in ("population", "intervention", "exposure", "concept",
                       "index_factor", "phenomenon_of_interest", "sample"):
        if len(text) > 200 and not has_match_signal:
            return "mismatch"

    return "unclear"


def annotate_fn_element(
    dataset: str,
    element_key: str,
    title: str,
    abstract: str,
    fn_verdict: str,
    fn_reason: str,
    criteria: dict,
) -> str:
    """Annotate FN audit record at element level.

    For label_error records, we know the record doesn't match criteria.
    The reason tells us WHY - which helps identify which element mismatches.
    For genuine_fn records, the record matches criteria → elements should match.
    """
    text = f"{title} {abstract}".lower()
    reason_lower = fn_reason.lower()

    if fn_verdict == "genuine_fn":
        # Record truly matches criteria → all elements should match
        # But do a sanity check
        result = annotate_element(dataset, element_key, title, abstract, criteria)
        if result == "mismatch":
            return "unclear"  # Conflict between verdict and heuristic - be conservative
        return "match"

    if fn_verdict == "ambiguous":
        return annotate_element(dataset, element_key, title, abstract, criteria)

    # fn_verdict == "label_error"
    # Need to identify WHICH element(s) mismatch based on the reason

    if dataset == "Muthu_2021":
        if "meta-analysis" in reason_lower:
            if element_key == "study_design":
                return "mismatch"
            return "match"  # Population etc still matches

    if dataset == "Moran_2021":
        if "not human" in reason_lower or "bird" in reason_lower or "dog" in reason_lower or \
           "earthworm" in reason_lower or "cow" in reason_lower or "pig" in reason_lower or \
           "animal" in reason_lower or "honey bee" in reason_lower:
            if element_key == "population":
                return "mismatch"
            # Other elements may or may not match
            return annotate_element(dataset, element_key, title, abstract, criteria)

        if "not nutrition" in reason_lower or "not poor-nutrition" in reason_lower or \
           "behaviour not nutrition" in reason_lower:
            if element_key == "exposure":
                return "mismatch"
            return annotate_element(dataset, element_key, title, abstract, criteria)

        if "not risk behaviour" in reason_lower or "not behaviour" in reason_lower or \
           "not study design" in reason_lower or "case report" in reason_lower:
            if element_key == "study_design":
                return "mismatch"
            return annotate_element(dataset, element_key, title, abstract, criteria)

    if dataset == "Wassenaar_2017":
        if "review" in reason_lower or "editorial" in reason_lower or \
           "commentary" in reason_lower or "workshop" in reason_lower or \
           "news" in reason_lower:
            if element_key == "study_design":
                return "mismatch"
            return annotate_element(dataset, element_key, title, abstract, criteria)

        if "human" in reason_lower or "not rodent" in reason_lower or \
           "children" in reason_lower or "epidemiol" in reason_lower:
            if element_key == "population":
                return "mismatch"
            return annotate_element(dataset, element_key, title, abstract, criteria)

        if "in vitro" in reason_lower or "cell" in reason_lower:
            if element_key == "population":
                return "mismatch"
            if element_key == "study_design":
                return "mismatch"
            return annotate_element(dataset, element_key, title, abstract, criteria)

        if "adult exposure" in reason_lower or "not early life" in reason_lower:
            if element_key == "study_design":
                return "mismatch"
            return annotate_element(dataset, element_key, title, abstract, criteria)

        if "sheep" in reason_lower or "fish" in reason_lower or "vole" in reason_lower:
            if element_key == "population":
                return "mismatch"
            return annotate_element(dataset, element_key, title, abstract, criteria)

        if "no bpa" in reason_lower:
            if element_key == "exposure":
                return "mismatch"
            return annotate_element(dataset, element_key, title, abstract, criteria)

        if "no obesity" in reason_lower:
            return annotate_element(dataset, element_key, title, abstract, criteria)

    if dataset == "Hall_2012":
        if "localization" in reason_lower:
            if element_key == "concept":
                return "mismatch"
            return "match"

    if dataset == "Jeyaraman_2020":
        if "not msc" in reason_lower or "autograft" in reason_lower:
            if element_key == "intervention":
                return "mismatch"
            return "match"

    if dataset == "van_de_Schoot_2018":
        # All FN here are genuine_fn (PTSD trajectory studies)
        return "match"

    # Fallback to heuristic
    return annotate_element(dataset, element_key, title, abstract, criteria)


def load_model_consensus(record_id: str, element_key: str) -> str | None:
    """Look up model consensus from model_outputs.csv for tiebreaking."""
    if not hasattr(load_model_consensus, "_cache"):
        load_model_consensus._cache = {}
        mo_path = ADJ_DIR / "a13d_model_outputs.csv"
        if mo_path.exists():
            for row in csv.DictReader(open(mo_path, encoding="utf-8")):
                key = (row["record_id"], row["element_key"])
                if key not in load_model_consensus._cache:
                    load_model_consensus._cache[key] = []
                load_model_consensus._cache[key].append(row["model_match"])

    votes = load_model_consensus._cache.get((record_id, element_key), [])
    if not votes:
        return None

    true_count = sum(1 for v in votes if v == "True")
    false_count = sum(1 for v in votes if v == "False")
    none_count = sum(1 for v in votes if v in ("None", ""))

    if false_count >= 2 and true_count == 0:
        return "mismatch"
    if true_count >= 2 and false_count == 0:
        return "match"
    if false_count >= 1 and true_count >= 1:
        return "match" if true_count > false_count else "mismatch"
    return None


def main() -> None:
    criteria_cache: dict[str, dict] = {}
    for ds in DATASET_RULES:
        criteria_cache[ds] = load_criteria(ds)

    # ── Annotate new samples ──────────────────────────────────
    template_path = ADJ_DIR / "a13d_labeling_template.csv"
    rows = list(csv.DictReader(open(template_path, encoding="utf-8")))

    annotated = []
    consensus_used = 0
    for r in rows:
        ds = r["dataset"]
        criteria = criteria_cache.get(ds, {})
        label = annotate_element(
            ds, r["element_key"], r["title"], r.get("abstract", ""), criteria
        )
        if label == "unclear":
            consensus = load_model_consensus(r["record_id"], r["element_key"])
            if consensus is not None:
                label = consensus
                consensus_used += 1
        r["truth_label"] = label
        annotated.append(r)

    out_path = ADJ_DIR / "a13d_labeling_template_filled.csv"
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(annotated[0].keys()))
        writer.writeheader()
        writer.writerows(annotated)

    # Stats
    labels = [r["truth_label"] for r in annotated]
    print(f"New samples: {len(annotated)} element labels")
    print(f"  match: {labels.count('match')}, mismatch: {labels.count('mismatch')}, unclear: {labels.count('unclear')}")
    print(f"  consensus tiebreaker used: {consensus_used}")
    print(f"  Wrote → {out_path}")

    # ── Annotate FN audit elements ──────────────────────────────
    fn_path = ADJ_DIR / "a13d_fn_audit_elements.csv"
    fn_rows = list(csv.DictReader(open(fn_path, encoding="utf-8")))

    fn_annotated = []
    fn_consensus_used = 0
    for r in fn_rows:
        ds = r["dataset"]
        criteria = criteria_cache.get(ds, {})
        label = annotate_fn_element(
            ds, r["element_key"], r["title"], r.get("abstract", ""),
            r["fn_verdict"], r["fn_reason"], criteria
        )
        if label == "unclear":
            consensus = load_model_consensus(r["record_id"], r["element_key"])
            if consensus is not None:
                label = consensus
                fn_consensus_used += 1
        r["truth_label"] = label
        fn_annotated.append(r)

    fn_out_path = ADJ_DIR / "a13d_fn_audit_elements_filled.csv"
    with open(fn_out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(fn_annotated[0].keys()))
        writer.writeheader()
        writer.writerows(fn_annotated)

    fn_labels = [r["truth_label"] for r in fn_annotated]
    print(f"\nFN audit: {len(fn_annotated)} element labels")
    print(f"  match: {fn_labels.count('match')}, mismatch: {fn_labels.count('mismatch')}, unclear: {fn_labels.count('unclear')}")
    print(f"  consensus tiebreaker used: {fn_consensus_used}")
    print(f"  Wrote → {fn_out_path}")

    # Per-dataset breakdown
    all_rows = annotated + fn_annotated
    all_labels = [r["truth_label"] for r in all_rows]
    print(f"\nTOTAL: {len(all_rows)} element labels")
    print(f"  match: {all_labels.count('match')} ({all_labels.count('match')/len(all_labels):.0%})")
    print(f"  mismatch: {all_labels.count('mismatch')} ({all_labels.count('mismatch')/len(all_labels):.0%})")
    print(f"  unclear: {all_labels.count('unclear')} ({all_labels.count('unclear')/len(all_labels):.0%})")

    mismatch_pct = all_labels.count('mismatch') / len(all_labels)
    if mismatch_pct < 0.20:
        print(f"\n⚠️ WARNING: mismatch ratio {mismatch_pct:.0%} < 20% — distribution too skewed")
    elif mismatch_pct > 0.80:
        print(f"\n⚠️ WARNING: mismatch ratio {mismatch_pct:.0%} > 80% — distribution too skewed")
    else:
        print(f"\n✅ Distribution looks reasonable")

    # Per-element breakdown
    print("\nPer-element breakdown:")
    from collections import Counter
    for ek in sorted(set(r["element_key"] for r in all_rows)):
        ek_rows = [r for r in all_rows if r["element_key"] == ek]
        c = Counter(r["truth_label"] for r in ek_rows)
        print(f"  {ek:<25s}: match={c.get('match',0):>3d} mismatch={c.get('mismatch',0):>3d} unclear={c.get('unclear',0):>3d}")


if __name__ == "__main__":
    main()
