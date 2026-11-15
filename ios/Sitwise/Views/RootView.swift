import SwiftUI

struct RootView: View {
    @EnvironmentObject var app: AppState

    var body: some View {
        switch app.stage {
        case .loading:
            ProgressView().controlSize(.large)
        case .pairing:
            PairingView()
        case .calibrating:
            CalibrationView()
        case .main:
            TabView {
                LiveStatusView()
                    .tabItem { Label("Live", systemImage: "waveform.path.ecg") }
                SettingsView()
                    .tabItem { Label("Settings", systemImage: "slider.horizontal.3") }
            }
        }
    }
}

/// Shared look for a posture state: colour AND icon AND label (never colour alone).
extension PostureState {
    var label: String {
        switch self {
        case .good: return "Good posture"
        case .deviating: return "Drifting"
        case .slouching: return "Slouching"
        case .away: return "Away"
        }
    }
    var symbol: String {
        switch self {
        case .good: return "checkmark.circle"
        case .deviating: return "hourglass"
        case .slouching: return "exclamationmark.triangle"
        case .away: return "moon"
        }
    }
    var tint: Color {
        switch self {
        case .good: return .green
        case .deviating: return .orange
        case .slouching: return .red
        case .away: return .gray
        }
    }
}
