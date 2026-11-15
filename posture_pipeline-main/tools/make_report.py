"""Render the saved evaluation; never train, recalibrate, or tune on test rows."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def _pct(value):
    return f"{100 * value:.2f}%"


def _table(headers, rows):
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    lines.extend("| " + " | ".join(map(str, row)) + " |" for row in rows)
    return "\n".join(lines)


def render_plot(evaluation, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.ticker as ticker
    import numpy as np

    cnn, before = evaluation["cnn"], evaluation["cnn_before_calibration"]
    blue, orange, gray = "#176995", "#c76926", "#64748b"
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10.5, "axes.titlesize": 13, "axes.labelsize": 10.5, "axes.spines.top": False, "axes.spines.right": False, "figure.facecolor": "#f6f8fb", "savefig.facecolor": "#f6f8fb", "axes.facecolor": "white"})
    fig, axes = plt.subplots(2, 2, figsize=(14, 10.3))
    fig.subplots_adjust(left=0.08, right=0.965, bottom=0.165, top=0.855, hspace=0.49, wspace=0.29)
    fig.suptitle("MultiPosture | Held-out subject evaluation", fontsize=21, fontweight="bold", x=0.08, y=0.965, ha="left", color="#142638")
    fig.text(0.08, 0.922, f"{cnn['n']:,} recorded poses · {len(evaluation['subjects'])} held-out participants (IDs {', '.join(evaluation['subjects'])}) · approximately frontal source view", fontsize=11.5, color="#4b5e70")
    fig.text(0.08, 0.888, f"CNN accuracy {_pct(cnn['accuracy'])} · macro-F1 {cnn['macro_f1_all_four_classes']:.3f}    |    Linear baseline accuracy {_pct(evaluation['logistic_regression']['accuracy'])}", fontsize=11.5, color="#142638")

    ax = axes[0, 0]
    matrix = np.array(cnn["confusion_matrix_true_rows_predicted_columns"])
    fraction = matrix / matrix.sum(axis=1, keepdims=True)
    ax.imshow(fraction, cmap="Blues", vmin=0, vmax=1, aspect="auto")
    short = ["Upright", "Forward", "Back", "Side"]
    ax.set(xticks=range(4), yticks=range(4), xticklabels=short, yticklabels=short, xlabel="Predicted class", ylabel="True class")
    ax.set_title("A  CNN confusion matrix", loc="left", pad=12, fontweight="bold")
    for i in range(4):
        for j in range(4):
            ax.text(j, i, f"{matrix[i, j]}\n{fraction[i, j]:.1%}", ha="center", va="center", color="white" if fraction[i, j] > 0.6 else "#183c56", fontsize=11)
    ax.text(0, -0.22, "Counts and row percentages; all four classes shown.", transform=ax.transAxes, fontsize=9, color=gray)

    ax = axes[0, 1]
    ax.plot([0.45, 1], [0.45, 1], color="#b3bec9", lw=1, linestyle=":", label="Perfect calibration")
    for values, color, marker, label in [(before, gray, "s", "Before temperature"), (cnn, blue, "o", "After temperature")]:
        bins = [b for b in values["reliability_bins"] if b["count"]]
        ax.plot([b["mean_confidence"] for b in bins], [b["accuracy"] for b in bins], color=color, marker=marker, markersize=5, lw=1.7, label=label)
    ax.set(xlim=(0.45, 1.02), ylim=(-0.04, 1.06), xlabel="Mean predicted confidence per bin", ylabel="Observed accuracy per bin")
    ax.set_title("B  CNN reliability on held-out subjects", loc="left", pad=12, fontweight="bold")
    ax.grid(alpha=0.18)
    ax.legend(loc="lower right", fontsize=8.3, frameon=True)
    calibration_note = "Both worsened after calibration" if cnn['nll'] > before['nll'] and cnn['ece'] > before['ece'] else "Lower values indicate better calibration"
    ax.text(0.02, 0.97, f"Test NLL: {before['nll']:.4f} → {cnn['nll']:.4f}\nTest ECE: {before['ece']:.4f} → {cnn['ece']:.4f}\n{calibration_note}", transform=ax.transAxes, ha="left", va="top", fontsize=9.1, color="#8d3f19", bbox={"boxstyle": "round,pad=0.45", "facecolor": "#fff4e8", "edgecolor": "#f2dfc9"})
    ax.text(0, -0.22, "10 equal-width bins; low-count bins can be unstable.", transform=ax.transAxes, fontsize=9, color=gray)

    ax = axes[1, 0]
    for key, color, label in [("cnn", blue, "CNN"), ("logistic_regression", orange, "Linear baseline")]:
        rows = evaluation[key + "_probability_threshold_coverage"]
        ax.plot([r["coverage"] for r in rows], [r["accuracy_when_accepted"] for r in rows], marker="o", color=color, lw=2, label=label)
        for threshold in (0.6, 0.9):
            row = next((r for r in rows if abs(r["probability_threshold"] - threshold) < 1e-9), None)
            if row is None or row["accuracy_when_accepted"] is None:
                continue
            offset = (-7, 8) if key == "cnn" else (7, -14)
            ax.annotate(f"t={threshold}", (row["coverage"], row["accuracy_when_accepted"]), xytext=offset, textcoords="offset points", color=color, fontsize=9, ha="right" if key == "cnn" else "left")
    ax.set(xlim=(0.62, 1.015), ylim=(0.8, 1.01), xlabel="Coverage: fraction of samples retained", ylabel="Accuracy among retained samples")
    ax.set_title("C  Probability threshold trade-off", loc="left", pad=12, fontweight="bold")
    ax.xaxis.set_major_formatter(ticker.PercentFormatter(xmax=1, decimals=0))
    ax.yaxis.set_major_formatter(ticker.PercentFormatter(xmax=1, decimals=0))
    ax.grid(alpha=0.18)
    ax.legend(loc="upper left", fontsize=9)
    ax.text(0, -0.23, "Classifier probability only; detector-quality gating is unmeasured.", transform=ax.transAxes, fontsize=9, color=gray)

    ax = axes[1, 1]
    subjects = evaluation["subjects"]
    x = np.arange(len(subjects))
    for key, color, label, offset in [("cnn", blue, "CNN", -0.17), ("logistic_regression", orange, "Linear baseline", 0.17)]:
        values = [evaluation[key + "_per_subject"][subject]["macro_f1_all_four_classes"] for subject in subjects]
        bars = ax.bar(x + offset, values, width=0.3, color=color, label=label, zorder=3)
        ax.bar_label(bars, labels=[f"{v:.3f}" for v in values], padding=5, fontsize=10)
    ax.set(xticks=x, xticklabels=[f"Participant {s}\nn={evaluation['cnn_per_subject'][s]['n']}" for s in subjects], ylim=(0, 1.1), ylabel="Macro-F1 across all four classes")
    ax.set_title("D  Performance differs by participant", loc="left", pad=12, fontweight="bold")
    ax.grid(axis="y", alpha=0.18, zorder=0)
    ax.legend(loc="lower right", fontsize=9)
    ax.text(0, -0.23, "Only two held-out people; no population-level conclusion.", transform=ax.transAxes, fontsize=9, color=gray)
    fig.text(0.08, 0.035, "One fixed participant split. Temperature was fitted on separate calibration subjects; test results were not used to retune it.\nNo side-view/occlusion annotations or angle ground truth. Classifier latency is reported separately from camera and pose extraction.", fontsize=9.3, color="#4b5e70", linespacing=1.6)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=180)
    plt.close(fig)


def render_markdown(evaluation, training, output, plot):
    cnn, baseline = evaluation["cnn"], evaluation["logistic_regression"]
    before = evaluation["cnn_before_calibration"]
    cal = training["calibration"]
    metric_rows = []
    for title, key in [("Accuracy", "accuracy"), ("Balanced accuracy", "balanced_accuracy_present_classes"), ("Macro-F1, four classes", "macro_f1_all_four_classes"), ("Weighted F1", "weighted_f1"), ("NLL after temperature (lower is better)", "nll"), ("Brier after temperature (lower is better)", "brier_multiclass_sum"), ("ECE after temperature (lower is better)", "ece")]:
        metric_rows.append([title, f"{cnn[key]:.5f}", f"{baseline[key]:.5f}"])
    classification = _table(["Held-out metric", "CNN", "StandardScaler + logistic regression"], metric_rows)
    class_rows = []
    for label in evaluation["labels"]:
        c, b = cnn["per_class"][label], baseline["per_class"][label]
        class_rows.append([label, c["support"], *[f"{c[key]:.4f}" for key in ("precision", "recall", "f1")], *[f"{b[key]:.4f}" for key in ("precision", "recall", "f1")]])
    per_class = _table(["Class", "Support", "CNN P", "CNN R", "CNN F1", "Baseline P", "Baseline R", "Baseline F1"], class_rows)
    confusion_tables = []
    for title, result in [("CNN", cnn), ("Logistic regression", baseline)]:
        rows = [[name, *row] for name, row in zip(evaluation["labels"], result["confusion_matrix_true_rows_predicted_columns"])]
        confusion_tables.append(f"### {title}\n\n" + _table(["True / predicted", "Upright", "Forward", "Back", "Side"], rows))
    person_rows = []
    for subject in evaluation["subjects"]:
        for key, name in [("cnn", "CNN"), ("logistic_regression", "Baseline")]:
            row = evaluation[key + "_per_subject"][subject]
            person_rows.append([subject, name, row["n"], _pct(row["accuracy"]), *[f"{row[k]:.4f}" for k in ("macro_f1_all_four_classes", "nll", "brier_multiclass_sum", "ece")]])
    per_person = _table(["Participant", "Model", "Rows", "Accuracy", "Macro-F1", "NLL", "Brier", "ECE"], person_rows)
    calibration_rows = []
    for split, models in [("Calibration fit", {"cnn": cal["cnn"], "logistic_regression": cal["logistic_regression"]}), ("Held-out test", {"cnn": {"before": before, "after": cnn}, "logistic_regression": {"before": evaluation["logistic_regression_before_calibration"], "after": baseline}})]:
        for key, name in [("cnn", "CNN"), ("logistic_regression", "Baseline")]:
            values = models[key]
            calibration_rows.append([split, name, *[f"{values[stage][metric]:.5f}" for metric in ("nll", "brier_multiclass_sum", "ece") for stage in ("before", "after")]])
    calibration_table = _table(["Data", "Model", "NLL before", "NLL after", "Brier before", "Brier after", "ECE before", "ECE after"], calibration_rows)
    coverage_rows = []
    for c, b in zip(evaluation["cnn_probability_threshold_coverage"], evaluation["logistic_regression_probability_threshold_coverage"]):
        coverage_rows.append([f"{c['probability_threshold']:.1f}", c["accepted"], _pct(c["coverage"]), _pct(c["accuracy_when_accepted"]) if c["accuracy_when_accepted"] is not None else "—", b["accepted"], _pct(b["coverage"]), _pct(b["accuracy_when_accepted"]) if b["accuracy_when_accepted"] is not None else "—"])
    coverage_table = _table(["Probability threshold", "CNN kept", "CNN coverage", "CNN accuracy kept", "Baseline kept", "Baseline coverage", "Baseline accuracy kept"], coverage_rows)
    latency = evaluation["latency"]
    latency_rows = []
    for key, name in [("cnn", "CNN forward pass"), ("logistic_regression_including_standard_scaler", "Baseline scaler + decision function")]:
        values = latency[key]
        latency_rows.append([name, f"{values['mean_ms']:.4f}", f"{values['p50_ms']:.4f}", f"{values['p95_ms']:.4f}", values["repeats"]])
    latency_table = _table(["Operation", "Mean ms", "Median ms", "95th percentile ms", "Timed calls"], latency_rows)
    hardware = latency["hardware"]
    hardware_table = _table(["Recorded environment", "Value"], [[name, hardware[key]] for name, key in [("Operating system", "platform"), ("Processor identifier", "processor"), ("Architecture", "machine"), ("Device", "device"), ("PyTorch CPU threads", "torch_cpu_threads"), ("Python", "python"), ("PyTorch", "torch"), ("NumPy", "numpy"), ("scikit-learn", "sklearn")]])
    split_rows = [[name, training["split_counts"][name], ", ".join(training["split_subjects"][name])] for name in ("train", "val", "calibration", "test")]
    split_table = _table(["Split", "Rows", "Participant IDs"], split_rows)
    plot_link = os.path.relpath(plot, output.parent).replace(os.sep, "/")
    run_link = os.path.relpath(plot.parent, output.parent).replace(os.sep, "/")
    metrics_to_compare = ("nll", "brier_multiclass_sum", "ece")
    worsened = all(cnn[k] > before[k] for k in metrics_to_compare)
    calibration_summary = "Temperature scaling did not transfer reliably to the test subjects." if worsened else "Calibration transfer must be assessed on the held-out subjects."
    cal_fit_improved = all(cal["cnn"]["after"][k] < cal["cnn"]["before"][k] for k in metrics_to_compare)
    fit_note = "although all three calibration-fit metrics improved" if cal_fit_improved else "with calibration-fit results shown separately below"
    lowest_class = min(evaluation["labels"], key=lambda label: cnn["per_class"][label]["recall"])
    lowest_index = evaluation["labels"].index(lowest_class)
    low_row = cnn["confusion_matrix_true_rows_predicted_columns"][lowest_index]
    error_details = ", ".join(f"{low_row[i]} classified as `{evaluation['labels'][i]}`" for i in sorted(range(4), key=lambda i: low_row[i], reverse=True) if i != lowest_index and low_row[i])
    confusion_summary = f"The lowest CNN recall is `{lowest_class}`: {low_row[lowest_index]} of {sum(low_row)} examples are correct, with {error_details}."
    side_index = evaluation["labels"].index("leaning_side")
    upright_index = evaluation["labels"].index("upright")
    side_baseline = baseline["confusion_matrix_true_rows_predicted_columns"][side_index]
    side_baseline_errors = ", ".join(f"{side_baseline[i]} as `{evaluation['labels'][i]}`" for i in sorted(range(4), key=lambda i: side_baseline[i], reverse=True) if i != side_index and side_baseline[i])
    up_to_side = cnn["confusion_matrix_true_rows_predicted_columns"][upright_index][side_index]
    side_to_up = cnn["confusion_matrix_true_rows_predicted_columns"][side_index][upright_index]
    person_f1 = [r["macro_f1_all_four_classes"] for r in evaluation["cnn_per_subject"].values()]
    person_counts = ", ".join(f"participant {s}: {evaluation['cnn_per_subject'][s]['n']} rows" for s in evaluation["subjects"])
    threshold_examples = []
    for row in evaluation["cnn_probability_threshold_coverage"]:
        if row["probability_threshold"] in (0.6, 0.9) and row["accuracy_when_accepted"] is not None:
            threshold_examples.append(f"threshold {row['probability_threshold']:.1f}: {row['accepted']}/{row['total']} rows retained ({_pct(row['coverage'])}) at {_pct(row['accuracy_when_accepted'])} accepted-sample accuracy")
    threshold_summary = "; ".join(threshold_examples)
    temperature_action = "sharpens" if evaluation["temperature"] < 1 else "softens"
    baseline_improved = all(baseline[k] < evaluation["logistic_regression_before_calibration"][k] for k in metrics_to_compare)
    baseline_calibration_note = "The baseline's fitted temperature improves all three test probability metrics on this split." if baseline_improved else "The baseline's before/after metrics should also be assessed individually."
    text = f"""# Observed results on MultiPosture

