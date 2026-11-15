# Health claims

**Policy:** the app is illustrative and educational, never medical advice, and carries a visible
disclaimer wherever an outlook or evidence is shown. **No invented statistics.** Any specific number
about health outcomes needs a real source listed in this file *before* it goes in the UI. The only health
numbers shown are the Global Burden of Disease population figures (S3, S4), quoted from the papers.
Everything else is qualitative or about the user's own data.

## Claims currently shown

| Where | Text (abridged) | Kind | Source status |
|---|---|---|---|
| Analytics > Outlook (score below 70) | "Poor sitting posture is linked with neck discomfort in some studies, but research hasn't shown that it causes pain. Moving regularly is still a good habit." | Qualitative association, with the causal limit stated | **Supported (qualitative)** by S2 (forward-head posture associated with neck pain in adults, cross-sectional) and S1/S2 (causation not established). Reworded from the original "associated with neck and back pain risk over the years", which implied a longitudinal effect no source shows. |
| Analytics > Outlook (score 70+) | "You're on track to be healthy!" | Encouragement, not a medical claim | n/a (product copy; keep it from implying a diagnosis) |
| Live break banner, Analytics tip | "A common suggestion is to stand and move every 30-45 minutes." | Behavioural suggestion from the product spec | **Source needed** before presenting it as guidance rather than a prompt. |
| Analytics tips | Chin tuck and doorway chest stretch instructions | Exercise instructions, no outcome claims | Fine as instructions; have a clinician/PT sanity-check the wording before any real release. |
| Pain & evidence > "Does slouching cause pain?" (`web/src/evidence.ts`) | Neck pain: *associated, cause not established*. Low back pain: *mixed, no consensus on cause*. Arthritis: *no evidence found* | Evidence meter with the level written out | Neck: S2. Back: S1. Arthritis is an **absence statement** ("we found no research"), not a claim, and rests on a non-exhaustive search (see below). Keep `evidence.ts` and this table in sync. |
| Pain & evidence > "How common are back and neck pain?" | Low back pain 619 million people (95% UI 554-694M) in 2020, projected 843 million by 2050; neck pain 203 million (163-253M) in 2020, most common between ages 45 and 74 | Population statistics, worded as "population context, not your risk" | S3 (low back) and S4 (neck), quoted from the abstracts. The card says they describe how widespread the problems are, not an individual's risk, and don't isolate posture. |
| Pain & evidence > "Your pain vs your slouching" | "In your N weeks of data, weeks with more slouching tended to be weeks with more pain..." | The user's **own** data, not a claim about people in general | No outside source needed, but the wording rules are binding: always "a pattern in your own weeks, not proof that slouching causes pain"; call any pattern *tentative* below 8 weeks; show n and the rank correlation; never present it as a prediction. |
| Calibration (back-angle check) | "Your back is leaning forward about 18° (aim for within 10° of upright)" | A **product parameter**, not a medical threshold | S5, S6 (see below). The allowed range is 10° either side of upright (forward and back are both refused). It is a product choice that separates the example good (5°) and slouched (18°) values. S5/S6 describe a slight recline as comfortable, which is in tension with the 10° backward limit, so that side may need widening. Tune against real model output. |
| Coach > Profile, Patterns, Coaching, Habits | "Your posture tends to slip after about N minutes", "You respond best in the morning", "13% of your nudges are followed by sitting up within 30 seconds", streaks and challenges | The user's **own** data, descriptive only | No outside source needed. No health outcome is implied; wording is about habits, never about pain or risk. The Gemini payload contains none of the pain data, and the prompts forbid medical advice. |
| Coach > Exercises (chin tuck, doorway stretch, shoulder-blade squeeze, stand-and-walk) | Step-by-step instructions plus "Stop if anything hurts. These are general suggestions, not medical advice." | Exercise instructions, **no outcome claims** | Instructions only. Have a clinician/PT sanity-check the wording before any real release. The app never claims an exercise prevents or treats pain. |
| Coach > Break target | "Stand up every 45 minutes" (`SIT_TARGET_MIN`) | Behavioural default (a fixed product value, not user-adjustable) | **Source needed** before presenting it as guidance rather than a prompt (same status as the Live banner). |

## Sources reviewed (checked 2026-11-15)

