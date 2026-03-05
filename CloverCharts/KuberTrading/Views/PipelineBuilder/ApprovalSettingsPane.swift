import SwiftUI

struct ApprovalSettingsPane: View {
    @Bindable var viewModel: PipelineBuilderViewModel

    private let availableModes = ["live", "paper"]
    private let availableChannels = ["web", "sms", "telegram"]
    private let timeoutRange = 1...120

    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            // Header
            Label("Trade Approval", systemImage: "checkmark.shield")
                .font(.headline)

            Text("Require manual approval before trades are executed. This adds a safety step where you must approve or reject each trade.")
                .font(.caption)
                .foregroundStyle(.secondary)

            // Require Approval Toggle
            Toggle(isOn: $viewModel.requireApproval) {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Require Approval")
                        .font(.subheadline.weight(.medium))

                    Text("Trades will wait for your approval before execution")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            .tint(.brandPrimary)

            if viewModel.requireApproval {
                approvalSettings
                    .transition(.opacity.combined(with: .move(edge: .top)))
            }
        }
        .animation(.easeInOut(duration: 0.2), value: viewModel.requireApproval)
    }

    // MARK: - Approval Settings Content

    private var approvalSettings: some View {
        VStack(alignment: .leading, spacing: 20) {
            // Approval Modes
            VStack(alignment: .leading, spacing: 8) {
                Text("Approval Modes")
                    .font(.subheadline.weight(.medium))

                Text("Select which execution modes require approval.")
                    .font(.caption)
                    .foregroundStyle(.secondary)

                ForEach(availableModes, id: \.self) { mode in
                    modeToggleRow(mode)
                }
            }

            // Timeout
            VStack(alignment: .leading, spacing: 8) {
                HStack {
                    Text("Approval Timeout")
                        .font(.subheadline.weight(.medium))

                    Spacer()

                    Text("\(viewModel.approvalTimeoutMinutes) min")
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(.brandPrimary)
                }

                Text("Time before the approval request expires. The trade will be rejected after timeout.")
                    .font(.caption)
                    .foregroundStyle(.secondary)

                Stepper(
                    "\(viewModel.approvalTimeoutMinutes) minutes",
                    value: $viewModel.approvalTimeoutMinutes,
                    in: timeoutRange,
                    step: 5
                )
                .padding(10)
                .background(Color.surfaceElevated, in: RoundedRectangle(cornerRadius: 8))
            }

            // Channels
            VStack(alignment: .leading, spacing: 8) {
                Text("Notification Channels")
                    .font(.subheadline.weight(.medium))

                Text("How you want to be notified when approval is needed.")
                    .font(.caption)
                    .foregroundStyle(.secondary)

                ForEach(availableChannels, id: \.self) { channel in
                    channelToggleRow(channel)
                }
            }

            // Phone Number (shown when SMS selected)
            if viewModel.approvalChannels.contains("sms") {
                VStack(alignment: .leading, spacing: 6) {
                    Text("Phone Number")
                        .font(.subheadline.weight(.medium))

                    Text("Required for SMS approval notifications.")
                        .font(.caption)
                        .foregroundStyle(.secondary)

                    TextField("+1 (555) 123-4567", text: $viewModel.approvalPhone)
                        .textFieldStyle(.plain)
                        .padding(10)
                        .background(Color.surfaceElevated, in: RoundedRectangle(cornerRadius: 8))
                        .keyboardType(.phonePad)
                        .textContentType(.telephoneNumber)
                }
                .transition(.opacity.combined(with: .move(edge: .top)))
            }
        }
    }

    // MARK: - Mode Toggle Row

    private func modeToggleRow(_ mode: String) -> some View {
        let isSelected = viewModel.approvalModes.contains(mode)

        return Button {
            if isSelected {
                viewModel.approvalModes.removeAll { $0 == mode }
            } else {
                viewModel.approvalModes.append(mode)
            }
        } label: {
            HStack(spacing: 12) {
                Image(systemName: isSelected ? "checkmark.square.fill" : "square")
                    .font(.title3)
                    .foregroundStyle(isSelected ? .brandPrimary : .secondary)

                Image(systemName: mode == "live" ? "bolt.fill" : "doc.text")
                    .font(.callout)
                    .foregroundStyle(modeColor(mode))
                    .frame(width: 24)

                VStack(alignment: .leading, spacing: 2) {
                    Text(mode.capitalized)
                        .font(.subheadline)
                        .foregroundStyle(.primary)

                    Text(modeDescription(mode))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                Spacer()
            }
            .padding(10)
            .background(
                isSelected ? Color.brandPrimary.opacity(0.06) : Color.surfaceElevated,
                in: RoundedRectangle(cornerRadius: 8)
            )
        }
        .buttonStyle(.plain)
    }

    // MARK: - Channel Toggle Row

    private func channelToggleRow(_ channel: String) -> some View {
        let isSelected = viewModel.approvalChannels.contains(channel)

        return Button {
            if isSelected {
                viewModel.approvalChannels.removeAll { $0 == channel }
            } else {
                viewModel.approvalChannels.append(channel)
            }
        } label: {
            HStack(spacing: 12) {
                Image(systemName: isSelected ? "checkmark.square.fill" : "square")
                    .font(.title3)
                    .foregroundStyle(isSelected ? .brandPrimary : .secondary)

                Image(systemName: channelIcon(channel))
                    .font(.callout)
                    .foregroundStyle(.brandPrimary)
                    .frame(width: 24)

                VStack(alignment: .leading, spacing: 2) {
                    Text(channelLabel(channel))
                        .font(.subheadline)
                        .foregroundStyle(.primary)

                    Text(channelDescription(channel))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                Spacer()
            }
            .padding(10)
            .background(
                isSelected ? Color.brandPrimary.opacity(0.06) : Color.surfaceElevated,
                in: RoundedRectangle(cornerRadius: 8)
            )
        }
        .buttonStyle(.plain)
    }

    // MARK: - Helpers

    private func modeColor(_ mode: String) -> Color {
        switch mode {
        case "live": return .accountLive
        case "paper": return .accountPaper
        default: return .secondary
        }
    }

    private func modeDescription(_ mode: String) -> String {
        switch mode {
        case "live": return "Require approval for real money trades"
        case "paper": return "Require approval for paper trades"
        default: return ""
        }
    }

    private func channelIcon(_ channel: String) -> String {
        switch channel {
        case "web": return "globe"
        case "sms": return "message"
        case "telegram": return "paperplane"
        default: return "bell"
        }
    }

    private func channelLabel(_ channel: String) -> String {
        switch channel {
        case "web": return "Web / Push Notification"
        case "sms": return "SMS"
        case "telegram": return "Telegram"
        default: return channel.capitalized
        }
    }

    private func channelDescription(_ channel: String) -> String {
        switch channel {
        case "web": return "Receive approval requests via push notification and in-app"
        case "sms": return "Receive approval requests via text message"
        case "telegram": return "Receive approval requests via Telegram bot"
        default: return ""
        }
    }
}

#Preview {
    ScrollView {
        ApprovalSettingsPane(viewModel: {
            let vm = PipelineBuilderViewModel()
            vm.requireApproval = true
            vm.approvalModes = ["live"]
            vm.approvalChannels = ["web", "sms"]
            vm.approvalPhone = "+1234567890"
            return vm
        }())
        .padding()
    }
    .preferredColorScheme(.dark)
}
