// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "OKWWMacProbe",
    platforms: [.macOS(.v14)],
    products: [.executable(name: "okww-mac-probe", targets: ["MacProbe"])],
    targets: [
        .target(name: "ProbeCore"),
        .executableTarget(name: "MacProbe", dependencies: ["ProbeCore"]),
        .testTarget(name: "ProbeCoreTests", dependencies: ["ProbeCore"]),
    ]
)
