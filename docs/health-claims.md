# Health claims

**Policy:** the app is illustrative and educational, never medical advice, and carries a visible
disclaimer wherever an outlook is shown. **No invented statistics.** Any specific number about
health outcomes needs a real source listed in this file *before* it goes in the UI. Today the UI
contains **no health statistics**, only the qualitative statements below.

## Claims currently shown

| Where | Text (abridged) | Kind | Source status |
|---|---|---|---|
| Analytics > Outlook (score below 70) | "Sustained slouching is associated with neck and back pain risk over the years." | Qualitative association | **Only partly supported; recommend rewording.** Sources S1/S2 below: forward-head posture is *associated* with neck pain in adults (cross-sectional), and there is *no consensus on causality* for back pain. "Risk over the years" implies a longitudinal effect no source shows. Suggested: "Poor sitting posture is linked with neck discomfort in some studies, but research hasn't shown that it causes pain. Moving regularly is still a good habit." (Product decision, so the UI copy is unchanged.) |
| Analytics > Outlook (score 70+) | "You're on track to be healthy!" | Encouragement, not a medical claim | n/a (product copy; keep it from implying a diagnosis) |
| Live break banner, Analytics tip | "A common suggestion is to stand and move every 30-45 minutes." | Behavioural suggestion from the product spec | **Source needed** before presenting it as guidance rather than a prompt. |
| Analytics tips | Chin tuck and doorway chest stretch instructions | Exercise instructions, no outcome claims | Fine as instructions; have a clinician/PT sanity-check the wording before any real release. |

## Sources reviewed (checked 2026-11-15; none is used for a number in the UI yet)

| ID | Source | What it supports | What it does **not** support |
|---|---|---|---|
| S1 | Swain CTV, Pan F, Owen PJ, Schmidt H, Belavy DL. *No consensus on causality of spine postures or physical exposure and low back pain: a systematic review of systematic reviews.* J Biomech 2020;102:109312. [PubMed](https://pubmed.ncbi.nlm.nih.gov/31451200/) | 41 reviews included; positive and null associations found for posture, prolonged sitting/standing, bending, awkward postures. "Despite the availability of many reviews, there is no consensus regarding causality of physical exposure to LBP." | That slouching or sitting causes low back pain |
| S2 | Mahmoud NF et al. *The Relationship Between Forward Head Posture and Neck Pain: a Systematic Review and Meta-Analysis.* Curr Rev Musculoskelet Med 2019. [PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC6942109) | 15 cross-sectional studies; adults with neck pain had more forward-head posture; no association in adolescents; age is a confounder | Causation: "the causal relationship is not possible to establish". (The abstract and results disagree on one adolescent figure, so don't quote its effect sizes without re-reading it.) |
| S3 | GBD 2021 Low Back Pain Collaborators. *Global, regional, and national burden of low back pain, 1990-2020, its attributable risk factors, and projections to 2050.* Lancet Rheumatol 2023;5(6):e316-e329. [PubMed](https://pubmed.ncbi.nlm.nih.gov/37273833/) | Population burden: 619 million people (95% UI 554-694M) in 2020, 843 million (759-933M) projected for 2050; 38.8% (28.7-47.0) of years lived with disability attributed to occupational factors, smoking and high BMI | Anything about *posture* specifically ("occupational factors" is broader), or any individual's risk |
| S4 | GBD 2021 neck pain paper (about 203 million people in 2020) | Population burden of neck pain | **Not independently checked** (seen only in a search summary). Verify before use |

Not found: any source linking sitting posture or slouching to **arthritis**. Do not make that claim. Do not
show individual predictions such as "you will develop X in N years": no validated model supports them (see
`features.md` section 4 for what we can build instead).

## Not medical

- The **70% "on track" line** (`GOOD_THRESHOLD_PCT` in `api/core/scoring.py`) is an arbitrary product threshold used for the outlook message, day streaks and goals. It is **not** a clinical threshold.
- The **posture score** is a transparent, explainable ratio (see `docs/api.md`), not a validated clinical measure.
- Disclaimer text shown in the UI: "Illustrative and educational only. Not medical advice. Talk to a clinician about pain or health concerns."

## Adding a claim

1. Write the claim here with its source (title, authors/organisation, year, link).
2. Quote or paraphrase only what the source supports; keep the wording qualitative unless the source gives a number.
3. Then, and only then, add it to the UI.
