import SwiftUI

struct ExecutionDetailView: View {
    let executionId: String
    @State private var viewModel: ExecutionDetailViewModel
    @Environment(NavigationRouter.self) private var router
    @State private var selectedTab = 0

    init(executionId: String) {
        self.executionId = executionId
        _viewModel = State(initialValue: ExecutionDetailViewModel(executionId: executionId))
    }

    var body: some View {
        Group {
            if viewModel.isLoading && viewModel.execution == nil {
                LoadingView(message: "Loading execution...")
            } else if let error = viewModel.errorMessage, viewModel.execution == nil {
                EmptyStateView(
                    icon: "exclamationmark.triangle",
                    title: "Failed to Load",
                    message: error,
                    actionTitle: "Retry"
                ) {
                    Task { await viewModel.loadExecution() }
                }
            } else if let execution = viewModel.execution {
                executionContent(execution)
            }
        }
        .navigationTitle(viewModel.execution?.pipelineName ?? "Execution")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Menu {
                    toolbarActions
                } label: {
                    Image(systemName: "ellipsis.circle")
                }
            }
        }
        .task {
            await viewModel.loadExecution()
            await viewModel.loadLogs()
            viewModel.startLiveUpdates()
        }
        .onDisappear {
            viewModel.stopLiveUpdates()
        }
    }

    // MARK: - Execution Content

    private func executionContent(_ execution: Execution) -> some View {
        ScrollView {
            LazyVStack(spacing: 16) {
                // Error banner
                if let error = viewModel.errorMessage {
                    ErrorBanner(message: error) {
                        viewModel.errorMessage = nil
                    }
                }

                // Approval Banner
                if viewModel.showApprovalBanner {
                    ApprovalBanner(
                        execution: execution,
                        timeRemaining: viewModel.approvalTimeRemaining,
                        onApprove: {
                            Task { await viewModel.approveExecution() }
                        },
                        onReject: {
                            Task { await viewModel.rejectExecution() }
                        }
                    )
                    .padding(.horizontal)
                }

                // Monitoring Banner
                if viewModel.showMonitoringBanner {
                    MonitoringBanner(
                        execution: execution,
                        onClosePosition: {
                            Task { await viewModel.closePosition() }
                        }
                    )
                    .padding(.horizontal)
                }

                // Status Header
                statusHeader(execution)
                    .padding(.horizontal)

                // Tab Picker
                Picker("Section", selection: $selectedTab) {
                    Text("Agents").tag(0)
                    Text("Results").tag(1)
                    Text("Logs").tag(2)
                }
                .pickerStyle(.segmented)
                .padding(.horizontal)

                // Tab Content
                switch selectedTab {
                case 0:
                    if let states = execution.agentStates, !states.isEmpty {
                        AgentStateListView(agentStates: states)
                            .padding(.horizontal)
                    } else {
                        emptyTabContent("No agent states available", icon: "cpu")
                    }

                case 1:
                    ExecutionResultsView(execution: execution)
                        .padding(.horizontal)

                case 2:
                    ExecutionLogsView(logs: viewModel.logs)
                        .padding(.horizontal)

                default:
                    EmptyView()
                }

                // Navigation to report
                if execution.status == "completed" {
                    Button {
                        router.monitoringPath.append(
                            MonitoringDestination.executionReport(id: execution.id)
                        )
                    } label: {
                        Label("View Full Report", systemImage: "doc.text.magnifyingglass")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.large)
                    .padding(.horizontal)
                    .padding(.bottom, 16)
                }
            }
            .padding(.top, 8)
        }
    }

    // MARK: - Status Header

    private func statusHeader(_ execution: Execution) -> some View {
        VStack(spacing: 12) {
            HStack {
                StatusBadge(status: execution.status, size: .large)

                Spacer()

                if let symbol = execution.symbol, !symbol.isEmpty {
                    Text(symbol)
                        .font(.headline.weight(.bold))
                        .foregroundStyle(.brandPrimary)
                }
            }

            HStack(spacing: 16) {
                // Mode
                Label(execution.mode.capitalized, systemImage: execution.mode == "live" ? "bolt.fill" : "doc.text")
                    .font(.caption)
                    .foregroundStyle(execution.mode == "live" ? .accountLive : .accountPaper)

                // Started
                Label(execution.startedAt?.formattedRelative ?? "N/A", systemImage: "clock")
                    .font(.caption)
                    .foregroundStyle(.secondary)

                // Duration
                if let completedAt = execution.completedAt,
                   let start = execution.startedAt?.asDate,
                   let end = completedAt.asDate {
                    let durationSeconds = Int(end.timeIntervalSince(start))
                    Label(durationSeconds.durationFormatted, systemImage: "timer")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                Spacer()
            }

            // Cost
            if let cost = execution.costBreakdown {
                HStack {
                    Label("Total Cost", systemImage: "dollarsign.circle")
                        .font(.caption)
                        .foregroundStyle(.secondary)

                    Spacer()

                    Text((cost.totalCost ?? 0).costFormatted)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.statusWarning)
                }
            }

            // Error message
            if let error = execution.errorMessage, !error.isEmpty {
                HStack(alignment: .top, spacing: 8) {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .foregroundStyle(.statusError)

                    Text(error)
                        .font(.caption)
                        .foregroundStyle(.statusError)

                    Spacer()
                }
                .padding(10)
                .background(Color.statusError.opacity(0.08), in: RoundedRectangle(cornerRadius: 8))
            }
        }
        .padding()
        .background(Color.surfaceCard, in: RoundedRectangle(cornerRadius: 12))
    }

    // MARK: - Toolbar Actions

    @ViewBuilder
    private var toolbarActions: some View {
        let status = viewModel.execution?.status ?? ""

        if status == "running" {
            Button {
                Task { await viewModel.stopExecution() }
            } label: {
                Label("Stop Execution", systemImage: "stop.fill")
            }
        }

        if status == "monitoring" {
            Button {
                Task { await viewModel.closePosition() }
            } label: {
                Label("Close Position", systemImage: "xmark.circle")
            }
        }

        if ["running", "pending", "awaiting_approval"].contains(status) {
            Button(role: .destructive) {
                Task { await viewModel.cancelExecution() }
            } label: {
                Label("Cancel Execution", systemImage: "xmark")
            }
        }

        Button {
            Task {
                await viewModel.loadExecution()
                await viewModel.loadLogs()
            }
        } label: {
            Label("Refresh", systemImage: "arrow.clockwise")
        }
    }

    // MARK: - Empty Tab Content

    private func emptyTabContent(_ message: String, icon: String) -> some View {
        VStack(spacing: 12) {
            Image(systemName: icon)
                .font(.title2)
                .foregroundStyle(.secondary)

            Text(message)
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 40)
    }
}

#Preview {
    NavigationStack {
        ExecutionDetailView(executionId: "test-id")
    }
    .environment(NavigationRouter.shared)
    .preferredColorScheme(.dark)
}
