import Foundation

/// Everything environment-specific lives here, so moving from the temporary Vercel URL to a real
/// domain is a one-line change.
enum Config {
    /// The deployed API host. Replace with your project's URL, e.g. https://sitwise-abc123.vercel.app
    /// For local dev against Flask on your Mac use its LAN address: http://192.168.1.20:5001
    static let baseURL = URL(string: "https://REPLACE-ME.vercel.app")!

    /// Dev builds (Xcode run) get *sandbox* APNs device tokens; TestFlight / App Store builds get
    /// production ones. We tell the server which this token is so it picks the right Apple host.
    #if DEBUG
    static let apnsSandbox = true
    #else
    static let apnsSandbox = false
    #endif

    /// Samples are sent about once a second (the server's stale-detection assumes this order).
    static let sampleInterval: TimeInterval = 1.0
}
