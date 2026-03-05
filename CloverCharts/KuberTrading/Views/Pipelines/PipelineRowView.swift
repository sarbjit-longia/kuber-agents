import SwiftUI

struct PipelineRowView: View {
    let pipeline: Pipeline
    var onToggleActive: () -> Void

    var body: some View {
        HStack(spacing: 12) {
            // Trigger mode icon
            Image(systemName: triggerIcon)
                .font(.title3)
                .foregroundStyle(pipeline.isActive ? .brandPrimary : .secondary)
                .frame(width: 36, height: 36)
                .background(
                    (pipeline.isActive ? Color.brandPrimary : Color.secondary).opacity(0.12),
                    in: RoundedRectangle(cornerRadius: 8)
                )

            // Pipeline info
            VStack(alignment: .leading, spacing: 4) {
                Text(pipeline.name)
                    .font(.subheadline.weight(.semibold))
                    .lineLimit(1)

                HStack(spacing: 8) {
                    // Trigger mode badge
                    modeBadge

                    if let description = pipeline.description, !description.isEmpty {
                        Text(description)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                    }
                }
            }

            Spacer()

            // Active toggle
            Toggle("", isOn: Binding(
                get: { pipeline.isActive },
                set: { _ in onToggleActive() }
            ))
            .labelsHidden()
            .tint(.brandPrimary)
        }
        .padding(.vertical, 4)
    }

    // MARK: - Trigger Icon

    private var triggerIcon: String {
        switch pipeline.triggerMode {
        case "signal":
            return "antenna.radiowaves.left.and.right"
        case "periodic":
            return "clock.arrow.circlepath"
        default:
            return "arrow.triangle.branch"
        }
    }

    // MARK: - Mode Badge

    private var modeBadge: some View {
        Text(pipeline.triggerMode.capitalized)
            .font(.caption2.weight(.medium))
            .foregroundStyle(modeBadgeColor)
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(modeBadgeColor.opacity(0.12), in: Capsule())
    }

    private var modeBadgeColor: Color {
        switch pipeline.triggerMode {
        case "signal": return .statusWarning
        case "periodic": return .brandPrimary
        default: return .secondary
        }
    }
}

#Preview {
    List {
        PipelineRowView(
            pipeline: Pipeline(
                id: "1",
                userId: "u1",
                name: "Morning Momentum Scanner",
                description: "Scans for momentum signals at market open",
                config: PipelineConfig(
                    symbol: nil,
                    mode: "paper",
                    brokerTool: nil,
                    nodes: [],
                    edges: []
                ),
                isActive: true,
                triggerMode: "signal",
                scannerId: nil,
                signalSubscriptions: nil,
                scannerTickers: nil,
                notificationEnabled: true,
                notificationEvents: nil,
                requireApproval: false,
                approvalModes: nil,
                approvalTimeoutMinutes: 15,
                approvalChannels: nil,
                approvalPhone: nil,
                createdAt: "2024-01-01",
                updatedAt: "2024-01-01"
            ),
            onToggleActive: {}
        )

        PipelineRowView(
            pipeline: Pipeline(
                id: "2",
                userId: "u1",
                name: "Weekly Rebalancer",
                description: nil,
                config: PipelineConfig(
                    symbol: nil,
                    mode: "paper",
                    brokerTool: nil,
                    nodes: [],
                    edges: []
                ),
                isActive: false,
                triggerMode: "periodic",
                scannerId: nil,
                signalSubscriptions: nil,
                scannerTickers: nil,
                notificationEnabled: false,
                notificationEvents: nil,
                requireApproval: true,
                approvalModes: nil,
                approvalTimeoutMinutes: 15,
                approvalChannels: nil,
                approvalPhone: nil,
                createdAt: "2024-01-01",
                updatedAt: "2024-01-01"
            ),
            onToggleActive: {}
        )
    }
    .listStyle(.insetGrouped)
    .preferredColorScheme(.dark)
}
