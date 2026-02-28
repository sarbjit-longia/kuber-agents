import SwiftUI

struct ExecutionReportView: View {
    let executionId: String
    @State private var viewModel: ExecutionReportViewModel
    @State private var selectedSection = "executive_summary"
    @State private var isSharePresented = false
    @State private var pdfData: Data?
    @State private var isDownloadingPDF = false

    private let sections: [(id: String, title: String, icon: String)] = [
        ("executive_summary", "Summary", "doc.text"),
        ("ai_analysis", "AI Analysis", "brain"),
        ("strategy", "Strategy", "lightbulb"),
        ("risk", "Risk", "shield"),
        ("trade", "Trade", "arrow.left.arrow.right"),
        ("pnl", "P&L", "chart.line.uptrend.xyaxis"),
        ("agents", "Agents", "cpu"),
        ("timeline", "Timeline", "clock"),
        ("cost", "Cost", "dollarsign.circle"),
    ]

    init(executionId: String) {
        self.executionId = executionId
        _viewModel = State(initialValue: ExecutionReportViewModel(executionId: executionId))
    }

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                if viewModel.isLoading && viewModel.execution == nil {
                    LoadingView(message: "Loading report...")
                } else if let error = viewModel.errorMessage, viewModel.execution == nil {
                    EmptyStateView(
                        icon: "exclamationmark.triangle",
                        title: "Failed to Load Report",
                        message: error,
                        actionTitle: "Retry"
                    ) {
                        Task { await viewModel.loadReport() }
                    }
                } else {
                    LazyVStack(spacing: 0) {
                        // Section picker
                        sectionPicker(proxy: proxy)

                        // Error banner (non-blocking)
                        if let error = viewModel.errorMessage {
                            ErrorBanner(message: error) {
                                viewModel.errorMessage = nil
                            }
                            .padding(.top, 8)
                        }

                        // Sections
                        LazyVStack(spacing: 20) {
                            // Executive Summary
                            sectionContainer(id: "executive_summary") {
                                ExecutiveSummarySection(
                                    execution: viewModel.execution,
                                    summary: viewModel.executiveSummary
                                )
                            }

                            // AI Analysis
                            sectionContainer(id: "ai_analysis") {
                                AIAnalysisSection(
                                    analysis: viewModel.aiAnalysis,
                                    tradeAnalysis: viewModel.tradeAnalysis
                                )
                            }

                            // Strategy
                            sectionContainer(id: "strategy") {
                                StrategySection(strategy: viewModel.strategyDetails)
                            }

                            // Risk
                            sectionContainer(id: "risk") {
                                RiskSection(risk: viewModel.riskDetails)
                            }

                            // Trade Execution
                            sectionContainer(id: "trade") {
                                TradeExecutionSection(trade: viewModel.tradeExecution)
                            }

                            // P&L Summary
                            sectionContainer(id: "pnl") {
                                PnLSummarySection(pnl: viewModel.pnlSummary)
                            }

                            // Agent Reports
                            sectionContainer(id: "agents") {
                                AgentReportSection(
                                    agentReports: viewModel.agentReports,
                                    executionReports: viewModel.execution?.reports
                                )
                            }

                            // Timeline
                            sectionContainer(id: "timeline") {
                                ExecutionTimelineSection(
                                    timeline: viewModel.timeline,
                                    agentStates: viewModel.execution?.agentStates
                                )
                            }

                            // Cost Breakdown
                            sectionContainer(id: "cost") {
                                CostBreakdownSection(cost: viewModel.costBreakdown)
                            }
                        }
                        .padding(.horizontal)
                        .padding(.top, 12)
                        .padding(.bottom, 40)
                    }
                }
            }
        }
        .background(Color.surfaceBackground)
        .navigationTitle("Execution Report")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button {
                    Task { await downloadAndSharePDF() }
                } label: {
                    if isDownloadingPDF {
                        ProgressView()
                            .scaleEffect(0.8)
                    } else {
                        Image(systemName: "square.and.arrow.up")
                    }
                }
                .disabled(isDownloadingPDF)
            }
        }
        .sheet(isPresented: $isSharePresented) {
            if let pdfData {
                ShareSheet(activityItems: [pdfData])
            }
        }
        .task {
            await viewModel.loadReport()
        }
    }

    // MARK: - Section Picker

    @ViewBuilder
    private func sectionPicker(proxy: ScrollViewProxy) -> some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(sections, id: \.id) { section in
                    Button {
                        selectedSection = section.id
                        withAnimation(.easeInOut(duration: 0.3)) {
                            proxy.scrollTo(section.id, anchor: .top)
                        }
                    } label: {
                        HStack(spacing: 4) {
                            Image(systemName: section.icon)
                                .font(.caption2)
                            Text(section.title)
                                .font(.caption.weight(.medium))
                        }
                        .padding(.horizontal, 12)
                        .padding(.vertical, 8)
                        .background(
                            selectedSection == section.id
                                ? Color.brandPrimary.opacity(0.2)
                                : Color.surfaceElevated,
                            in: Capsule()
                        )
                        .foregroundStyle(
                            selectedSection == section.id ? .brandPrimary : .secondary
                        )
                    }
                }
            }
            .padding(.horizontal)
            .padding(.vertical, 8)
        }
        .background(Color.surfaceCard)
    }

    // MARK: - Section Container

    @ViewBuilder
    private func sectionContainer<Content: View>(
        id: String,
        @ViewBuilder content: () -> Content
    ) -> some View {
        content()
            .id(id)
    }

    // MARK: - PDF Download

    private func downloadAndSharePDF() async {
        isDownloadingPDF = true
        do {
            pdfData = try await viewModel.downloadPDF()
            isSharePresented = true
        } catch {
            viewModel.errorMessage = "Failed to download PDF: \(error.localizedDescription)"
        }
        isDownloadingPDF = false
    }
}

// MARK: - Share Sheet

struct ShareSheet: UIViewControllerRepresentable {
    let activityItems: [Any]

    func makeUIViewController(context: Context) -> UIActivityViewController {
        UIActivityViewController(activityItems: activityItems, applicationActivities: nil)
    }

    func updateUIViewController(_ uiViewController: UIActivityViewController, context: Context) {}
}

#Preview {
    NavigationStack {
        ExecutionReportView(executionId: "test-123")
    }
    .preferredColorScheme(.dark)
}
