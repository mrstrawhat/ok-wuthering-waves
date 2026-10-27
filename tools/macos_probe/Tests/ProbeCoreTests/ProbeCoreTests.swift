import Foundation
import Testing
@testable import ProbeCore

@Suite
struct ProbeCoreTests {
    let window = Rect(x: 100, y: 60, width: 960, height: 540)
    var mapper: CoordinateMapper { try! CoordinateMapper(window: window, imageWidth: 1920, imageHeight: 1080) }
    var target: WindowState { WindowState(id: 17, pid: 42, bounds: window, isFrontmost: true) }

    @Test
    func testRetinaMappingUsesPointsRatherThanPixels() throws {
        #expect(try mapper.screenPoint(x: 0.5, y: 0.5) == Point(x: 580, y: 330))
    }

    @Test
    func testContentRectangleAndNegativeDisplayOrigin() throws {
        let map = try CoordinateMapper(window: Rect(x: -960, y: -540, width: 960, height: 540),
                                       imageWidth: 1920, imageHeight: 1080,
                                       content: Rect(x: 0, y: 80, width: 1920, height: 1000))
        #expect(try map.screenPoint(x: 0, y: 0) == Point(x: -960, y: -500))
        let centre = try map.screenPoint(x: 0.5, y: 0.5)
        #expect(abs(centre.x - (-480)) < 1e-9)
        #expect(abs(centre.y - (-250)) < 1e-9)
    }

    @Test
    func testUpperEdgeNeverHitsAdjacentWindow() throws {
        #expect(window.contains(try mapper.screenPoint(x: 1, y: 1)))
    }

