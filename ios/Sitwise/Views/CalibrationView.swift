import SwiftUI

/// Guided "sit comfortably" flow: instructions -> countdown -> the model captures the goal posture
/// -> we store it -> confirmation. The model does the math; this screen owns the flow.
struct CalibrationView: View {
    @EnvironmentObject var app: AppState
    private let countdownSeconds = 10

    enum Phase { case intro, counting, saving, done(CalibrationBaseline), rejected([String]) }
    @State private var phase: Phase = .intro
    @State private var remaining = 10
    @State private var error: String?

    var body: some View {
        VStack(spacing: 20) {
            Spacer()
            switch phase {
            case .intro:
                Image(systemName: "figure.seated.side").font(.system(size: 64)).foregroundStyle(.tint)
                Text("Set your goal posture").font(.title2.bold())
                Text("Mount the phone on the side of your chair. Then sit the way you want to sit: back supported, shoulders relaxed, ears over shoulders. Hold still during the countdown.")
                    .multilineTextAlignment(.center).foregroundStyle(.secondary)
                Button { Task { await run() } } label: { Text("I'm sitting comfortably. Start").frame(maxWidth: .infinity) }
                    .buttonStyle(.borderedProminent).controlSize(.large)
                Button("Skip for now") { app.finishCalibration() }.foregroundStyle(.secondary)

            case .counting:
                Text("Hold your best posture").foregroundStyle(.secondary)
                Text("\(remaining)").font(.system(size: 110, weight: .semibold)).monospacedDigit()
                ProgressView(value: Double(countdownSeconds - remaining), total: Double(countdownSeconds))

            case .saving:
                ProgressView("Checking your posture…")

            case .rejected(let issues):
                Image(systemName: "exclamationmark.triangle").font(.system(size: 56)).foregroundStyle(.orange)
                Text("That wasn't your best posture").font(.title2.bold())
                Text("Sitwise only saves a goal posture that's healthy to aim for, so nothing was saved. Here's what it noticed:")
                    .multilineTextAlignment(.center).foregroundStyle(.secondary)
                VStack(alignment: .leading, spacing: 6) {
                    ForEach(issues.isEmpty ? ["Your posture looked slouched."] : issues, id: \.self) { issue in
                        Label(issue, systemImage: "xmark.circle").font(.callout)
                    }
                }
                Text("Sit tall with your lower back supported, let your shoulders drop, and bring your ears over your shoulders. It should feel comfortable, not stiff.")
                    .font(.footnote).foregroundStyle(.secondary).multilineTextAlignment(.center)
                Button { phase = .intro } label: { Text("Try again").frame(maxWidth: .infinity) }
                    .buttonStyle(.borderedProminent).controlSize(.large)

            case .done(let baseline):
                Image(systemName: "checkmark.circle.fill").font(.system(size: 64)).foregroundStyle(.green)
                Text("Goal posture saved").font(.title2.bold())
                HStack(spacing: 12) {
                    stat("Neck", "\(Int(baseline.goal.neckAngle))°")
                    stat("Torso", "\(Int(baseline.goal.torsoAngle))°")
                    stat("Head fwd", String(format: "%.2f", baseline.goal.headForwardOffset))
                }
                Text("You can redo this any time from Settings.").font(.footnote).foregroundStyle(.secondary)
                Button { app.finishCalibration() } label: { Text("Done").frame(maxWidth: .infinity) }
                    .buttonStyle(.borderedProminent).controlSize(.large)
            }
            if let error { Text(error).foregroundStyle(.red).font(.callout) }
            Spacer()
        }
        .padding(24)
    }

    private func stat(_ name: String, _ value: String) -> some View {
        VStack { Text(name).font(.caption).foregroundStyle(.secondary); Text(value).font(.headline) }
            .frame(maxWidth: .infinity).padding(.vertical, 10)
            .background(.quaternary, in: RoundedRectangle(cornerRadius: 12))
    }

    private func run() async {
        error = nil
        phase = .counting
        remaining = countdownSeconds
        for _ in 0..<countdownSeconds {
            try? await Task.sleep(nanoseconds: 1_000_000_000)
            remaining -= 1
        }
        phase = .saving
        do {
            let baseline = try await app.model.calibrate()
            try await app.api.putCalibration(baseline)
            phase = .done(baseline)
        } catch CalibrationError.notGoodPosture(let issues) {
            phase = .rejected(issues)                        // the model said this isn't a good posture
        } catch APIError.server(let code, let message) where code == "posture_not_good" {
            phase = .rejected([message])                     // backstop: the server's gate refused it
        } catch {
            self.error = error.localizedDescription
            phase = .intro
        }
    }
}
