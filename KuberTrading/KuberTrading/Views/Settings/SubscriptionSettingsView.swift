import SwiftUI

struct SubscriptionSettingsView: View {
    @Bindable var viewModel: SettingsViewModel

    var body: some View {
        ScrollView {
            VStack(spacing: 20) {
                // Subscription tier card
                if let subscription = viewModel.subscription {
                    tierCard(subscription)

                    // Usage stats
                    usageSection(subscription)

                    // Available signals
                    if !subscription.availableSignals.isEmpty {
                        signalsSection(subscription.availableSignals)
                    }

                    // Expiry info
                    if let expiresAt = subscription.subscriptionExpiresAt {
                        expirySection(expiresAt)
                    }
                } else {
                    EmptyStateView(
                        icon: "crown",
                        title: "Subscription Info Unavailable",
                        message: "Unable to load subscription details.",
                        actionTitle: "Retry"
                    ) {
                        Task { await viewModel.loadSettings() }
                    }
                }
            }
            .padding()
        }
        .background(Color.surfaceBackground)
        .navigationTitle("Subscription")
        .navigationBarTitleDisplayMode(.inline)
    }

    // MARK: - Tier Card

    @ViewBuilder
    private func tierCard(_ subscription: SubscriptionInfo) -> some View {
        VStack(spacing: 12) {
            Image(systemName: tierIcon(subscription.tier))
                .font(.system(size: 36))
                .foregroundStyle(tierColor(subscription.tier))

            Text(subscription.tier.capitalized)
                .font(.title2.weight(.bold))

            if subscription.isLimitEnforced {
                Text("Limits enforced")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 24)
        .background(
            RoundedRectangle(cornerRadius: 16)
                .fill(
                    LinearGradient(
                        colors: [tierColor(subscription.tier).opacity(0.15), Color.surfaceCard],
                        startPoint: .top,
                        endPoint: .bottom
                    )
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 16)
                        .strokeBorder(tierColor(subscription.tier).opacity(0.3), lineWidth: 1)
                )
        )
    }

    // MARK: - Usage Section

    @ViewBuilder
    private func usageSection(_ subscription: SubscriptionInfo) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Pipeline Usage")
                .sectionHeader()

            VStack(spacing: 0) {
                usageRow(label: "Max Active Pipelines", value: "\(subscription.maxActivePipelines)")
                Divider().padding(.horizontal)
                usageRow(label: "Currently Active", value: "\(subscription.currentActivePipelines)")
                Divider().padding(.horizontal)
                usageRow(label: "Remaining", value: "\(subscription.pipelinesRemaining)") {
                    Text("\(subscription.pipelinesRemaining)")
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(
                            subscription.pipelinesRemaining > 0 ? .statusSuccess : .statusError
                        )
                }
                Divider().padding(.horizontal)
                usageRow(label: "Total Created", value: "\(subscription.totalPipelines)")

                // Usage bar
                VStack(spacing: 6) {
                    let progress = subscription.maxActivePipelines > 0
                        ? Double(subscription.currentActivePipelines) / Double(subscription.maxActivePipelines)
                        : 0

                    ProgressView(value: min(progress, 1.0))
                        .tint(progress >= 0.9 ? .statusError : progress >= 0.7 ? .statusWarning : .brandPrimary)

                    Text("\(Int(progress * 100))% of limit used")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                .padding()
            }
            .cardStyle()
        }
    }

    // MARK: - Usage Row

    @ViewBuilder
    private func usageRow(
        label: String,
        value: String,
        @ViewBuilder trailing: () -> some View = { EmptyView() }
    ) -> some View {
        HStack {
            Text(label)
                .font(.subheadline)
                .foregroundStyle(.secondary)
            Spacer()
            if trailing() is EmptyView {
                Text(value)
                    .font(.subheadline.weight(.medium))
            } else {
                trailing()
            }
        }
        .padding(.horizontal)
        .padding(.vertical, 10)
    }

    // MARK: - Signals Section

    @ViewBuilder
    private func signalsSection(_ signals: [String]) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Available Signals")
                .sectionHeader()

            VStack(spacing: 0) {
                ForEach(signals, id: \.self) { signal in
                    HStack {
                        Image(systemName: "antenna.radiowaves.left.and.right")
                            .font(.caption)
                            .foregroundStyle(.brandPrimary)
                            .frame(width: 24)

                        Text(signal.replacingOccurrences(of: "_", with: " ").capitalized)
                            .font(.subheadline)

                        Spacer()

                        Image(systemName: "checkmark.circle.fill")
                            .font(.caption)
                            .foregroundStyle(.statusSuccess)
                    }
                    .padding(.horizontal)
                    .padding(.vertical, 8)

                    if signal != signals.last {
                        Divider().padding(.horizontal)
                    }
                }
            }
            .cardStyle()
        }
    }

    // MARK: - Expiry Section

    @ViewBuilder
    private func expirySection(_ expiresAt: String) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Subscription Period")
                .sectionHeader()

            HStack {
                Image(systemName: "calendar")
                    .foregroundStyle(.brandPrimary)

                VStack(alignment: .leading, spacing: 2) {
                    Text("Expires")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Text(expiresAt.formattedDate)
                        .font(.subheadline.weight(.medium))
                }

                Spacer()

                if let date = expiresAt.asDate {
                    let daysLeft = Calendar.current.dateComponents([.day], from: Date(), to: date).day ?? 0
                    Text("\(max(daysLeft, 0)) days left")
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(daysLeft > 30 ? .statusSuccess : daysLeft > 7 ? .statusWarning : .statusError)
                }
            }
            .cardStyle()
        }
    }

    // MARK: - Tier Helpers

    private func tierIcon(_ tier: String) -> String {
        switch tier.lowercased() {
        case "free": return "sparkle"
        case "starter", "basic": return "star"
        case "pro", "professional": return "crown"
        case "enterprise": return "building.2"
        default: return "crown"
        }
    }

    private func tierColor(_ tier: String) -> Color {
        switch tier.lowercased() {
        case "free": return .secondary
        case "starter", "basic": return .brandPrimary
        case "pro", "professional": return .brandSecondary
        case "enterprise": return .statusWarning
        default: return .brandPrimary
        }
    }
}

#Preview {
    NavigationStack {
        SubscriptionSettingsView(viewModel: SettingsViewModel())
    }
    .preferredColorScheme(.dark)
}
