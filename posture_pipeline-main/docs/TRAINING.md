# Training, calibration and evaluation

`posture.learning` trains a compact anatomical-chain CNN and a shallow baseline
from the normalized cache produced by `posture.data`. It does not train or update
MediaPipe. Image or video capture is outside the supervised training dataset.

The four output classes are `upright`, `leaning_forward`, `leaning_back`, and
`leaning_side`; the last combines left and right lean. See the saved label mapping
and dataset audit for the source-label interpretation and its limits.

## Input and architecture

The input is `[batch, 4 chains, 6 channels, 5 landmarks]`. Each landmark has x, y,
z, confidence, coordinate-availability mask, and confidence-known flag. Coordinates
are world coordinates centered on the hip midpoint and divided by the valid torso
scale in the data preparation step. The learning module does not rotate poses or
perform any additional implicit geometric normalization.

The chains, in MediaPipe index order, are:

| Chain | Landmark indices |
| --- | --- |
| Left trunk and leg | 0, 11, 23, 25, 27 |
| Right trunk and leg | 0, 12, 24, 26, 28 |
| Left trunk and arm | 23, 11, 13, 15, 19 |
| Right trunk and arm | 24, 12, 14, 16, 20 |

Two shared Conv1d layers (6 to 24 to 32 channels, kernel 3, padding 1, ReLU)
operate independently on each five-point chain. Chain boundaries are never
adjacent convolution positions. Flattening preserves the chain identity and all
five positions before a 96-unit dense layer, ReLU, dropout and four logits.
These chains are an explicit skeleton sequence design; their index order is not
claimed to be a spatially uniform metric grid.

The source CSV supplies no visibility or presence values. Confidence and
confidence-known are therefore zero during training. Availability says only that
coordinates were finite and accepted by preprocessing. At live classification,
confidence channels must also be zero because the classifier has not learned
their relationship to the labels. Real detector confidence should independently
control inference quality/abstention; it must not be fabricated for this dataset.

## Separation and fitting

The split JSON lists row indices for four disjoint participant groups: training,
validation, calibration and test. The loader rejects overlap of both rows and
subjects, invalid labels, invalid samples, empty splits, and a training group
missing any canonical class. Never randomly split individual frames across
groups: adjacent frames from one participant can be strongly correlated.

Training uses seeded AdamW, class-balanced cross-entropy weights computed from
training labels only, and early stopping on validation macro-F1 across all four
classes. Default settings are 80 maximum epochs, batch size 128, learning rate
0.001, weight decay 0.0001, patience 12 and improvement threshold 0.0001. The best
validation state is restored before calibration. Validation and test metrics are
unweighted by the training loss weights.

Augmentation is limited to uniform per-sample scale jitter of ±3% and 2% random
non-torso landmark dropout. Dropout is consistent for a landmark occurring in
several chains, clears every feature channel at that landmark, and preserves
shoulders and hips. There are no label-changing rotations or reflections.
Synthetic missing-joint augmentation is not evidence of accuracy under real
occlusion. Set `scale_jitter` and/or `joint_dropout` to zero to disable them;
record any such choice before examining the test results.

The baseline is `StandardScaler` followed by multinomial `LogisticRegression`
with C=1, at most 3,000 iterations, and the same class-weighting setting. Both
scaler and classifier are fitted exclusively on the flattened training features.
This provides a reproducible comparison for whether the CNN improves on a simple
linear decision rule using the same input information.

After all model selection, a scalar positive temperature is fitted separately
for each classifier using the calibration subjects. Bounded optimization minimizes
unweighted negative log-likelihood over temperatures from 0.05 to 20. The original
temperature of 1 is retained if optimization fails or increases calibration NLL.
Calibration cannot change the argmax class or improve its accuracy; it adjusts
probabilities and threshold behavior. It does not guarantee good calibration
outside the source distribution or on every subject. A small calibration group
can give an unstable fitted temperature.

