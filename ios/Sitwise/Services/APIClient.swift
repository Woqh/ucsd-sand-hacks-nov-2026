import Foundation

enum APIError: LocalizedError {
    case unauthorized
    case server(code: String, message: String)
    case network(String)

    var errorDescription: String? {
        switch self {
        case .unauthorized: return "This phone is no longer paired. Please pair again."
        case .server(_, let message): return message
        case .network(let m): return "Can't reach the server (\(m))."
        }
    }
}

private struct AnyEncodable: Encodable {
    let value: any Encodable
    func encode(to encoder: Encoder) throws { try value.encode(to: encoder) }
}

private struct ErrorEnvelope: Decodable {
    struct Body: Decodable { var code: String; var message: String }
    var error: Body
}

/// Thin client for the Flask API. Base URL comes from `Config.baseURL`; the device token from the Keychain.
final class APIClient {
    static let shared = APIClient()
    private let session = URLSession(configuration: .default)

    private func send<T: Decodable>(_ method: String, _ path: String, body: (any Encodable)? = nil,
                                    auth: Bool = true) async throws -> T {
        let base = Config.baseURL.absoluteString.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        guard let url = URL(string: "\(base)/api\(path)") else { throw APIError.network("bad URL") }
        var req = URLRequest(url: url, timeoutInterval: 10)
        req.httpMethod = method
        if let body { req.httpBody = try JSONEncoder().encode(AnyEncodable(value: body)) }
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if auth, let token = Keychain.token { req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization") }

        let (data, response): (Data, URLResponse)
        do { (data, response) = try await session.data(for: req) }
        catch { throw APIError.network(error.localizedDescription) }

        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        guard (200..<300).contains(status) else {
            if status == 401 && auth { throw APIError.unauthorized }
            if let e = try? JSONDecoder().decode(ErrorEnvelope.self, from: data) {
                throw APIError.server(code: e.error.code, message: e.error.message)
            }
            throw APIError.server(code: "http_\(status)", message: "Server error (\(status))")
        }
        return try JSONDecoder().decode(T.self, from: data)
    }

    // MARK: - Contract

    /// POST /pair/claim: exchange the code shown on the dashboard for a device token.
    func claim(code: String) async throws -> String {
        let r: PairClaimResponse = try await send("POST", "/pair/claim", body: ["code": code], auth: false)
        return r.deviceToken
    }

    /// POST /posture/ingest: one PostureSample (numbers only), about once a second.
    func ingest(_ sample: PostureSample) async throws -> IngestResponse {
        try await send("POST", "/posture/ingest", body: sample)
    }

    func getSettings() async throws -> AppSettings {
        let r: SettingsEnvelope = try await send("GET", "/settings")
        return r.settings
    }

    func putSettings(_ settings: AppSettings) async throws -> AppSettings {
        let r: SettingsEnvelope = try await send("PUT", "/settings", body: SettingsEnvelope(settings: settings))
        return r.settings
    }

    func getCalibration() async throws -> CalibrationEnvelope {
        try await send("GET", "/calibration")
    }

    func putCalibration(_ baseline: CalibrationBaseline) async throws {
        let _: CalibrationEnvelope = try await send("PUT", "/calibration", body: baseline)
    }

    /// POST /push/apns/register: so the server can vibrate this phone with a push.
    func registerAPNs(token: String, sandbox: Bool) async throws {
        struct Body: Encodable { let token: String; let sandbox: Bool }
        let _: OKResponse = try await send("POST", "/push/apns/register", body: Body(token: token, sandbox: sandbox))
    }
}
