// What the research does and doesn't say about slouching and pain. This is a MIRROR of the
// "Sources reviewed" table in docs/health-claims.md (S1-S4): change both together, and add a source
// there before adding any claim here. No statistic in this file may lack a source.

export type EvidenceLevel = 'none' | 'mixed' | 'associated' | 'causal'

/** Steps of the evidence meter, weakest to strongest. `none` fills no segments. */
export const LEVEL_STEPS: { key: Exclude<EvidenceLevel, 'none'>; label: string }[] = [
  { key: 'mixed', label: 'Mixed' },
  { key: 'associated', label: 'Associated' },
  { key: 'causal', label: 'Cause shown' },
]

export const LEVEL_LABEL: Record<EvidenceLevel, string> = {
  none: 'No evidence found',
  mixed: 'Mixed, no consensus on cause',
  associated: 'Associated, cause not established',
  causal: 'Cause shown',
}

export interface Source {
  label: string
  url: string
}

export interface EvidenceItem {
  outcome: string
  level: EvidenceLevel
  summary: string
  sources: Source[]
}

const S1: Source = { label: 'Swain et al., J Biomech 2020', url: 'https://pubmed.ncbi.nlm.nih.gov/31451200/' }
const S2: Source = { label: 'Mahmoud et al., Curr Rev Musculoskelet Med 2019', url: 'https://pmc.ncbi.nlm.nih.gov/articles/PMC6942109' }
const S3: Source = { label: 'GBD 2021 low back pain, Lancet Rheumatol 2023', url: 'https://pubmed.ncbi.nlm.nih.gov/37273833/' }
const S4: Source = { label: 'GBD 2021 neck pain, Lancet Rheumatol 2024', url: 'https://pubmed.ncbi.nlm.nih.gov/38383088/' }

export const EVIDENCE: EvidenceItem[] = [
  {
    outcome: 'Neck pain',
    level: 'associated',
    summary:
      'In adults, people with neck pain tend to show more forward-head posture. The studies are cross-sectional, so they can’t show which causes which, and the link wasn’t seen in adolescents.',
    sources: [S2],
  },
  {
    outcome: 'Low back pain',
    level: 'mixed',
    summary:
      'Many reviews find links between posture or long sitting and back pain, and others find none. A review of 41 reviews found no consensus on whether these exposures cause back pain.',
    sources: [S1],
  },
  {
    outcome: 'Arthritis',
    level: 'none',
    summary: 'We found no research linking sitting posture to arthritis, so Sitwise doesn’t make that claim.',
    sources: [],
  },
]

// Population burden (Global Burden of Disease 2021). Describes how common these problems are; it says
// nothing about any individual's risk and doesn't isolate posture.
export const POPULATION = {
  lowBack: {
    now: '619 million',
    nowRange: '554–694 million',
    projected: '843 million by 2050 (95% uncertainty interval 759–933 million)',
    source: S3,
  },
  neck: {
    now: '203 million',
    nowRange: '163–253 million',
    peakAges: '45 and 74',
    source: S4,
  },
  toolUrl: 'https://vizhub.healthdata.org/gbd-results/',
}