The CNN achieved **{_pct(cnn['accuracy'])} accuracy and {cnn['macro_f1_all_four_classes']:.4f} macro-F1** on {cnn['n']} rows from two held-out participants. The baseline achieved {_pct(baseline['accuracy'])} and {baseline['macro_f1_all_four_classes']:.4f}. These are results from one participant split in the approximately frontal acquisition domain, not side-camera validation or a clinical assessment.

**{calibration_summary}** CNN test NLL changed from {before['nll']:.4f} to {cnn['nll']:.4f}, Brier from {before['brier_multiclass_sum']:.4f} to {cnn['brier_multiclass_sum']:.4f}, and ECE from {before['ece']:.5f} to {cnn['ece']:.5f}, {fit_note}. The original fitted temperature is retained; test results were not used to recalibrate, select a different checkpoint, or choose a threshold.

![Evaluation overview]({plot_link})

## Protocol and provenance

The exact downloaded CSV contained 4,794 rows and 13 participants. Participant groups are disjoint. Normalization is deterministic per pose; the baseline scaler is fit on training rows only. Validation selects the CNN epoch, separate calibration subjects fit one scalar temperature per model, and test subjects are evaluated after fitting.

{split_table}

The CNN has {training['parameter_count']:,} parameters. Best validation macro-F1 was {training['best_validation_macro_f1']:.4f} at epoch {training['best_epoch']}; early stopping ended training after {training['epochs_run']} epochs. Training plus scalar calibration and baseline fitting took {training['training_and_calibration_seconds']:.2f} seconds on the recorded host. The seed was {training['config']['seed']}. Resolved settings, all class weights, hashes and selected epoch are saved in [train_summary.json]({run_link}/train_summary.json) and the checkpoint.

