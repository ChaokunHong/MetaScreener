"""Generate PICO criteria drafts for 15 SYNERGY datasets.

Uses ReviewCriteria format (elements dict, per MetaScreener models_base.py).
Saves to experiments/criteria/{dataset}_criteria.json.
Also generates criteria_summary.md.
"""
from __future__ import annotations

import json
from pathlib import Path

CRITERIA_DIR = Path(__file__).parent.parent / "criteria"
CRITERIA_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Criteria definitions — drafted from publication titles + domain knowledge
# Fields: framework, research_question, elements {name, include, exclude},
#         study_design_include, study_design_exclude,
#         NEEDS_REVIEW (bool), review_notes (per-field review flags)
# ---------------------------------------------------------------------------

CRITERIA: dict[str, dict] = {

    "Walker_2018": {
        "framework": "peco",
        "research_question": (
            "What is the human and animal evidence for potential "
            "transgenerational inheritance of health effects?"
        ),
        "elements": {
            "population": {
                "name": "Population",
                "include": [
                    "humans (any age, both sexes)",
                    "animal models (rodents, zebrafish, Drosophila, C. elegans)",
                    "F1/F2/F3 offspring generations",
                ],
                "exclude": [
                    "in vitro cell line studies without whole-organism data",
                ],
            },
            "exposure": {
                "name": "Exposure",
                "include": [
                    "environmental chemical exposures (pesticides, endocrine disruptors, heavy metals)",
                    "nutritional exposures (high-fat diet, caloric restriction, protein restriction)",
                    "physical/social stressors (stress, trauma, exercise)",
                    "paternal or maternal exposures before conception or during gestation",
                ],
                "exclude": [
                    "therapeutic drug exposures with no transgenerational follow-up",
                    "exposures without generational follow-up (F0 only)",
                ],
            },
            "comparison": {
                "name": "Comparison",
                "include": [
                    "unexposed control offspring",
                    "vehicle-treated controls",
                ],
                "exclude": [],
            },
            "outcome": {
                "name": "Outcome",
                "include": [
                    "health effects in unexposed F1/F2+ offspring",
                    "epigenetic changes (DNA methylation, histone modification, miRNA)",
                    "metabolic, reproductive, neurological, or immunological outcomes",
                ],
                "exclude": [
                    "outcomes measured only in directly exposed generation (F0)",
                ],
            },
        },
        "study_design_include": [
            "animal experimental studies",
            "human epidemiological studies (cohort, cross-sectional)",
            "evidence maps",
        ],
        "study_design_exclude": [
            "review articles",
            "editorials",
            "opinion pieces",
        ],
        "NEEDS_REVIEW": True,
        "review_notes": {
            "exposure": "Exposure taxonomy is broad — reviewer should confirm whether epigenetic mechanism studies without phenotypic outcome are included.",
            "outcome": "Definition of 'transgenerational' (F1 germ-line vs F2+ true transgenerational) may need clarification.",
        },
    },

    "Brouwer_2019": {
        "framework": "peco",
        "research_question": (
            "Do psychological risk factors predict depressive relapse or "
            "recurrence in individuals with a history of depression?"
        ),
        "elements": {
            "population": {
                "name": "Population",
                "include": [
                    "adults (≥18 years) with a history of major depressive disorder or depressive episode",
                    "currently in remission or partial remission at baseline",
                ],
                "exclude": [
                    "children and adolescents (<18 years)",
                    "bipolar disorder without unipolar depression data",
                    "primary diagnosis other than depression (e.g., anxiety-only, psychosis)",
                ],
            },
            "exposure": {
                "name": "Exposure (Psychological Risk Factor)",
                "include": [
                    "cognitive reactivity / negative automatic thoughts",
                    "rumination",
                    "mindfulness / self-compassion",
                    "emotion regulation strategies",
                    "psychological theories/models (Beck, Teasdale, Nolen-Hoeksema, etc.)",
                ],
                "exclude": [
                    "pharmacological or biological predictors only",
                    "sociodemographic predictors without psychological theory link",
                ],
            },
            "comparison": {
                "name": "Comparison",
                "include": [
                    "lower levels of the same psychological risk factor",
                    "absence of the risk factor",
                ],
                "exclude": [],
            },
            "outcome": {
                "name": "Outcome",
                "include": [
                    "depressive relapse (return of symptoms in same episode)",
                    "depressive recurrence (new depressive episode)",
                    "time to relapse/recurrence",
                ],
                "exclude": [
                    "first onset of depression (no prior history)",
                    "subclinical depressive symptoms without diagnostic threshold",
                ],
            },
        },
        "study_design_include": [
            "prospective longitudinal studies",
            "cohort studies",
            "randomized controlled trials with relapse/recurrence follow-up",
        ],
        "study_design_exclude": [
            "cross-sectional studies",
            "case reports",
            "retrospective studies",
            "qualitative studies",
        ],
        "NEEDS_REVIEW": True,
        "review_notes": {
            "exposure": "NEEDS_REVIEW: List of psychological theories may be incomplete — check whether all theories covered in the original SR are listed.",
            "population": "NEEDS_REVIEW: Confirm whether studies on dysthymia/persistent depressive disorder were included.",
        },
    },

    "van_Dis_2020": {
        "framework": "pico",
        "research_question": (
            "What are the long-term outcomes of CBT for anxiety-related disorders "
            "compared to other treatments or control conditions?"
        ),
        "elements": {
            "population": {
                "name": "Population",
                "include": [
                    "adults (≥18 years) with a primary anxiety-related disorder",
                    "specific phobia, social anxiety disorder, panic disorder, agoraphobia, GAD, OCD, PTSD",
                ],
                "exclude": [
                    "children and adolescents (<18 years)",
                    "comorbid anxiety as secondary diagnosis only",
                    "subclinical anxiety without formal diagnosis",
                ],
            },
            "intervention": {
                "name": "Intervention",
                "include": [
                    "cognitive behavioral therapy (CBT)",
                    "exposure-based CBT",
                    "CBT variants (ACT, MBCT, DBT with CBT component)",
                ],
                "exclude": [
                    "pharmacotherapy only",
                    "psychodynamic therapy without CBT component",
                ],
            },
            "comparison": {
                "name": "Comparison",
                "include": [
                    "waitlist control",
                    "active control (supportive therapy, pill placebo)",
                    "pharmacotherapy",
                    "other psychotherapy",
                ],
                "exclude": [],
            },
            "outcome": {
                "name": "Outcome",
                "include": [
                    "symptom severity at ≥12 months follow-up",
                    "remission/response rate at long-term follow-up",
                    "relapse rates",
                    "quality of life at follow-up",
                ],
                "exclude": [
                    "outcomes measured only at post-treatment (no follow-up data)",
                ],
            },
        },
        "study_design_include": [
            "randomized controlled trials (RCTs)",
            "controlled clinical trials",
        ],
        "study_design_exclude": [
            "case studies",
            "observational studies without control group",
            "qualitative studies",
        ],
        "NEEDS_REVIEW": False,
        "review_notes": {
            "outcome": "Long-term defined as ≥12 months — confirm actual threshold used in original review.",
        },
    },

    "Hall_2012": {
        "framework": "pico",
        "research_question": (
            "What is the performance of fault prediction models in software engineering, "
            "and which predictors and techniques perform best?"
        ),
        "elements": {
            "population": {
                "name": "Population (Software Context)",
                "include": [
                    "software systems, modules, files, or classes",
                    "open-source or industrial software projects",
                    "any programming language",
                ],
                "exclude": [
                    "hardware fault prediction",
                    "network/infrastructure fault prediction (non-software)",
                ],
            },
            "intervention": {
                "name": "Intervention (Prediction Technique)",
                "include": [
                    "machine learning-based fault prediction models (Naive Bayes, random forest, neural networks, etc.)",
                    "statistical models (logistic regression, discriminant analysis)",
                    "software metrics-based approaches (CK metrics, McCabe, Halstead)",
                    "process metrics, change metrics, social network metrics",
                ],
                "exclude": [
                    "manual code review or inspection without prediction model",
                    "testing techniques not involving predictive models",
                ],
            },
            "comparison": {
                "name": "Comparison",
                "include": [
                    "baseline model (e.g., random classifier)",
                    "alternative fault prediction model",
                    "no explicit comparator (single-model studies)",
                ],
                "exclude": [],
            },
            "outcome": {
                "name": "Outcome (Performance Metric)",
                "include": [
                    "prediction accuracy, precision, recall, F-measure",
                    "AUC-ROC",
                    "probability of detection (PD), probability of false alarm (PF)",
                ],
                "exclude": [
                    "subjective quality assessments without quantitative metrics",
                ],
            },
        },
        "study_design_include": [
            "empirical studies (experiments, case studies, controlled experiments)",
            "cross-project prediction studies",
            "within-project prediction studies",
        ],
        "study_design_exclude": [
            "theoretical papers without empirical validation",
            "secondary studies (existing systematic reviews, mapping studies)",
        ],
        "NEEDS_REVIEW": True,
        "review_notes": {
            "intervention": "NEEDS_REVIEW: May need to confirm whether process/change metrics were in scope vs static code metrics only.",
            "outcome": "NEEDS_REVIEW: Confirm exact set of performance metrics included (some early SLRs restricted to PD/PF).",
        },
    },

    "Wassenaar_2017": {
        "framework": "peco",
        "research_question": (
            "Does early-life exposure to Bisphenol A (BPA) lead to "
            "obesity-related outcomes in rodents?"
        ),
        "elements": {
            "population": {
                "name": "Population",
                "include": [
                    "rodents (mice and rats)",
                    "exposed during early life (prenatal, postnatal, perinatal, neonatal periods)",
                ],
                "exclude": [
                    "non-rodent animals (fish, birds, primates)",
                    "adult-only exposures without early-life component",
                    "in vitro studies",
                ],
            },
            "exposure": {
                "name": "Exposure",
                "include": [
                    "Bisphenol A (BPA) exposure",
                    "any route of administration (oral gavage, diet, injection, osmotic pump)",
                ],
                "exclude": [
                    "bisphenol analogues (BPS, BPF) without BPA comparison",
                    "combined chemical mixtures without isolatable BPA effect",
                ],
            },
            "comparison": {
                "name": "Comparison",
                "include": [
                    "vehicle control (oil, water, corn oil)",
                    "unexposed control group",
                ],
                "exclude": [],
            },
            "outcome": {
                "name": "Outcome",
                "include": [
                    "body weight, body mass index (BMI equivalent)",
                    "fat mass, adiposity",
                    "metabolic parameters (glucose, insulin, lipid profiles)",
                    "adipokines (leptin, adiponectin)",
                ],
                "exclude": [
                    "reproductive or endocrine outcomes unrelated to obesity",
                    "behavioral outcomes without metabolic component",
                ],
            },
        },
        "study_design_include": [
            "controlled animal experiments",
            "randomized animal studies",
        ],
        "study_design_exclude": [
            "human studies",
            "in vitro / cell culture studies",
            "review articles",
        ],
        "NEEDS_REVIEW": False,
        "review_notes": {},
    },

    "Leenaars_2020": {
        "framework": "pico",
        "research_question": (
            "How do animal and human methotrexate efficacy studies for "
            "rheumatoid arthritis compare in experimental design, and what "
            "does this reveal about translational value?"
        ),
        "elements": {
            "population": {
                "name": "Population",
                "include": [
                    "animal models of rheumatoid arthritis (collagen-induced arthritis, adjuvant-induced arthritis, etc.)",
                    "human patients with rheumatoid arthritis",
                ],
                "exclude": [
                    "other inflammatory conditions (psoriasis, IBD) without RA-specific data",
                ],
            },
            "intervention": {
                "name": "Intervention",
                "include": [
                    "methotrexate (MTX) at any dose, route, duration",
                ],
                "exclude": [
                    "combination biologic therapies (MTX + bDMARD) without MTX-alone arm",
                    "other DMARDs without methotrexate group",
                ],
            },
            "comparison": {
                "name": "Comparison",
                "include": [
                    "placebo",
                    "vehicle control",
                    "no treatment",
                    "other DMARD comparator",
                ],
                "exclude": [],
            },
            "outcome": {
                "name": "Outcome",
                "include": [
                    "disease activity measures (DAS28, ACR response, joint scores)",
                    "structural/radiological outcomes",
                    "study design characteristics (dose, duration, endpoints)",
                ],
                "exclude": [],
            },
        },
        "study_design_include": [
            "randomized controlled trials (human studies)",
            "controlled animal experiments",
        ],
        "study_design_exclude": [
            "observational studies",
            "case reports",
            "reviews",
        ],
        "NEEDS_REVIEW": True,
        "review_notes": {
            "general": "NEEDS_REVIEW: This SR compares study design features (translational research), not just clinical outcomes. Confirm whether observational animal studies were also included.",
        },
    },

    "Radjenovic_2013": {
        "framework": "pico",
        "research_question": (
            "Which software metrics are effective for fault prediction in "
            "software systems, and how do they compare?"
        ),
        "elements": {
            "population": {
                "name": "Population (Software Context)",
                "include": [
                    "software modules, classes, files, or functions",
                    "any programming language, paradigm, or project scale",
                ],
                "exclude": [
                    "hardware or network fault prediction",
                ],
            },
            "intervention": {
                "name": "Intervention (Metrics/Predictors)",
                "include": [
                    "object-oriented metrics (CK metrics: CBO, WMC, RFC, LCOM, DIT, NOC)",
                    "process metrics (number of changes, change frequency, code churn)",
                    "code complexity metrics (McCabe cyclomatic complexity, lines of code)",
                    "developer/social network metrics",
                ],
                "exclude": [
                    "prediction techniques without metric specification",
                ],
            },
            "comparison": {
                "name": "Comparison",
                "include": [
                    "alternative metric sets",
                    "baseline (no metric)",
                ],
                "exclude": [],
            },
            "outcome": {
                "name": "Outcome",
                "include": [
                    "fault/defect prediction accuracy",
                    "AUC, precision, recall, F-measure, G-measure",
                ],
                "exclude": [],
            },
        },
        "study_design_include": [
            "empirical studies using fault/defect datasets",
            "controlled experiments",
            "case studies with quantitative results",
        ],
        "study_design_exclude": [
            "theoretical papers without quantitative evaluation",
            "secondary studies (SLRs, mapping studies)",
        ],
        "NEEDS_REVIEW": True,
        "review_notes": {
            "intervention": "NEEDS_REVIEW: Distinction between Radjenovic_2013 (metrics focus) and Hall_2012 (model performance focus) needs to be verified — there is overlap.",
        },
    },

    "Moran_2021": {
        "framework": "peco",
        "research_question": (
            "Does poor nutritional condition promote high-risk behaviours "
            "in animals?"
        ),
        "elements": {
            "population": {
                "name": "Population",
                "include": [
                    "non-human animals (any species)",
                    "animals with manipulated nutritional status",
                ],
                "exclude": [
                    "humans",
                    "studies on domesticated livestock with no wild-type parallels",
                ],
            },
            "exposure": {
                "name": "Exposure",
                "include": [
                    "food restriction, fasting, or caloric deficit",
                    "poor nutritional condition (low body condition index)",
                    "protein or micronutrient deprivation",
                ],
                "exclude": [
                    "pharmacological appetite suppression without nutritional manipulation",
                    "obesity/overnutrition conditions",
                ],
            },
            "comparison": {
                "name": "Comparison",
                "include": [
                    "ad libitum fed controls",
                    "good body condition animals",
                ],
                "exclude": [],
            },
            "outcome": {
                "name": "Outcome",
                "include": [
                    "predator approach / anti-predator behaviour",
                    "novel food/environment exploration",
                    "activity levels / foraging risk-taking",
                    "boldness or risk-taking behaviour indices",
                ],
                "exclude": [
                    "physiological stress markers without behavioural outcome",
                ],
            },
        },
        "study_design_include": [
            "controlled animal experiments",
            "observational field studies with nutritional manipulation",
        ],
        "study_design_exclude": [
            "review articles",
            "modelling studies without empirical data",
        ],
        "NEEDS_REVIEW": True,
        "review_notes": {
            "population": "NEEDS_REVIEW: Confirm whether humans were explicitly excluded or just absent from the original dataset.",
            "outcome": "NEEDS_REVIEW: Operational definition of 'high-risk behaviour' should be verified against original coding scheme.",
        },
    },

    "van_de_Schoot_2018": {
        "framework": "peco",
        "research_question": (
            "What are the longitudinal PTSD symptom trajectories following "
            "trauma exposure, as reported in prospective studies?"
        ),
        "elements": {
            "population": {
                "name": "Population",
                "include": [
                    "individuals exposed to a traumatic event (any type)",
                    "adults or adolescents (≥12 years)",
                    "clinical and non-clinical populations post-trauma",
                ],
                "exclude": [
                    "general population without specified trauma exposure",
                    "children (<12 years) only without adult data",
                ],
            },
            "exposure": {
                "name": "Exposure",
                "include": [
                    "trauma exposure (combat, disaster, accident, assault, abuse)",
                ],
                "exclude": [
                    "subclinical stressful life events not meeting trauma criteria",
                ],
            },
            "comparison": {
                "name": "Comparison",
                "include": [
                    "within-person trajectory comparison (different trajectory classes)",
                    "no explicit between-group comparison required",
                ],
                "exclude": [],
            },
            "outcome": {
                "name": "Outcome",
                "include": [
                    "PTSD symptom severity assessed at ≥3 time points",
                    "trajectory group membership (resilient, recovery, chronic, delayed onset)",
                    "PTSD diagnosis using DSM or ICD criteria",
                ],
                "exclude": [
                    "single time-point PTSD assessment only",
                    "general anxiety or depression without PTSD-specific measures",
                ],
            },
        },
        "study_design_include": [
            "prospective longitudinal studies",
            "cohort studies with ≥3 assessment waves",
        ],
        "study_design_exclude": [
            "cross-sectional studies",
            "retrospective studies",
            "case reports",
        ],
        "NEEDS_REVIEW": True,
        "review_notes": {
            "general": "NEEDS_REVIEW: This SR feeds informed priors for Bayesian analysis — confirm whether studies without individual-level data were included.",
            "outcome": "NEEDS_REVIEW: Minimum number of time points (≥3) needs verification.",
        },
    },

    "Muthu_2021": {
        "framework": "pico",
        "research_question": (
            "What is the fragility of statistically significant outcomes "
            "reported in RCTs in spine surgery?"
        ),
        "elements": {
            "population": {
                "name": "Population (Meta-Research)",
                "include": [
                    "randomized controlled trials (RCTs) in spine surgery",
                    "RCTs reporting at least one statistically significant binary outcome (p < 0.05)",
                ],
                "exclude": [
                    "non-randomized studies",
                    "studies without binary outcomes (continuous outcomes only)",
                    "studies in non-spine orthopaedic surgery",
                ],
            },
            "intervention": {
                "name": "Intervention",
                "include": [
                    "any surgical or non-surgical treatment for spine conditions",
                ],
                "exclude": [],
            },
            "comparison": {
                "name": "Comparison",
                "include": [
                    "any comparator arm in the RCT",
                ],
                "exclude": [],
            },
            "outcome": {
                "name": "Outcome",
                "include": [
                    "fragility index (FI) — minimum events to reverse significance",
                    "fragility quotient (FI / sample size)",
                    "reversal number",
                    "p-value of the original outcome",
                ],
                "exclude": [
                    "clinical outcomes without fragility analysis",
                ],
            },
        },
        "study_design_include": [
            "randomized controlled trials (RCTs) in spine surgery",
        ],
        "study_design_exclude": [
            "observational studies",
            "systematic reviews",
            "case series",
        ],
        "NEEDS_REVIEW": True,
        "review_notes": {
            "general": "NEEDS_REVIEW: This is a meta-research review of RCT fragility — the 'population' is the RCTs themselves, not patients. Standard PICO may not be optimal; consider a custom framework.",
            "intervention": "NEEDS_REVIEW: Confirm whether all spine surgery types (lumbar, cervical, thoracic) were included or only specific procedures.",
        },
    },

    "Appenzeller-Herzog_2019": {
        "framework": "pico",
        "research_question": (
            "What is the comparative effectiveness and safety of common "
            "therapies (D-penicillamine, zinc, trientine, tetrathiomolybdate) "
            "for Wilson disease?"
        ),
        "elements": {
            "population": {
                "name": "Population",
                "include": [
                    "patients with Wilson disease (any age, any stage)",
                    "both hepatic and neurological presentation",
                ],
                "exclude": [
                    "healthy controls",
                    "patients with other copper metabolism disorders",
                ],
            },
            "intervention": {
                "name": "Intervention",
                "include": [
                    "D-penicillamine",
                    "zinc salts (zinc sulfate, zinc acetate, zinc gluconate)",
                    "trientine (triethylene tetramine)",
                    "tetrathiomolybdate (ammonium tetrathiomolybdate)",
                ],
                "exclude": [
                    "liver transplantation",
                    "dietary restriction alone",
                ],
            },
            "comparison": {
                "name": "Comparison",
                "include": [
                    "placebo",
                    "no treatment",
                    "any other active Wilson disease treatment",
                ],
                "exclude": [],
            },
            "outcome": {
                "name": "Outcome",
                "include": [
                    "mortality",
                    "clinical symptom improvement (hepatic and neurological)",
                    "copper excretion / serum copper levels",
                    "treatment discontinuation due to adverse events",
                    "side effects / tolerability",
                ],
                "exclude": [],
            },
        },
        "study_design_include": [
            "randomized controlled trials (RCTs)",
            "prospective controlled studies",
            "retrospective controlled studies",
        ],
        "study_design_exclude": [
            "case reports",
            "uncontrolled observational studies",
            "review articles",
        ],
        "NEEDS_REVIEW": False,
        "review_notes": {},
    },

    "Smid_2020": {
        "framework": "pico",
        "research_question": (
            "How does Bayesian estimation compare to frequentist estimation "
            "for structural equation models (SEM) in small sample contexts?"
        ),
        "elements": {
            "population": {
                "name": "Population (Study Context)",
                "include": [
                    "studies using structural equation models (SEM)",
                    "small sample contexts (typically n < 200)",
                    "simulation studies and empirical comparisons",
                ],
                "exclude": [
                    "studies on other multivariate methods (e.g., HLM, MANOVA) without SEM",
                    "large-sample-only studies (n > 1000 without small sample conditions)",
                ],
            },
            "intervention": {
                "name": "Intervention (Estimation Method)",
                "include": [
                    "Bayesian estimation (MCMC, Gibbs sampling, etc.)",
                    "informative prior specification",
                ],
                "exclude": [],
            },
            "comparison": {
                "name": "Comparison",
                "include": [
                    "maximum likelihood (ML) estimation",
                    "generalized least squares (GLS)",
                    "weighted least squares (WLS/DWLS)",
                    "other frequentist estimators",
                ],
                "exclude": [],
            },
            "outcome": {
                "name": "Outcome",
                "include": [
                    "parameter bias / estimation accuracy",
                    "standard error accuracy",
                    "model fit indices",
                    "convergence rates",
                    "Type I error / power",
                ],
                "exclude": [],
            },
        },
        "study_design_include": [
            "Monte Carlo simulation studies",
            "empirical comparisons",
            "methodological studies comparing estimation approaches",
        ],
        "study_design_exclude": [
            "theoretical/conceptual papers without simulation or empirical data",
            "application papers without method comparison",
        ],
        "NEEDS_REVIEW": True,
        "review_notes": {
            "population": "NEEDS_REVIEW: Confirm exact sample size threshold used to define 'small sample'.",
            "intervention": "NEEDS_REVIEW: Confirm whether prior sensitivity analyses were required for inclusion.",
        },
    },

    "van_der_Waal_2022": {
        "framework": "peo",
        "research_question": (
            "What role do older adults with cancer prefer in treatment "
            "decision making?"
        ),
        "elements": {
            "population": {
                "name": "Population",
                "include": [
                    "older adults (≥60 years) with any cancer type",
                    "cancer patients in active treatment or treatment decision phase",
                ],
                "exclude": [
                    "cancer survivors in long-term follow-up without treatment decisions",
                    "caregivers/family members (unless patient data reported separately)",
                    "adults <60 years",
                ],
            },
            "exposure": {
                "name": "Exposure / Phenomenon",
                "include": [
                    "treatment decision-making process",
                    "preferred role in treatment decisions (active, shared, passive)",
                ],
                "exclude": [],
            },
            "outcome": {
                "name": "Outcome",
                "include": [
                    "preferred decision-making role (active, passive, shared/collaborative)",
                    "actual decision-making role",
                    "concordance between preferred and actual role",
                    "satisfaction with decision-making",
                ],
                "exclude": [
                    "clinical treatment outcomes (survival, response rate) without role data",
                ],
            },
        },
        "study_design_include": [
            "quantitative surveys / questionnaire studies",
            "mixed-methods studies",
            "qualitative studies with reported role preferences",
        ],
        "study_design_exclude": [
            "case reports",
            "opinion pieces",
        ],
        "NEEDS_REVIEW": True,
        "review_notes": {
            "population": "NEEDS_REVIEW: Confirm exact age cutoff (≥60 vs ≥65 vs ≥70) used in the original review.",
            "general": "NEEDS_REVIEW: Framework is PEO (not standard PICO) — no formal comparison/intervention group required.",
        },
    },

    "Chou_2003": {
        "framework": "pico",
        "research_question": (
            "What is the comparative efficacy and safety of long-acting oral "
            "opioids for chronic non-cancer pain?"
        ),
        "elements": {
            "population": {
                "name": "Population",
                "include": [
                    "adults (≥18 years) with chronic non-cancer pain (≥3 months duration)",
                    "any chronic pain etiology (low back pain, neuropathic pain, osteoarthritis, fibromyalgia)",
                ],
                "exclude": [
                    "acute pain (< 3 months)",
                    "cancer-related pain",
                    "palliative/end-of-life care",
                    "post-operative pain",
                ],
            },
            "intervention": {
                "name": "Intervention",
                "include": [
                    "long-acting (extended-release / sustained-release) oral opioids",
                    "morphine SR/ER",
                    "oxycodone CR/ER",
                    "methadone (oral)",
                    "oxymorphone ER",
                    "hydromorphone ER",
                    "levorphanol",
                ],
                "exclude": [
                    "short-acting / immediate-release opioids",
                    "parenteral opioids",
                    "transdermal opioids (patches)",
                ],
            },
            "comparison": {
                "name": "Comparison",
                "include": [
                    "placebo",
                    "other long-acting opioid",
                    "non-opioid analgesic",
                ],
                "exclude": [],
            },
            "outcome": {
                "name": "Outcome",
                "include": [
                    "pain intensity / pain relief",
                    "functional outcomes",
                    "adverse events (constipation, nausea, sedation, respiratory depression)",
                    "withdrawal / discontinuation rates",
                ],
                "exclude": [],
            },
        },
        "study_design_include": [
            "randomized controlled trials (RCTs)",
            "controlled clinical trials",
        ],
        "study_design_exclude": [
            "uncontrolled trials",
            "observational studies",
            "case reports",
        ],
        "NEEDS_REVIEW": False,
        "review_notes": {},
    },

    "Jeyaraman_2020": {
        "framework": "pico",
        "research_question": (
            "Does the source of mesenchymal stem cells (MSC) affect treatment "
            "outcomes in knee osteoarthritis?"
        ),
        "elements": {
            "population": {
                "name": "Population",
                "include": [
                    "adult patients with knee osteoarthritis (any grade)",
                    "diagnosis confirmed by clinical and/or radiological criteria",
                ],
                "exclude": [
                    "rheumatoid arthritis",
                    "post-traumatic arthritis without OA diagnosis",
                    "pediatric patients (<18 years)",
                ],
            },
            "intervention": {
                "name": "Intervention",
                "include": [
                    "mesenchymal stem cell (MSC) therapy / intra-articular MSC injection",
                    "bone marrow-derived MSCs (BM-MSCs)",
                    "adipose-derived MSCs (AD-MSCs)",
                    "synovial-derived MSCs (Syn-MSCs)",
                    "umbilical cord-derived MSCs (UC-MSCs)",
                    "peripheral blood-derived MSCs",
                ],
                "exclude": [
                    "platelet-rich plasma (PRP) alone without MSC",
                    "exosome therapy without whole-cell MSC",
                ],
            },
            "comparison": {
                "name": "Comparison",
                "include": [
                    "placebo / saline injection",
                    "hyaluronic acid injection",
                    "corticosteroid injection",
                    "different MSC source",
                ],
                "exclude": [],
            },
            "outcome": {
                "name": "Outcome",
                "include": [
                    "pain scores (VAS, NRS)",
                    "functional outcomes (KOOS, WOMAC, Lysholm score)",
                    "cartilage regeneration (MRI assessment)",
                    "adverse events",
                ],
                "exclude": [],
            },
        },
        "study_design_include": [
            "randomized controlled trials (RCTs)",
        ],
        "study_design_exclude": [
            "non-randomized studies",
            "observational studies",
            "case reports",
            "animal studies",
        ],
        "NEEDS_REVIEW": False,
        "review_notes": {},
    },
}


