import SwiftUI

/// Enter the 6-character code shown on the dashboard's "Pair" page.
struct PairingView: View {
    @EnvironmentObject var app: AppState
    @State private var code = ""
    @State private var busy = false
    @State private var error: String?
    @FocusState private var focused: Bool

    var body: some View {
        VStack(spacing: 20) {
            Spacer()
            Image(systemName: "figure.seated.side")
                .font(.system(size: 56))
                .foregroundStyle(.tint)
            Text("Pair with your dashboard").font(.title2.bold())
            Text("Open the Sitwise dashboard in a browser, go to Pair, and enter the code it shows.")
                .multilineTextAlignment(.center)
                .foregroundStyle(.secondary)

            TextField("ABC234", text: $code)
                .textInputAutocapitalization(.characters)
                .autocorrectionDisabled()
                .font(.system(size: 34, weight: .semibold, design: .monospaced))
                .multilineTextAlignment(.center)
                .padding()
                .background(.quaternary, in: RoundedRectangle(cornerRadius: 14))
                .focused($focused)
                .onChange(of: code) { new in
                    code = String(new.uppercased().filter { $0.isLetter || $0.isNumber }.prefix(6))
                }

            if let error { Text(error).foregroundStyle(.red).font(.callout).multilineTextAlignment(.center) }

            Button {
                Task { await pair() }
            } label: {
                Text(busy ? "Pairing…" : "Pair").frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
            .disabled(code.count != 6 || busy)

            Text("Only numbers leave this phone. Camera frames are never saved or uploaded.")
                .font(.footnote).foregroundStyle(.secondary).multilineTextAlignment(.center)
            Spacer()
        }
        .padding(24)
        .onAppear { focused = true }
    }

    private func pair() async {
        busy = true; error = nil
        defer { busy = false }
        do {
            let token = try await app.api.claim(code: code)
            app.didPair(token: token)
        } catch {
            self.error = error.localizedDescription
        }
    }
}
