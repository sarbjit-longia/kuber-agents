import SwiftUI
import Charts

struct CostBreakdownSection: View {
    let cost: CostBreakdown?

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label("Cost Breakdown", systemImage: "dollarsign.circle")
                .font(.headline)

            if let cost {
                VStack(spacing: 16) {
                    // Total cost hero
                    totalCostCard(cost.totalCost ?? 0)

                    // Category breakdown
                    VStack(spacing: 0) {
                        costRow(label: "LLM Cost", value: cost.llmCost ?? 0, icon: "brain", color: .brandPrimary)
                        Divider().padding(.horizontal)
                        costRow(label: "Agent Rental", value: cost.agentRentalCost ?? 0, icon: "cpu", color: .brandSecondary)
                        Divider().padding(.horizontal)
                        costRow(label: "API Calls", value: cost.apiCallCost ?? 0, icon: "network", color: .statusInfo)
                    }
                    .cardStyle()

                    // Pie chart
                    if (cost.totalCost ?? 0) > 0 {
                        costPieChart(cost)
                    }

                    // By-agent breakdown
                    if let byAgent = cost.byAgent, !byAgent.isEmpty {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("By Agent")
                                .font(.subheadline.weight(.semibold))
                                .foregroundStyle(.secondary)

                            VStack(spacing: 0) {
                                ForEach(
                                    byAgent.sorted(by: { $0.value > $1.value }),
                                    id: \.key
                                ) { agentType, agentCost in
                                    HStack {
                                        Text(agentType
                                            .replacingOccurrences(of: "_", with: " ")
                                            .capitalized)
                                            .font(.subheadline)
                                            .foregroundStyle(.secondary)
                                        Spacer()
                                        Text(agentCost.costFormatted)
                                            .font(.subheadline.weight(.medium))

                                        if (cost.totalCost ?? 0) > 0 {
                                            Text(String(format: "(%.0f%%)", (agentCost / (cost.totalCost ?? 1)) * 100))
                                                .font(.caption)
                                                .foregroundStyle(.tertiary)
                                                .frame(width: 50, alignment: .trailing)
                                        }
                                    }
                                    .padding(.horizontal)
                                    .padding(.vertical, 8)

                                    if agentType != byAgent.sorted(by: { $0.value > $1.value }).last?.key {
                                        Divider().padding(.horizontal)
                                    }
                                }
                            }
                            .cardStyle()
                        }
                    }
                }
            } else {
                noDataView
            }
        }
    }

    // MARK: - Total Cost Card

    @ViewBuilder
    private func totalCostCard(_ total: Double) -> some View {
        VStack(spacing: 4) {
            Text("Total Cost")
                .font(.subheadline)
                .foregroundStyle(.secondary)
            Text(total.costFormatted)
                .font(.system(size: 28, weight: .bold, design: .rounded))
                .foregroundStyle(.statusWarning)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 16)
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(Color.statusWarning.opacity(0.08))
                .overlay(
                    RoundedRectangle(cornerRadius: 12)
                        .strokeBorder(Color.statusWarning.opacity(0.2), lineWidth: 1)
                )
        )
    }

    // MARK: - Cost Row

    @ViewBuilder
    private func costRow(label: String, value: Double, icon: String, color: Color) -> some View {
        HStack(spacing: 10) {
            Image(systemName: icon)
                .font(.caption)
                .foregroundStyle(color)
                .frame(width: 24, height: 24)
                .background(color.opacity(0.15), in: Circle())

            Text(label)
                .font(.subheadline)
                .foregroundStyle(.secondary)

            Spacer()

            Text(value.costFormatted)
                .font(.subheadline.weight(.medium))

            if let cost, (cost.totalCost ?? 0) > 0 {
                Text(String(format: "%.0f%%", (value / (cost.totalCost ?? 1)) * 100))
                    .font(.caption)
                    .foregroundStyle(.tertiary)
                    .frame(width: 40, alignment: .trailing)
            }
        }
        .padding(.horizontal)
        .padding(.vertical, 10)
    }

    // MARK: - Pie Chart

    @ViewBuilder
    private func costPieChart(_ cost: CostBreakdown) -> some View {
        let data: [(String, Double, Color)] = [
            ("LLM", cost.llmCost ?? 0, .brandPrimary),
            ("Agent", cost.agentRentalCost ?? 0, .brandSecondary),
            ("API", cost.apiCallCost ?? 0, .statusInfo),
        ].filter { $0.1 > 0 }

        Chart(data, id: \.0) { item in
            SectorMark(
                angle: .value("Cost", item.1),
                innerRadius: .ratio(0.6),
                angularInset: 2
            )
            .foregroundStyle(item.2)
            .annotation(position: .overlay) {
                if item.1 / (cost.totalCost ?? 1) > 0.1 {
                    Text(item.0)
                        .font(.caption2.weight(.bold))
                        .foregroundStyle(.white)
                }
            }
        }
        .frame(height: 160)
        .chartLegend(position: .bottom, spacing: 16)
        .cardStyle()
    }

    private var noDataView: some View {
        VStack(spacing: 8) {
            Image(systemName: "dollarsign.circle")
                .font(.title2)
                .foregroundStyle(.secondary)
            Text("No cost data available")
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 24)
        .cardStyle()
    }
}

#Preview {
    ScrollView {
        CostBreakdownSection(
            cost: CostBreakdown(
                totalCost: 0.0523,
                llmCost: 0.0312,
                agentRentalCost: 0.0150,
                apiCallCost: 0.0061,
                byAgent: [
                    "strategy_agent": 0.0200,
                    "risk_agent": 0.0112,
                    "execution_agent": 0.0150,
                    "reporting_agent": 0.0061,
                ]
            )
        )
        .padding()
    }
    .background(Color.surfaceBackground)
    .preferredColorScheme(.dark)
}
