import Foundation

public enum ProbeError: Error, LocalizedError {
    case invalid(String)
    case refused(String)

    public var errorDescription: String? {
        switch self {
        case .invalid(let reason), .refused(let reason): return reason
        }
    }
}

public struct Point: Codable, Equatable {
    public let x: Double
    public let y: Double
    public init(x: Double, y: Double) { self.x = x; self.y = y }
}

public struct Rect: Codable, Equatable {
    public let x: Double
    public let y: Double
    public let width: Double
    public let height: Double

    public init(x: Double, y: Double, width: Double, height: Double) {
        self.x = x; self.y = y; self.width = width; self.height = height
    }

    public var isValid: Bool {
        [x, y, width, height, x + width, y + height].allSatisfy(\.isFinite) && width > 0 && height > 0
    }

    public func contains(_ point: Point) -> Bool {
        point.x >= x && point.y >= y && point.x < x + width && point.y < y + height
    }

    public func intersects(_ other: Rect) -> Bool {
        isValid && other.isValid && x < other.x + other.width && x + width > other.x
            && y < other.y + other.height && y + height > other.y
    }
}

public struct WindowLayer {
    public let id: UInt32
    public let bounds: Rect
    public let alpha: Double

    public init(id: UInt32, bounds: Rect, alpha: Double) {
        self.id = id; self.bounds = bounds; self.alpha = alpha
    }
}

public enum WindowOcclusion {
    /// Input is guarded against overlapping normal windows, not unrelated
    /// menu labels in the full-screen title area outside the game content.
    public static func frontmostOverlapping(_ windows: [WindowLayer], target: Rect) -> UInt32? {
        windows.first { $0.alpha > 0 && $0.bounds.intersects(target) }?.id
    }
}

/// Coordinates use the Quartz global top-left origin, including negative display origins.
public struct CoordinateMapper {
    public let window: Rect
    public let image: Rect
    public let content: Rect

    public init(window: Rect, imageWidth: Double, imageHeight: Double, content: Rect? = nil) throws {
        let image = Rect(x: 0, y: 0, width: imageWidth, height: imageHeight)
        let content = content ?? image
        guard window.isValid, image.isValid, content.isValid,
              content.x >= 0, content.y >= 0,
              content.x + content.width <= image.width,
              content.y + content.height <= image.height else {
            throw ProbeError.invalid("Invalid window, image size or content rectangle")
        }
        self.window = window; self.image = image; self.content = content
    }

    public func screenPoint(x: Double, y: Double) throws -> Point {
        guard x.isFinite, y.isFinite, x >= 0, x <= 1, y >= 0, y <= 1 else {
            throw ProbeError.invalid("Normalized coordinates must be finite and within [0, 1]")
        }
        // The upper endpoint is the last pixel's centre, never the neighbouring window.
        let px = content.x + min(x * content.width, max(0, content.width - 0.5))
        let py = content.y + min(y * content.height, max(0, content.height - 0.5))
        return Point(x: window.x + px / image.width * window.width,
                     y: window.y + py / image.height * window.height)
    }
}

public struct WindowState: Codable, Equatable {
    public let id: UInt32
    public let pid: Int32
    public let bounds: Rect
    public let isFrontmost: Bool
    public let isVisible: Bool
    public let isTopWindow: Bool

    public init(id: UInt32, pid: Int32, bounds: Rect, isFrontmost: Bool,
                isVisible: Bool = true, isTopWindow: Bool = true) {
        self.id = id; self.pid = pid; self.bounds = bounds
        self.isFrontmost = isFrontmost; self.isVisible = isVisible; self.isTopWindow = isTopWindow
    }

    public func validate(against original: WindowState) throws {
        guard id == original.id, pid == original.pid else {
            throw ProbeError.refused("Target window or process changed; no further input sent")
        }
        guard isFrontmost, isVisible, isTopWindow else {
            throw ProbeError.refused("Target lost focus, became hidden or another window covered it")
        }
        guard bounds.isValid, bounds == original.bounds else {
            throw ProbeError.refused("Target window moved or resized; refresh coordinates before retrying")
        }
    }
}

public enum Statistics {
    public static func percentile(_ values: [Double], _ fraction: Double) -> Double? {
        guard !values.isEmpty, fraction.isFinite, (0...1).contains(fraction),
              values.allSatisfy(\.isFinite) else { return nil }
        let values = values.sorted()
        let index = fraction * Double(values.count - 1)
        let lower = Int(index.rounded(.down)), upper = Int(index.rounded(.up))
        return values[lower] + (values[upper] - values[lower]) * (index - Double(lower))
    }
}