Cache SHA-256: `{evaluation['cache_sha256']}`. Split SHA-256: `{evaluation['splits_sha256']}`. These identify the exact prepared inputs, not an independent validation study.

## CNN versus the shallow baseline

{classification}

The CNN-minus-baseline difference is {100 * (cnn['accuracy'] - baseline['accuracy']):+.2f} percentage points in pooled accuracy and {cnn['macro_f1_all_four_classes'] - baseline['macro_f1_all_four_classes']:+.4f} in macro-F1 on this split. This is a descriptive comparison; two test participants do not support a reliable statistical claim of superiority across users.

Macro-F1 averages all four class F1 values. Balanced accuracy averages recall of classes present; all four are present here. Multiclass Brier is the mean sum of squared probability errors over four classes (range 0–2). ECE uses 10 equal-width maximum-probability bins. Detailed definitions and reliability bin counts are in [evaluation_test.json]({run_link}/evaluation_test.json).

## Per-class errors and confusion

{per_class}

{confusion_summary} CNN backward precision is {cnn['per_class']['leaning_back']['precision']:.4f}, with recall {cnn['per_class']['leaning_back']['recall']:.4f}. Baseline side-class errors are {side_baseline_errors}. Counts below use true classes on rows and predictions on columns.

{chr(10).join(confusion_tables)}

