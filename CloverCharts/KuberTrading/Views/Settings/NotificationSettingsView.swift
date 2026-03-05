import SwiftUI

struct NotificationSettingsView: View {
    @Bindable var viewModel: SettingsViewModel
    @State private var pushAuthorized = PushNotificationService.shared.isAuthorized
    @State private var isRequestingPermission = false

    private let notificationCategories = [
        ("Execution Started", "play.circle", "pipeline_started"),
        ("Execution Completed", "checkmark.circle", "pipeline_completed"),
        ("Execution Failed", "exclamationmark.triangle", "pipeline_failed"),
        ("Approval Required", "hand.raised", "approval_required"),
        ("Trade Executed", "arrow.left.arrow.right", "trade_executed"),
        ("Position Closed", "xmark.circle", "position_closed"),
        ("Signal Detected", "antenna.radiowaves.left.and.right", "signal_detected"),
    ]

    var body: some View {
        Form {
            // Push Notifications
            Section {
                HStack {
                    Label("Push Notifications", systemImage: "bell.badge.fill")

                    Spacer()

                    if pushAuthorized {
                        Text("Enabled")
                            .font(.subheadline)
                            .foregroundStyle(.statusSuccess)
                    } else {
                        Button {
                            Task { await requestPushPermission() }
                        } label: {
                            if isRequestingPermission {
                                ProgressView()
                                    .scaleEffect(0.8)
                            } else {
                                Text("Enable")
                                    .font(.subheadline.weight(.medium))
                            }
                        }
                        .disabled(isRequestingPermission)
                    }
                }
            } header: {
                Text("Push Notifications")
            } footer: {
                if !pushAuthorized {
                    Text("Enable push notifications to receive real-time alerts for pipeline executions, trade approvals, and signals.")
                }
            }

            // Notification categories
            if pushAuthorized {
                Section {
                    ForEach(notificationCategories, id: \.2) { category in
                        HStack {
                            Image(systemName: category.1)
                                .font(.body)
                                .foregroundStyle(.brandPrimary)
                                .frame(width: 28)

                            Text(category.0)
                                .font(.subheadline)

                            Spacer()

                            Image(systemName: "checkmark.circle.fill")
                                .font(.caption)
                                .foregroundStyle(.statusSuccess)
                        }
                    }
                } header: {
                    Text("Categories")
                } footer: {
                    Text("All notification categories are enabled by default. Manage notification preferences in iOS Settings.")
                }
            }

            // Telegram section
            Section {
                Toggle(isOn: $viewModel.telegramEnabled) {
                    Label("Telegram Notifications", systemImage: "paperplane.fill")
                }
                .onChange(of: viewModel.telegramEnabled) { _, _ in
                    Task { await viewModel.updateTelegram() }
                }

                if viewModel.telegramEnabled {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Chat ID")
                            .font(.caption)
                            .foregroundStyle(.secondary)

                        HStack {
                            TextField("Enter Telegram Chat ID", text: $viewModel.telegramChatId)
                                .font(.subheadline.monospaced())
                                .keyboardType(.numberPad)

                            Button {
                                Task { await viewModel.updateTelegram() }
                            } label: {
                                Text("Save")
                                    .font(.caption.weight(.semibold))
                            }
                            .buttonStyle(.bordered)
                        }
                    }

                    if let botUsername = viewModel.telegramConfig?.telegramBotUsername {
                        HStack {
                            Text("Bot")
                                .font(.subheadline)
                                .foregroundStyle(.secondary)
                            Spacer()
                            Text("@\(botUsername)")
                                .font(.subheadline.monospaced())
                                .foregroundStyle(.brandPrimary)
                        }
                    }

                    HStack(spacing: 12) {
                        Button {
                            Task { await viewModel.testTelegram() }
                        } label: {
                            Label("Test", systemImage: "paperplane")
                                .font(.subheadline)
                        }
                        .buttonStyle(.bordered)

                        Button(role: .destructive) {
                            Task { await viewModel.deleteTelegram() }
                        } label: {
                            Label("Remove", systemImage: "trash")
                                .font(.subheadline)
                        }
                        .buttonStyle(.bordered)
                    }
                    .padding(.vertical, 4)
                }
            } header: {
                Text("Telegram")
            } footer: {
                if !viewModel.telegramEnabled {
                    Text("Connect your Telegram account to receive notifications via Telegram bot.")
                }
            }

            // Error/Success
            if let error = viewModel.errorMessage {
                Section {
                    Text(error)
                        .font(.subheadline)
                        .foregroundStyle(.statusError)
                }
            }

            if let success = viewModel.successMessage {
                Section {
                    Text(success)
                        .font(.subheadline)
                        .foregroundStyle(.statusSuccess)
                }
            }
        }
        .scrollContentBackground(.hidden)
        .background(Color.surfaceBackground)
        .navigationTitle("Notifications")
        .navigationBarTitleDisplayMode(.inline)
        .task {
            await PushNotificationService.shared.checkPermissionStatus()
            pushAuthorized = PushNotificationService.shared.isAuthorized
        }
    }

    // MARK: - Request Push Permission

    private func requestPushPermission() async {
        isRequestingPermission = true
        let granted = await PushNotificationService.shared.requestPermission()
        pushAuthorized = granted
        isRequestingPermission = false

        if !granted {
            viewModel.errorMessage = "Push notifications were denied. Enable them in iOS Settings > KuberTrading > Notifications."
        }
    }
}

#Preview {
    NavigationStack {
        NotificationSettingsView(viewModel: SettingsViewModel())
    }
    .preferredColorScheme(.dark)
}