Random number generators are seeded. PyTorch deterministic behavior is requested
with warnings for unsupported operations, so identical results are not promised
across hardware or software versions. Resolved configuration, split participants,
data/split SHA-256 values, and the selected epoch are saved with the checkpoint.

## Python interface and artifacts

```python
from posture.learning import train, evaluate, load_model

summary = train("data/cache.npz", "data/split.json", "configs/train.json", "models")
report = evaluate("data/cache.npz", "data/split.json", "models/best_model.pt", "reports")
model, checkpoint = load_model("models/best_model.pt", device="cpu")
```

Paths are interpreted from the caller's working directory. Use the actual cache
and split paths produced by the preparation command. The config JSON is a partial
or complete dictionary of `DEFAULT_CONFIG` keys in `learning.py`; unknown keys
raise an error. `device` supports `cpu`, `cuda`, or `auto`. The root configuration
selects CPU for reproducibility on the available host.

Training saves:

- `best_model.pt`: best validation state, fitted temperature, canonical labels,
  resolved configuration, provenance, supported-view metadata and preprocessing
  version. Loading uses `torch.load(..., weights_only=True)`.
- `baseline.joblib`: fitted scaler/classifier plus temperature and provenance.
  Joblib uses pickle: load only artifacts you produced or otherwise trust.
- `training_history.json`: epoch training loss and validation accuracy/F1/NLL.
- `calibration.json`: calibration subjects and NLL, summed multiclass Brier score,
  ECE and reliability bins before and after temperature fitting for both models.
- `train_summary.json`: counts, class weights, participants, model size, selected
  epoch, elapsed fit time and resolved configuration.

Evaluation saves `evaluation_test.json` and `confusion_matrix_test.csv` (or the
requested split name). It requires the exact data and split hashes used during
training. It reads the trusted sibling `baseline.joblib` when available and
performs no fitting. Evaluation of train/validation/calibration is also supported,
but only the test split is marked as held-out test evaluation.

## Interpreting the report

The report includes overall accuracy, macro-F1, weighted F1, balanced accuracy
over classes present, all four classes' precision/recall/F1/support, confusion
matrix, participant-level results, and calibrated-probability coverage versus
accepted-sample accuracy. CNN and baseline results use identical rows. The
confusion matrix uses true labels on rows and predicted labels on columns.
An absent class receives zero F1 in the four-class macro average; inspect support,
particularly in participant-level summaries.

NLL, multiclass Brier score and equal-width maximum-probability ECE are reported
before and after calibration on both calibration and evaluation data. Brier is
the mean sum over four classes (range 0–2). ECE is the sample-weighted absolute
difference between mean confidence and accuracy in each bin. Ten bins is the
default. Calibration-set values are fit diagnostics; test values assess transfer
to held-out participants. ECE depends on binning and sample size.

Coverage uses only maximum calibrated class probability. It does not simulate
MediaPipe confidence gating because the CSV contains no detector confidence.
Thresholds should be chosen using validation/calibration and operational needs,
not tuned after looking at held-out test labels. With few held-out subjects and
correlated frames, these metrics do not establish population-wide performance;
subject-level cross-validation or a larger independent study is needed for that.

The source lacks row-level viewpoint/occlusion labels and ground-truth angles.
The report therefore explicitly marks viewpoint-stratified, occlusion-stratified,
and angle-error evaluation as unsupported. The checkpoint's `supported_viewpoints`
is `['front']`, reflecting the approximately frontal source setup rather than
independent proof of camera/viewpoint generalization. Side/oblique inputs require
a separately validated model or conservative abstention. A single side image
cannot recover every coronal, sagittal and axial posture component.

Classifier latency is measured at batch size one after warmup. CPU thread count,
Python/library versions and hardware are recorded; CUDA execution is synchronized
when used. Mean, median and 95th percentile are provided. CNN timing excludes
feature preparation, transfer, softmax, camera capture, MediaPipe, normalization,
smoothing and rendering. Baseline timing includes its fitted scaler and linear
decision function. These numbers must not be presented as camera-to-result FPS
or as an end-to-end real-time guarantee.
