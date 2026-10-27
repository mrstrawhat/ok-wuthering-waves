import AppKit
import CoreImage
import CoreMedia
import CoreVideo
import Foundation
import ImageIO
import ProbeCore
import ScreenCaptureKit
import UniformTypeIdentifiers

struct CaptureReport: Codable {
    let target: WindowDescription
    let captureFramePoints: Rect
    let pointPixelScale: Double
    let requestedFPS: Int
    let elapsedSeconds: Double
    let completeFrames: Int
    let sampledBlackFrames: Int
    let sampledChangedFrames: Int
    let statusCounts: [String: Int]
    let actualFPS: Double
    let intervalP50Ms: Double?
    let intervalP95Ms: Double?
    let frameAgeP50Ms: Double?
    let frameAgeP95Ms: Double?
    let imageWidth: Int?
    let imageHeight: Int?
    let contentRectPoints: Rect?
    let contentScale: Double?
    let displayScaleFactor: Double?
    let maximumArrivalGapMs: Double?
    let cancelled: Bool
    let streamError: String?
    let gameAcceptanceVerified: Bool
}

final class FrameCollector: NSObject, SCStreamOutput, SCStreamDelegate {
    private let lock = NSLock()
    private var arrivals: [Double] = [], ages: [Double] = []
    private var statuses: [String: Int] = [:]
    private var blackCount = 0, changedCount = 0
    private var previousHash: UInt64?
    private var first: CVPixelBuffer?, last: CVPixelBuffer?
    private var content: Rect?
    private var contentScale: Double?, displayScaleFactor: Double?
    private var streamError: String?

    func recordFailure(_ error: Error) {
        lock.lock(); defer { lock.unlock() }
        streamError = error.localizedDescription
    }

    func stream(_ stream: SCStream, didStopWithError error: Error) {
        lock.lock(); defer { lock.unlock() }
        streamError = error.localizedDescription
    }

    func stream(_ stream: SCStream, didOutputSampleBuffer sampleBuffer: CMSampleBuffer,
                of outputType: SCStreamOutputType) {
        guard outputType == .screen, sampleBuffer.isValid else { return }
        let attachments = (CMSampleBufferGetSampleAttachmentsArray(sampleBuffer, createIfNecessary: false)
                           as? [[SCStreamFrameInfo: Any]])?.first
        let raw = (attachments?[.status] as? NSNumber)?.intValue ?? -1
        let names = [0: "complete", 1: "idle", 2: "blank", 3: "suspended", 4: "started", 5: "stopped"]
        lock.lock(); defer { lock.unlock() }
        statuses[names[raw] ?? "unknown", default: 0] += 1
        guard raw == SCFrameStatus.complete.rawValue,
              let pixel = CMSampleBufferGetImageBuffer(sampleBuffer) else { return }
        guard CVPixelBufferGetPixelFormatType(pixel) == kCVPixelFormatType_32BGRA else {
            streamError = "Capture returned a pixel format other than the requested BGRA"
            return
        }
        arrivals.append(ProcessInfo.processInfo.systemUptime)
        let pts = CMSampleBufferGetPresentationTimeStamp(sampleBuffer)
        let age = CMClockGetTime(CMClockGetHostTimeClock()).seconds - pts.seconds
        if age.isFinite, age >= 0 { ages.append(age * 1000) }
        if let dict = attachments?[.contentRect] as? [String: Any],
           let rect = CGRect(dictionaryRepresentation: dict as CFDictionary) { content = bounds(rect) }
        // Apple's attachment contentRect uses points in the surface, not pixels.
        // Preserve all scale metadata rather than silently mislabelling the raw rectangle.
        contentScale = (attachments?[.contentScale] as? NSNumber)?.doubleValue
        displayScaleFactor = (attachments?[.scaleFactor] as? NSNumber)?.doubleValue
        let sample = fingerprint(pixel)
        if sample.black { blackCount += 1 }
        if let previousHash, previousHash != sample.hash { changedCount += 1 }
        previousHash = sample.hash
        if first == nil { first = pixel }
        last = pixel
    }

    private func fingerprint(_ pixel: CVPixelBuffer) -> (hash: UInt64, black: Bool) {
        CVPixelBufferLockBaseAddress(pixel, .readOnly)
        defer { CVPixelBufferUnlockBaseAddress(pixel, .readOnly) }
        guard let base = CVPixelBufferGetBaseAddress(pixel) else { return (0, false) }
        let width = CVPixelBufferGetWidth(pixel), height = CVPixelBufferGetHeight(pixel)
        let stride = CVPixelBufferGetBytesPerRow(pixel)
        let bytes = base.assumingMemoryBound(to: UInt8.self)
        var hash: UInt64 = 14695981039346656037, bright = false
        for row in 0..<16 {
            for col in 0..<16 {
                let offset = min(height - 1, row * height / 16) * stride + min(width - 1, col * width / 16) * 4
                for channel in 0..<3 {
                    let value = bytes[offset + channel]
                    hash = (hash ^ UInt64(value)) &* 1099511628211
                    if value > 8 { bright = true }
                }
            }
        }
        return (hash, !bright)
    }

