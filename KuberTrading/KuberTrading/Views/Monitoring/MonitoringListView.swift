import SwiftUI

struct MonitoringListView: View {
    @State private var viewModel = MonitoringListViewModel()
    @Environment(NavigationRouter.self) private var router

    var body: some View {
        Group {
            if viewModel.isLoading && viewModel.executions.isEmpty {
                LoadingView(message: "Loading executions...")
            } else if let error = viewModel.errorMessage, viewModel.executions.isEmpty {
                EmptyStateView(
                    icon: "exclamationmark.triangle",
                    title: "Failed to Load",
                    message: error,
                    actionTitle: "Retry"
                ) {
                    Task { await viewModel.refresh() }
                }
            } else if viewModel.executions.isEmpty && viewModel.statusFilter == nil {
                EmptyStateView(
                    icon: "eye.slash",
                    title: "No Executions",
                    message: "Execute a pipeline to see monitoring data here.",
                    actionTitle: "Go to Pipelines"
                ) {
                    router.selectedTab = .pipelines
                }
            } else {
                executionContent
            }
        }
        .navigationTitle("Monitoring")
        .refreshable {
            await viewModel.refresh()
        }
        .task {
            await viewModel.refresh()
        }
    }

    // MARK: - Execution Content

    private var executionContent: some View {
        ScrollView {
            LazyVStack(spacing: 0) {
                // Error banner (non-blocking)
                if let error = viewModel.errorMessage {
                    ErrorBanner(message: error) {
                        viewModel.errorMessage = nil
                    }
                    .padding(.bottom, 8)
                }

                // Stats summary
                if let stats = viewModel.stats {
                    statsRow(stats)
                        .padding(.horizontal)
                        .padding(.bottom, 8)
                }

                // Timeline chart
                ExecutionTimelineChart(executions: viewModel.executions)
                    .padding(.horizontal)
                    .padding(.bottom, 12)

                // Filter bar
                ExecutionFilterBar(
                    selectedFilter: viewModel.statusFilter,
                    onFilterChanged: { viewModel.setStatusFilter($0) }
                )
                .padding(.bottom, 8)

                // Execution list
                if viewModel.executions.isEmpty {
                    VStack(spacing: 12) {
                        Image(systemName: "magnifyingglass")
                            .font(.title2)
                            .foregroundStyle(.secondary)

                        Text("No executions match this filter")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                    }
                    .padding(.vertical, 40)
                } else {
                    LazyVStack(spacing: 0) {
                        ForEach(viewModel.executions) { execution in
                            Button {
                                router.monitoringPath.append(
                                    MonitoringDestination.executionDetail(id: execution.id)
                                )
                            } label: {
                                ExecutionRow(execution: execution)
                                    .padding(.horizontal)
                                    .padding(.vertical, 8)
                            }
                            .buttonStyle(.plain)

                            if execution.id != viewModel.executions.last?.id {
                                Divider()
                                    .padding(.horizontal)
                            }
                        }
                    }
                    .background(Color.surfaceCard, in: RoundedRectangle(cornerRadius: 12))
                    .padding(.horizontal)
                }

                // Load more
                if viewModel.executions.count < viewModel.total {
                    ProgressView()
                        .padding(.vertical, 20)
                        .onAppear {
                            Task { await viewModel.loadMore() }
                        }
                }

                // Total count
                if !viewModel.executions.isEmpty {
                    Text("Showing \(viewModel.executions.count) of \(viewModel.total)")
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                        .padding(.vertical, 12)
                }
            }
            .padding(.top, 8)
        }
    }

    // MARK: - Stats Row

    private func statsRow(_ stats: ExecutionStats) -> some View {
        HStack(spacing: 0) {
            statItem("Total", "\(stats.totalExecutions ?? 0)", .secondary)
            Divider().frame(height: 30)
            statItem("Running", "\(stats.runningExecutions ?? 0)", .brandPrimary)
            Divider().frame(height: 30)
            statItem("Completed", "\(stats.completedExecutions ?? 0)", .statusWarning)
            Divider().frame(height: 30)
            statItem("Success", (stats.successRate ?? 0).percentFormatted, .statusSuccess)
        }
        .padding(.vertical, 8)
        .background(Color.surfaceCard, in: RoundedRectangle(cornerRadius: 10))
    }

    private func statItem(_ label: String, _ value: String, _ color: Color) -> some View {
        VStack(spacing: 2) {
            Text(value)
                .font(.caption.weight(.bold))
                .foregroundStyle(color)
            Text(label)
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
    }
}

#Preview {
    NavigationStack {
        MonitoringListView()
    }
    .environment(NavigationRouter.shared)
    .preferredColorScheme(.dark)
}
