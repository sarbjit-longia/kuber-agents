import SwiftUI

struct SettingsView: View {
    @State private var viewModel = SettingsViewModel()
    @State private var showLogoutConfirmation = false

    var body: some View {
        List {
            // Error / Success banners
            if let error = viewModel.errorMessage {
                Section {
                    ErrorBanner(message: error) {
                        viewModel.errorMessage = nil
                    }
                }
                .listRowBackground(Color.clear)
                .listRowInsets(EdgeInsets())
            }

            if let success = viewModel.successMessage {
                Section {
                    SuccessBanner(message: success) {
                        viewModel.successMessage = nil
                    }
                }
                .listRowBackground(Color.clear)
                .listRowInsets(EdgeInsets())
            }

            // Profile
            Section {
                NavigationLink(value: SettingsDestination.profile) {
                    HStack(spacing: 14) {
                        initialsAvatar

                        VStack(alignment: .leading, spacing: 2) {
                            Text(viewModel.user?.fullName ?? "User")
                                .font(.body.weight(.semibold))
                            Text(viewModel.user?.email ?? "")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }
                    .padding(.vertical, 4)
                }
            } header: {
                Text("Profile")
            }

            // Subscription
            Section {
                NavigationLink(value: SettingsDestination.subscription) {
                    HStack {
                        Label("Subscription", systemImage: "crown")
                        Spacer()
                        Text(viewModel.subscription?.tier.capitalized ?? "Free")
                            .font(.subheadline)
                            .foregroundStyle(.brandPrimary)
                    }
                }

                if let subscription = viewModel.subscription {
                    HStack {
                        Text("Active Pipelines")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                        Spacer()
                        Text("\(subscription.currentActivePipelines) / \(subscription.maxActivePipelines)")
                            .font(.subheadline.weight(.medium))
                    }
                }
            } header: {
                Text("Subscription")
            }

            // Security
            Section {
                if viewModel.biometricType != .none {
                    HStack {
                        Label(
                            biometricLabel,
                            systemImage: biometricIcon
                        )

                        Spacer()

                        Toggle("", isOn: Binding(
                            get: { viewModel.biometricEnabled },
                            set: { _ in
                                Task { await viewModel.toggleBiometric() }
                            }
                        ))
                        .labelsHidden()
                    }
                } else {
                    Label("Biometric login not available", systemImage: "faceid")
                        .foregroundStyle(.secondary)
                }
            } header: {
                Text("Security")
            }

            // Notifications
            Section {
                NavigationLink(value: SettingsDestination.notifications) {
                    HStack {
                        Label("Push Notifications", systemImage: "bell.badge")
                        Spacer()
                        Text(PushNotificationService.shared.isAuthorized ? "Enabled" : "Disabled")
                            .font(.subheadline)
                            .foregroundStyle(
                                PushNotificationService.shared.isAuthorized
                                    ? .statusSuccess
                                    : .secondary
                            )
                    }
                }
            } header: {
                Text("Notifications")
            }

            // Telegram
            Section {
                HStack {
                    Label("Telegram", systemImage: "paperplane")
                    Spacer()
                    Text(viewModel.telegramEnabled ? "Connected" : "Not Connected")
                        .font(.subheadline)
                        .foregroundStyle(viewModel.telegramEnabled ? .statusSuccess : .secondary)
                }

                if viewModel.telegramEnabled {
                    HStack {
                        Text("Chat ID")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                        Spacer()
                        Text(viewModel.telegramChatId)
                            .font(.caption.monospaced())
                            .foregroundStyle(.secondary)
                    }

                    Button {
                        Task { await viewModel.testTelegram() }
                    } label: {
                        Label("Send Test Message", systemImage: "paperplane.fill")
                    }
                }
            } header: {
                Text("Telegram")
            }

            // About
            Section {
                HStack {
                    Label("Version", systemImage: "info.circle")
                    Spacer()
                    Text(appVersion)
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }

                Link(destination: URL(string: "https://kubertrading.com/support")!) {
                    Label("Support", systemImage: "questionmark.circle")
                }

                Link(destination: URL(string: "https://kubertrading.com/privacy")!) {
                    Label("Privacy Policy", systemImage: "hand.raised")
                }

                Link(destination: URL(string: "https://kubertrading.com/terms")!) {
                    Label("Terms of Service", systemImage: "doc.plaintext")
                }
            } header: {
                Text("About")
            }

            // Logout
            Section {
                Button(role: .destructive) {
                    showLogoutConfirmation = true
                } label: {
                    HStack {
                        Spacer()
                        Label("Log Out", systemImage: "rectangle.portrait.and.arrow.right")
                            .font(.body.weight(.medium))
                        Spacer()
                    }
                }
            }
        }
        .scrollContentBackground(.hidden)
        .background(Color.surfaceBackground)
        .navigationTitle("Settings")
        .navigationDestination(for: SettingsDestination.self) { destination in
            switch destination {
            case .profile:
                ProfileSettingsView(viewModel: viewModel)
            case .subscription:
                SubscriptionSettingsView(viewModel: viewModel)
            case .notifications:
                NotificationSettingsView(viewModel: viewModel)
            }
        }
        .confirmationDialog("Log Out", isPresented: $showLogoutConfirmation, titleVisibility: .visible) {
            Button("Log Out", role: .destructive) {
                Task { await viewModel.logout() }
            }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("Are you sure you want to log out?")
        }
        .overlay {
            if viewModel.isLoading && viewModel.user == nil {
                LoadingView(message: "Loading settings...")
            }
        }
        .task {
            await viewModel.loadSettings()
        }
    }

    // MARK: - Initials Avatar

    private var initialsAvatar: some View {
        let initials = (viewModel.user?.fullName ?? "U")
            .split(separator: " ")
            .prefix(2)
            .compactMap { $0.first.map(String.init) }
            .joined()

        return Text(initials.uppercased())
            .font(.callout.weight(.bold))
            .foregroundStyle(.white)
            .frame(width: 44, height: 44)
            .background(Color.brandPrimary, in: Circle())
    }

    // MARK: - Biometric Helpers

    private var biometricLabel: String {
        switch viewModel.biometricType {
        case .faceID: return "Face ID Login"
        case .touchID: return "Touch ID Login"
        case .none: return "Biometric Login"
        }
    }

    private var biometricIcon: String {
        switch viewModel.biometricType {
        case .faceID: return "faceid"
        case .touchID: return "touchid"
        case .none: return "lock"
        }
    }

    // MARK: - App Version

    private var appVersion: String {
        let version = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "1.0"
        let build = Bundle.main.infoDictionary?["CFBundleVersion"] as? String ?? "1"
        return "\(version) (\(build))"
    }
}

#Preview {
    NavigationStack {
        SettingsView()
    }
    .preferredColorScheme(.dark)
}
