import SwiftUI

struct NotificationSettingsPane: View {
    @Bindable var viewModel: PipelineBuilderViewModel

    private let availableEvents: [(key: String, label: String, icon: String, description: String)] = [
        ("trade_executed", "Trade Executed", "checkmark.circle", "Get notified when a trade is executed."),
        ("position_closed", "Position Closed", "xmark.circle", "Get notified when a position is closed."),
        ("pipeline_failed", "Pipeline Failed", "exclamationmark.triangle", "Get notified when the pipeline encounters an error."),
        ("risk_rejected", "Risk Rejected", "shield.slash", "Get notified when the risk manager rejects a trade."),
    ]

    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            // Header
            Label("Notification Settings", systemImage: "bell")
                .font(.headline)

            Text("Configure when you want to receive notifications for this pipeline.")
                .font(.caption)
                .foregroundStyle(.secondary)

            // Enable Toggle
            Toggle(isOn: $viewModel.notificationEnabled) {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Enable Notifications")
                        .font(.subheadline.weight(.medium))

                    Text("Receive push notifications for pipeline events")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            .tint(.brandPrimary)

            // Event Selection
            if viewModel.notificationEnabled {
                VStack(alignment: .leading, spacing: 8) {
                    Text("Notification Events")
                        .font(.subheadline.weight(.medium))

                    ForEach(availableEvents, id: \.key) { event in
                        eventToggleRow(event)
                    }
                }
                .transition(.opacity.combined(with: .move(edge: .top)))
            }
        }
        .animation(.easeInOut(duration: 0.2), value: viewModel.notificationEnabled)
    }

    // MARK: - Event Toggle Row

    private func eventToggleRow(_ event: (key: String, label: String, icon: String, description: String)) -> some View {
        let isEnabled = viewModel.notificationEvents.contains(event.key)

        return Button {
            if isEnabled {
                viewModel.notificationEvents.removeAll { $0 == event.key }
            } else {
                viewModel.notificationEvents.append(event.key)
            }
        } label: {
            HStack(spacing: 12) {
                Image(systemName: isEnabled ? "checkmark.square.fill" : "square")
                    .font(.title3)
                    .foregroundStyle(isEnabled ? .brandPrimary : .secondary)

                Image(systemName: event.icon)
                    .font(.callout)
                    .foregroundStyle(isEnabled ? .brandPrimary : .secondary)
                    .frame(width: 24)

                VStack(alignment: .leading, spacing: 2) {
                    Text(event.label)
                        .font(.subheadline)
                        .foregroundStyle(.primary)

                    Text(event.description)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                Spacer()
            }
            .padding(10)
            .background(
                isEnabled ? Color.brandPrimary.opacity(0.06) : Color.surfaceElevated,
                in: RoundedRectangle(cornerRadius: 8)
            )
        }
        .buttonStyle(.plain)
    }
}

#Preview {
    ScrollView {
        NotificationSettingsPane(viewModel: {
            let vm = PipelineBuilderViewModel()
            vm.notificationEnabled = true
            vm.notificationEvents = ["trade_executed", "pipeline_failed"]
            return vm
        }())
        .padding()
    }
    .preferredColorScheme(.dark)
}
