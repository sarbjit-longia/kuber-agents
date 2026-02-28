import SwiftUI

struct AgentSlotListView: View {
    let slots: [PipelineBuilderViewModel.AgentSlot]
    let selectedAgentType: String?
    let onSelect: (String) -> Void

    var body: some View {
        ForEach(Array(slots.enumerated()), id: \.element.id) { index, slot in
            Button {
                onSelect(slot.agentType)
            } label: {
                HStack(spacing: 12) {
                    // Step number with connection line
                    ZStack {
                        // Vertical connector line
                        if index < slots.count - 1 {
                            VStack {
                                Spacer()
                                Rectangle()
                                    .fill(Color.surfaceElevated)
                                    .frame(width: 2, height: 20)
                            }
                            .offset(y: 20)
                        }

                        // Icon circle
                        Image(systemName: slot.icon)
                            .font(.callout)
                            .foregroundStyle(iconColor(for: slot))
                            .frame(width: 36, height: 36)
                            .background(
                                iconColor(for: slot).opacity(0.12),
                                in: Circle()
                            )
                            .overlay {
                                if selectedAgentType == slot.agentType {
                                    Circle()
                                        .stroke(Color.brandPrimary, lineWidth: 2)
                                }
                            }
                    }

                    // Agent info
                    VStack(alignment: .leading, spacing: 2) {
                        Text(slot.title)
                            .font(.subheadline.weight(.medium))
                            .foregroundStyle(.primary)

                        Text(slot.isConfigured ? "Configured" : "Not configured")
                            .font(.caption)
                            .foregroundStyle(slot.isConfigured ? .statusSuccess : .secondary)
                    }

                    Spacer()

                    // Configuration status indicator
                    Image(systemName: slot.isConfigured ? "checkmark.circle.fill" : "circle.dashed")
                        .font(.body)
                        .foregroundStyle(slot.isConfigured ? .statusSuccess : .secondary.opacity(0.5))
                }
                .padding(.vertical, 4)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .listRowBackground(
                selectedAgentType == slot.agentType
                    ? Color.brandPrimary.opacity(0.08)
                    : Color.clear
            )
        }
    }

    private func iconColor(for slot: PipelineBuilderViewModel.AgentSlot) -> Color {
        if selectedAgentType == slot.agentType {
            return .brandPrimary
        }
        return slot.isConfigured ? .statusSuccess : .secondary
    }
}

#Preview {
    List {
        Section("Agents") {
            AgentSlotListView(
                slots: [
                    .init(agentType: "market_data_agent", title: "Market Data Agent", icon: "chart.xyaxis.line", isConfigured: true),
                    .init(agentType: "bias_agent", title: "Bias Agent", icon: "safari", isConfigured: true),
                    .init(agentType: "strategy_agent", title: "Strategy Agent", icon: "brain", isConfigured: false),
                    .init(agentType: "risk_manager_agent", title: "Risk Manager", icon: "shield", isConfigured: false),
                    .init(agentType: "trade_manager_agent", title: "Trade Manager", icon: "dollarsign.circle", isConfigured: false),
                ],
                selectedAgentType: "bias_agent",
                onSelect: { _ in }
            )
        }
    }
    .listStyle(.insetGrouped)
    .preferredColorScheme(.dark)
}
