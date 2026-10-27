import AppKit
import ApplicationServices
import Foundation
import ProbeCore
import ScreenCaptureKit

struct Options {
    let command: String
    let values: [String: String]
    let execute: Bool

    init(_ arguments: [String]) throws {
        command = arguments.first ?? "help"
        let known = Set(["bundle", "window-id", "output", "seconds", "fps", "script", "stop-file",
                         "image-width", "image-height", "content-rect"])
        var values: [String: String] = [:], execute = false, index = 1
        while index < arguments.count {
            let arg = arguments[index]
            if arg == "--execute" {
                guard !execute else { throw ProbeError.invalid("Duplicate --execute") }
                execute = true; index += 1; continue
            }
            guard arg.hasPrefix("--"), known.contains(String(arg.dropFirst(2))),
                  index + 1 < arguments.count, !arguments[index + 1].hasPrefix("--") else {
                throw ProbeError.invalid("Unknown option or missing value: \(arg)")
            }
            let key = String(arg.dropFirst(2))
            guard values[key] == nil else { throw ProbeError.invalid("Duplicate option: \(arg)") }
            values[key] = arguments[index + 1]; index += 2
        }
        self.values = values; self.execute = execute
    }

    var bundle: String { values["bundle"] ?? "com.kurogame.mingchao" }

    func required(_ key: String) throws -> String {
        guard let value = values[key], !value.isEmpty else { throw ProbeError.invalid("Missing --\(key)") }
        return value
    }

    func number(_ key: String, default fallback: Double? = nil) throws -> Double {
        guard let value = values[key].flatMap(Double.init) ?? fallback, value.isFinite else {
            throw ProbeError.invalid("--\(key) must be a finite number")
        }
        return value
    }

    func windowID() throws -> UInt32 {
        guard let value = UInt32(try required("window-id")), value > 0 else {
            throw ProbeError.invalid("--window-id must be a positive integer from the windows command")
        }
        return value
    }

    func script() throws -> InputScript {
        let url = URL(fileURLWithPath: try required("script"))
        let attributes = try FileManager.default.attributesOfItem(atPath: url.path)
        guard ((attributes[.size] as? NSNumber)?.intValue ?? 0) <= 65536 else {
            throw ProbeError.invalid("Input scripts cannot exceed 64KiB")
        }
        return try InputScript.decode(Data(contentsOf: url))
    }

    func mapper(bounds: Rect) throws -> CoordinateMapper {
        let width = try number("image-width"), height = try number("image-height")
        var content: Rect?
        if let raw = values["content-rect"] {
            let parts = raw.split(separator: ",", omittingEmptySubsequences: false).compactMap { Double($0) }
            guard parts.count == 4 else { throw ProbeError.invalid("--content-rect expects x,y,width,height in captured pixels") }
            content = Rect(x: parts[0], y: parts[1], width: parts[2], height: parts[3])
        }
        return try CoordinateMapper(window: bounds, imageWidth: width, imageHeight: height, content: content)
    }
}

final class StopToken: @unchecked Sendable {
    private let lock = NSLock()
    private var value = false
    private var sources: [DispatchSourceSignal] = []

    var cancelled: Bool { lock.lock(); defer { lock.unlock() }; return value }
    func cancel() { lock.lock(); value = true; lock.unlock() }
    func installSignals() {
        for code in [SIGINT, SIGTERM] {
            signal(code, SIG_IGN)
            let source = DispatchSource.makeSignalSource(signal: code, queue: .global())
            source.setEventHandler { [weak self] in self?.cancel() }
            source.resume(); sources.append(source)
        }
    }
}

func jsonData<T: Encodable>(_ value: T) throws -> Data {
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes]
    return try encoder.encode(value)
}

func emit<T: Encodable>(_ value: T) throws {
    FileHandle.standardOutput.write(try jsonData(value))
    FileHandle.standardOutput.write(Data([10]))
}

