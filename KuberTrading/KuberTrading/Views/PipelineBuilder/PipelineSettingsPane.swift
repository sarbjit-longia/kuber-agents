import SwiftUI

struct PipelineSettingsPane: View {
    @Bindable var viewModel: PipelineBuilderViewModel

    private let executionModes = ["paper", "live", "simulation", "validation"]
    private let triggerModes = ["periodic", "signal"]

    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            // Header
            Label("Pipeline Settings", systemImage: "gearshape")
                .font(.headline)

            // Pipeline Name
            VStack(alignment: .leading, spacing: 6) {
                Text("Pipeline Name")
                    .font(.subheadline.weight(.medium))

                TextField("Enter pipeline name", text: $viewModel.pipelineName)
                    .textFieldStyle(.plain)
                    .padding(10)
                    .background(Color.surfaceElevated, in: RoundedRectangle(cornerRadius: 8))
            }

            // Description
            VStack(alignment: .leading, spacing: 6) {
                Text("Description")
                    .font(.subheadline.weight(.medium))

                TextField("Optional description", text: $viewModel.pipelineDescription)
                    .textFieldStyle(.plain)
                    .padding(10)
                    .background(Color.surfaceElevated, in: RoundedRectangle(cornerRadius: 8))
            }

            // Execution Mode
            VStack(alignment: .leading, spacing: 6) {
                Text("Execution Mode")
                    .font(.subheadline.weight(.medium))

                Picker("Mode", selection: $viewModel.executionMode) {
                    ForEach(executionModes, id: \.self) { mode in
                        Text(mode.capitalized).tag(mode)
                    }
                }
                .pickerStyle(.segmented)

                Text(executionModeDescription)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            // Trigger Mode
            VStack(alignment: .leading, spacing: 6) {
                Text("Trigger Mode")
                    .font(.subheadline.weight(.medium))

                Picker("Trigger", selection: $viewModel.triggerMode) {
                    ForEach(triggerModes, id: \.self) { mode in
                        HStack {
                            Image(systemName: mode == "signal" ? "antenna.radiowaves.left.and.right" : "clock.arrow.circlepath")
                            Text(mode.capitalized)
                        }
                        .tag(mode)
                    }
                }
                .pickerStyle(.segmented)

                Text(triggerModeDescription)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
    }

    private var executionModeDescription: String {
        switch viewModel.executionMode {
        case "paper":
            return "Simulated trading with no real money. Perfect for testing strategies."
        case "live":
            return "Real trading with real money. Use with caution."
        case "simulation":
            return "Full simulation with historical data replay."
        case "validation":
            return "Validates the pipeline configuration without executing trades."
        default:
            return ""
        }
    }

    private var triggerModeDescription: String {
        switch viewModel.triggerMode {
        case "periodic":
            return "Runs on a schedule (e.g., every hour, daily at market open)."
        case "signal":
            return "Triggered by market signals from a scanner (e.g., golden cross, volume spike)."
        default:
            return ""
        }
    }
}

#Preview {
    ScrollView {
        PipelineSettingsPane(viewModel: PipelineBuilderViewModel())
            .padding()
    }
    .preferredColorScheme(.dark)
}