| ID | Source | What it supports | What it does **not** support |
|---|---|---|---|
| S1 | Swain CTV, Pan F, Owen PJ, Schmidt H, Belavy DL. *No consensus on causality of spine postures or physical exposure and low back pain: a systematic review of systematic reviews.* J Biomech 2020;102:109312. [PubMed](https://pubmed.ncbi.nlm.nih.gov/31451200/) | 41 reviews included; positive and null associations found for posture, prolonged sitting/standing, bending, awkward postures. "Despite the availability of many reviews, there is no consensus regarding causality of physical exposure to LBP." | That slouching or sitting causes low back pain |
| S2 | Mahmoud NF et al. *The Relationship Between Forward Head Posture and Neck Pain: a Systematic Review and Meta-Analysis.* Curr Rev Musculoskelet Med 2019. [PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC6942109) | 15 cross-sectional studies; adults with neck pain had more forward-head posture; no association in adolescents; age is a confounder | Causation: "the causal relationship is not possible to establish". (The abstract and results disagree on one adolescent figure, so don't quote its effect sizes without re-reading it.) |
| S3 | GBD 2021 Low Back Pain Collaborators. *Global, regional, and national burden of low back pain, 1990-2020, its attributable risk factors, and projections to 2050.* Lancet Rheumatol 2023;5(6):e316-e329. [PubMed](https://pubmed.ncbi.nlm.nih.gov/37273833/) | Population burden: 619 million people (95% UI 554-694M) in 2020, 843 million (759-933M) projected for 2050; 38.8% (28.7-47.0) of years lived with disability attributed to occupational factors, smoking and high BMI | Anything about *posture* specifically ("occupational factors" is broader), or any individual's risk |
| S4 | GBD 2021 Neck Pain Collaborators. *Global, regional, and national burden of neck pain, 1990-2020, and projections to 2050.* Lancet Rheumatol 2024 (PMID 38383088). [PubMed](https://pubmed.ncbi.nlm.nih.gov/38383088/) | "Globally, in 2020, neck pain affected 203 million (95% UI 163-253) people", with prevalence "peaking between 45 years and 74 years in male and female sexes" (checked against the abstract) | Anything about posture or any individual's risk |
| S5 | Cornell University, Human Factors & Ergonomics course notes (DEA 3250), "Sitting". [page](https://ergo.human.cornell.edu/DEA3250Flipbook/DEA3250notes/sitting.html) | "Optimal angle seems to be between 100-110-degrees" for the backrest; "the preferred seat back angle for comfort is 15-degrees" (a study of college students); VDT operators preferred a 13-15 degree backward incline (Grandjean). I.e. a supported, slightly reclined back is fine, rigid 90-degree sitting is not a requirement | Course notes, not peer-reviewed; the page cites no source for the 100-110 figure. Context for the backward limit in the calibration check: these sources describe a slightly reclined back as comfortable, which is in tension with a 10° backward limit |
| S6 | Colorado Mesa University HR, ergonomic workstation setup handout. [PDF](https://www.coloradomesa.edu/human-resources/documents/wellness-and-safety/ergonomics-ws-setup.pdf) | Backrest "tilted slightly back so the angle of the trunk is 10 to 20 degrees from vertical" | **Seen only in a search-result excerpt; I did not open the PDF.** A workplace handout, not research |

**Population data access:** the IHME GBD Results Tool (<https://vizhub.healthdata.org/gbd-results/>) is linked from the UI for age/region detail. My fetch of it returned HTTP 403, so its terms of use are **unverified**. Check them before reusing its data.

**Not found:** any source linking sitting posture or slouching to **arthritis**. The search was not
exhaustive, but there is no basis to claim it. Do not make that claim, and do not show individual predictions
such as "you will develop X in N years": no validated model supports them (see `features.md` section 4).

## Gemini (sponsor API) data terms

Checked on Google's Gemini API terms page: on the **unpaid** tier, content you send may be used to improve Google's
products and reviewed by humans, and you must not submit personal or sensitive information; on the **paid** tier it is
not used that way. (Paraphrased, not quoted.) Terms change, so re-read the current page before the demo. How we comply: only
de-identified habit numbers are sent, after in-app consent and a preview of the exact payload; **pain check-ins, ids,
dates and images are never sent**; the README requires a billing-enabled key; nothing returned is stored on our server.
The prompts also instruct the model not to give medical advice and to use only the numbers provided.

## Not medical

- The **70% "on track" line** (`GOOD_THRESHOLD_PCT` in `api/core/scoring.py`) is an arbitrary product threshold used for the outlook message, day streaks and goals. It is **not** a clinical threshold.
- The **posture score** is a transparent, explainable ratio (see `docs/api.md`), not a validated clinical measure.
- The **back-angle limits** (`api/core/calibration_gate.py`) are product parameters. The "pain vs slouching" correlation is descriptive only, and its strength buckets (0.3 / 0.6) are rough rules of thumb.
- Disclaimer text shown in the UI: "Illustrative and educational only. Not medical advice. Talk to a clinician about pain or health concerns."

## Adding a claim

1. Write the claim here with its source (title, authors/organisation, year, link).
2. Quote or paraphrase only what the source supports; keep the wording qualitative unless the source gives a number.
3. Then, and only then, add it to the UI.
