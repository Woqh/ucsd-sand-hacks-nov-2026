# Geometry, confidence, and measurement validity

The geometric outputs are separate from the classifier. They are **2D image
projections**, in degrees, computed from MediaPipe image landmarks. They do not
use the estimator's world z coordinate. A class prediction can abstain while
some geometric measurements remain available, or vice versa. None of these
proxies is a clinical diagnosis, a calibrated 3D angle, or a physical distance.

## Coordinate preparation and camera calibration

Image landmarks have x normalized by frame width and y normalized by frame
height. Convert to pixel coordinates before taking angles:
`p = (x * width, y * height)`. Computing angles directly in normalized image
coordinates distorts them when the frame is not square. Image x increases to
the right, and y increases downward.

`camera_roll_deg` means the observed clockwise rotation of a truly upright
scene in the image. For angle r, apply `[[cos(r), sin(r)], [-sin(r), cos(r)]]`
to pixel column vectors before measuring. Translation to the image center is
included but does not affect angles. Obtain r from an external plumb line or
another calibrated vertical reference. A vertical line that tilts 10 degrees
toward image right has r = +10. A zero argument uses an upright-camera
assumption; the output warns about that assumption. **Never estimate camera
roll by forcing the observed torso upright**, because that removes posture.

The caller supplies `viewpoint`: `front`, `side`, `oblique`, `back`, or
`unknown`. These are camera-context assertions, not measured classifications.
Front means approximately frontal and side approximately sagittal; there is
no measured tolerance or viewpoint detector in this baseline. Oblique, back,
and unknown permit only the generic projected torso inclination. The input
image must be unmirrored when interpreting anatomical left/right; mirroring
the rendered preview after analysis is safe.

## Confidence and missingness

`measure_pose` accepts one combined score per landmark or two columns of
visibility and presence. A combined score means `min(visibility, presence)`;
it is not a calibrated probability of geometric accuracy. Both fields must
exist for the two-column score to be known. Coordinates must be finite,
inside the original image, and have known score at least 0.5. Unknown
confidence causes image geometry to abstain, even if coordinate values exist.

`quality.pose_confidence` is the arithmetic mean of the four combined scores
at left/right shoulder and left/right hip (11, 12, 23, 24). A missing or
nonfinite coordinate, or unknown score, contributes zero. Low scores remain
in the mean rather than being dropped. Offscreen predicted coordinates may
still have model confidence, so this aggregate alone is not a geometry
validity decision; offscreen points are rejected separately. Side-view
geometry can use a visible unilateral chain even when this four-point
aggregate is low. Classification applies its own quality and coverage gates.

Every measurement has `measurement_details` with `valid`, `reason`, `units`,
`space`, landmark names, sign, reference axis, proxy, and selected body side.
A non-estimable measurement is JSON `null`, never zero. Reasons distinguish
unsupported view, unknown facing, missing/nonfinite coordinates, offscreen
landmarks, unknown confidence, low confidence, and degenerate segments.
Segments shorter than two pixels are rejected. These engineering thresholds
are defaults, not empirically validated accuracy guarantees.

## Definitions

Let `S = midpoint(left_shoulder, right_shoulder)`,
`H = midpoint(left_hip, right_hip)`, and `E = midpoint(left_ear, right_ear)`.
For an upward-directed vector v define
`inclination(v) = atan2(v.x, -v.y) * 180/pi` in [-180, 180] degrees.
All axes below are roll-corrected image axes.

| Output | Landmarks and formula | Sign/reference | Validity |
|---|---|---|---|
| `torso_inclination_deg` | `inclination(S-H)` | Zero vertical; positive toward image right | All four torso points; in side view only, one valid ipsilateral shoulder/hip pair is a fallback, recorded in metadata |
| `sagittal_torso_inclination_deg` | Torso inclination times +1 if facing right, -1 if facing left | Positive anatomical forward, negative backward | Side view and supplied or conservatively inferred facing; torso must be valid |
| `neck_inclination_deg` | Front: `inclination(E-S)`; side: `inclination(ear-shoulder)` on one visible side | Zero vertical; positive toward image right, consistently with generic torso | Front needs both ears and shoulders; side needs an ipsilateral ear/shoulder pair; other views abstain |
| `hip_flexion_deg` | `180 - angle(shoulder-hip, knee-hip)` on one side | Unsigned: zero straight, increases as projected segments bend | Side view with a complete ipsilateral shoulder/hip/knee chain |
| `knee_flexion_deg` | `180 - angle(hip-knee, ankle-knee)` on one side | Unsigned: zero straight, increases as projected segments bend | Side view with a complete ipsilateral hip/knee/ankle chain |
| `shoulder_alignment_deg` | Bilateral shoulder line, endpoints sorted by image x: `atan2(-dy, dx)` | Zero horizontal; positive when image-right endpoint is higher | Front view, both shoulders, horizontal separation at least two pixels |
| `hip_alignment_deg` | Same line-slope formula for left/right hips | Zero horizontal; positive when image-right endpoint is higher | Front view, both hips, horizontal separation at least two pixels |
| `lateral_trunk_inclination_deg` | `inclination(S-H)` in frontal projection | Positive toward image right; this is not an anatomical-left sign | Front view and all four torso points; no unilateral fallback |

