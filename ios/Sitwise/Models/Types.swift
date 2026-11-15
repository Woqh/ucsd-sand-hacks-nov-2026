import Foundation

// Hand-written mirrors of the API contract (docs/openapi.yaml) and of web/src/types.ts.
// If you change a shape, change all three in the same commit.
// PRIVACY: nothing in this file (or anywhere) carries image data. Only numbers leave the phone.

enum PostureLabel: String, Codable {
    case good = "GOOD", slouching = "SLOUCHING", away = "AWAY", unknown = "UNKNOWN"
}

enum PostureState: String, Codable {
    case away = "AWAY", good = "GOOD", deviating = "DEVIATING", slouching = "SLOUCHING"
}

/// Units/conventions are owned by the model implementer: confirm angle conventions with the
/// interface owner before coding, because they define this payload.
struct PostureFeatures: Codable, Equatable {
    var neckAngle: Double
    var torsoAngle: Double
    var headForwardOffset: Double
}

/// What the model returns per frame; also what we POST to /api/posture/ingest.
struct PostureSample: Codable {
    var schema: Int = 1
    var sessionId: String
    var t: Int64                 // epoch milliseconds
    var label: PostureLabel
    var deviation: Double?       // 0 = matches goal posture, higher = worse
    var confidence: Double       // 0...1; the server ignores low-confidence samples
    var features: PostureFeatures
}

struct CalibrationBaseline: Codable, Equatable {
    var schema: Int = 1
    var goal: PostureFeatures
    var tolerance: Double
    var capturedAt: Int64
    /// Calibration gate verdict. Absent/nil = accepted. A model should THROW `CalibrationError`
    /// rather than return a rejected baseline; these exist to mirror the wire contract.
    var accepted: Bool? = nil
    var issues: [String]? = nil
}

struct AlertChannels: Codable, Equatable {
    var phone: Bool
    var desktop: Bool
}

struct QuietHours: Codable, Equatable {
    var enabled: Bool
    var start: String            // "HH:MM" 24h
    var end: String
}

struct AppSettings: Codable, Equatable {
    var schema: Int = 1
    var slouchThresholdSec: Int
    var sensitivity: Double      // 0 forgiving ... 1 strict
    var alertChannels: AlertChannels
    var cooldownSec: Int
    var quietHours: QuietHours
    var tzOffsetMin: Int
}

// MARK: - Responses

struct SettingsEnvelope: Codable {
    var schema: Int = 1
    var settings: AppSettings
}

struct CalibrationEnvelope: Decodable {
    var calibrated: Bool
    var baseline: CalibrationBaseline?
}

struct PairClaimResponse: Decodable {
    var deviceToken: String
}

struct ChannelResult: Decodable {
    var sent: Int
    var failed: Int
    var skipped: String?
}

struct AlertInfo: Decodable {
    var level: Int
    var channels: [String: ChannelResult]
}

struct IngestResponse: Decodable {
    var state: PostureState
    var stateSince: Int64?
    var serverTime: Int64
    var alert: AlertInfo?
}

struct OKResponse: Decodable {}
