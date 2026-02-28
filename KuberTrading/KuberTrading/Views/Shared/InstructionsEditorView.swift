import SwiftUI

struct InstructionsEditorView: View {
    let agentType: String
    @Binding var instructions: String
    @Binding var documentUrl: String

    @State private var isValidating = false
    @State private var validationResult: ValidateInstructionsResponse?
    @State private var validationError: String?
    @State private var characterCount: Int = 0

    private let maxCharacters = 10_000

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            // Header
            HStack {
                Text("Agent Instructions")
                    .font(.subheadline.weight(.semibold))

                Spacer()

                // Character count
                Text("\(characterCount) / \(maxCharacters)")
                    .font(.caption.monospaced())
                    .foregroundStyle(characterCount > maxCharacters ? .statusError : .secondary)
            }

            // Text editor
            TextEditor(text: $instructions)
                .font(.subheadline)
                .scrollContentBackground(.hidden)
                .frame(minHeight: 120, maxHeight: 300)
                .padding(10)
                .background(Color.surfaceElevated, in: RoundedRectangle(cornerRadius: 10))
                .overlay(
                    RoundedRectangle(cornerRadius: 10)
                        .strokeBorder(Color.surfaceElevated.opacity(0.5), lineWidth: 1)
                )
                .onChange(of: instructions) { _, newValue in
                    characterCount = newValue.count
                }

            // Placeholder hint
            if instructions.isEmpty {
                Text("Provide natural language instructions for this agent. Describe the trading strategy, conditions, risk parameters, or any specific behavior.")
                    .font(.caption)
                    .foregroundStyle(.tertiary)
                    .padding(.horizontal, 4)
            }

            // Document URL
            VStack(alignment: .leading, spacing: 4) {
                Text("Reference Document URL (optional)")
                    .font(.caption)
                    .foregroundStyle(.secondary)

                HStack {
                    TextField("https://example.com/strategy.pdf", text: $documentUrl)
                        .font(.subheadline)
                        .keyboardType(.URL)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .textFieldStyle(.roundedBorder)
                }
            }

            // Validate button
            HStack(spacing: 12) {
                Button {
                    Task { await validateInstructions() }
                } label: {
                    HStack(spacing: 6) {
                        if isValidating {
                            ProgressView()
                                .scaleEffect(0.7)
                        } else {
                            Image(systemName: "checkmark.shield")
                        }
                        Text("Validate Instructions")
                            .font(.subheadline.weight(.medium))
                    }
                }
                .buttonStyle(.bordered)
                .disabled(instructions.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || isValidating)

                Spacer()
            }

            // Validation results
            if let result = validationResult {
                validationResultView(result)
            }

            if let error = validationError {
                HStack(spacing: 6) {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .foregroundStyle(.statusError)
                    Text(error)
                        .font(.caption)
                        .foregroundStyle(.statusError)
                }
            }
        }
        .onAppear {
            characterCount = instructions.count
        }
    }

    // MARK: - Validation Result View

    @ViewBuilder
    private func validationResultView(_ result: ValidateInstructionsResponse) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            // Valid/Invalid header
            HStack(spacing: 6) {
                Image(systemName: result.isValid ? "checkmark.circle.fill" : "xmark.circle.fill")
                    .foregroundStyle(result.isValid ? .statusSuccess : .statusError)
                Text(result.isValid ? "Instructions Valid" : "Issues Found")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(result.isValid ? .statusSuccess : .statusError)
            }

            // Errors
            if let errors = result.errors, !errors.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    ForEach(errors, id: \.self) { error in
                        HStack(alignment: .top, spacing: 6) {
                            Image(systemName: "exclamationmark.circle")
                                .font(.caption)
                                .foregroundStyle(.statusError)
                                .padding(.top, 1)
                            Text(error)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }
                }
            }

            // Detected tools
            if let tools = result.detectedTools, !tools.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Detected Tools:")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.secondary)

                    FlowLayout(spacing: 4) {
                        ForEach(tools, id: \.toolType) { tool in
                            Text(tool.name)
                                .font(.caption2.weight(.medium))
                                .padding(.horizontal, 8)
                                .padding(.vertical, 3)
                                .background(Color.brandPrimary.opacity(0.15), in: Capsule())
                                .foregroundStyle(.brandPrimary)
                        }
                    }
                }
            }

            // Cost estimates
            HStack(spacing: 16) {
                if let toolCost = result.estimatedToolCost {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Est. Tool Cost")
                            .font(.caption2)
                            .foregroundStyle(.tertiary)
                        Text(toolCost.costFormatted)
                            .font(.caption.weight(.semibold))
                    }
                }

                if let llmCost = result.estimatedLlmCost {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Est. LLM Cost")
                            .font(.caption2)
                            .foregroundStyle(.tertiary)
                        Text(llmCost.costFormatted)
                            .font(.caption.weight(.semibold))
                    }
                }
            }
        }
        .padding(12)
        .background(
            RoundedRectangle(cornerRadius: 10)
                .fill((validationResult?.isValid == true ? Color.statusSuccess : Color.statusError).opacity(0.05))
                .overlay(
                    RoundedRectangle(cornerRadius: 10)
                        .strokeBorder(
                            (validationResult?.isValid == true ? Color.statusSuccess : Color.statusError).opacity(0.2),
                            lineWidth: 1
                        )
                )
        )
    }

    // MARK: - Validate

    private func validateInstructions() async {
        isValidating = true
        validationError = nil
        validationResult = nil

        do {
            let result = try await AgentService.shared.validateInstructions(
                agentType: agentType,
                instructions: instructions,
                documentUrl: documentUrl.isEmpty ? nil : documentUrl
            )
            validationResult = result
        } catch let error as APIError {
            validationError = error.errorDescription
        } catch {
            validationError = error.localizedDescription
        }

        isValidating = false
    }
}

#Preview {
    ScrollView {
        InstructionsEditorView(
            agentType: "strategy_agent",
            instructions: .constant("Buy AAPL when RSI drops below 30 and MACD crosses bullish."),
            documentUrl: .constant("")
        )
        .padding()
    }
    .background(Color.surfaceBackground)
    .preferredColorScheme(.dark)
}