func bounds(_ rect: CGRect) -> Rect {
    Rect(x: rect.origin.x, y: rect.origin.y, width: rect.width, height: rect.height)
}

@MainActor
func initializeNativeSession() {
    // A CLI has no NSApplication lifecycle. Initialize its WindowServer
    // connection on the main actor before SCK creates a filter or stream.
    // Prohibited activation keeps this helper from taking focus from the game.
    NSApplication.shared.setActivationPolicy(.prohibited)
    _ = NSScreen.screens
}

func requireScreenPermission() throws {
    guard CGPreflightScreenCaptureAccess() else {
        throw ProbeError.refused("Screen recording permission is missing. Grant it to the host running this tool, then restart that host. This tool never opens permission prompts automatically.")
    }
}

func runningApp(_ bundle: String) throws -> NSRunningApplication {
    let apps = NSRunningApplication.runningApplications(withBundleIdentifier: bundle)
    guard apps.count == 1, let app = apps.first, !app.isTerminated else {
        throw ProbeError.refused("Expected exactly one running app for \(bundle). No app was launched.")
    }
    return app
}

func targetWindows(_ bundle: String) async throws -> [SCWindow] {
    let app = try runningApp(bundle)
    try requireScreenPermission()
    // Full-screen games live in a separate Space. Capture may target that
    // window even while the caller is on another desktop; input still uses
    // windowState's independent visibility and foreground guards.
    let shareable = try await SCShareableContent.excludingDesktopWindows(true, onScreenWindowsOnly: false)
    return shareable.windows.filter {
        $0.owningApplication?.processID == app.processIdentifier && $0.windowLayer == 0
            && $0.frame.width >= 100 && $0.frame.height >= 100
    }.sorted { $0.windowID < $1.windowID }
}

func targetWindow(_ options: Options) async throws -> SCWindow {
    let id = try options.windowID()
    guard let window = try await targetWindows(options.bundle).first(where: { $0.windowID == id }) else {
        throw ProbeError.refused("Target window was not found. Refresh windows; no input or launch was attempted.")
    }
    return window
}

