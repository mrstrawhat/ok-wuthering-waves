import AppKit
import ApplicationServices
import Foundation
import ProbeCore

final class QuartzSink {
    private let source: CGEventSource
    private let targetBounds: Rect
    private var dragging = false
    private var modifiers: Set<String> = []

    init(targetBounds: Rect) throws {
        guard let source = CGEventSource(stateID: .combinedSessionState) else {
            throw ProbeError.refused("Cannot create a Quartz event source")
        }
        self.source = source
        self.targetBounds = targetBounds
    }

    func send(_ event: InputEvent) throws {
        var native: CGEvent?
        let cursor = event.point.map { CGPoint(x: $0.x, y: $0.y) }
            ?? CGEvent(source: nil)?.location ?? .zero
        if event.kind == .scroll || event.kind == .relativeMove {
            guard targetBounds.contains(Point(x: cursor.x, y: cursor.y)) else {
                throw ProbeError.refused("Pointer is outside the target window; scroll/relative movement refused")
            }
        }
        switch event.kind {
        case .move:
            native = CGEvent(mouseEventSource: source, mouseType: dragging ? .leftMouseDragged : .mouseMoved,
                             mouseCursorPosition: cursor, mouseButton: .left)
        case .relativeMove:
            native = CGEvent(mouseEventSource: source, mouseType: dragging ? .leftMouseDragged : .mouseMoved,
                             mouseCursorPosition: cursor, mouseButton: .left)
            native?.setIntegerValueField(.mouseEventDeltaX, value: Int64(event.deltaX ?? 0))
            native?.setIntegerValueField(.mouseEventDeltaY, value: Int64(event.deltaY ?? 0))
        case .mouseDown, .mouseUp:
            dragging = event.kind == .mouseDown
            native = CGEvent(mouseEventSource: source, mouseType: dragging ? .leftMouseDown : .leftMouseUp,
                             mouseCursorPosition: cursor, mouseButton: .left)
            native?.setIntegerValueField(.mouseEventClickState, value: 1)
        case .keyDown, .keyUp:
            guard let key = event.key, let code = InputPlan.keyCodes[key] else {
                throw ProbeError.invalid("Unsupported key")
            }
            if ["shift", "ctrl"].contains(key) {
                if event.kind == .keyDown { modifiers.insert(key) } else { modifiers.remove(key) }
            }
            native = CGEvent(keyboardEventSource: source, virtualKey: code, keyDown: event.kind == .keyDown)
            var flags: CGEventFlags = []
            if modifiers.contains("shift") { flags.insert(.maskShift) }
            if modifiers.contains("ctrl") { flags.insert(.maskControl) }
            native?.flags = flags
        case .scroll:
            native = CGEvent(scrollWheelEvent2Source: source, units: .pixel, wheelCount: 2,
                             wheel1: Int32(event.deltaY ?? 0), wheel2: Int32(event.deltaX ?? 0), wheel3: 0)
        }
        guard let native else { throw ProbeError.refused("Quartz could not allocate the requested event") }
        native.post(tap: .cghidEventTap)
    }
}

func emergencyChord() -> Bool {
    CGEventSource.keyState(.combinedSessionState, key: 53)
        && CGEventSource.keyState(.combinedSessionState, key: 58)
        && CGEventSource.keyState(.combinedSessionState, key: 59)
}

extension MacProbe {
    static func input(_ options: Options) async throws {
        // Validate the complete script before any OS interaction or partial dispatch.
        let script = try options.script()
        _ = try InputPlan(script: script, mapper: options.mapper(
            bounds: Rect(x: 0, y: 0, width: 1920, height: 1080)))
        let window = try await targetWindow(options)
        let pid = window.owningApplication!.processID
        let initial = try windowState(id: window.windowID, pid: pid)
        let plan = try InputPlan(script: script, mapper: options.mapper(bounds: initial.bounds))
        struct Preview: Codable { let executed: Bool; let target: WindowState; let plan: InputPlan }
        guard options.execute else {
            try emit(Preview(executed: false, target: initial, plan: plan)); return
        }
        guard AXIsProcessTrusted(), CGPreflightPostEventAccess() else {
            throw ProbeError.refused("Accessibility/event-posting permission is missing; no input sent")
        }
        let stopPath = try options.required("stop-file")
        guard stopPath.hasPrefix("/"), !FileManager.default.fileExists(atPath: stopPath),
              FileManager.default.fileExists(atPath: URL(fileURLWithPath: stopPath).deletingLastPathComponent().path) else {
            throw ProbeError.invalid("--stop-file must be an absent file in an existing absolute parent directory")
        }
        try initial.validate(against: initial)
        guard !InputPlan.keyCodes.values.contains(where: { CGEventSource.keyState(.combinedSessionState, key: $0) }),
              !CGEventSource.buttonState(.combinedSessionState, button: .left),
              !CGEventSource.buttonState(.combinedSessionState, button: .right) else {
            throw ProbeError.refused("A key or mouse button is already held; release physical input before starting")
        }
        let stop = StopToken(); stop.installSignals()
        let sink = try QuartzSink(targetBounds: initial.bounds)
        let runner = InputRunner(snapshot: { try windowState(id: window.windowID, pid: pid) },
                                 send: sink.send,
                                 stopped: { stop.cancelled || emergencyChord()
                                     || FileManager.default.fileExists(atPath: stopPath) },
                                 now: { ProcessInfo.processInfo.systemUptime }, sleep: Thread.sleep)
        let count = try runner.run(plan, target: initial)
        struct Result: Codable {
            let eventsPosted: Int
            let durationMs: Int
            let gameAcceptanceVerified: Bool
        }
        try emit(Result(eventsPosted: count, durationMs: plan.durationMs, gameAcceptanceVerified: false))
    }
}
