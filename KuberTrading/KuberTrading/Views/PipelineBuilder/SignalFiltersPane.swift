import SwiftUI

struct SignalFiltersPane: View {
    @Bindable var viewModel: PipelineBuilderViewModel
    @State private var newSignalType: String = ""
    @State private var newTimeframe: String = "1d"
    @State private var newMinConfidence: Double = 0.7

    private let timeframes = ["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"]

    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            // Header
            Label("Signal Filters", systemImage: "antenna.radiowaves.left.and.right")
                .font(.headline)

            // Show only when trigger mode is signal
            if viewModel.triggerMode != "signal" {
                notSignalModeView
            } else {
                signalConfigView
            }
        }
    }

    // MARK: - Not Signal Mode

    private var notSignalModeView: some View {
        VStack(spacing: 16) {
            Image(systemName: "antenna.radiowaves.left.and.right")
                .font(.system(size: 40))
                .foregroundStyle(.secondary)

            Text("Signal Filters Unavailable")
                .font(.subheadline.weight(.semibold))

            Text("Signal filters are only available when the trigger mode is set to \"Signal\". Change the trigger mode in Pipeline Settings to enable signal-based triggering.")
                .font(.caption)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)

            Button {
                viewModel.triggerMode = "signal"
                viewModel.selectSetupItem("pipeline_settings")
            } label: {
                Text("Switch to Signal Mode")
            }
            .buttonStyle(.bordered)
            .controlSize(.small)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 20)
    }

    // MARK: - Signal Config View

    private var signalConfigView: some View {
        VStack(alignment: .leading, spacing: 20) {
            // Scanner Picker
            scannerPicker

            // Current Subscriptions
            if !viewModel.signalSubscriptions.isEmpty {
                subscriptionsList
            }

            // Add New Subscription
            addSubscriptionForm

            // Info
            if viewModel.signalSubscriptions.isEmpty {
                HStack(alignment: .top, spacing: 8) {
                    Image(systemName: "info.circle.fill")
                        .foregroundStyle(.statusInfo)

                    Text("Add at least one signal subscription to define which signals should trigger this pipeline. Without subscriptions, the pipeline will be triggered for all signals from the selected scanner.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                .padding(12)
                .background(Color.statusInfo.opacity(0.08), in: RoundedRectangle(cornerRadius: 8))
            }
        }
    }

    // MARK: - Scanner Picker

    private var scannerPicker: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Scanner")
                .font(.subheadline.weight(.medium))

            Text("Select the scanner that provides market signals.")
                .font(.caption)
                .foregroundStyle(.secondary)

            if viewModel.scanners.isEmpty {
                HStack(spacing: 8) {
                    Image(systemName: "exclamationmark.triangle")
                        .foregroundStyle(.statusWarning)
                    Text("No scanners available. Create a scanner first.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                .padding(12)
                .background(Color.surfaceElevated, in: RoundedRectangle(cornerRadius: 8))
            } else {
                Picker("Scanner", selection: Binding(
                    get: { viewModel.scannerId ?? "" },
                    set: { newValue in
                        viewModel.scannerId = newValue.isEmpty ? nil : newValue
                    }
                )) {
                    Text("Select a scanner...").tag("")
                    ForEach(viewModel.scanners) { scanner in
                        HStack {
                            Text(scanner.name)
                            if let tickerCount = scanner.tickerCount {
                                Text("(\(tickerCount) tickers)")
                                    .foregroundStyle(.secondary)
                            }
                        }
                        .tag(scanner.id)
                    }
                }
                .pickerStyle(.menu)
                .tint(.brandPrimary)
                .padding(10)
                .background(Color.surfaceElevated, in: RoundedRectangle(cornerRadius: 8))
            }
        }
    }

    // MARK: - Subscriptions List

    private var subscriptionsList: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Signal Subscriptions")
                .font(.subheadline.weight(.medium))

            ForEach(Array(viewModel.signalSubscriptions.enumerated()), id: \.offset) { index, subscription in
                HStack(spacing: 12) {
                    VStack(alignment: .leading, spacing: 2) {
                        HStack(spacing: 6) {
                            // Signal type icon
                            if let signalType = viewModel.signalTypes.first(where: { $0.signalType == subscription.signalType }) {
                                Image(systemName: signalType.icon)
                                    .font(.caption)
                                    .foregroundStyle(.brandPrimary)
                            }

                            Text(subscription.signalType.replacingOccurrences(of: "_", with: " ").capitalized)
                                .font(.subheadline.weight(.medium))
                        }

                        HStack(spacing: 8) {
                            if let timeframe = subscription.timeframe {
                                Text(timeframe)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                    .padding(.horizontal, 6)
                                    .padding(.vertical, 2)
                                    .background(Color.surfaceElevated, in: Capsule())
                            }

                            if let confidence = subscription.minConfidence {
                                Text("\(Int(confidence * 100))% min confidence")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }
                    }

                    Spacer()

                    Button {
                        viewModel.removeSignalSubscription(at: index)
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundStyle(.secondary)
                    }
                    .buttonStyle(.plain)
                }
                .padding(10)
                .background(Color.surfaceElevated, in: RoundedRectangle(cornerRadius: 8))
            }
        }
    }

    // MARK: - Add Subscription Form

    private var addSubscriptionForm: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Add Subscription")
                .font(.subheadline.weight(.medium))

            // Signal Type Picker
            VStack(alignment: .leading, spacing: 4) {
                Text("Signal Type")
                    .font(.caption.weight(.medium))

                Picker("Signal Type", selection: $newSignalType) {
                    Text("Select signal type...").tag("")
                    ForEach(viewModel.signalTypes) { signalType in
                        HStack {
                            Image(systemName: signalType.icon)
                            Text(signalType.name)
                        }
                        .tag(signalType.signalType)
                    }
                }
                .pickerStyle(.menu)
                .tint(.brandPrimary)
                .padding(10)
                .background(Color.surfaceElevated, in: RoundedRectangle(cornerRadius: 8))
            }

            // Timeframe Picker
            VStack(alignment: .leading, spacing: 4) {
                Text("Timeframe")
                    .font(.caption.weight(.medium))

                Picker("Timeframe", selection: $newTimeframe) {
                    ForEach(timeframes, id: \.self) { tf in
                        Text(tf).tag(tf)
                    }
                }
                .pickerStyle(.segmented)
            }

            // Confidence Slider
            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text("Min Confidence")
                        .font(.caption.weight(.medium))

                    Spacer()

                    Text("\(Int(newMinConfidence * 100))%")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.brandPrimary)
                }

                Slider(value: $newMinConfidence, in: 0.1...1.0, step: 0.05)
                    .tint(.brandPrimary)
            }

            // Add Button
            Button {
                guard !newSignalType.isEmpty else { return }
                let subscription = SignalSubscription(
                    signalType: newSignalType,
                    timeframe: newTimeframe,
                    minConfidence: newMinConfidence
                )
                viewModel.addSignalSubscription(subscription)
                newSignalType = ""
            } label: {
                Label("Add Subscription", systemImage: "plus")
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.bordered)
            .controlSize(.regular)
            .disabled(newSignalType.isEmpty)
        }
        .padding(12)
        .background(Color.surfaceCard, in: RoundedRectangle(cornerRadius: 10))
    }
}

#Preview {
    ScrollView {
        SignalFiltersPane(viewModel: {
            let vm = PipelineBuilderViewModel()
            vm.triggerMode = "signal"
            return vm
        }())
        .padding()
    }
    .preferredColorScheme(.dark)
}
