// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "ZhuyinBridgeCore",
    products: [.library(name: "ZhuyinBridgeCore", targets: ["ZhuyinBridgeCore"])],
    targets: [
        .target(name: "ZhuyinBridgeCore", path: "Shared"),
        .testTarget(name: "ZhuyinBridgeCoreTests", dependencies: ["ZhuyinBridgeCore"], path: "CoreTests")
    ]
)
