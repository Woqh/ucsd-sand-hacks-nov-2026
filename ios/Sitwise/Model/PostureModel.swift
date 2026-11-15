import CoreVideo
import Foundation

/// THE SEAM between the interface and the on-device model (OpenCV, owned by the teammate).
/// The interface only ever talks to this protocol. The teammate provides a real implementation
/// (e.g. `OpenCVPostureModel`) and swaps it in `AppState.model`; nothing else changes.
/// Do not change this signature silently: it's part of the contract (see CLAUDE.md).
protocol PostureModel {
    /// Capture the user's goal posture (called while they hold it comfortably).
    func calibrate() async throws -> CalibrationBaseline
    /// Classify one camera frame. The frame must not be stored or transmitted.
    func analyze(frame: CVPixelBuffer) async throws -> PostureSample
}

/// Returns fixed mock data so the whole app (and the server's alerts) can be exercised without the
/// real model: cycles GOOD -> SLOUCHING -> GOOD on a timer, ignoring the frame entirely.
final class StubPostureModel: PostureModel {
    private let sessionId = UUID().uuidString.lowercased()
    private let started = Date()
    // seconds: good, then slouching, then good again, then repeat
    private let phases: [(PostureLabel, TimeInterval)] = [(.good, 20), (.slouching, 25), (.good, 15)]

    func calibrate() async throws -> CalibrationBaseline {
        try await Task.sleep(nanoseconds: 800_000_000)   // pretend to think
        return CalibrationBaseline(
            goal: PostureFeatures(neckAngle: 15.0, torsoAngle: 5.0, headForwardOffset: 0.18),
            tolerance: 6.0,
            capturedAt: Int64(Date().timeIntervalSince1970 * 1000))
    }

    func analyze(frame: CVPixelBuffer) async throws -> PostureSample {
        let cycle = phases.reduce(0) { $0 + $1.1 }
        var t = Date().timeIntervalSince(started).truncatingRemainder(dividingBy: cycle)
        var label = PostureLabel.good
        for (l, d) in phases {
            if t < d { label = l; break }
            t -= d
        }
        let slouching = label == .slouching
        func jitter(_ a: Double) -> Double { Double.random(in: -a...a) }
        return PostureSample(
            sessionId: sessionId,
            t: Int64(Date().timeIntervalSince1970 * 1000),
            label: label,
            deviation: max(0, (slouching ? 0.72 : 0.12) + jitter(0.04)),
            confidence: 0.93,
            features: PostureFeatures(
                neckAngle: (slouching ? 34 : 16) + jitter(2),
                torsoAngle: (slouching ? 18 : 5.5) + jitter(1),
                headForwardOffset: (slouching ? 0.52 : 0.19) + jitter(0.02)))
    }
}
