import SwiftUI

struct AgentReportSection: View {
    let agentReports: [[String: AnyCodable]]?
    let executionReports: [String: AgentReport]?

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label("Agent Reports", systemImage: "cpu")
                .font(.headline)

            if let reports = mergedReports, !reports.isEmpty {
                VStack(spacing: 12) {
                    ForEach(Array(reports.enumerated()), id: \.offset) { _, report in
                        AgentReportCard(report: report)
                    }
                }
            } else {
                noDataView
            }
        }
    }

    // MARK: - Merge Reports

    private var mergedReports: [AgentReportData]? {
        var results: [AgentReportData] = []

        // From execution.reports dict (typed)
        if let executionReports {
            for (_, report) in executionReports.sorted(by: { $0.key < $1.key }) {
                results.append(AgentReportData(
                    agentId: report.agentId ?? UUID().uuidString,
                    agentType: report.agentType ?? "unknown",
                    title: report.title ?? "Agent Report",
                    summary: report.summary ?? "",
                    status: report.status ?? "completed",
                    details: report.details,
                    metrics: report.metrics,
                    data: report.data
                ))
            }
        }

        // From executive report agent_reports array (untyped dicts)
        if let agentReports {
            for dict in agentReports {
                let agentId = dict["agent_id"]?.stringValue ?? dict["agentId"]?.stringValue ?? UUID().uuidString
                // Skip if already have from typed reports
                if results.contains(where: { $0.agentId == agentId }) { continue }

                results.append(AgentReportData(
                    agentId: agentId,
                    agentType: dict["agent_type"]?.stringValue ?? dict["agentType"]?.stringValue ?? "unknown",
                    title: dict["title"]?.stringValue ?? dict["name"]?.stringValue ?? "Agent Report",
                    summary: dict["summary"]?.stringValue ?? "",
                    status: dict["status"]?.stringValue ?? "completed",
                    details: dict["details"]?.stringValue,
                    metrics: extractMetrics(from: dict),
                    data: dict["data"]
                ))
            }
        }

        return results.isEmpty ? nil : results
    }

    private func extractMetrics(from dict: [String: AnyCodable]) -> [AgentReportMetric]? {
        guard let metricsValue = dict["metrics"],
              let array = metricsValue.arrayValue else {
            return nil
        }

        return array.compactMap { item -> AgentReportMetric? in
            guard let metricDict = item as? [String: Any],
                  let label = metricDict["label"] as? String else {
                return nil
            }
            return AgentReportMetric(
                label: label,
                value: AnyCodable(metricDict["value"] ?? ""),
                type: metricDict["type"] as? String
            )
        }
    }

    private var noDataView: some View {
        VStack(spacing: 8) {
            Image(systemName: "cpu")
                .font(.title2)
                .foregroundStyle(.secondary)
            Text("No agent reports available")
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 24)
        .cardStyle()
    }
}

// MARK: - Report Data (Unified)

struct AgentReportData {
    let agentId: String
    let agentType: String
    let title: String
    let summary: String
    let status: String
    let details: String?
    let metrics: [AgentReportMetric]?
    let data: AnyCodable?
}

// MARK: - Agent Report Card

struct AgentReportCard: View {
    let report: AgentReportData
    @State private var isExpanded = false

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Header
            Button {
                withAnimation(.easeInOut(duration: 0.2)) {
                    isExpanded.toggle()
                }
            } label: {
                HStack(spacing: 10) {
                    Image(systemName: agentIcon)
                        .font(.body)
                        .foregroundStyle(.brandPrimary)
                        .frame(width: 28, height: 28)
                        .background(Color.brandPrimary.opacity(0.15), in: Circle())

                    VStack(alignment: .leading, spacing: 2) {
                        Text(report.title)
                            .font(.subheadline.weight(.semibold))
                            .foregroundStyle(.primary)
                        Text(report.agentType.replacingOccurrences(of: "_", with: " ").capitalized)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }

                    Spacer()

                    StatusBadge(status: report.status, size: .small)

                    Image(systemName: "chevron.right")
                        .font(.caption)
                        .foregroundStyle(.tertiary)
                        .rotationEffect(.degrees(isExpanded ? 90 : 0))
                }
                .padding()
            }

            // Summary always visible
            if !report.summary.isEmpty {
                Text(report.summary)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .lineLimit(isExpanded ? nil : 2)
                    .padding(.horizontal)
                    .padding(.bottom, 8)
            }

            // Expanded content
            if isExpanded {
                Divider().padding(.horizontal)

                VStack(alignment: .leading, spacing: 12) {
                    // Metrics table
                    if let metrics = report.metrics, !metrics.isEmpty {
                        VStack(spacing: 0) {
                            ForEach(Array(metrics.enumerated()), id: \.offset) { index, metric in
                                HStack {
                                    Text(metric.label)
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                    Spacer()
                                    Text(formatMetricValue(metric))
                                        .font(.caption.weight(.medium))
                                        .foregroundStyle(metricColor(metric))
                                }
                                .padding(.vertical, 4)

                                if index < metrics.count - 1 {
                                    Divider()
                                }
                            }
                        }
                        .padding(12)
                        .background(Color.surfaceElevated, in: RoundedRectangle(cornerRadius: 8))
                    }

                    // Details text
                    if let details = report.details, !details.isEmpty {
                        VStack(alignment: .leading, spacing: 4) {
                            Text("Details")
                                .font(.caption.weight(.semibold))
                                .foregroundStyle(.secondary)
                            MarkdownView(content: details)
                                .font(.caption)
                        }
                    }
                }
                .padding()
            }
        }
        .background(Color.surfaceCard, in: RoundedRectangle(cornerRadius: 12))
    }

    // MARK: - Helpers

    private var agentIcon: String {
        switch report.agentType.lowercased() {
        case let t where t.contains("strategy"):
            return "lightbulb"
        case let t where t.contains("risk"):
            return "shield"
        case let t where t.contains("execution") || t.contains("trade"):
            return "arrow.left.arrow.right"
        case let t where t.contains("data") || t.contains("market"):
            return "chart.bar"
        case let t where t.contains("trigger"):
            return "bolt"
        case let t where t.contains("report"):
            return "doc.text"
        default:
            return "cpu"
        }
    }

    private func formatMetricValue(_ metric: AgentReportMetric) -> String {
        if let str = metric.value.stringValue { return str }
        if let dbl = metric.value.doubleValue {
            if metric.type == "currency" { return dbl.currencyFormatted }
            if metric.type == "percent" { return dbl.percentFormatted }
            if metric.type == "cost" { return dbl.costFormatted }
            return String(format: "%.4f", dbl)
        }
        if let intVal = metric.value.intValue { return "\(intVal)" }
        if let boolVal = metric.value.boolValue { return boolVal ? "Yes" : "No" }
        return String(describing: metric.value.value)
    }

    private func metricColor(_ metric: AgentReportMetric) -> Color {
        if metric.type == "pnl", let dbl = metric.value.doubleValue {
            return Color.pnlColor(for: dbl)
        }
        return .primary
    }
}

#Preview {
    ScrollView {
        AgentReportSection(
            agentReports: nil,
            executionReports: nil
        )
        .padding()
    }
    .background(Color.surfaceBackground)
    .preferredColorScheme(.dark)
}
