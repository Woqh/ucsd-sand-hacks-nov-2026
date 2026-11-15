import SwiftUI

struct LiveStatusView: View {
    @EnvironmentObject var app: AppState

    var body: some View { MonitorContent(monitor: app.monitor) }
}

/// Split out so the view observes `app.monitor` itself (it lives on AppState, created lazily).
private struct MonitorContent: View {
    @ObservedObject var monitor: PostureMonitor

    var body: some View {
        ScrollView {
            VStack(spacing: 16) {
                if let message = monitor.alertMessage {
                    Label(message, systemImage: "bell.fill")
                        .font(.headline).padding().frame(maxWidth: .infinity)
                        .background(.red.opacity(0.15), in: RoundedRectangle(cornerRadius: 14))
                        .transition(.move(edge: .top).combined(with: .opacity))
                }

                stateCard

                Button {
                    if monitor.isRunning {
                        monitor.stop()
                    } else {
                        Task { await monitor.start() }
                    }
                } label: {
                    Label(monitor.isRunning ? "Stop monitoring" : "Start monitoring",
                          systemImage: monitor.isRunning ? "stop.circle" : "play.circle")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent).controlSize(.large)
                .tint(monitor.isRunning ? .gray : .accentColor)

                if monitor.isRunning {
                    GroupBox("Latest reading") {
                        if let s = monitor.lastSample {
                            VStack(alignment: .leading, spacing: 6) {
                                row("Deviation", String(format: "%.2f", s.deviation ?? 0))
                                row("Neck angle", String(format: "%.1f°", s.features.neckAngle))
                                row("Torso angle", String(format: "%.1f°", s.features.torsoAngle))
                                row("Head forward", String(format: "%.2f", s.features.headForwardOffset))
                            }
                        } else { Text("Waiting for the first frame…").foregroundStyle(.secondary) }
                    }
                    if monitor.usingSyntheticFrames {
                        Text("No camera in use: running on the stub model with synthetic frames.")
                            .font(.footnote).foregroundStyle(.secondary)
                    }
                } else {
                    Text("Mount the phone on the side of your chair, keep the app open and the screen on, then start monitoring.")
                        .font(.footnote).foregroundStyle(.secondary).multilineTextAlignment(.center)
                }
                if let e = monitor.lastError { Text(e).font(.footnote).foregroundStyle(.red) }
            }
            .padding()
            .animation(.default, value: monitor.alertMessage)
        }
    }

    private var stateCard: some View {
        let state = monitor.isRunning ? monitor.serverState : .away
        return VStack(spacing: 6) {
            Image(systemName: state.symbol).font(.system(size: 44))
            Text(monitor.isRunning ? state.label : "Not monitoring").font(.largeTitle.bold())
            if monitor.isRunning, let since = monitor.stateSince {
                // `since` is the phone's own clock (it stamped the samples), so this stays accurate.
                Text("for ").foregroundStyle(.secondary) + Text(since, style: .relative).foregroundStyle(.secondary)
            }
        }
        .foregroundStyle(state.tint)
        .frame(maxWidth: .infinity).padding(.vertical, 28)
        .background(state.tint.opacity(0.12), in: RoundedRectangle(cornerRadius: 22))
    }

    private func row(_ k: String, _ v: String) -> some View {
        HStack { Text(k).foregroundStyle(.secondary); Spacer(); Text(v).monospacedDigit() }
    }
}
