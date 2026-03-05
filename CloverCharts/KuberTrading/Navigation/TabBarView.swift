import SwiftUI

struct TabBarView: View {
    @Environment(NavigationRouter.self) private var router

    var body: some View {
        @Bindable var router = router

        TabView(selection: $router.selectedTab) {
            NavigationStack(path: router.path(for: .dashboard)) {
                DashboardView()
                    .navigationDestination(for: MonitoringDestination.self) { dest in
                        destinationView(for: dest)
                    }
            }
            .tabItem {
                Label(AppTab.dashboard.title, systemImage: AppTab.dashboard.icon)
            }
            .tag(AppTab.dashboard)

            NavigationStack(path: router.path(for: .pipelines)) {
                PipelineListView()
                    .navigationDestination(for: PipelineDestination.self) { dest in
                        switch dest {
                        case .builder(let id):
                            PipelineBuilderView(pipelineId: id)
                        }
                    }
            }
            .tabItem {
                Label(AppTab.pipelines.title, systemImage: AppTab.pipelines.icon)
            }
            .tag(AppTab.pipelines)

            NavigationStack(path: router.path(for: .monitoring)) {
                MonitoringListView()
                    .navigationDestination(for: MonitoringDestination.self) { dest in
                        destinationView(for: dest)
                    }
            }
            .tabItem {
                Label(AppTab.monitoring.title, systemImage: AppTab.monitoring.icon)
            }
            .tag(AppTab.monitoring)

            NavigationStack(path: router.path(for: .scanners)) {
                ScannerListView()
            }
            .tabItem {
                Label(AppTab.scanners.title, systemImage: AppTab.scanners.icon)
            }
            .tag(AppTab.scanners)

            NavigationStack(path: router.path(for: .settings)) {
                SettingsView()
            }
            .tabItem {
                Label(AppTab.settings.title, systemImage: AppTab.settings.icon)
            }
            .tag(AppTab.settings)
        }
        .tint(.blue)
        .fullScreenCover(isPresented: $router.showApprovalSheet) {
            if let token = router.approvalToken {
                ApprovalDeepLinkView(token: token)
            }
        }
    }

    @ViewBuilder
    private func destinationView(for dest: MonitoringDestination) -> some View {
        switch dest {
        case .executionDetail(let id):
            ExecutionDetailView(executionId: id)
        case .executionReport(let id):
            ExecutionReportView(executionId: id)
        }
    }
}
