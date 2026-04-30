# SYNERGY Criteria — Approved Drafts

All 15 datasets reviewed and approved. Status: **ready for experiments**.

## Summary Table

| Dataset | Framework | Population | Intervention/Exposure | Comparison | Outcome |
|---------|-----------|-----------|----------------------|-----------|---------|
| Appenzeller-Herzog_2019 | PICO | patients with Wilson disease (any age, any stage) | D-penicillamine | placebo | mortality |
| Brouwer_2019 | PECO | adults (≥18 years) with a history of major depressive d | cognitive reactivity / negative automatic thoughts | lower levels of the same psychologi | depressive relapse (return of symptoms in same episode) |
| Chou_2003 | PICO | adults (≥18 years) with chronic non-cancer pain (≥3 mon | long-acting (extended-release / sustained-release) oral | placebo | pain intensity / pain relief |
| Hall_2012 | PICO | software systems, modules, files, or classes | machine learning-based fault prediction models (Naive B | baseline model (e.g., random classi | prediction accuracy, precision, recall, F-measure |
| Jeyaraman_2020 | PICO | adult patients with knee osteoarthritis (any grade) | mesenchymal stem cell (MSC) therapy / intra-articular M | placebo / saline injection | pain scores (VAS, NRS) |
| Leenaars_2020 | PICO | animal models of rheumatoid arthritis (collagen-induced | methotrexate (MTX) at any dose, route, duration | placebo | disease activity measures (DAS28, ACR response, joint s |
| Moran_2021 | PECO | non-human animals (any species) | food restriction, fasting, or caloric deficit | ad libitum fed controls | predator approach / anti-predator behaviour |
| Muthu_2021 | PICO | randomized controlled trials (RCTs) in spine surgery | any surgical or non-surgical treatment for spine condit | any comparator arm in the RCT | fragility index (FI) — minimum events to reverse signif |
| Radjenovic_2013 | PICO | software modules, classes, files, or functions | object-oriented metrics (CK metrics: CBO, WMC, RFC, LCO | alternative metric sets | fault/defect prediction accuracy |
| Smid_2020 | PICO | studies using structural equation models (SEM) | Bayesian estimation (MCMC, Gibbs sampling, etc.) | maximum likelihood (ML) estimation | parameter bias / estimation accuracy |
| Walker_2018 | PECO | humans (any age, both sexes) | environmental chemical exposures (pesticides, endocrine | unexposed control offspring | health effects in unexposed F2+ offspring (true transge |
| Wassenaar_2017 | PECO | rodents (mice and rats) | Bisphenol A (BPA) exposure | vehicle control (oil, water, corn o | body weight, body mass index (BMI equivalent) |
| van_Dis_2020 | PICO | adults (≥18 years) with a primary anxiety-related disor | cognitive behavioral therapy (CBT) | waitlist control | symptom severity at ≥12 months follow-up |
| van_de_Schoot_2018 | PECO | individuals exposed to a traumatic event (any type) | trauma exposure (combat, disaster, accident, assault, a | within-person trajectory comparison | PTSD symptom severity assessed at ≥3 time points |
| van_der_Waal_2022 | PEO | older adults (≥60 years) with any cancer type | treatment decision-making process | — | preferred decision-making role (active, passive, shared |

---

## Per-Dataset Details

### Appenzeller-Herzog_2019
- **Framework**: PICO
- **RQ**: What is the comparative effectiveness and safety of common therapies (D-penicillamine, zinc, trientine, tetrathiomolybdate) for Wilson disease?
- **P**: patients with Wilson disease (any age, any stage); both hepatic and neurological presentation
- **INTERVENTION**: D-penicillamine;zinc salts (zinc sulfate, zinc acetate, zinc gluconate);trientine (triethylene tetramine)
- **C**: placebo;no treatment
- **O**: mortality;clinical symptom improvement (hepatic and neurological);copper excretion / serum copper levels
- **Study designs**: randomized controlled trials (RCTs),prospective controlled studies,retrospective controlled studies

### Brouwer_2019
- **Framework**: PECO
- **RQ**: Do psychological risk factors predict depressive relapse or recurrence in individuals with a history of depression?
- **P**: adults (≥18 years) with a history of major depressive disorder or depressive episode; currently in remission or partial remission at baseline
- **EXPOSURE**: cognitive reactivity / negative automatic thoughts;rumination;mindfulness / self-compassion
- **C**: lower levels of the same psychological risk factor;absence of the risk factor
- **O**: depressive relapse (return of symptoms in same episode);depressive recurrence (new depressive episode);time to relapse/recurrence
- **Study designs**: prospective longitudinal studies,cohort studies,randomized controlled trials with relapse/recurrence follow-up

### Chou_2003
- **Framework**: PICO
- **RQ**: What is the comparative efficacy and safety of long-acting oral opioids for chronic non-cancer pain?
- **P**: adults (≥18 years) with chronic non-cancer pain (≥3 months duration); any chronic pain etiology (low back pain, neuropathic pain, osteoarthritis, fibromyalgia)
- **INTERVENTION**: long-acting (extended-release / sustained-release) oral opioids;morphine SR/ER;oxycodone CR/ER
- **C**: placebo;other long-acting opioid
- **O**: pain intensity / pain relief;functional outcomes;adverse events (constipation, nausea, sedation, respiratory depression)
- **Study designs**: randomized controlled trials (RCTs),controlled clinical trials

### Hall_2012
- **Framework**: PICO
- **RQ**: What is the performance of fault prediction models in software engineering, and which predictors and techniques perform best?
- **P**: software systems, modules, files, or classes; open-source or industrial software projects; any programming language
- **INTERVENTION**: machine learning-based fault prediction models (Naive Bayes, random forest, neural networks, etc.);statistical models (logistic regression, discriminant analysis);software metrics-based approaches (CK metrics, McCabe, Halstead)
- **C**: baseline model (e.g., random classifier);alternative fault prediction model
- **O**: prediction accuracy, precision, recall, F-measure;AUC-ROC;probability of detection (PD), probability of false alarm (PF)
- **Study designs**: empirical studies (experiments, case studies, controlled experiments),cross-project prediction studies,within-project prediction studies

### Jeyaraman_2020
- **Framework**: PICO
- **RQ**: Does the source of mesenchymal stem cells (MSC) affect treatment outcomes in knee osteoarthritis?
- **P**: adult patients with knee osteoarthritis (any grade); diagnosis confirmed by clinical and/or radiological criteria
- **INTERVENTION**: mesenchymal stem cell (MSC) therapy / intra-articular MSC injection;bone marrow-derived MSCs (BM-MSCs);adipose-derived MSCs (AD-MSCs)
- **C**: placebo / saline injection;hyaluronic acid injection
- **O**: pain scores (VAS, NRS);functional outcomes (KOOS, WOMAC, Lysholm score);cartilage regeneration (MRI assessment)
- **Study designs**: randomized controlled trials (RCTs)

### Leenaars_2020
- **Framework**: PICO
- **RQ**: How do animal and human methotrexate efficacy studies for rheumatoid arthritis compare in experimental design, and what does this reveal about translational value?
- **P**: animal models of rheumatoid arthritis (collagen-induced arthritis, adjuvant-induced arthritis, etc.); human patients with rheumatoid arthritis
- **INTERVENTION**: methotrexate (MTX) at any dose, route, duration
- **C**: placebo;vehicle control
- **O**: disease activity measures (DAS28, ACR response, joint scores);structural/radiological outcomes;study design characteristics (dose, duration, endpoints)
- **Study designs**: randomized controlled trials (human studies),controlled animal experiments

### Moran_2021
- **Framework**: PECO
- **RQ**: Does poor nutritional condition promote high-risk behaviours in animals?
- **P**: non-human animals (any species); animals with manipulated nutritional status
- **EXPOSURE**: food restriction, fasting, or caloric deficit;poor nutritional condition (low body condition index);protein or micronutrient deprivation
- **C**: ad libitum fed controls;good body condition animals
- **O**: predator approach / anti-predator behaviour;novel food/environment exploration;activity levels / foraging risk-taking
- **Study designs**: controlled animal experiments,observational field studies with nutritional manipulation

### Muthu_2021
- **Framework**: PICO
- **RQ**: What is the fragility of statistically significant outcomes reported in RCTs in spine surgery?
- **P**: randomized controlled trials (RCTs) in spine surgery; RCTs reporting at least one statistically significant binary outcome (p < 0.05)
- **INTERVENTION**: any surgical or non-surgical treatment for spine conditions
- **C**: any comparator arm in the RCT
- **O**: fragility index (FI) — minimum events to reverse significance;fragility quotient (FI / sample size);reversal number
- **Study designs**: randomized controlled trials (RCTs) in spine surgery

### Radjenovic_2013
- **Framework**: PICO
- **RQ**: Which software metrics are effective for fault prediction in software systems, and how do they compare?
- **P**: software modules, classes, files, or functions; any programming language, paradigm, or project scale
- **INTERVENTION**: object-oriented metrics (CK metrics: CBO, WMC, RFC, LCOM, DIT, NOC);process metrics (number of changes, change frequency, code churn);code complexity metrics (McCabe cyclomatic complexity, lines of code)
- **C**: alternative metric sets;baseline (no metric)
- **O**: fault/defect prediction accuracy;AUC, precision, recall, F-measure, G-measure
- **Study designs**: empirical studies using fault/defect datasets,controlled experiments,case studies with quantitative results

### Smid_2020
- **Framework**: PICO
- **RQ**: How does Bayesian estimation compare to frequentist estimation for structural equation models (SEM) in small sample contexts?
- **P**: studies using structural equation models (SEM); studies addressing small sample contexts in SEM (no fixed numeric threshold required); simulation studies and empirical comparisons of estimation methods
- **INTERVENTION**: Bayesian estimation (MCMC, Gibbs sampling, etc.);informative prior specification
- **C**: maximum likelihood (ML) estimation;generalized least squares (GLS)
- **O**: parameter bias / estimation accuracy;standard error accuracy;model fit indices
- **Study designs**: Monte Carlo simulation studies,empirical comparisons,methodological studies comparing estimation approaches

### Walker_2018
- **Framework**: PECO
- **RQ**: What is the human and animal evidence for potential transgenerational inheritance of health effects?
- **P**: humans (any age, both sexes); animal models (rodents, zebrafish, Drosophila, C. elegans); F1/F2/F3 offspring generations
- **EXPOSURE**: environmental chemical exposures (pesticides, endocrine disruptors, heavy metals);nutritional exposures (high-fat diet, caloric restriction, protein restriction);physical/social stressors (stress, trauma, exercise)
- **C**: unexposed control offspring;vehicle-treated controls
- **O**: health effects in unexposed F2+ offspring (true transgenerational; F1 germline transmission counts only if unexposed in utero);epigenetic changes (DNA methylation, histone modification, miRNA) in offspring;metabolic, reproductive, neurological, or immunological outcomes across generations
- **Study designs**: animal experimental studies,human epidemiological studies (cohort, cross-sectional),evidence maps

### Wassenaar_2017
- **Framework**: PECO
- **RQ**: Does early-life exposure to Bisphenol A (BPA) lead to obesity-related outcomes in rodents?
- **P**: rodents (mice and rats); exposed during early life (prenatal, postnatal, perinatal, neonatal periods)
- **EXPOSURE**: Bisphenol A (BPA) exposure;any route of administration (oral gavage, diet, injection, osmotic pump)
- **C**: vehicle control (oil, water, corn oil);unexposed control group
- **O**: body weight, body mass index (BMI equivalent);fat mass, adiposity;metabolic parameters (glucose, insulin, lipid profiles)
- **Study designs**: controlled animal experiments,randomized animal studies

### van_Dis_2020
- **Framework**: PICO
- **RQ**: What are the long-term outcomes of CBT for anxiety-related disorders compared to other treatments or control conditions?
- **P**: adults (≥18 years) with a primary anxiety-related disorder; specific phobia, social anxiety disorder, panic disorder, agoraphobia, GAD, OCD, PTSD
- **INTERVENTION**: cognitive behavioral therapy (CBT);exposure-based CBT;CBT variants (ACT, MBCT, DBT with CBT component)
- **C**: waitlist control;active control (supportive therapy, pill placebo)
- **O**: symptom severity at ≥12 months follow-up;remission/response rate at long-term follow-up;relapse rates
- **Study designs**: randomized controlled trials (RCTs),controlled clinical trials

### van_de_Schoot_2018
- **Framework**: PECO
- **RQ**: What are the longitudinal PTSD symptom trajectories following trauma exposure, as reported in prospective studies?
- **P**: individuals exposed to a traumatic event (any type); adults or adolescents (≥12 years); clinical and non-clinical populations post-trauma
- **EXPOSURE**: trauma exposure (combat, disaster, accident, assault, abuse)
- **C**: within-person trajectory comparison (different trajectory classes);no explicit between-group comparison required
- **O**: PTSD symptom severity assessed at ≥3 time points;trajectory group membership (resilient, recovery, chronic, delayed onset);PTSD diagnosis using DSM or ICD criteria
- **Study designs**: prospective longitudinal studies,cohort studies with ≥3 assessment waves

### van_der_Waal_2022
- **Framework**: PEO
- **RQ**: What role do older adults with cancer prefer in treatment decision making?
- **P**: older adults (≥60 years) with any cancer type; cancer patients in active treatment or treatment decision phase
- **EXPOSURE**: treatment decision-making process;preferred role in treatment decisions (active, shared, passive)
- **C**: —
- **O**: preferred decision-making role (active, passive, shared/collaborative);actual decision-making role;concordance between preferred and actual role
- **Study designs**: quantitative surveys / questionnaire studies,mixed-methods studies,qualitative studies with reported role preferences
