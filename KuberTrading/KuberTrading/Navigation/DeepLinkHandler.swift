import Foundation

@Observable
final class DeepLinkHandler {
    static let shared = DeepLinkHandler()

    private let router = NavigationRouter.shared

    private init() {}

    func handle(url: URL) {
        guard let components = URLComponents(url: url, resolvingAgainstBaseURL: true) else { return }

        let pathComponents = components.path.split(separator: "/").map(String.init)

        // Handle approval deep links: /approve/{token}
        if pathComponents.count >= 2, pathComponents[0] == "approve" {
            let token = pathComponents[1]
            router.showApproval(token: token)
            return
        }

        // Handle execution deep links: /monitoring/{id}
        if pathComponents.count >= 2, pathComponents[0] == "monitoring" {
            let executionId = pathComponents[1]
            if pathComponents.count >= 3, pathComponents[2] == "report" {
                router.navigateToExecutionReport(id: executionId)
            } else {
                router.navigateToExecution(id: executionId)
            }
            return
        }

        // Handle pipeline deep links: /pipeline-builder/{id}
        if pathComponents.count >= 2, pathComponents[0] == "pipeline-builder" {
            let pipelineId = pathComponents[1]
            router.navigateToPipeline(id: pipelineId)
            return
        }
    }

    @MainActor
    func handlePushNotification(userInfo: [AnyHashable: Any]) {
        guard let type = userInfo["type"] as? String else { return }

        switch type {
        case "trade_approval":
            if let executionId = userInfo["execution_id"] as? String {
                router.navigateToExecution(id: executionId)
            }
        case "position_closed", "pipeline_failed", "risk_rejected":
            if let executionId = userInfo["execution_id"] as? String {
                router.navigateToExecution(id: executionId)
            }
        default:
            break
        }
    }
}
