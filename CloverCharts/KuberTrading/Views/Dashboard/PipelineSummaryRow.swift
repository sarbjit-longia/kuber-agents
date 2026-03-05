import SwiftUI

struct PipelineSummaryRow: View {
    let pipeline: DashboardPipeline
    var onTap: (() -> Void)?

    var body: some View {
        Button {
            onTap?()
        } label: {
            HStack(spacing: 12) {
                Circle()
                    .fill(pipeline.isActive ? Color.statusSuccess : Color.secondary.opacity(0.3))
                    .frame(width: 8, height: 8)

                VStack(alignment: .leading, spacing: 2) {
                    Text(pipeline.name)
                        .font(.subheadline.weight(.medium))
                        .lineLimit(1)

                    HStack(spacing: 6) {
                        Label((pipeline.triggerMode ?? "periodic").capitalized, systemImage: pipeline.triggerMode == "signal" ? "antenna.radiowaves.left.and.right" : "clock")
                            .font(.caption2)
                            .foregroundStyle(.secondary)

                        Text("\(pipeline.totalExecutions ?? 0) runs")
                            .font(.caption2)
                            .foregroundStyle(.tertiary)
                    }
                }

                Spacer()

                PnLText(value: pipeline.totalPnl ?? 0)
                    .font(.subheadline)
            }
            .padding(.vertical, 4)
        }
        .buttonStyle(.plain)
    }
}
