# Source and third-party notices

## MultiPosture data and derived feature cache

MultiPosture v1, DOI https://doi.org/10.5281/zenodo.14230872, by David Carneros Prado, Luis Cabañero Gómez, Jesús Fontecha, Ramon Hervas, Iván González Díaz and Esperanza Johnson. Dataset declared license: [Creative Commons Attribution 4.0](https://creativecommons.org/licenses/by/4.0/). The unchanged source file and metadata are in `data/raw/`; derived data in `data/prepared/` applies the documented hip-centering, torso scaling and four-class label mapping. No original images/videos are redistributed. Source checksum and changes are documented in the audit.

Associated study: D. Carneros-Prado et al., “A Comparison Between Multilayer Perceptrons and Kolmogorov-Arnold Networks for Multi-Task Classification in Sitting Posture Recognition,” IEEE Access 12 (2024), 180198–180209, DOI https://doi.org/10.1109/ACCESS.2024.3510034. This pipeline is a new baseline, not a reproduction of its reported results.

## Pose model and dependencies

MediaPipe source is [Apache 2.0](https://github.com/google-ai-edge/mediapipe/blob/master/LICENSE). The bundled frozen asset is Google's Pose Landmarker Heavy, float16, version 1, downloaded from:

https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_heavy/float16/1/pose_landmarker_heavy.task

SHA-256: `64437af838a65d18e5ba7a0d39b465540069bc8aae8308de3e318aad31fcbc7b`.

The official [model guide and model-card links](https://ai.google.dev/edge/mediapipe/solutions/vision/pose_landmarker) are the provenance for this asset. Do not assume a source-code license grants rights to every training dataset. Preserve applicable upstream notices and review asset terms for your intended redistribution/use.

PyTorch, NumPy, scikit-learn, OpenCV, MediaPipe and their dependencies retain their own licenses; installation packages contain their notices. The environment lock records versions used for this run. The optional RTMPose discussion references [MMPose's Apache 2.0 code license](https://github.com/open-mmlab/mmpose/blob/main/LICENSE), not an assertion about every third-party checkpoint.

The Google-hosted pose test JPEG used for integration timing is linked in the benchmark JSON and is not redistributed. It is an integration fixture, not training data or an accuracy benchmark.
