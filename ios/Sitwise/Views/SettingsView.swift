import SwiftUI

/// Same settings as the dashboard (they're the same server-side record, so edits show up on both).
struct SettingsView: View {
    @EnvironmentObject var app: AppState
    @State private var settings: AppSettings?
    @State private var saveTask: Task<Void, Never>?
    @State private var skipNextSave = false
    @State private var error: String?
    @State private var confirmUnpair = false

    var body: some View {
        NavigationStack {
            Form {
                if let s = Binding($settings) {
                    Section("When to nudge me") {
                        VStack(alignment: .leading) {
                            HStack { Text("Slouch threshold"); Spacer(); Text("\(s.wrappedValue.slouchThresholdSec)s").foregroundStyle(.secondary) }
                            Slider(value: Binding(get: { Double(s.wrappedValue.slouchThresholdSec) },
                                                  set: { s.wrappedValue.slouchThresholdSec = Int($0) }),
                                   in: 5...300, step: 5)
                            Text("How long you can be off your goal posture before a nudge.").font(.footnote).foregroundStyle(.secondary)
                        }
                        VStack(alignment: .leading) {
                            HStack { Text("Sensitivity"); Spacer()
                                Text(s.wrappedValue.sensitivity < 0.34 ? "Forgiving" : s.wrappedValue.sensitivity > 0.66 ? "Strict" : "Balanced")
                                    .foregroundStyle(.secondary) }
                            Slider(value: s.sensitivity, in: 0...1, step: 0.05)
                        }
                        VStack(alignment: .leading) {
                            HStack { Text("Cooldown"); Spacer(); Text("\(s.wrappedValue.cooldownSec)s").foregroundStyle(.secondary) }
                            Slider(value: Binding(get: { Double(s.wrappedValue.cooldownSec) },
                                                  set: { s.wrappedValue.cooldownSec = Int($0) }),
                                   in: 15...900, step: 15)
                        }
                    }
                    Section("How to nudge me") {
                        Toggle("This iPhone (vibrates)", isOn: s.alertChannels.phone)
                        Toggle("Desktop browser", isOn: s.alertChannels.desktop)
                    }
                    Section("Quiet hours") {
                        Toggle("Don't alert during quiet hours", isOn: s.quietHours.enabled)
                    }
                }
                Section {
                    Button("Recalibrate goal posture") { app.recalibrate() }
                    Button("Unpair this phone", role: .destructive) { confirmUnpair = true }
                }
                if let error { Section { Text(error).foregroundStyle(.red) } }
            }
            .navigationTitle("Settings")
            .task { await load() }
            .onChange(of: settings) { _ in scheduleSave() }
            .confirmationDialog("Unpair this phone?", isPresented: $confirmUnpair, titleVisibility: .visible) {
                Button("Unpair", role: .destructive) { app.signOut() }
            }
        }
    }

    private func load() async {
        do {
            let loaded = try await app.api.getSettings()
            skipNextSave = true   // assigning the loaded value isn't a user edit
            settings = loaded
        } catch { self.error = error.localizedDescription }
    }

    /// Debounced so dragging a slider doesn't hammer the API.
    private func scheduleSave() {
        if skipNextSave { skipNextSave = false; return }
        guard let current = settings else { return }
        saveTask?.cancel()
        saveTask = Task {
            try? await Task.sleep(nanoseconds: 600_000_000)
            if Task.isCancelled { return }
            do { _ = try await app.api.putSettings(current); error = nil }
            catch { self.error = error.localizedDescription }
        }
    }
}
