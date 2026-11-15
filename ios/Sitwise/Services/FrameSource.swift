import AVFoundation
import CoreVideo
import Foundation

/// Hands camera frames to the model. Frames exist only in memory, for the duration of one
/// `analyze` call: they are never written to disk, logged, or sent anywhere.
protocol FrameSource: AnyObject {
    func start(onFrame: @escaping (CVPixelBuffer) -> Void) async throws
    func stop()
}

/// Real camera (physical iPhone). Delivers at most one frame per `Config.sampleInterval`.
final class CameraFrameSource: NSObject, FrameSource, AVCaptureVideoDataOutputSampleBufferDelegate {
    private let session = AVCaptureSession()
    private let queue = DispatchQueue(label: "sitwise.camera")
    private var onFrame: ((CVPixelBuffer) -> Void)?
    private var lastDelivered = Date.distantPast

    func start(onFrame: @escaping (CVPixelBuffer) -> Void) async throws {
        guard await AVCaptureDevice.requestAccess(for: .video) else { throw FrameSourceError.cameraDenied }
        guard let device = AVCaptureDevice.default(.builtInWideAngleCamera, for: .video, position: .back),
              let input = try? AVCaptureDeviceInput(device: device) else { throw FrameSourceError.noCamera }
        self.onFrame = onFrame

        session.beginConfiguration()
        session.sessionPreset = .vga640x480          // small is plenty for pose estimation
        if session.canAddInput(input) { session.addInput(input) }
        let output = AVCaptureVideoDataOutput()
        output.alwaysDiscardsLateVideoFrames = true
        output.setSampleBufferDelegate(self, queue: queue)
        if session.canAddOutput(output) { session.addOutput(output) }
        session.commitConfiguration()

        queue.async { [session] in session.startRunning() }
    }

    func stop() {
        queue.async { [session] in if session.isRunning { session.stopRunning() } }
        onFrame = nil
    }

    func captureOutput(_ output: AVCaptureOutput, didOutput sampleBuffer: CMSampleBuffer, from connection: AVCaptureConnection) {
        let now = Date()
        guard now.timeIntervalSince(lastDelivered) >= Config.sampleInterval,
              let buffer = CMSampleBufferGetImageBuffer(sampleBuffer) else { return }
        lastDelivered = now
        onFrame?(buffer)
    }
}

/// Simulator / no-camera fallback: ticks once a second with a tiny blank buffer. Good enough because
/// the stub model ignores pixels; the real model needs the real camera.
final class SyntheticFrameSource: FrameSource {
    private var timer: Timer?

    func start(onFrame: @escaping (CVPixelBuffer) -> Void) async throws {
        await MainActor.run {
            timer = Timer.scheduledTimer(withTimeInterval: Config.sampleInterval, repeats: true) { _ in
                var buffer: CVPixelBuffer?
                CVPixelBufferCreate(kCFAllocatorDefault, 2, 2, kCVPixelFormatType_32BGRA, nil, &buffer)
                if let buffer { onFrame(buffer) }
            }
        }
    }

    func stop() {
        DispatchQueue.main.async { [timer] in timer?.invalidate() }
        timer = nil
    }
}

enum FrameSourceError: LocalizedError {
    case cameraDenied, noCamera
    var errorDescription: String? {
        switch self {
        case .cameraDenied: return "Camera access is off. Enable it in Settings > Sitwise."
        case .noCamera: return "No camera available on this device."
        }
    }
}