    func saveAndReport(directory: URL, target: SCWindow, bundle: String, filter: SCContentFilter,
                       fps: Int, elapsed: Double, cancelled: Bool) throws -> CaptureReport {
        lock.lock(); defer { lock.unlock() }
        let context = CIContext()
        for (name, pixel) in [("first.png", first), ("last.png", last)] {
            if let pixel {
                let image = CIImage(cvPixelBuffer: pixel)
                guard let cgImage = context.createCGImage(image, from: image.extent),
                      let destination = CGImageDestinationCreateWithURL(directory.appendingPathComponent(name) as CFURL,
                                                                        UTType.png.identifier as CFString, 1, nil) else {
                    throw ProbeError.refused("Cannot encode captured PNG")
                }
                CGImageDestinationAddImage(destination, cgImage, nil)
                guard CGImageDestinationFinalize(destination) else { throw ProbeError.refused("Cannot save captured PNG") }
            }
        }
        let intervals = zip(arrivals.dropFirst(), arrivals).map { ($0 - $1) * 1000 }
        let span = (arrivals.last ?? 0) - (arrivals.first ?? 0)
        let description = WindowDescription(id: target.windowID, pid: target.owningApplication!.processID,
                                            bundle: bundle, title: target.title, framePoints: bounds(target.frame),
                                            onScreen: target.isOnScreen)
        let report = CaptureReport(target: description, captureFramePoints: bounds(filter.contentRect),
            pointPixelScale: Double(filter.pointPixelScale), requestedFPS: fps, elapsedSeconds: elapsed,
            completeFrames: arrivals.count, sampledBlackFrames: blackCount, sampledChangedFrames: changedCount,
            statusCounts: statuses, actualFPS: arrivals.count > 1 && span > 0 ? Double(arrivals.count - 1) / span : 0,
            intervalP50Ms: Statistics.percentile(intervals, 0.5), intervalP95Ms: Statistics.percentile(intervals, 0.95),
            frameAgeP50Ms: Statistics.percentile(ages, 0.5), frameAgeP95Ms: Statistics.percentile(ages, 0.95),
            imageWidth: last.map(CVPixelBufferGetWidth), imageHeight: last.map(CVPixelBufferGetHeight),
            contentRectPoints: content, contentScale: contentScale, displayScaleFactor: displayScaleFactor,
            maximumArrivalGapMs: intervals.max(), cancelled: cancelled,
            streamError: streamError, gameAcceptanceVerified: false)
        try jsonData(report).write(to: directory.appendingPathComponent("report.json"), options: .atomic)
        return report
    }
}

extension MacProbe {
    static func capture(_ options: Options) async throws -> CaptureReport {
        let seconds = try options.number("seconds", default: 3)
        let fps = try options.number("fps", default: 30)
        guard seconds > 0, seconds <= 30, fps.rounded() == fps, (1...120).contains(fps) else {
            throw ProbeError.invalid("Capture requires 0 < seconds <= 30 and an integer fps within [1,120]")
        }
        let output = try options.required("output")
        guard output.hasPrefix("/") else { throw ProbeError.invalid("--output must be an absolute directory") }
        let directory = URL(fileURLWithPath: output, isDirectory: true)
        guard !FileManager.default.fileExists(atPath: directory.path) else {
            throw ProbeError.refused("Output already exists; use a new evidence directory to preserve earlier results")
        }
        initializeNativeSession()
        let window = try await targetWindow(options)
        let filter = SCContentFilter(desktopIndependentWindow: window)
        let config = SCStreamConfiguration()
        config.width = Int((filter.contentRect.width * CGFloat(filter.pointPixelScale)).rounded())
        config.height = Int((filter.contentRect.height * CGFloat(filter.pointPixelScale)).rounded())
        guard config.width > 0, config.height > 0 else { throw ProbeError.refused("Target capture area is empty") }
        config.pixelFormat = kCVPixelFormatType_32BGRA
        config.colorSpaceName = CGColorSpace.sRGB
        config.showsCursor = false
        config.capturesAudio = false
        config.queueDepth = 5
        config.minimumFrameInterval = CMTime(value: 1, timescale: Int32(fps))
        if #available(macOS 14.2, *) { config.ignoreShadowsSingleWindow = true; config.includeChildWindows = false }
        let collector = FrameCollector()
        let stream = SCStream(filter: filter, configuration: config, delegate: collector)
        let queue = DispatchQueue(label: "okww.mac-probe.capture")
        try stream.addStreamOutput(collector, type: .screen, sampleHandlerQueue: queue)
        let stop = StopToken(); stop.installSignals()
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let start = ProcessInfo.processInfo.systemUptime
        do {
            try await stream.startCapture()
            while ProcessInfo.processInfo.systemUptime - start < seconds, !stop.cancelled {
                try await Task.sleep(nanoseconds: 20_000_000)
            }
            try await stream.stopCapture()
        } catch {
            collector.recordFailure(error)
            try? await stream.stopCapture()
        }
        // Drain callbacks before reading metrics or releasing retained pixel buffers.
        queue.sync {}
        let report = try collector.saveAndReport(directory: directory, target: window, bundle: options.bundle,
                                                filter: filter, fps: Int(fps),
                                                elapsed: ProcessInfo.processInfo.systemUptime - start,
                                                cancelled: stop.cancelled)
        guard report.completeFrames > 0, report.streamError == nil else {
            throw ProbeError.refused("No valid frames or stream failure; inspect \(directory.path)/report.json")
        }
        return report
    }
}
