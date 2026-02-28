import SwiftUI

struct ExecutionLogsView: View {
    let logs: [ExecutionLog]

    @State private var filterLevel: String?
    @State private var filterAgentType: String?
    @State private var autoScroll = true

    private var filteredLogs: [ExecutionLog] {
        logs.filter { log in
            if let level = filterLevel, log.level?.lowercased() != level.lowercased() {
                return false
            }
            if let agentType = filterAgentType, log.agentType != agentType {
                return false
            }
            return true
        }
    }

    private var uniqueAgentTypes: [String] {
        Array(Set(logs.compactMap(\.agentType))).sorted()
    }

    var body: some View {
        VStack(spacing: 10) {
            // Filter controls
            filterBar

            // Logs
            if filteredLogs.isEmpty {
                emptyLogsView
            } else {
                logsContent
            }
        }
    }

    // MARK: - Filter Bar

    private var filterBar: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                // Level filters
                levelFilterPill(nil, "All")
                levelFilterPill("info", "Info")
                levelFilterPill("warning", "Warning")
                levelFilterPill("error", "Error")
                levelFilterPill("debug", "Debug")

                Divider()
                    .frame(height: 20)

                // Agent type filters
                if !uniqueAgentTypes.isEmpty {
                    Menu {
                        Button("All Agents") {
                            filterAgentType = nil
                        }
                        ForEach(uniqueAgentTypes, id: \.self) { agentType in
                            Button(agentType.replacingOccurrences(of: "_", with: " ").capitalized) {
                                filterAgentType = agentType
                            }
                        }
                    } label: {
                        HStack(spacing: 4) {
                            Image(systemName: "cpu")
                                .font(.caption2)

                            Text(filterAgentType?.replacingOccurrences(of: "_", with: " ").capitalized ?? "All Agents")
                                .font(.caption)
                        }
                        .foregroundStyle(filterAgentType != nil ? .white : .secondary)
                        .padding(.horizontal, 10)
                        .padding(.vertical, 5)
                        .background(
                            filterAgentType != nil ? Color.brandPrimary : Color.surfaceElevated,
                            in: Capsule()
                        )
                    }
                }
            }
        }
    }

    // MARK: - Level Filter Pill

    private func levelFilterPill(_ level: String?, _ label: String) -> some View {
        let isSelected = filterLevel == level

        return Button {
            filterLevel = level
        } label: {
            HStack(spacing: 4) {
                if let level {
                    Circle()
                        .fill(logLevelColor(level))
                        .frame(width: 6, height: 6)
                }

                Text(label)
                    .font(.caption)
            }
            .foregroundStyle(isSelected ? .white : .secondary)
            .padding(.horizontal, 10)
            .padding(.vertical, 5)
            .background(
                isSelected ? (level != nil ? logLevelColor(level!) : Color.brandPrimary) : Color.surfaceElevated,
                in: Capsule()
            )
        }
        .buttonStyle(.plain)
    }

    // MARK: - Empty Logs

    private var emptyLogsView: some View {
        VStack(spacing: 12) {
            Image(systemName: "doc.text.magnifyingglass")
                .font(.title2)
                .foregroundStyle(.secondary)

            Text(logs.isEmpty ? "No logs available" : "No logs match this filter")
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 40)
    }

    // MARK: - Logs Content

    private var logsContent: some View {
        ScrollViewReader { proxy in
            LazyVStack(alignment: .leading, spacing: 2) {
                ForEach(filteredLogs) { log in
                    logRow(log)
                        .id(log.id)
                }
            }
            .padding(8)
            .background(Color(red: 0.05, green: 0.05, blue: 0.07), in: RoundedRectangle(cornerRadius: 8))
            .onChange(of: filteredLogs.count) {
                if autoScroll, let lastLog = filteredLogs.last {
                    withAnimation {
                        proxy.scrollTo(lastLog.id, anchor: .bottom)
                    }
                }
            }
        }
    }

    // MARK: - Log Row

    private func logRow(_ log: ExecutionLog) -> some View {
        HStack(alignment: .top, spacing: 8) {
            // Timestamp
            Text(formatTimestamp(log.timestamp ?? ""))
                .font(.caption2.monospaced())
                .foregroundStyle(.tertiary)
                .frame(width: 65, alignment: .leading)

            // Level indicator
            Text((log.level ?? "I").prefix(1).uppercased())
                .font(.caption2.weight(.bold).monospaced())
                .foregroundStyle(logLevelColor(log.level ?? "info"))
                .frame(width: 12)

            // Agent type
            if let agentType = log.agentType {
                Text(abbreviatedAgentType(agentType))
                    .font(.caption2.monospaced())
                    .foregroundStyle(.brandPrimary)
                    .frame(width: 40, alignment: .leading)
            }

            // Message
            Text(log.message)
                .font(.caption2)
                .foregroundStyle(logMessageColor(log.level ?? "info"))
                .lineLimit(4)
        }
        .padding(.vertical, 2)
    }

    // MARK: - Helpers

    private func logLevelColor(_ level: String) -> Color {
        switch level.lowercased() {
        case "error", "critical": return .statusError
        case "warning", "warn": return .statusWarning
        case "info": return .primary
        case "debug": return .secondary
        default: return .secondary
        }
    }

    private func logMessageColor(_ level: String) -> Color {
        switch level.lowercased() {
        case "error", "critical": return .statusError
        case "warning", "warn": return .statusWarning
        default: return .primary
        }
    }

    private func formatTimestamp(_ timestamp: String) -> String {
        guard let date = timestamp.asDate else {
            return String(timestamp.suffix(8))
        }
        return date.timeString
    }

    private func abbreviatedAgentType(_ agentType: String) -> String {
        // Create abbreviation from agent type, e.g. "strategy_agent" -> "STRT"
        let parts = agentType.split(separator: "_")
        if parts.count >= 2, parts.last == "agent" {
            return String(parts.first?.prefix(4) ?? "").uppercased()
        }
        return String(agentType.prefix(4)).uppercased()
    }
}

#Preview {
    ScrollView {
        ExecutionLogsView(logs: [
            ExecutionLog(
                executionId: "e1",
                timestamp: "2024-01-15T10:30:00Z",
                level: "info",
                agentType: "market_data_agent",
                message: "Fetching market data for AAPL",
                details: nil
            ),
            ExecutionLog(
                executionId: "e1",
                timestamp: "2024-01-15T10:30:02Z",
                level: "info",
                agentType: "market_data_agent",
                message: "Retrieved 30 days of OHLCV data",
                details: nil
            ),
            ExecutionLog(
                executionId: "e1",
                timestamp: "2024-01-15T10:30:05Z",
                level: "warning",
                agentType: "strategy_agent",
                message: "Low confidence signal detected, proceeding with caution",
                details: nil
            ),
            ExecutionLog(
                executionId: "e1",
                timestamp: "2024-01-15T10:30:08Z",
                level: "error",
                agentType: "risk_manager_agent",
                message: "Position size exceeds maximum allowed risk per trade",
                details: nil
            ),
            ExecutionLog(
                executionId: "e1",
                timestamp: "2024-01-15T10:30:10Z",
                level: "debug",
                agentType: "risk_manager_agent",
                message: "Recalculating position size with adjusted risk parameters",
                details: nil
            ),
        ])
        .padding()
    }
    .preferredColorScheme(.dark)
}
