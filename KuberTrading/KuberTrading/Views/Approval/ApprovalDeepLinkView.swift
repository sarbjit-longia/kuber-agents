import SwiftUI

struct ApprovalDeepLinkView: View {
    let token: String
    @State private var viewModel: ApprovalViewModel
    @Environment(\.dismiss) private var dismiss

    init(token: String) {
        self.token = token
        // Extract execution ID from token if embedded (format: executionId:token)
        let parts = token.split(separator: ":", maxSplits: 1)
        let executionId = parts.count > 1 ? String(parts[0]) : nil
        let actualToken = parts.count > 1 ? String(parts[1]) : token
        _viewModel = State(initialValue: ApprovalViewModel(token: actualToken, executionId: executionId))
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 24) {
                    if viewModel.isLoading && viewModel.preTradeReport == nil && !viewModel.isActioned {
                        LoadingView(message: "Loading trade details...")
                    } else if viewModel.isActioned {
                        resultView
                    } else if viewModel.isExpired {
                        expiredView
                    } else if let error = viewModel.errorMessage, viewModel.preTradeReport == nil {
                        errorView(error)
                    } else {
                        tradeApprovalContent
                    }
                }
                .padding()
            }
            .background(Color.surfaceBackground)
            .navigationTitle("Trade Approval")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        dismiss()
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundStyle(.secondary)
                    }
                }
            }
            .task {
                await viewModel.loadPreTradeReport()
            }
        }
    }

    // MARK: - Trade Approval Content

    @ViewBuilder
    private var tradeApprovalContent: some View {
        // Header
        VStack(spacing: 8) {
            Image(systemName: "exclamationmark.shield.fill")
                .font(.system(size: 44))
                .foregroundStyle(.statusWarning)

            Text("Trade Approval Required")
                .font(.title3.weight(.bold))

            Text("Review the trade details below and approve or reject.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
        }

        // Countdown timer
        if viewModel.expiresAt != nil {
            countdownTimer
        }

        // Error banner (non-blocking)
        if let error = viewModel.errorMessage {
            ErrorBanner(message: error) {
                viewModel.errorMessage = nil
            }
        }

        // Trade details card
        if let report = viewModel.preTradeReport {
            tradeDetailsCard(report)
        }

        // Action buttons
        if !viewModel.isActioned && !viewModel.isExpired {
            actionButtons
        }
    }

    // MARK: - Countdown Timer

    private var countdownTimer: some View {
        let minutes = Int(viewModel.timeRemaining) / 60
        let seconds = Int(viewModel.timeRemaining) % 60
        let isUrgent = viewModel.timeRemaining < 120

        return VStack(spacing: 4) {
            Text("Time Remaining")
                .font(.caption)
                .foregroundStyle(.secondary)

            Text(String(format: "%02d:%02d", minutes, seconds))
                .font(.system(size: 28, weight: .bold, design: .monospaced))
                .foregroundStyle(isUrgent ? .statusError : .statusWarning)
                .contentTransition(.numericText())
                .animation(.easeInOut(duration: 0.3), value: Int(viewModel.timeRemaining))
        }
        .padding(.horizontal, 24)
        .padding(.vertical, 12)
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill((isUrgent ? Color.statusError : Color.statusWarning).opacity(0.1))
                .overlay(
                    RoundedRectangle(cornerRadius: 12)
                        .strokeBorder((isUrgent ? Color.statusError : Color.statusWarning).opacity(0.3), lineWidth: 1)
                )
        )
    }

    // MARK: - Trade Details Card

    @ViewBuilder
    private func tradeDetailsCard(_ report: [String: AnyCodable]) -> some View {
        let tradeDetails = extractDict("trade_details", from: report)
            ?? extractDict("tradeDetails", from: report)
            ?? report

        VStack(spacing: 0) {
            // Symbol
            if let symbol = tradeDetails["symbol"]?.stringValue ?? report["symbol"]?.stringValue {
                detailRow(label: "Symbol", icon: "chart.line.uptrend.xyaxis") {
                    Text(symbol)
                        .font(.headline.weight(.bold))
                }
                Divider().padding(.horizontal)
            }

            // Side
            if let side = tradeDetails["side"]?.stringValue ?? tradeDetails["action"]?.stringValue {
                let isBuy = ["buy", "long"].contains(side.lowercased())
                detailRow(label: "Side", icon: "arrow.up.arrow.down") {
                    Text(side.uppercased())
                        .font(.subheadline.weight(.bold))
                        .foregroundStyle(isBuy ? .actionBuy : .actionSell)
                        .padding(.horizontal, 10)
                        .padding(.vertical, 4)
                        .background(
                            (isBuy ? Color.actionBuy : Color.actionSell).opacity(0.15),
                            in: Capsule()
                        )
                }
                Divider().padding(.horizontal)
            }

            // Quantity
            if let qty = extractNumber("quantity", from: tradeDetails)
                ?? extractNumber("qty", from: tradeDetails) {
                detailRow(label: "Quantity", icon: "number") {
                    Text(formatQuantity(qty))
                        .font(.subheadline.weight(.semibold))
                }
                Divider().padding(.horizontal)
            }

            // Entry price
            if let price = extractNumber("entry_price", from: tradeDetails)
                ?? extractNumber("price", from: tradeDetails) {
                detailRow(label: "Entry Price", icon: "dollarsign.circle") {
                    Text(price.currencyFormatted)
                        .font(.subheadline.weight(.semibold))
                }
                Divider().padding(.horizontal)
            }

            // Stop loss
            if let stopLoss = extractNumber("stop_loss", from: tradeDetails)
                ?? extractNumber("stop_loss_price", from: tradeDetails) {
                detailRow(label: "Stop Loss", icon: "shield.slash") {
                    Text(stopLoss.currencyFormatted)
                        .font(.subheadline.weight(.medium))
                        .foregroundStyle(.statusError)
                }
                Divider().padding(.horizontal)
            }

            // Take profit
            if let takeProfit = extractNumber("take_profit", from: tradeDetails)
                ?? extractNumber("take_profit_price", from: tradeDetails) {
                detailRow(label: "Take Profit", icon: "target") {
                    Text(takeProfit.currencyFormatted)
                        .font(.subheadline.weight(.medium))
                        .foregroundStyle(.statusSuccess)
                }
                Divider().padding(.horizontal)
            }

            // Mode
            if let mode = tradeDetails["mode"]?.stringValue ?? report["mode"]?.stringValue {
                detailRow(label: "Mode", icon: "circle.fill") {
                    HStack(spacing: 4) {
                        Circle()
                            .fill(mode.lowercased() == "live" ? Color.accountLive : Color.accountPaper)
                            .frame(width: 8, height: 8)
                        Text(mode.capitalized)
                            .font(.subheadline.weight(.medium))
                    }
                }
                Divider().padding(.horizontal)
            }

            // Pipeline name
            if let pipeline = report["pipeline_name"]?.stringValue
                ?? report["pipelineName"]?.stringValue {
                detailRow(label: "Pipeline", icon: "arrow.triangle.branch") {
                    Text(pipeline)
                        .font(.subheadline)
                        .lineLimit(1)
                }
            }

            // Reasoning
            if let reasoning = tradeDetails["reasoning"]?.stringValue
                ?? tradeDetails["reason"]?.stringValue {
                Divider().padding(.horizontal)
                VStack(alignment: .leading, spacing: 4) {
                    Text("Reasoning")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Text(reasoning)
                        .font(.subheadline)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .padding()
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        .cardStyle()
    }

    // MARK: - Detail Row

    @ViewBuilder
    private func detailRow(
        label: String,
        icon: String,
        @ViewBuilder trailing: () -> some View
    ) -> some View {
        HStack {
            Image(systemName: icon)
                .font(.caption)
                .foregroundStyle(.secondary)
                .frame(width: 20)
            Text(label)
                .font(.subheadline)
                .foregroundStyle(.secondary)
            Spacer()
            trailing()
        }
        .padding(.horizontal)
        .padding(.vertical, 10)
    }

    // MARK: - Action Buttons

    private var actionButtons: some View {
        HStack(spacing: 16) {
            // Reject
            Button {
                Task { await viewModel.reject() }
            } label: {
                HStack {
                    Image(systemName: "xmark.circle.fill")
                    Text("Reject")
                }
                .font(.body.weight(.semibold))
                .frame(maxWidth: .infinity)
                .padding(.vertical, 14)
            }
            .buttonStyle(.bordered)
            .tint(.statusError)
            .disabled(viewModel.isLoading)

            // Approve
            Button {
                Task { await viewModel.approve() }
            } label: {
                HStack {
                    if viewModel.isLoading {
                        ProgressView()
                            .scaleEffect(0.8)
                            .tint(.white)
                    } else {
                        Image(systemName: "checkmark.circle.fill")
                    }
                    Text("Approve")
                }
                .font(.body.weight(.semibold))
                .frame(maxWidth: .infinity)
                .padding(.vertical, 14)
            }
            .buttonStyle(.borderedProminent)
            .tint(.statusSuccess)
            .disabled(viewModel.isLoading)
        }
    }

    // MARK: - Result View

    private var resultView: some View {
        VStack(spacing: 20) {
            let isApproved = viewModel.actionResult == "approved"

            Image(systemName: isApproved ? "checkmark.seal.fill" : "xmark.seal.fill")
                .font(.system(size: 64))
                .foregroundStyle(isApproved ? .statusSuccess : .statusError)

            Text(isApproved ? "Trade Approved" : "Trade Rejected")
                .font(.title2.weight(.bold))

            Text(isApproved
                ? "The trade will now be executed by the pipeline."
                : "The trade has been rejected and the pipeline will not execute.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)

            Button {
                dismiss()
            } label: {
                Text("Done")
                    .font(.body.weight(.semibold))
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 14)
            }
            .buttonStyle(.borderedProminent)
            .padding(.top, 8)
        }
        .padding(.top, 40)
    }

    // MARK: - Expired View

    private var expiredView: some View {
        VStack(spacing: 20) {
            Image(systemName: "clock.badge.xmark")
                .font(.system(size: 64))
                .foregroundStyle(.statusWarning)

            Text("Approval Expired")
                .font(.title2.weight(.bold))

            Text("The approval window has expired. The pipeline has been cancelled.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)

            Button {
                dismiss()
            } label: {
                Text("Close")
                    .font(.body.weight(.semibold))
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 14)
            }
            .buttonStyle(.borderedProminent)
        }
        .padding(.top, 40)
    }

    // MARK: - Error View

    @ViewBuilder
    private func errorView(_ error: String) -> some View {
        VStack(spacing: 20) {
            Image(systemName: "exclamationmark.triangle.fill")
                .font(.system(size: 48))
                .foregroundStyle(.statusError)

            Text("Failed to Load")
                .font(.title3.weight(.bold))

            Text(error)
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)

            Button {
                Task { await viewModel.loadPreTradeReport() }
            } label: {
                Text("Retry")
                    .font(.body.weight(.semibold))
            }
            .buttonStyle(.borderedProminent)

            Button {
                dismiss()
            } label: {
                Text("Close")
                    .font(.body.weight(.medium))
                    .foregroundStyle(.secondary)
            }
        }
        .padding(.top, 40)
    }

    // MARK: - Helpers

    private func extractDict(_ key: String, from dict: [String: AnyCodable]) -> [String: AnyCodable]? {
        guard let value = dict[key], let dictValue = value.dictValue else { return nil }
        return dictValue.mapValues { AnyCodable($0) }
    }

    private func extractNumber(_ key: String, from dict: [String: AnyCodable]?) -> Double? {
        guard let dict else { return nil }
        if let val = dict[key]?.doubleValue { return val }
        if let val = dict[key]?.intValue { return Double(val) }
        return nil
    }

    private func formatQuantity(_ qty: Double) -> String {
        if qty == qty.rounded() {
            return String(format: "%.0f", qty)
        }
        return String(format: "%.4f", qty)
    }
}

#Preview {
    ApprovalDeepLinkView(token: "test-execution-id:test-token-123")
        .preferredColorScheme(.dark)
}