    @Test
    func testRejectsNonFiniteAndOutOfBoundsCoordinates() {
        for x in [-0.001, 1.01, .infinity, .nan] {
            #expect(throws: (any Error).self) { try mapper.screenPoint(x: x, y: 0.5) }
        }
        #expect(throws: (any Error).self) { try CoordinateMapper(window: window, imageWidth: 0, imageHeight: 1080) }
        #expect(throws: (any Error).self) { try CoordinateMapper(window: window, imageWidth: 1920, imageHeight: 1080,
            content: Rect(x: 1800, y: 0, width: 200, height: 100)) }
    }

    @Test
    func testScriptRejectsUnknownFieldsAndVersions() {
        for json in [
            #"{"schemaVersion":1,"actions":[{"kind":"key","keys":["w"],"durationMS":100}]}"#,
            #"{"schemaVersion":2,"actions":[{"kind":"wait"}]}"#,
            #"{"schemaVersion":1,"actions":[],"execute":true}"#,
        ] {
            #expect(throws: (any Error).self) { try InputScript.decode(Data(json.utf8)) }
        }
    }

    @Test
    func testValidJSONAndChordReleaseOrder() throws {
        let script = try InputScript.decode(Data(#"{"schemaVersion":1,"actions":[{"kind":"key","keys":["shift","w"],"durationMs":400}]}"#.utf8))
        let plan = try InputPlan(script: script, mapper: mapper)
        #expect(plan.durationMs == 400)
        #expect(plan.events.map(\.event.key) == ["shift", "w", "w", "shift"])
        #expect(plan.events.map(\.event.kind) == [.keyDown, .keyDown, .keyUp, .keyUp])
    }

    @Test
    func testEntireScriptValidatedBeforeDispatch() {
        let script = InputScript(actions: [.init(kind: .key, keys: ["w"]), .init(kind: .click, x: 9, y: 0.5)])
        #expect(throws: (any Error).self) { try InputPlan(script: script, mapper: mapper) }
        #expect(throws: (any Error).self) { try InputPlan(script: .init(actions: [.init(kind: .key, keys: ["w"], deltaX: 4)]), mapper: mapper) }
    }

    @Test
    func testRejectsUnboundedDurationsAndUnsupportedKeys() {
        let invalid: [[Action]] = [
            [], [.init(kind: .key, keys: ["cmd", "q"])], [.init(kind: .key, keys: ["w", "w"])],
            [.init(kind: .key, keys: ["w"], durationMs: -1)],
            [.init(kind: .wait, durationMs: 5001)],
            Array(repeating: .init(kind: .wait, durationMs: 4000), count: 4),
            [.init(kind: .relativeMove, deltaX: Int.min)],
            [.init(kind: .drag, x: 0, y: 0, toX: 1, toY: 1, durationMs: 0)],
        ]
        for actions in invalid { #expect(throws: (any Error).self) { try InputPlan(script: .init(actions: actions), mapper: mapper) } }
    }

    @Test
    func testDragInterpolationAndReleaseCoordinates() throws {
        let plan = try InputPlan(script: .init(actions: [
            .init(kind: .drag, x: 0.2, y: 0.5, toX: 0.8, toY: 0.5, durationMs: 600)
        ]), mapper: mapper)
        #expect(plan.events.first?.event.kind == .move)
        #expect(plan.events.last?.event.kind == .mouseUp)
        #expect(try plan.events.last?.event.point == mapper.screenPoint(x: 0.8, y: 0.5))
        #expect(plan.events.last?.offsetMs == 600)
        #expect(plan.events.filter { $0.event.kind == .move }.count > 30)
    }

    @Test
    func testNormalRunReleasesChordAndHonoursWait() throws {
        var clock = 0.0, events: [InputEvent] = []
        let plan = try InputPlan(script: .init(actions: [
            .init(kind: .key, keys: ["shift", "w"], durationMs: 100), .init(kind: .wait, durationMs: 200)
        ]), mapper: mapper)
        let runner = InputRunner(snapshot: { self.target }, send: { events.append($0) },
            stopped: { false }, now: { clock }, sleep: { clock += max($0, 0.0000001) })
        #expect(try runner.run(plan, target: target) == 4)
        #expect(events.map(\.kind) == [.keyDown, .keyDown, .keyUp, .keyUp])
        #expect(clock >= 0.3)
    }

    @Test
    func testNoEventsWhenInitialWindowIsNotFrontmost() throws {
        var events: [InputEvent] = []
        let hidden = WindowState(id: 17, pid: 42, bounds: window, isFrontmost: false)
        let plan = try InputPlan(script: .init(actions: [.init(kind: .key, keys: ["w"])]), mapper: mapper)
        let runner = InputRunner(snapshot: { hidden }, send: { events.append($0) },
            stopped: { false }, now: { 0 }, sleep: { _ in Issue.record("Must not wait") })
        #expect(throws: (any Error).self) { try runner.run(plan, target: target) }
        #expect(events.isEmpty)
    }

    @Test
    func testFocusLossReleasesHeldKeyWithoutSendingFollowingAction() throws {
        var clock = 0.0, events: [InputEvent] = []
        let plan = try InputPlan(script: .init(actions: [.init(kind: .key, keys: ["w"], durationMs: 500),
                                                        .init(kind: .click, x: 0.5, y: 0.5)]), mapper: mapper)
        let runner = InputRunner(snapshot: {
            WindowState(id: 17, pid: 42, bounds: self.window, isFrontmost: clock < 0.03)
        }, send: { events.append($0) }, stopped: { false }, now: { clock },
            sleep: { clock += max($0, 0.0000001) })
        #expect(throws: (any Error).self) { try runner.run(plan, target: target) }
        #expect(events.map(\.kind) == [.keyDown, .keyUp])
        #expect(clock < 0.05)
    }

    @Test
    func testCancellationDuringDragReleasesButton() throws {
        var clock = 0.0, events: [InputEvent] = []
        let plan = try InputPlan(script: .init(actions: [
            .init(kind: .drag, x: 0.2, y: 0.5, toX: 0.8, toY: 0.5)
        ]), mapper: mapper)
        let runner = InputRunner(snapshot: { self.target }, send: { events.append($0) },
            stopped: { clock >= 0.025 }, now: { clock }, sleep: { clock += max($0, 0.0000001) })
        #expect(throws: (any Error).self) { try runner.run(plan, target: target) }
        #expect(events.last?.kind == .mouseUp)
        #expect(events.filter { $0.kind == .mouseDown }.count == 1)
        #expect(events.filter { $0.kind == .mouseUp }.count == 1)
        #expect(clock < 0.05)
    }

    @Test
    func testSinkFailureStillAttemptsRelease() throws {
        var events: [InputEvent] = []
        let plan = try InputPlan(script: .init(actions: [.init(kind: .key, keys: ["w"])]), mapper: mapper)
        let runner = InputRunner(snapshot: { self.target }, send: {
            events.append($0)
            if $0.kind == .keyDown { throw ProbeError.refused("test dispatch failure") }
        }, stopped: { false }, now: { 0 }, sleep: { _ in Issue.record("Must not wait") })
        #expect(throws: (any Error).self) { try runner.run(plan, target: target) }
        #expect(events.map(\.kind) == [.keyDown, .keyUp])
    }

    @Test
    func testPIDReuseWindowChangesAndOcclusionRefused() {
        let invalid = [
            WindowState(id: 17, pid: 99, bounds: window, isFrontmost: true),
            WindowState(id: 18, pid: 42, bounds: window, isFrontmost: true),
            WindowState(id: 17, pid: 42, bounds: .init(x: 101, y: 60, width: 960, height: 540), isFrontmost: true),
            WindowState(id: 17, pid: 42, bounds: window, isFrontmost: true, isVisible: false),
            WindowState(id: 17, pid: 42, bounds: window, isFrontmost: true, isTopWindow: false),
        ]
        for state in invalid { #expect(throws: (any Error).self) { try state.validate(against: target) } }
    }

    @Test
    func testStatisticsDoNotInventMeasurements() {
        #expect(Statistics.percentile([], 0.95) == nil)
        #expect(Statistics.percentile([.nan], 0.95) == nil)
        #expect(Statistics.percentile([10], 2) == nil)
        #expect(Statistics.percentile([40, 10, 30, 20], 0.5) == 25)
        #expect(Statistics.percentile([10], 0.95) == 10)
    }

    @Test
    func testStopBeforeFirstActionNeverReadsWindowOrSendsInput() throws {
        let plan = try InputPlan(script: .init(actions: [.init(kind: .key, keys: ["w"])]), mapper: mapper)
        let runner = InputRunner(snapshot: { Issue.record("Must not inspect a stopped target"); return self.target },
            send: { _ in Issue.record("Must not send input") }, stopped: { true },
            now: { 0 }, sleep: { _ in Issue.record("Must not sleep") })
        #expect(throws: (any Error).self) { try runner.run(plan, target: target) }
    }

    @Test
    func testOverflowingRectanglesAreRejected() {
        #expect(!Rect(x: Double.greatestFiniteMagnitude, y: 0,
                      width: Double.greatestFiniteMagnitude, height: 1).isValid)
    }
}