For the included joint angle, `angle(a,b) = acos(clamp(dot(a,b)/(|a||b|), -1, 1))`
in degrees. Each segment must be at least two pixels. If both left and right
chains are usable, choose the chain with the highest minimum confidence;
ties choose left. The neck proxy combines head position, neck orientation,
and shoulder location; it is not a cervical joint angle. The hip output is an
unsigned bend proxy: it does **not** distinguish hip flexion from extension.
The knee output similarly does not establish a clinical joint range of
motion. Do not interpret these proxy names beyond their formulas.

Facing is supplied as `left` or `right` in the roll-corrected image. A supplied
value wins. With `unknown`, inference is attempted only in a supplied side
view. It requires score >=0.8 for the nose, at least one ear, both heels, and
both foot-index points. Nose-minus-ear horizontal direction and both
toe-minus-heel directions must all agree and each exceed
`max(3 pixels, 0.06 * projected torso length)`. Otherwise facing remains
unknown and sagittal inclination is null. This is a conservative heuristic,
not a validated facing detector: turned heads, unusual foot placement,
crossed legs, occlusion, or depth errors can invalidate its assumptions.
Confirm camera-facing direction manually for controlled measurement.

## World-coordinate classifier normalization

`normalize_world` processes 33 x 3 estimator world landmarks, preserving x,
y, and z camera-related axes and the posture's relation to vertical. It
subtracts the midpoint of both hips and divides by the median of available,
nondegenerate left and right shoulder-to-hip lengths. It performs **no
pose-derived rotation, reflection, facing normalization, or depth calibration**.
This normalization removes translation and positive scale while retaining
inclination. Both hips and at least one torso length are required.

For a camera with known roll, call
`correct_world_camera_roll(world, camera_roll_deg)` **before** normalization.
The helper applies the same inverse rotation used for image measurements to
world x/y and leaves z unchanged. Positive roll has the same observed
clockwise-image convention described above. It returns a separate float64
array; zero roll is an unchanged copy. It uses only the supplied camera
calibration, never the observed body orientation. This optional correction
therefore does not conflict with `normalize_world` retaining posture tilt.
For example, explicitly removing 11 degrees of known camera roll from a
torso that leans 22 degrees preserves that 22-degree lean.

This operation assumes estimated world x/y approximately follow camera
x/y. Monocular world axes are model estimates, not a calibrated metric camera
frame, and their response to camera rotation is not guaranteed to be exactly
equivariant. Consequently this helper is an approximate feature correction,
not a validated gravity alignment or a source of physical angle accuracy.
Validate it with controlled recordings for the actual estimator and camera.
Use pixel geometry with the external vertical reference for the documented
measurement outputs. Dataset records have no camera-roll metadata and use an
upright-camera assumption; no per-record roll is inferred from posture.

The supplied dataset has world coordinates without confidence. Its finite
coordinates are available to the classifier (`mask=1`), but confidence remains
zero and `confidence_known=0`: coordinate availability does not imply visible
joints. At live inference, known low-confidence coordinates receive mask zero.
Invalid coordinates are filled with zero after normalization, accompanied by
mask zero. Unknown and known-zero confidence are distinguishable through
`confidence_known`. Failed normalization returns `valid=false` and a reason;
callers must not classify that record. No statistic is learned from the full
dataset during this deterministic per-record transform. Facing normalization
is deliberately absent from this frontal-data baseline; side-domain training
would require a separately validated anatomical convention.

## Observable limits and evaluation

A single side camera cannot reliably observe lateral movement toward/away
from its optical axis. Lateral trunk inclination and bilateral alignment are
therefore null in side view even if estimated depth suggests a value. The
classifier's `leaning_side` class does not overcome this observability limit.
An additional frontal camera, or an oblique camera with appropriate training
and validation, is needed for dependable four-way coverage.

Camera yaw, pitch, perspective, lens distortion, body rotation, loose
clothing, self-occlusion, and position within the frame affect these projected
angles. World coordinates from monocular pose estimation do not fix camera
calibration or produce calibrated physical measurements. Frontal and side
measurements should not be compared as if they were the same anatomical
plane. No angle error is reported without suitable synchronized ground-truth
angle annotations. The current dataset does not supply that ground truth.

The synthetic geometry tests cover translation/scale invariance, preservation
of torso tilt, pixel aspect correction, explicit camera-roll correction,
facing sign and consensus failures, view-dependent nulls, occluded unilateral
fallbacks, projected 90-degree joint bends, confidence/presence aggregation,
offscreen rejection, and JSON-safe no-person output. These verify formulas
and software behavior; they do not measure real-world angular accuracy.
