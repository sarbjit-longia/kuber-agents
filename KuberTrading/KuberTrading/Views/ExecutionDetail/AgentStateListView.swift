import SwiftUI

struct AgentStateListView: View {
    let agentStates: [AgentState]
    @State private var expandedAgentId: String?

    var body: some View {
        VStack(spacing: 8) {
            ForEach(agentStates) { state in
                agentStateRow(state)
            }
        }
    }

    // MARK: - Agent State Row

    private func agentStateRow(_ state: AgentState) -> some View {
        let isExpanded = expandedAgentId == state.agentId

        return VStack(spacing: 0) {
            // Header (always visible)
            Button {
                withAnimation(.easeInOut(duration: 0.2)) {
                    expandedAgentId = isExpanded ? nil : state.agentId
                }
            } label: {
                HStack(spacing: 12) {
                    // Status icon
                    statusIcon(for: state.status ?? "pending")
                        .frame(width: 28, height: 28)

                    // Agent info
                    VStack(alignment: .leading, spacing: 2) {
                        Text(state.agentName ?? (state.agentType ?? "Agent").replacingOccurrences(of: "_", with: " ").capitalized)
                            .font(.subheadline.weight(.medium))
                            .foregroundStyle(.primary)

                        HStack(spacing: 8) {
                            StatusBadge(status: state.status ?? "pending", size: .small)

                            if let duration = agentDuration(state) {
                                Text(duration)
                                    .font(.caption2)
                                    .foregroundStyle(.secondary)
                            }
                        }
                    }

                    Spacer()

                    // Cost
                    if let cost = state.cost {
                        Text(cost.costFormatted)
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(.statusWarning)
                    }

                    // Expand/collapse indicator
                    Image(systemName: "chevron.right")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .rotationEffect(.degrees(isExpanded ? 90 : 0))
                }
                .padding(12)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)

            // Expanded content
            if isExpanded {
                expandedContent(state)
                    .transition(.opacity.combined(with: .move(edge: .top)))
            }
        }
        .background(Color.surfaceCard, in: RoundedRectangle(cornerRadius: 10))
    }

    // MARK: - Expanded Content

    private func expandedContent(_ state: AgentState) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Divider()

            // Timing
            VStack(alignment: .leading, spacing: 4) {
                if let startedAt = state.startedAt {
                    HStack {
                        Text("Started")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Spacer()
                        Text(startedAt.formattedDateTime)
                            .font(.caption)
                    }
                }

                if let completedAt = state.completedAt {
                    HStack {
                        Text("Completed")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Spacer()
                        Text(completedAt.formattedDateTime)
                            .font(.caption)
                    }
                }
            }

            // Error
            if let error = state.errorMessage, !error.isEmpty {
                HStack(alignment: .top, spacing: 6) {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .font(.caption)
                        .foregroundStyle(.statusError)

                    Text(error)
                        .font(.caption)
                        .foregroundStyle(.statusError)
                }
                .padding(8)
                .background(Color.statusError.opacity(0.08), in: RoundedRectangle(cornerRadius: 6))
            }

            // Output
            if let output = state.output, !output.isNull {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Output")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.secondary)

                    if let dict = output.dictValue {
                        ForEach(dict.sorted(by: { $0.key < $1.key }), id: \.key) { key, value in
                            HStack(alignment: .top) {
                                Text(key.replacingOccurrences(of: "_", with: " ").capitalized)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                    .frame(minWidth: 80, alignment: .leading)

                                Text(formatOutputValue(value))
                                    .font(.caption)
                                    .foregroundStyle(.primary)
                                    .lineLimit(3)
                            }
                        }
                    } else if let str = output.stringValue {
                        Text(str)
                            .font(.caption)
                            .foregroundStyle(.primary)
                            .lineLimit(10)
                    } else {
                        Text(String(describing: output.value))
                            .font(.caption)
                            .foregroundStyle(.primary)
                            .lineLimit(5)
                    }
                }
                .padding(8)
                .background(Color.surfaceElevated, in: RoundedRectangle(cornerRadius: 6))
            }
        }
        .padding(.horizontal, 12)
        .padding(.bottom, 12)
    }

    // MARK: - Status Icon

    @ViewBuilder
    private func statusIcon(for status: String) -> some View {
        let color = Color.executionStatusColor(status)

        switch status.lowercased() {
        case "completed":
            Image(systemName: "checkmark.circle.fill")
                .foregroundStyle(color)
        case "running":
            ProgressView()
                .scaleEffect(0.7)
                .tint(color)
        case "failed":
            Image(systemName: "xmark.circle.fill")
                .foregroundStyle(color)
        case "pending":
            Image(systemName: "clock")
                .foregroundStyle(color)
        default:
            Image(systemName: "circle.fill")
                .foregroundStyle(color)
        }
    }

    // MARK: - Helpers

    private func agentDuration(_ state: AgentState) -> String? {
        guard let startStr = state.startedAt,
              let endStr = state.completedAt,
              let start = startStr.asDate,
              let end = endStr.asDate else {
            return nil
        }
        let seconds = Int(end.timeIntervalSince(start))
        return seconds.durationFormatted
    }

    private func formatOutputValue(_ value: Any) -> String {
        if let str = value as? String { return str }
        if let num = value as? Double { return String(format: "%.4f", num) }
        if let num = value as? Int { return "\(num)" }
        if let bool = value as? Bool { return bool ? "Yes" : "No" }
        if let arr = value as? [Any] { return "[\(arr.count) items]" }
        if let dict = value as? [String: Any] { return "{\(dict.count) keys}" }
        return String(describing: value)
    }
}

#Preview {
    ScrollView {
        AgentStateListView(agentStates: [
            AgentState(
                agentId: "market_data_agent",
                agentType: "market_data_agent",
                agentName: "Market Data Agent",
                status: "completed",
                startedAt: "2024-01-15T10:30:00Z",
                completedAt: "2024-01-15T10:30:05Z",
                errorMessage: nil,
                output: AnyCodable(["price": 185.50, "volume": 1234567]),
                cost: 0.05
            ),
            AgentState(
                agentId: "strategy_agent",
                agentType: "strategy_agent",
                agentName: "Strategy Agent",
                status: "running",
                startedAt: "2024-01-15T10:30:05Z",
                completedAt: nil,
                errorMessage: nil,
                output: nil,
                cost: 0.15
            ),
            AgentState(
                agentId: "risk_manager_agent",
                agentType: "risk_manager_agent",
                agentName: "Risk Manager",
                status: "pending",
                startedAt: nil,
                completedAt: nil,
                errorMessage: nil,
                output: nil,
                cost: nil
            ),
        ])
        .padding()
    }
    .preferredColorScheme(.dark)
}
