import Foundation

public struct Action: Codable {
    public enum Kind: String, Codable {
        case click, drag, key, move, scroll, wait
        case relativeMove = "relative_move"
    }
    public let kind: Kind
    public var x: Double?
    public var y: Double?
    public var toX: Double?
    public var toY: Double?
    public var keys: [String]?
    public var durationMs: Int?
    public var deltaX: Int?
    public var deltaY: Int?

    public init(kind: Kind, x: Double? = nil, y: Double? = nil,
                toX: Double? = nil, toY: Double? = nil, keys: [String]? = nil,
                durationMs: Int? = nil, deltaX: Int? = nil, deltaY: Int? = nil) {
        self.kind = kind; self.x = x; self.y = y; self.toX = toX; self.toY = toY
        self.keys = keys; self.durationMs = durationMs; self.deltaX = deltaX; self.deltaY = deltaY
    }
}

public struct InputScript: Codable {
    public let schemaVersion: Int
    public let actions: [Action]

    public init(actions: [Action]) { schemaVersion = 1; self.actions = actions }

    public static func decode(_ data: Data) throws -> InputScript {
        guard let root = try JSONSerialization.jsonObject(with: data) as? [String: Any],
              Set(root.keys).isSubset(of: ["schemaVersion", "actions"]),
              let actions = root["actions"] as? [[String: Any]] else {
            throw ProbeError.invalid("Expected {schemaVersion: 1, actions: [...]}; unknown fields are rejected")
        }
        let fields: Set<String> = ["kind", "x", "y", "toX", "toY", "keys", "durationMs", "deltaX", "deltaY"]
        guard actions.allSatisfy({ Set($0.keys).isSubset(of: fields) }) else {
            throw ProbeError.invalid("Unknown action field; check the script for spelling errors")
        }
        let script = try JSONDecoder().decode(InputScript.self, from: data)
        guard script.schemaVersion == 1 else { throw ProbeError.invalid("Unsupported script schema version") }
        return script
    }
}

public struct InputEvent: Codable, Equatable {
    public enum Kind: String, Codable { case move, mouseDown, mouseUp, keyDown, keyUp, scroll, relativeMove }
    public let kind: Kind
    public var point: Point?
    public var key: String?
    public var deltaX: Int?
    public var deltaY: Int?

    public init(_ kind: Kind, point: Point? = nil, key: String? = nil,
                deltaX: Int? = nil, deltaY: Int? = nil) {
        self.kind = kind; self.point = point; self.key = key; self.deltaX = deltaX; self.deltaY = deltaY
    }
}

public struct TimedEvent: Codable {
    public let offsetMs: Int
    public let event: InputEvent
}

public struct InputPlan: Codable {
    public let events: [TimedEvent]
    public let durationMs: Int
    public let actionCount: Int

    // Deliberately bounded, physical game keys. No text entry, arbitrary key codes or shell commands.
    public static let keyCodes: [String: UInt16] = [
        "a": 0, "s": 1, "d": 2, "f": 3, "h": 4, "g": 5, "z": 6, "x": 7,
        "c": 8, "v": 9, "b": 11, "q": 12, "w": 13, "e": 14, "r": 15,
        "y": 16, "t": 17, "1": 18, "2": 19, "3": 20, "4": 21, "6": 22,
        "5": 23, "9": 25, "7": 26, "8": 28, "0": 29, "o": 31, "u": 32,
        "i": 34, "p": 35, "enter": 36, "l": 37, "j": 38, "k": 40, "n": 45,
        "m": 46, "tab": 48, "space": 49, "escape": 53, "shift": 56, "ctrl": 59,
        "left": 123, "right": 124, "down": 125, "up": 126,
        "f1": 122, "f2": 120, "f3": 99, "f4": 118,
    ]

