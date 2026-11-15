import SwiftUI

/// App-wide state: which screen to show, and the single `PostureModel` in use.
@MainActor
final class AppState: ObservableObject {
    enum Stage { case loading, pairing, calibrating, main }

    @Published var stage: Stage = .loading

    /// SWAP POINT: the teammate's real model goes here (see Model/OpenCV/README.md).
    let model: PostureModel = StubPostureModel()
    let api = APIClient.shared

    lazy var monitor = PostureMonitor(model: model, api: api) { [weak self] in
        self?.signOut()
    }

    func bootstrap() async {
        guard Keychain.token != nil else { stage = .pairing; return }
        PushManager.shared.requestPermissionAndRegister()
        do {
            let c = try await api.getCalibration()
            stage = c.calibrated ? .main : .calibrating
        } catch APIError.unauthorized {
            signOut()
        } catch {
            stage = .main   // offline at launch: let them in, the monitor will report errors
        }
    }

    func didPair(token: String) {
        Keychain.token = token
        PushManager.shared.requestPermissionAndRegister()
        PushManager.shared.syncToServer()
        stage = .calibrating
    }

    func finishCalibration() { stage = .main }

    func recalibrate() { monitor.stop(); stage = .calibrating }

    func signOut() {
        monitor.stop()
        Keychain.token = nil
        stage = .pairing
    }
}
