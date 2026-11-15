import SwiftUI
import UIKit

private struct FrameBox: @unchecked Sendable { let buffer: CVPixelBuffer }

/// The loop: camera frame -> on-device model -> numeric PostureSample -> server. Publishes live
/// status for the UI and fires the foreground haptic when the server says it sent an alert.
@MainActor
final class PostureMonitor: ObservableObject {
    @Published private(set) var isRunning = false
    @Published private(set) var serverState: PostureState = .away
    @Published private(set) var stateSince: Date?
    @Published private(set) var lastSample: PostureSample?
    @Published private(set) var lastError: String?
    @Published private(set) var usingSyntheticFrames = false
    @Published var alertMessage: String?

    private let model: PostureModel
    private let api: APIClient
    private let onUnauthorized: () -> Void
    private var source: FrameSource?
    private var sessionId = UUID().uuidString.lowercased()
    private var busy = false   // drop frames while one is still in flight (backpressure)

    init(model: PostureModel, api: APIClient = .shared, onUnauthorized: @escaping () -> Void) {
        self.model = model
        self.api = api
        self.onUnauthorized = onUnauthorized
    }

    func start() async {
        guard !isRunning else { return }
        lastError = nil
        sessionId = UUID().uuidString.lowercased()   // a new sessionId per monitoring run

        var src: FrameSource = CameraFrameSource()
        #if targetEnvironment(simulator)
        src = SyntheticFrameSource()
        #endif
        let onFrame: (CVPixelBuffer) -> Void = { [weak self] buffer in
            let box = FrameBox(buffer: buffer)
            Task { @MainActor [weak self] in await self?.handle(box.buffer) }
        }
        do {
            try await src.start(onFrame: onFrame)
            usingSyntheticFrames = src is SyntheticFrameSource
        } catch {
            // No camera (denied / unavailable): fall back so the rest of the app still works.
            lastError = error.localizedDescription
            src = SyntheticFrameSource()
            try? await src.start(onFrame: onFrame)
            usingSyntheticFrames = true
        }
        source = src
        isRunning = true
        UIApplication.shared.isIdleTimerDisabled = true   // the phone is mounted: keep the screen on
    }

    func stop() {
        source?.stop()
        source = nil
        isRunning = false
        serverState = .away
        UIApplication.shared.isIdleTimerDisabled = false
    }

    private func handle(_ frame: CVPixelBuffer) async {
        guard isRunning, !busy else { return }
        busy = true
        defer { busy = false }
        do {
            var sample = try await model.analyze(frame: frame)   // frame is dropped after this call
            sample.sessionId = sessionId
            sample.t = Int64(Date().timeIntervalSince1970 * 1000)
            lastSample = sample

            let response = try await api.ingest(sample)
            serverState = response.state
            stateSince = response.stateSince.map { Date(timeIntervalSince1970: Double($0) / 1000) }
            lastError = nil
            if response.alert != nil { fireForegroundAlert(level: response.alert?.level ?? 1) }
        } catch APIError.unauthorized {
            stop()
            onUnauthorized()
        } catch {
            lastError = error.localizedDescription   // keep running: transient network errors are normal
        }
    }

    /// Foreground: in-app banner + haptic. Background: the APNs push the server sent vibrates the phone.
    private func fireForegroundAlert(level: Int) {
        UINotificationFeedbackGenerator().notificationOccurred(.warning)
        alertMessage = level >= 3 ? "Take a stretch break?" : level == 2 ? "Still slouching. Chin tuck, shoulders down." : "Sit up tall"
        Task { [weak self] in
            try? await Task.sleep(nanoseconds: 6_000_000_000)
            self?.alertMessage = nil
        }
    }
}
