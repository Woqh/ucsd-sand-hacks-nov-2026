"""The only health facts the Q&A may use. A Python MIRROR of web/src/evidence.ts and the "Sources
reviewed" table in docs/health-claims.md (S1-S4); a test keeps the URLs and numbers in step with the
web copy. No fact may be added here without a source in docs/health-claims.md."""
from __future__ import annotations

SOURCES = {
    "S1": ("Swain et al., J Biomech 2020", "https://pubmed.ncbi.nlm.nih.gov/31451200/"),
    "S2": ("Mahmoud et al., Curr Rev Musculoskelet Med 2019", "https://pmc.ncbi.nlm.nih.gov/articles/PMC6942109"),
    "S3": ("GBD 2021 low back pain, Lancet Rheumatol 2023", "https://pubmed.ncbi.nlm.nih.gov/37273833/"),
    "S4": ("GBD 2021 neck pain, Lancet Rheumatol 2024", "https://pubmed.ncbi.nlm.nih.gov/38383088/"),
}

FACTS = [
    "[S2] In adults, people with neck pain tend to show more forward-head posture. The studies are cross-sectional, so they can't show which causes which, and the link wasn't seen in adolescents.",
    "[S1] Many reviews find links between posture or long sitting and low back pain, and others find none. A review of 41 reviews found no consensus on whether these exposures cause back pain.",
    "No research was found linking sitting posture to arthritis, so no such claim is made.",
    "[S3] An estimated 619 million people lived with low back pain in 2020 (95% uncertainty interval 554-694 million), projected to reach 843 million by 2050 (759-933 million). This is population context, not an individual's risk, and does not isolate posture.",
    "[S4] An estimated 203 million people lived with neck pain in 2020 (95% uncertainty interval 163-253 million), with prevalence peaking between ages 45 and 74. This is population context, not an individual's risk.",
    "Research has not shown that slouching causes pain. Posture products must not claim it causes specific diseases or predict future illness.",
]