def save_criteria_json(name: str, criteria: dict) -> None:
    out = CRITERIA_DIR / f"{name}_criteria.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(criteria, f, indent=2, ensure_ascii=False)
    nr = "⚠ NEEDS_REVIEW" if criteria.get("NEEDS_REVIEW") else "✓"
    print(f"  {nr}  {name}")


def build_summary_md(all_criteria: dict[str, dict]) -> str:
    lines = [
        "# SYNERGY Criteria Draft — Human Review Summary",
        "",
        "Generated from publication titles. Items marked ⚠ require verification.",
        "",
        "## Quick Reference Table",
        "",
        "| Dataset | Framework | P / Population | I / Exposure | C | O | ⚠ Review items |",
        "|---------|-----------|---------------|------------|---|---|----------------|",
    ]

    for name, c in sorted(all_criteria.items()):
        fw = c["framework"].upper()
        elems = c["elements"]
        p = elems.get("population", {}).get("include", ["—"])[0][:60]
        i_key = next((k for k in ["intervention", "exposure"] if k in elems), None)
        i = elems[i_key].get("include", ["—"])[0][:60] if i_key else "—"
        comp = elems.get("comparison", {}).get("include", ["—"])[0][:40]
        o = elems.get("outcome", {}).get("include", ["—"])[0][:60]
        nr_count = len(c.get("review_notes", {}))
        needs = f"⚠ {nr_count}" if c.get("NEEDS_REVIEW") else "✓"
        lines.append(f"| {name} | {fw} | {p} | {i} | {comp} | {o} | {needs} |")

    lines += [
        "",
        "---",
        "",
        "## Per-Dataset Review Notes",
        "",
    ]

    for name, c in sorted(all_criteria.items()):
        lines.append(f"### {name}")
        lines.append(f"- **Framework**: {c['framework'].upper()}")
        lines.append(f"- **Research question**: {c['research_question']}")
        lines.append(f"- **NEEDS_REVIEW**: {c['NEEDS_REVIEW']}")
        notes = c.get("review_notes", {})
        if notes:
            lines.append("- **Review notes**:")
            for field, note in notes.items():
                lines.append(f"  - `{field}`: {note}")
        lines.append("")

    return "\n".join(lines)


def main() -> None:
    print(f"Writing criteria JSON to {CRITERIA_DIR}\n")
    for name, criteria in CRITERIA.items():
        save_criteria_json(name, criteria)

    # Summary markdown
    summary = build_summary_md(CRITERIA)
    summary_path = CRITERIA_DIR / "criteria_summary.md"
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(summary)

    print(f"\nSummary written to {summary_path}")
    print("\n" + "=" * 70)
    print(summary[:3000])


if __name__ == "__main__":
    main()
