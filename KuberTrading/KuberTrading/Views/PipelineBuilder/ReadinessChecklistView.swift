import SwiftUI

struct ReadinessChecklistView: View {
    let items: [PipelineBuilderViewModel.ReadinessItem]
    let isReady: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            // Overall status
            HStack(spacing: 8) {
                Image(systemName: isReady ? "checkmark.shield.fill" : "exclamationmark.shield")
                    .font(.title3)
                    .foregroundStyle(isReady ? .statusSuccess : .statusWarning)

                Text(isReady ? "Ready to Save" : "Not Ready")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(isReady ? .statusSuccess : .statusWarning)

                Spacer()

                Text("\(items.filter(\.isReady).count)/\(items.count)")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
            }

            // Individual items
            ForEach(items) { item in
                HStack(spacing: 10) {
                    Image(systemName: item.isReady ? "checkmark.circle.fill" : "xmark.circle")
                        .font(.callout)
                        .foregroundStyle(item.isReady ? .statusSuccess : .statusError)

                    Text(item.label)
                        .font(.caption)
                        .foregroundStyle(item.isReady ? .primary : .secondary)

                    Spacer()
                }
            }
        }
        .padding(12)
        .background(
            (isReady ? Color.statusSuccess : Color.statusWarning).opacity(0.06),
            in: RoundedRectangle(cornerRadius: 10)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 10)
                .stroke(
                    (isReady ? Color.statusSuccess : Color.statusWarning).opacity(0.2),
                    lineWidth: 1
                )
        )
    }
}

#Preview {
    VStack(spacing: 16) {
        ReadinessChecklistView(
            items: [
                .init(label: "Pipeline name", isReady: true),
                .init(label: "Bias Agent instructions", isReady: true),
                .init(label: "Strategy Agent instructions", isReady: false),
                .init(label: "Risk Manager instructions", isReady: false),
                .init(label: "Broker configured", isReady: true),
            ],
            isReady: false
        )

        ReadinessChecklistView(
            items: [
                .init(label: "Pipeline name", isReady: true),
                .init(label: "Bias Agent instructions", isReady: true),
                .init(label: "Strategy Agent instructions", isReady: true),
                .init(label: "Risk Manager instructions", isReady: true),
                .init(label: "Broker configured", isReady: true),
            ],
            isReady: true
        )
    }
    .padding()
    .preferredColorScheme(.dark)
}
