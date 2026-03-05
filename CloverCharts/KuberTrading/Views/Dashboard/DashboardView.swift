import SwiftUI

struct DashboardView: View {
    @State private var viewModel = DashboardViewModel()
    @Environment(NavigationRouter.self) private var router

    var body: some View {
        ScrollView {
            if viewModel.isLoading && viewModel.data == nil {
                LoadingView(message: "Loading dashboard...")
            } else if let error = viewModel.errorMessage, viewModel.data == nil {
                EmptyStateView(
                    icon: "exclamationmark.triangle",
                    title: "Failed to Load",
                    message: error,
                    actionTitle: "Retry"
                ) {
                    Task { await viewModel.loadDashboard() }
                }
            } else if let data = viewModel.data {
                LazyVStack(spacing: 16) {
                    // Error banner (non-blocking)
                    if let error = viewModel.errorMessage {
                        ErrorBanner(message: error) {
                            viewModel.errorMessage = nil
                        }
                    }

                    // Stat Cards
                    statCardsSection(data)

                    // P&L Chart
                    PnLBarChartView(
                        data: viewModel.pnlChartData,
                        selectedDays: $viewModel.pnlChartDays
                    )
                    .padding(.horizontal)

                    // Cost Chart
                    CostBarChartView(
                        data: viewModel.costChartData,
                        selectedDays: $viewModel.costChartDays
                    )
                    .padding(.horizontal)

                    // Pipeline P&L Chart
                    if !data.pipelineList.isEmpty {
                        PipelinePnLChartView(pipelines: data.pipelineList)
                            .padding(.horizontal)
                    }

                    // Broker Accounts
                    if !data.brokerAccounts.isEmpty {
                        brokerAccountsSection(data.brokerAccounts)
                    }

                    // Active Positions
                    if !data.activePositions.isEmpty {
                        activePositionsSection(data.activePositions)
                    }

                    // Trade Stats
                    tradeStatsSection(data.tradeStats)

                    // Recent Executions
                    if !data.recentExecutions.isEmpty {
                        recentExecutionsSection(data.recentExecutions)
                    }

                    // Pipeline Summary
                    if !data.pipelineList.isEmpty {
                        pipelineSummarySection(data.pipelineList)
                    }

                    // Last updated
                    if let lastUpdated = viewModel.lastUpdated {
                        Text("Updated \(lastUpdated.relativeString)")
                            .font(.caption2)
                            .foregroundStyle(.tertiary)
                            .padding(.bottom, 20)
                    }
                }
                .padding(.top, 8)
            }
        }
        .refreshable {
            await viewModel.loadDashboard()
        }
        .navigationTitle("Dashboard")
        .task {
            await viewModel.loadDashboard()
            viewModel.startAutoRefresh()
        }
        .onDisappear {
            viewModel.stopAutoRefresh()
        }
    }

    // MARK: - Stat Cards

    @ViewBuilder
    private func statCardsSection(_ data: DashboardData) -> some View {
        LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 12) {
            StatCardView(
                title: "Active Pipelines",
                value: "\(data.pipelines.active)",
                icon: "arrow.triangle.branch",
                subtitle: "\(data.pipelines.total) total",
                tintColor: .brandPrimary
            )

            StatCardView(
                title: "Total P&L",
                value: data.pnl.totalRealized.pnlFormatted,
                icon: "chart.line.uptrend.xyaxis",
                subtitle: "Unrealized: \(data.pnl.totalUnrealized.pnlFormatted)",
                tintColor: Color.pnlColor(for: data.pnl.totalRealized)
            )

            StatCardView(
                title: "Executions Today",
                value: "\(data.today.executions)",
                icon: "play.circle",
                subtitle: "\(data.executions.running) running, \(data.executions.monitoring) monitoring",
                tintColor: .statusInfo
            )

            StatCardView(
                title: "Total Cost",
                value: data.executions.totalCost.costFormatted,
                icon: "dollarsign.circle",
                subtitle: "Today: \(data.today.cost.costFormatted)",
                tintColor: .statusWarning
            )
        }
        .padding(.horizontal)
    }

    // MARK: - Broker Accounts

    @ViewBuilder
    private func brokerAccountsSection(_ accounts: [BrokerAccount]) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Broker Accounts")
                .sectionHeader()
                .padding(.horizontal)

            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 12) {
                    ForEach(accounts) { account in
                        BrokerAccountCard(account: account)
                            .frame(width: 200)
                    }
                }
                .padding(.horizontal)
            }
        }
    }

    // MARK: - Active Positions

    @ViewBuilder
    private func activePositionsSection(_ positions: [ActivePosition]) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Active Positions")
                .sectionHeader()
                .padding(.horizontal)

            VStack(spacing: 0) {
                ForEach(positions) { position in
                    ActivePositionRow(position: position) {
                        router.navigateToExecution(id: position.executionId)
                    }
                    .padding(.horizontal)

                    if position.id != positions.last?.id {
                        Divider().padding(.horizontal)
                    }
                }
            }
            .cardStyle()
            .padding(.horizontal)
        }
    }

    // MARK: - Trade Stats

    @ViewBuilder
    private func tradeStatsSection(_ stats: TradeStats) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Trade Statistics")
                .sectionHeader()
                .padding(.horizontal)

            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible()), GridItem(.flexible())], spacing: 12) {
                tradeStatItem("Total Trades", "\(stats.totalTrades ?? 0)")
                tradeStatItem("Win Rate", (stats.winRate ?? 0).percentFormatted)
                tradeStatItem("Profit Factor", String(format: "%.2f", stats.profitFactor ?? 0))
                tradeStatItem("Avg Win", (stats.avgWin ?? 0).currencyFormatted)
                tradeStatItem("Avg Loss", (stats.avgLoss ?? 0).currencyFormatted)
                tradeStatItem("Best Trade", (stats.bestTrade ?? 0).currencyFormatted)
            }
            .cardStyle()
            .padding(.horizontal)
        }
    }

    @ViewBuilder
    private func tradeStatItem(_ label: String, _ value: String) -> some View {
        VStack(spacing: 4) {
            Text(value)
                .font(.subheadline.weight(.semibold))
            Text(label)
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
    }

    // MARK: - Recent Executions

    @ViewBuilder
    private func recentExecutionsSection(_ executions: [RecentExecution]) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Recent Executions")
                .sectionHeader()
                .padding(.horizontal)

            VStack(spacing: 0) {
                ForEach(executions.prefix(10)) { execution in
                    RecentExecutionRow(execution: execution) {
                        router.navigateToExecution(id: execution.executionId)
                    }
                    .padding(.horizontal)

                    if execution.id != executions.prefix(10).last?.id {
                        Divider().padding(.horizontal)
                    }
                }
            }
            .cardStyle()
            .padding(.horizontal)
        }
    }

    // MARK: - Pipeline Summary

    @ViewBuilder
    private func pipelineSummarySection(_ pipelines: [DashboardPipeline]) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Pipelines")
                .sectionHeader()
                .padding(.horizontal)

            VStack(spacing: 0) {
                ForEach(pipelines) { pipeline in
                    PipelineSummaryRow(pipeline: pipeline) {
                        router.navigateToPipeline(id: pipeline.id)
                    }
                    .padding(.horizontal)

                    if pipeline.id != pipelines.last?.id {
                        Divider().padding(.horizontal)
                    }
                }
            }
            .cardStyle()
            .padding(.horizontal)
        }
    }
}
