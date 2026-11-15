# Health claims

**Policy:** the app is illustrative and educational, never medical advice, and carries a visible
disclaimer wherever an outlook is shown. **No invented statistics.** Any specific number about
health outcomes needs a real source listed in this file *before* it goes in the UI. Today the UI
contains **no health statistics**, only the qualitative statements below.

## Claims currently shown

| Where | Text (abridged) | Kind | Source status |
|---|---|---|---|
| Analytics > Outlook (score below 70) | "Sustained slouching is associated with neck and back pain risk over the years." | Qualitative association | **Source needed.** Add a peer-reviewed review or authoritative guidance here, then remove this note. |
| Analytics > Outlook (score 70+) | "You're on track to be healthy!" | Encouragement, not a medical claim | n/a (product copy; keep it from implying a diagnosis) |
| Live break banner, Analytics tip | "A common suggestion is to stand and move every 30-45 minutes." | Behavioural suggestion from the product spec | **Source needed** before presenting it as guidance rather than a prompt. |
| Analytics tips | Chin tuck and doorway chest stretch instructions | Exercise instructions, no outcome claims | Fine as instructions; have a clinician/PT sanity-check the wording before any real release. |

## Not medical

- The **70% "on track" line** (`GOOD_THRESHOLD_PCT` in `api/core/scoring.py`) is an arbitrary product threshold used for the outlook message, day streaks and goals. It is **not** a clinical threshold.
- The **posture score** is a transparent, explainable ratio (see `docs/api.md`), not a validated clinical measure.
- Disclaimer text shown in the UI: "Illustrative and educational only. Not medical advice. Talk to a clinician about pain or health concerns."

## Adding a claim

1. Write the claim here with its source (title, authors/organisation, year, link).
2. Quote or paraphrase only what the source supports; keep the wording qualitative unless the source gives a number.
3. Then, and only then, add it to the UI.