func windowState(id: UInt32, pid: Int32) throws -> WindowState {
    guard let list = CGWindowListCopyWindowInfo([.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID)
            as? [[String: Any]],
          let row = list.first(where: { ($0[kCGWindowNumber as String] as? NSNumber)?.uint32Value == id }),
          let owner = row[kCGWindowOwnerPID as String] as? NSNumber,
          let rectDict = row[kCGWindowBounds as String] as? [String: Any],
          let rect = CGRect(dictionaryRepresentation: rectDict as CFDictionary),
          owner.int32Value == pid else {
        throw ProbeError.refused("Target is no longer a visible window of the expected process")
    }
    let frontPID = NSWorkspace.shared.frontmostApplication?.processIdentifier
    let layers = list.compactMap { item -> WindowLayer? in
        guard (item[kCGWindowLayer as String] as? NSNumber)?.intValue == 0,
              let windowID = (item[kCGWindowNumber as String] as? NSNumber)?.uint32Value,
              let dict = item[kCGWindowBounds as String] as? [String: Any],
              let frame = CGRect(dictionaryRepresentation: dict as CFDictionary) else { return nil }
        return WindowLayer(id: windowID, bounds: bounds(frame),
                           alpha: (item[kCGWindowAlpha as String] as? NSNumber)?.doubleValue ?? 1)
    }
    let top = WindowOcclusion.frontmostOverlapping(layers, target: bounds(rect))
    return WindowState(id: id, pid: pid, bounds: bounds(rect), isFrontmost: frontPID == pid,
                       isTopWindow: top == id)
}

struct WindowDescription: Codable {
    let id: UInt32
    let pid: Int32
    let bundle: String
    let title: String?
    let framePoints: Rect
    let onScreen: Bool
}

let help = """
OK-WW macOS native capability probe (macOS 14+, no Python or game framework required)

Commands:
  help
  status [--bundle ID]                 Read-only environment and permission preflight
  windows [--bundle ID]                Enumerate only this already-running app's windows
  capture --window-id ID --output /absolute/new-directory [--seconds 3] [--fps 30]
  validate --script FILE --image-width W --image-height H [--content-rect x,y,w,h]
  input --window-id ID --script FILE --image-width W --image-height H
        [--content-rect x,y,w,h] [--execute --stop-file /absolute/stop-file]

input previews by default. --execute is required to send any events.
The tool NEVER launches or activates an app, requests permission, or changes system settings.
Execution requires the exact target window to already be frontmost and unobscured.
Input stops on focus/window changes, stop-file creation, Ctrl+Option+Escape, SIGINT or SIGTERM.
Release cleanup is attempted for owned keys/buttons on stop. Scripts are limited to 15 seconds.
Normalized x/y refer to the supplied capture's content rectangle. Verify mapping before use.
Capture does not prove that the game accepts input. Posted events are not acceptance evidence.
"""

@main
@MainActor
struct MacProbe {
    static func main() async {
        do {
            let options = try Options(Array(CommandLine.arguments.dropFirst()))
            switch options.command {
            case "help", "--help", "-h": print(help)
            case "status": try status(options)
            case "windows":
                initializeNativeSession()
                let windows = try await targetWindows(options.bundle)
                try emit(windows.map { WindowDescription(id: $0.windowID,
                    pid: $0.owningApplication!.processID, bundle: options.bundle,
                    title: $0.title, framePoints: bounds($0.frame), onScreen: $0.isOnScreen) })
            case "validate":
                let mapper = try options.mapper(bounds: Rect(x: 0, y: 0, width: 1920, height: 1080))
                try emit(InputPlan(script: options.script(), mapper: mapper))
            case "capture": try emit(try await capture(options))
            case "input": try await input(options)
            default: throw ProbeError.invalid("Unknown command: \(options.command). Use help.")
            }
        } catch {
            struct Failure: Encodable { let error: String; let ok = false }
            let payload = Failure(error: error.localizedDescription)
            if let data = try? jsonData(payload) {
                FileHandle.standardError.write(data); FileHandle.standardError.write(Data([10]))
            }
            exit(2)
        }
    }

    static func status(_ options: Options) throws {
        initializeNativeSession()
        struct Display: Codable {
            let appKitFramePoints: Rect
            let quartzFramePoints: Rect?
            let backingScale: Double
        }
        struct Status: Codable {
            let os: String; let architecture: String; let targetBundle: String
            let targetRunning: Bool; let targetPIDs: [Int32]
            let screenRecording: Bool; let accessibility: Bool; let eventPosting: Bool
            let displays: [Display]; let launchesApps: Bool
        }
        #if arch(arm64)
        let architecture = "arm64"
        #else
        let architecture = "x86_64"
        #endif
        let apps = NSRunningApplication.runningApplications(withBundleIdentifier: options.bundle)
        try emit(Status(os: ProcessInfo.processInfo.operatingSystemVersionString,
                        architecture: architecture, targetBundle: options.bundle,
                        targetRunning: !apps.isEmpty, targetPIDs: apps.map(\.processIdentifier),
                        screenRecording: CGPreflightScreenCaptureAccess(), accessibility: AXIsProcessTrusted(),
                        eventPosting: CGPreflightPostEventAccess(),
                        displays: NSScreen.screens.map {
                            let displayID = ($0.deviceDescription[NSDeviceDescriptionKey("NSScreenNumber")] as? NSNumber)?.uint32Value
                            return Display(appKitFramePoints: bounds($0.frame),
                                           quartzFramePoints: displayID.map { bounds(CGDisplayBounds($0)) },
                                           backingScale: $0.backingScaleFactor)
                        },
                        launchesApps: false))
    }
}
