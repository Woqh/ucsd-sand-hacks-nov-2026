# MultiPosture dataset audit

Audited 2026-11-14 against the exact user-provided file, downloaded record metadata, and the accompanying primary research paper. This dataset supports the requested four labels, but its acquisition protocol is predominantly frontal. It cannot establish side-view deployment accuracy.

## Identity, licensing, and files

- Dataset: **MultiPosture**, Zenodo record **14230872**, DOI **10.5281/zenodo.14230872**. [Dataset record](https://zenodo.org/records/14230872)
- Exact file: [data.csv](https://zenodo.org/records/14230872/files/data.csv?download=1).
- Record metadata explicitly contains `metadata.license.id = "cc-by-4.0"`; the dataset therefore declares **Creative Commons Attribution 4.0**. This was checked independently of the paper's license using the downloaded [Zenodo API metadata](https://zenodo.org/api/records/14230872). Preserve attribution to the creators and the DOI when sharing this dataset or derivatives.
- Creators: David Carneros Prado, Luis Cabañero Gómez, Jesús Fontecha, Ramón Hervás, Iván González Díaz, and Esperanza Johnson. Publication date: 2024-11-27.
- The release is a single CSV, not a directory of images. Raw images/videos are not included; the record explains the privacy restriction. Re-running pose extraction on the original recordings is consequently unavailable from this release. [Dataset record](https://zenodo.org/records/14230872)
- File size: **9,327,935 bytes**. MD5: `7efbc94d653acf32eefecec3ff26d6c6`, matching the record. SHA-256: `d21579200db9a57dd01c24fa6ece961b0be73aa0d5d402ae8e629761c03ebe38`.

## What the paper verifies

The study recruited 13 participants. A Reolink RLC-510A camera faced seated participants from 1–2 m, with slight lateral placement adjustments. Frames from videos were resized to 640 × 480. The extractor was MediaPipe Pose Heavy; the selected output was **World Landmarks**, described in meters relative to the hip midpoint. Labels were manually reviewed. The paper describes StandardScaler preprocessing and reduction to 11 joints, but does not give an unambiguous ordered list of those joints. Its evaluation used leave-one-subject-out validation. [Paper, sections III-A and III-B](https://brage.inn.no/inn-xmlui/bitstream/handle/11250/3197493/A_Comparison_Between_Multilayer_Perceptrons_and_Kolmogorov-Arnold_Networks_for_Multi-Task_Classification_in_Sitting_Posture_Recognition.pdf?sequence=1)

## Direct inspection of the downloaded CSV

These are measurements from the file itself, not estimates from the description:

| Item | Observed value |
|---|---|
| Data rows | **4,794** |
| Columns | **102** |
| Metadata columns | `subject`, `upperbody_label`, `lowerbody_label` |
| Coordinate columns | **99 = 33 landmarks × x/y/z** |
| Subjects | Integers 1 through 13 |
| Empty coordinate cells | 0 |
| NaN/infinite coordinate cells | 0 |
| Exact duplicate coordinate vectors | 0 |
| Coordinate range over all axes/joints | −0.8279072046 to +0.8656035662 |
| Maximum absolute hip-midpoint coordinate | 0.0060640816 |

**Two release-description discrepancies matter:** the record says 4,800 frames and 11 joints/33 dimensions; the actual release has 4,794 rows and all 33 joints/99 dimensions. The row deficit's cause is not documented. Do not silently manufacture six rows or discard 22 joints to match the prose. The small nonzero hip midpoint is why this pipeline recenters the stored landmarks explicitly.

Each landmark has three consecutive columns in `x,y,z` order. The names are self-describing and appear in this order:

```text
0 nose
1 left_eye_inner       2 left_eye          3 left_eye_outer
4 right_eye_inner      5 right_eye         6 right_eye_outer
7 left_ear             8 right_ear
9 mouth_left          10 mouth_right
11 left_shoulder      12 right_shoulder
13 left_elbow         14 right_elbow
15 left_wrist         16 right_wrist
17 left_pinky         18 right_pinky
19 left_index         20 right_index
21 left_thumb         22 right_thumb
23 left_hip           24 right_hip
25 left_knee          26 right_knee
27 left_ankle         28 right_ankle
29 left_heel          30 right_heel
31 left_foot_index    32 right_foot_index
```

The CSV has **no image-space coordinates, visibility/presence/confidence scores, missing-joint annotations, session/video IDs, frame IDs, timestamps, camera calibration, per-row viewpoint, occlusion annotations, or measured joint-angle ground truth**. Finite coordinates indicate an available estimate; they do not prove that a joint was visible or accurately localized.

## Exact label mapping

Use the upper-body label alone as the classification target. Lower-body labels remain metadata and must not be input features or substitutes for trunk labels. The meanings below follow the dataset's label definitions; counts come from the CSV. [Dataset label definitions](https://zenodo.org/records/14230872)

| Source label | Dataset meaning | Project category | Rows |
|---|---|---|---:|
| TUP | Upright trunk | `upright` | 1,615 |
| TLF | Trunk leaning forward | `leaning_forward` | 1,897 |
| TLB | Trunk leaning backward | `leaning_back` | 442 |
| TLR | Trunk leaning right | `leaning_side` | 420 |
| TLL | Trunk leaning left | `leaning_side` | 420 |

The resulting four-class counts are 1,615 / 1,897 / 442 / 840 in the order upright, forward, back, side. There is no absent requested class. Numeric angle thresholds and borderline-label adjudication rules are not supplied. This project does not invent them or reinterpret upright as a clinical judgment.

Forward/backward refer to the person's anatomical anterior/posterior direction, not image left/right. Left and right lateral trunk lean are merged. A camera-side or face-direction cue must be explicitly available before signing projected sagittal measurements; the dataset cannot verify per-row facing inference from images.

For completeness, lower-body label counts are: `LAP` 1,153, `LWA` 1,030, `LCS` 631, `LCR` 571, `LCL` 609, `LLR` 419, `LLL` 381. These correspond to apart, wide apart, closed, right-over-left crossed, left-over-right crossed, lateral right, and lateral left legs.

## Subjects and leakage controls

| Subject | Rows | TUP | TLF | TLB | TLL + TLR |
|---:|---:|---:|---:|---:|---:|
| 1 | 540 | 203 | 163 | 54 | 120 |
| 2 | 450 | 236 | 142 | 12 | 60 |
| 3 | 480 | 169 | 240 | 11 | 60 |
| 4 | 480 | 168 | 205 | 47 | 60 |
| 5 | 444 | 141 | 243 | 0 | 60 |
| 6 | 480 | 131 | 279 | 10 | 60 |
| 7 | 300 | 50 | 144 | 46 | 60 |
| 8 | 270 | 61 | 148 | 1 | 60 |
| 9 | 270 | 107 | 62 | 41 | 60 |
| 10 | 270 | 95 | 38 | 77 | 60 |
| 11 | 270 | 108 | 94 | 8 | 60 |
| 12 | 270 | 91 | 60 | 59 | 60 |
| 13 | 270 | 55 | 79 | 76 | 60 |

Split whole subjects, never random rows. Keeping each subject in only one partition also keeps all recordings attributed to that subject together. Independent verification of recording boundaries is impossible because video/session identifiers are absent. Subject 5 has no backward examples and subject 8 has only one: per-person metrics must disclose class support.

Train-derived standardization, class weights, augmentation choices, and model fitting use training subjects only. Validation subjects govern checkpoint choice and probability calibration. Keep test subjects untouched until evaluation. A single subject holdout is an initial baseline, not the paper's full LOSO protocol. Report the exact subject lists in every saved run.

Row order does not establish time continuity. There is no defensible temporal-CNN training sequence in this release; runtime smoothing is permissible as a separate configurable inference behavior.

## Coordinate semantics and preprocessing policy

MediaPipe distinguishes image-normalized landmarks from estimated three-dimensional world landmarks; the latter have a hip-center origin and meter units in its API convention. Both are model outputs. [MediaPipe Pose Landmarker documentation](https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker?tab=Python)

Treat the CSV as estimated world-landmark input. Do not reinterpret these numbers as normalized image pixels, calibrated motion capture, or direct physical distance measurements. The CSV's signed, sub-meter ranges and near-zero hip midpoint are consistent with that interpretation, but do not establish the exact original MediaPipe version or undocumented export transformations. In particular, the paper's mention of StandardScaler does not prove that the released CSV was already standardized; this project applies its own documented preprocessing and does not reuse any unknown fitted statistics.

The cache preserves all 33 named landmarks. The CNN uses explicitly defined anatomical chains covering 15 distinct landmarks; this is a project representation, **not a claimed reconstruction of the paper's ambiguous 11-joint subset**. Hip centering and robust body-scale normalization are per-frame operations. Global posture rotation is not removed, so the vertical inclination signal remains present. Keep image-space and world-space features in separate fields at inference.

CSV training confidence is unknown. Never label fabricated confidence=1 as an observed detector score. A finite-coordinate mask and a separate confidence-known indicator can encode availability honestly. Synthetic masking can test robustness but cannot stand in for measured real occlusion performance.

## What this release cannot validate

The acquisition protocol does not supply side-view test labels. A classifier trained here may exploit frontal-view depth patterns that do not transfer to a side camera. Four-class test metrics on held-out subjects are consequently **frontal-protocol classification results**, not evidence of reliable side-view recognition. A purely side-on projection can hide lateral trunk motion toward/away from the camera; model-estimated depth cannot remove this observational ambiguity.

Viewpoint-specific and occlusion-specific subgroup metrics, detector-confidence calibration, measured angle error, and original-image pose-extraction latency are unavailable from this CSV. Mark them unavailable rather than inferring hidden labels or borrowing the paper's results. Live runtime can be measured separately on actual hardware. Camera roll and anatomical facing require explicit runtime assumptions or calibration.

Before enabling validated side-view deployment, collect an independently labeled set with subject, recording/session, frame/time, view/azimuth, occlusion, facing, and camera-roll metadata. Include upright versus left/right lateral leaning at genuine side angles, and independently measured angles if angle accuracy is a requirement. Reserve whole subjects and recordings for testing. An oblique or additional camera can supply lateral evidence; quantify that benefit on collected footage.

## Attribution

Dataset: Carneros Prado, D.; Cabañero Gómez, L.; Fontecha, J.; Hervas, R.; González Díaz, I.; Johnson, E. **MultiPosture**. Zenodo, 2024. [doi:10.5281/zenodo.14230872](https://doi.org/10.5281/zenodo.14230872).

Study: Carneros-Prado et al. **A Comparison Between Multilayer Perceptrons and Kolmogorov-Arnold Networks for Multi-Task Classification in Sitting Posture Recognition**. IEEE Access 12, 180198–180209, 2024. [doi:10.1109/ACCESS.2024.3510034](https://doi.org/10.1109/ACCESS.2024.3510034).
