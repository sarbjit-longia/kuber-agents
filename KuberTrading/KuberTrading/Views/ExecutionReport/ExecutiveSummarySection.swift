import SwiftUI

struct ExecutiveSummarySection: View {
    let execution: Execution?
    let summary: [String: AnyCodable]?

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label("Executive Summary", systemImage: "doc.text")
                .font(.headline)

            if let execution {
                VStack(spacing: 0) {
                    summaryRow(label: "Pipeline", value: execution.pipelineName ?? "Unknown")
                    Divider().padding(.horizontal)
                    summaryRow(label: "Symbol", value: execution.symbol ?? "N/A")
                    Divider().padding(.horizontal)
                    summaryRow(label: "Mode", value: execution.mode.capitalized) {
                        modeIcon(execution.mode)
                    }
                    Divider().padding(.horizontal)
                    summaryRow(label: "Status", value: execution.status) {
                        StatusBadge(status: execution.status, size: .small)
                    }
                    Divider().padding(.horizontal)
                    summaryRow(label: "Duration", value: durationString)
                    Divider().padding(.horizontal)

                    if let totalCost = execution.costBreakdown?.totalCost {
                        summaryRow(label: "Total Cost", value: totalCost.costFormatted)
                        Divider().padding(.horizontal)
                    }

                    // Overall P&L from summary dict
                    if let pnlValue = extractDouble("overall_pnl") ?? extractDouble("total_pnl") {
                        HStack {
                            Text("Overall P&L")
                                .font(.subheadline)
                                .foregroundStyle(.secondary)
                            Spacer()
                            PnLText(value: pnlValue)
                                .font(.subheadline.weight(.semibold))
                        }
                        .padding(.horizontal)
                        .padding(.vertical, 10)
                    }

                    // Summary text if available
                    if let summaryText = extractString("summary") ?? extractString("description") {
                        Divider().padding(.horizontal)
                        Text(summaryText)
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                            .padding()
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                }
                .cardStyle()
            } else {
                noDataView
            }
        }
    }

    // MARK: - Row

    @ViewBuilder
    private func summaryRow(
        label: String,
        value: String,
        @ViewBuilder trailing: () -> some View = { EmptyView() }
    ) -> some View {
        HStack {
            Text(label)
                .font(.subheadline)
                .foregroundStyle(.secondary)
            Spacer()
            trailing()
            if !(trailing() is EmptyView) {
                // Custom trailing provided
            } else {
                Text(value)
                    .font(.subheadline.weight(.medium))
            }
        }
        .padding(.horizontal)
        .padding(.vertical, 10)
    }

    @ViewBuilder
    private func modeIcon(_ mode: String) -> some View {
        HStack(spacing: 4) {
            Circle()
                .fill(mode.lowercased() == "live" ? Color.accountLive : Color.accountPaper)
                .frame(width: 8, height: 8)
            Text(mode.capitalized)
                .font(.subheadline.weight(.medium))
        }
    }

    private var noDataView: some View {
        VStack(spacing: 8) {
            Image(systemName: "doc.text")
                .font(.title2)
                .foregroundStyle(.secondary)
            Text("No summary data available")
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 24)
        .cardStyle()
    }

    // MARK: - Helpers

    private var durationString: String {
        guard let execution else { return "N/A" }
        guard let startDate = execution.startedAt?.asDate else { return "N/A" }
        let endDate = execution.completedAt?.asDate ?? Date()
        let seconds = Int(endDate.timeIntervalSince(startDate))
        return seconds.durationFormatted
    }

    private func extractString(_ key: String) -> String? {
        summary?[key]?.stringValue
    }

    private func extractDouble(_ key: String) -> Double? {
        if let val = summary?[key]?.doubleValue { return val }
        if let val = summary?[key]?.intValue { return Double(val) }
        return nil
    }
}

#Preview {
    ScrollView {
        ExecutiveSummarySection(
            execution: nil,
            summary: nil
        )
        .padding()
    }
    .background(Color.surfaceBackground)
    .preferredColorScheme(.dark)
}