In these approximately frontal samples, upright-to-side confusion is {up_to_side} and side-to-upright confusion is {side_to_up}. **This does not test the upright-versus-lateral ambiguity of a side camera.** Side-view samples and per-row view labels are unavailable, and lateral movement along a side camera's viewing direction is not reliably recoverable from that single image. No side-view confusion matrix can be reported from this CSV.

## Performance by held-out person

{per_person}

Counts are {person_counts}, so pooled row metrics weight participants in proportion to their row counts. The CNN macro-F1 varies from {min(person_f1):.4f} to {max(person_f1):.4f}. Repeated or temporally nearby poses are not independent people; no frame-based confidence interval is presented as a population-level interval. More held-out participants and a prespecified subject-level cross-validation protocol are needed to assess uncertainty.

## Calibration before and after temperature scaling

CNN temperature: **{evaluation['temperature']:.6f}**. Baseline temperature: **{evaluation['logistic_regression_temperature']:.6f}**. Both were fitted using participants {', '.join(cal['subjects'])} only. Calibration-fit results are diagnostics of fitting, while test results assess transfer to new people.

{calibration_table}

NLL, Brier and ECE are lower-is-better. The fitted CNN temperature {temperature_action} its probabilities. Inspect the reliability plot and its bin counts: small bins are unstable, and a good calibration-fit result does not guarantee improvement for new people. {baseline_calibration_note} Neither result establishes deployment calibration. Temperature does not change either model's argmax prediction or classification accuracy.