    public init(script: InputScript, mapper: CoordinateMapper) throws {
        guard script.schemaVersion == 1, !script.actions.isEmpty, script.actions.count <= 100 else {
            throw ProbeError.invalid("A script requires 1 to 100 actions with schemaVersion 1")
        }
        var events: [TimedEvent] = [], offset = 0
        func append(_ event: InputEvent, at time: Int) { events.append(TimedEvent(offsetMs: time, event: event)) }
        for action in script.actions {
            let pointer = [Action.Kind.click, .drag, .move].contains(action.kind)
            guard (pointer || (action.x == nil && action.y == nil)),
                  (action.kind == .drag || (action.toX == nil && action.toY == nil)),
                  (action.kind == .key || action.keys == nil),
                  ([Action.Kind.scroll, .relativeMove].contains(action.kind)
                    || (action.deltaX == nil && action.deltaY == nil)) else {
                throw ProbeError.invalid("Action contains fields that do not apply to its kind")
            }
            let defaultDuration = action.kind == .drag ? 600 : (action.kind == .key ? 120 : 80)
            let duration = action.durationMs ?? defaultDuration
            guard (0...5000).contains(duration) else {
                throw ProbeError.invalid("Each durationMs must be between 0 and 5000")
            }
            func point(_ x: Double?, _ y: Double?) throws -> Point {
                guard let x, let y else { throw ProbeError.invalid("This action requires x and y coordinates") }
                return try mapper.screenPoint(x: x, y: y)
            }
            switch action.kind {
            case .click:
                let p = try point(action.x, action.y)
                append(InputEvent(.move, point: p), at: offset)
                append(InputEvent(.mouseDown, point: p), at: offset)
                append(InputEvent(.mouseUp, point: p), at: offset + duration)
            case .drag:
                guard duration >= 40 else { throw ProbeError.invalid("A drag must last at least 40ms") }
                let start = try point(action.x, action.y), end = try point(action.toX, action.toY)
                append(InputEvent(.move, point: start), at: offset)
                append(InputEvent(.mouseDown, point: start), at: offset)
                let steps = max(2, duration / 10)
                for step in 1...steps {
                    let f = Double(step) / Double(steps)
                    let p = Point(x: start.x + (end.x - start.x) * f, y: start.y + (end.y - start.y) * f)
                    append(InputEvent(.move, point: p), at: offset + duration * step / steps)
                }
                append(InputEvent(.mouseUp, point: end), at: offset + duration)
            case .move:
                append(InputEvent(.move, point: try point(action.x, action.y)), at: offset)
            case .key:
                guard let keys = action.keys, !keys.isEmpty, keys.count <= 5,
                      Set(keys).count == keys.count, keys.allSatisfy({ Self.keyCodes[$0] != nil }) else {
                    throw ProbeError.invalid("Provide 1 to 5 unique supported lower-case key names")
                }
                for key in keys { append(InputEvent(.keyDown, key: key), at: offset) }
                for key in keys.reversed() { append(InputEvent(.keyUp, key: key), at: offset + duration) }
            case .scroll, .relativeMove:
                let dx = action.deltaX ?? 0, dy = action.deltaY ?? 0
                guard action.deltaX != nil || action.deltaY != nil,
                      (-1000...1000).contains(dx), (-1000...1000).contains(dy), dx != 0 || dy != 0 else {
                    throw ProbeError.invalid("Provide a nonzero deltaX or deltaY, each within [-1000, 1000]")
                }
                append(InputEvent(action.kind == .scroll ? .scroll : .relativeMove,
                                  deltaX: dx, deltaY: dy), at: offset)
            case .wait: break
            }
            offset += duration
            guard offset <= 15000 else { throw ProbeError.invalid("A probe script cannot exceed 15000ms") }
        }
        self.events = events; self.durationMs = offset; self.actionCount = script.actions.count
    }
}

/// All OS effects are injected. Tests never post real mouse or keyboard events.
public final class InputRunner {
    public typealias Sink = (InputEvent) throws -> Void
    private let snapshot: () throws -> WindowState
    private let send: Sink
    private let stopped: () -> Bool
    private let now: () -> Double
    private let sleep: (Double) -> Void

    public init(snapshot: @escaping () throws -> WindowState, send: @escaping Sink,
                stopped: @escaping () -> Bool, now: @escaping () -> Double,
                sleep: @escaping (Double) -> Void) {
        self.snapshot = snapshot; self.send = send; self.stopped = stopped
        self.now = now; self.sleep = sleep
    }

    public func run(_ plan: InputPlan, target: WindowState) throws -> Int {
        var heldKeys: [String] = [], mousePoint: Point?, lastPoint: Point?, count = 0
        defer {
            // Release only events owned by this run, including on cancellation or focus loss.
            if let p = mousePoint { try? send(InputEvent(.mouseUp, point: lastPoint ?? p)) }
            for key in heldKeys.reversed() { try? send(InputEvent(.keyUp, key: key)) }
        }
        func check() throws {
            guard !stopped() else { throw ProbeError.refused("Input stopped; release cleanup will be attempted") }
            try snapshot().validate(against: target)
        }
        try check()
        let start = now()
        func wait(until milliseconds: Int) throws {
            while now() - start < Double(milliseconds) / 1000 {
                try check()
                sleep(min(0.01, max(0, Double(milliseconds) / 1000 - (now() - start))))
            }
            try check()
        }
        for timed in plan.events {
            try wait(until: timed.offsetMs)
            let event = timed.event
            // Track before dispatch so partially failed sinks still trigger cleanup.
            if event.kind == .keyDown, let key = event.key { heldKeys.append(key) }
            if event.kind == .mouseDown { mousePoint = event.point }
            if let p = event.point { lastPoint = p }
            try send(event)
            if event.kind == .keyUp, let key = event.key { heldKeys.removeAll { $0 == key } }
            if event.kind == .mouseUp { mousePoint = nil }
            count += 1
        }
        try wait(until: plan.durationMs)
        return count
    }
}
