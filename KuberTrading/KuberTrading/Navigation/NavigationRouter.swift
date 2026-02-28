import SwiftUI

enum AppTab: Int, CaseIterable {
    case dashboard = 0
    case pipelines
    case monitoring
    case scanners
    case settings

    var title: String {
        switch self {
        case .dashboard: return "Dashboard"
        case .pipelines: return "Pipelines"
        case .monitoring: return "Monitoring"
        case .scanners: return "Scanners"
        case .settings: return "Settings"
        }
    }

    var icon: String {
        switch self {
        case .dashboard: return "chart.bar.fill"
        case .pipelines: return "arrow.triangle.branch"
        case .monitoring: return "eye.fill"
        case .scanners: return "antenna.radiowaves.left.and.right"
        case .settings: return "gearshape.fill"
        }
    }
}

@Observable
final class NavigationRouter {
    static let shared = NavigationRouter()

    var selectedTab: AppTab = .dashboard
    var dashboardPath = NavigationPath()
    var pipelinesPath = NavigationPath()
    var monitoringPath = NavigationPath()
    var scannersPath = NavigationPath()
    var settingsPath = NavigationPath()

    var showApprovalSheet = false
    var approvalToken: String?

    private init() {}

    func path(for tab: AppTab) -> Binding<NavigationPath> {
        switch tab {
        case .dashboard: return Binding(get: { self.dashboardPath }, set: { self.dashboardPath = $0 })
        case .pipelines: return Binding(get: { self.pipelinesPath }, set: { self.pipelinesPath = $0 })
        case .monitoring: return Binding(get: { self.monitoringPath }, set: { self.monitoringPath = $0 })
        case .scanners: return Binding(get: { self.scannersPath }, set: { self.scannersPath = $0 })
        case .settings: return Binding(get: { self.settingsPath }, set: { self.settingsPath = $0 })
        }
    }

    func navigateToExecution(id: String) {
        selectedTab = .monitoring
        monitoringPath = NavigationPath()
        monitoringPath.append(MonitoringDestination.executionDetail(id: id))
    }

    func navigateToExecutionReport(id: String) {
        selectedTab = .monitoring
        monitoringPath = NavigationPath()
        monitoringPath.append(MonitoringDestination.executionDetail(id: id))
        monitoringPath.append(MonitoringDestination.executionReport(id: id))
    }

    func navigateToPipeline(id: String) {
        selectedTab = .pipelines
        pipelinesPath = NavigationPath()
        pipelinesPath.append(PipelineDestination.builder(id: id))
    }

    func navigateToNewPipeline() {
        selectedTab = .pipelines
        pipelinesPath = NavigationPath()
        pipelinesPath.append(PipelineDestination.builder(id: nil))
    }

    func showApproval(token: String) {
        approvalToken = token
        showApprovalSheet = true
    }

    func popToRoot(tab: AppTab) {
        switch tab {
        case .dashboard: dashboardPath = NavigationPath()
        case .pipelines: pipelinesPath = NavigationPath()
        case .monitoring: monitoringPath = NavigationPath()
        case .scanners: scannersPath = NavigationPath()
        case .settings: settingsPath = NavigationPath()
        }
    }
}

// MARK: - Navigation Destinations

enum MonitoringDestination: Hashable {
    case executionDetail(id: String)
    case executionReport(id: String)
}

enum PipelineDestination: Hashable {
    case builder(id: String?)
}

enum SettingsDestination: Hashable {
    case profile
    case subscription
    case notifications
}