## Threshold coverage and abstention

{coverage_table}

Illustrative CNN points: {threshold_summary}. These points describe this fixed test set and are **not a test-tuned threshold recommendation**. Probability is not an individual guarantee of correctness. The CSV has no detector confidence, visibility or presence, so these numbers cannot estimate coverage after live pose-quality/occlusion gating. The live pipeline additionally abstains for unsupported views and missing or unreliable landmarks.

## Classifier-only latency

{latency_table}

Measurements used batch size 1, {training['config']['latency_warmup']} warmup calls, and {training['config']['latency_repeats']} timed calls. Inputs were prepared before timing. The CNN measurement excludes camera capture, MediaPipe, normalization, feature construction, transfer, softmax, smoothing and rendering; the baseline includes its scaler and linear decision function. **Do not invert these latencies to claim camera-to-result FPS.** A separate pipeline benchmark is required for end-to-end performance.

{hardware_table}

The host reported a processor family identifier, not an exact retail CPU model. CPU measurements are sensitive to other workload and thread settings; they are not a deployment latency guarantee.

## Evidence limits

- This is one fixed split with only two test participants. Rows within a participant may be correlated; no external population test has been conducted.
- The source setup is approximately frontal, with no row-level view annotations. Side and oblique accuracy, and side-view upright/lateral confusion, are untested. The supplied classifier supports only the frontal source domain.
- Occlusion strata and real detector-confidence strata cannot be evaluated. Artificial joint dropout during training is not real-world occlusion validation.
- There are no ground-truth clinical angles or calibrated 3D measurements. Numeric measurement error, agreement with clinical reference measurements, and axis-specific physical accuracy are not established.
- Subject-independent pose-label accuracy does not validate ergonomic, medical, diagnostic or injury-risk conclusions. Projected image angles remain camera-dependent geometric summaries.
- Camera frames were not part of the supervised CSV. The classifier benchmark does not measure frozen MediaPipe extraction or a complete live pipeline.

