import SwiftUI

struct CreateScannerSheet: View {
    @Bindable var viewModel: ScannerViewModel
    @Environment(\.dismiss) private var dismiss

    private let scannerTypes = ["manual", "filter", "api"]

    var body: some View {
        NavigationStack {
            Form {
                // Basic Info
                Section("Scanner Details") {
                    TextField("Scanner Name", text: $viewModel.scannerName)
                        .textInputAutocapitalization(.words)

                    TextField("Description (optional)", text: $viewModel.scannerDescription, axis: .vertical)
                        .lineLimit(2...4)
                }

                // Scanner Type
                Section("Type") {
                    Picker("Scanner Type", selection: $viewModel.scannerType) {
                        ForEach(scannerTypes, id: \.self) { type in
                            HStack {
                                Image(systemName: typeIcon(type))
                                Text(type.capitalized)
                            }
                            .tag(type)
                        }
                    }
                    .pickerStyle(.segmented)

                    Text(typeDescription)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                // Tickers
                Section {
                    HStack {
                        TextField("Add ticker symbol", text: $viewModel.tickerInput)
                            .textInputAutocapitalization(.characters)
                            .autocorrectionDisabled()
                            .onSubmit {
                                viewModel.addTicker()
                            }

                        Button {
                            viewModel.addTicker()
                        } label: {
                            Image(systemName: "plus.circle.fill")
                                .foregroundStyle(.brandPrimary)
                        }
                        .disabled(viewModel.tickerInput.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    }

                    if viewModel.tickers.isEmpty {
                        Text("No tickers added yet")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                    } else {
                        FlowLayout(spacing: 6) {
                            ForEach(Array(viewModel.tickers.enumerated()), id: \.offset) { index, ticker in
                                tickerChip(ticker) {
                                    viewModel.removeTicker(at: index)
                                }
                            }
                        }
                    }
                } header: {
                    Text("Tickers (\(viewModel.tickers.count))")
                } footer: {
                    Text("Enter ticker symbols one at a time. Press return or tap + to add.")
                }

                // Error
                if let error = viewModel.errorMessage {
                    Section {
                        Text(error)
                            .font(.subheadline)
                            .foregroundStyle(.statusError)
                    }
                }
            }
            .scrollContentBackground(.hidden)
            .background(Color.surfaceBackground)
            .navigationTitle(viewModel.editingScanner != nil ? "Edit Scanner" : "New Scanner")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") {
                        viewModel.resetForm()
                        dismiss()
                    }
                }

                ToolbarItem(placement: .confirmationAction) {
                    Button(viewModel.editingScanner != nil ? "Save" : "Create") {
                        Task {
                            if viewModel.editingScanner != nil {
                                await viewModel.updateScanner()
                            } else {
                                await viewModel.createScanner()
                            }
                        }
                    }
                    .disabled(viewModel.scannerName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || viewModel.isLoading)
                }
            }
            .overlay {
                if viewModel.isLoading {
                    LoadingOverlay(message: viewModel.editingScanner != nil ? "Saving..." : "Creating...")
                }
            }
        }
    }

    // MARK: - Ticker Chip

    @ViewBuilder
    private func tickerChip(_ ticker: String, onRemove: @escaping () -> Void) -> some View {
        HStack(spacing: 4) {
            Text(ticker)
                .font(.caption.weight(.semibold))

            Button {
                onRemove()
            } label: {
                Image(systemName: "xmark.circle.fill")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 5)
        .background(Color.surfaceElevated, in: Capsule())
    }

    // MARK: - Type Helpers

    private func typeIcon(_ type: String) -> String {
        switch type {
        case "manual": return "hand.raised"
        case "filter": return "line.3.horizontal.decrease.circle"
        case "api": return "network"
        default: return "questionmark.circle"
        }
    }

    private var typeDescription: String {
        switch viewModel.scannerType {
        case "manual":
            return "Manually add and manage ticker symbols."
        case "filter":
            return "Automatically filter tickers based on criteria (e.g., market cap, sector)."
        case "api":
            return "Pull tickers from an external API source."
        default:
            return ""
        }
    }
}

#Preview {
    CreateScannerSheet(viewModel: ScannerViewModel())
        .preferredColorScheme(.dark)
}