Regenerate the figure and this report from the saved JSON using `python tools/make_report.py`. This reporting command never trains or tunes a model. See [TRAINING.md](TRAINING.md) for the method, [DATASET_AUDIT.md](DATASET_AUDIT.md) for source evidence, and the original machine-readable [evaluation_test.json]({run_link}/evaluation_test.json) for unrounded values.
"""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")


def main():
    project_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, default=project_root / "artifacts" / "run")
    parser.add_argument("--report", type=Path, default=project_root / "docs" / "RESULTS.md")
    parser.add_argument("--work-dir", type=Path, default=project_root / "work")
    args = parser.parse_args()
    cache_dir = args.work_dir.resolve() / "matplotlib-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(cache_dir))
    evaluation = json.loads((args.run / "evaluation_test.json").read_text(encoding="utf-8"))
    training = json.loads((args.run / "train_summary.json").read_text(encoding="utf-8"))
    if not evaluation.get("held_out_test") or evaluation["split"] != "test":
        raise ValueError("This report requires the saved held-out test evaluation")
    if evaluation["cnn"]["n"] != training["split_counts"]["test"]:
        raise ValueError("Training and evaluation sample counts do not match")
    plot = args.run.resolve() / "evaluation.png"
    render_plot(evaluation, plot)
    render_markdown(evaluation, training, args.report.resolve(), plot)
    print(json.dumps({"figure": str(plot), "report": str(args.report.resolve())}, indent=2))


if __name__ == "__main__":
    main()
