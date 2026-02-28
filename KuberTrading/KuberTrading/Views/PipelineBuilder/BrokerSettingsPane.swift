import SwiftUI

struct BrokerSettingsPane: View {
    @Bindable var viewModel: PipelineBuilderViewModel

    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            // Header
            Label("Broker Settings", systemImage: "building.columns")
                .font(.headline)

            Text("Select and configure the broker for this pipeline. The broker will be automatically assigned to Risk Manager and Trade Manager agents.")
                .font(.caption)
                .foregroundStyle(.secondary)

            // Broker Picker
            VStack(alignment: .leading, spacing: 6) {
                Text("Broker")
                    .font(.subheadline.weight(.medium))

                if viewModel.brokerTools.isEmpty {
                    HStack(spacing: 8) {
                        Image(systemName: "info.circle")
                            .foregroundStyle(.statusInfo)
                        Text("No broker tools available. Contact support.")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    .padding(12)
                    .background(Color.surfaceElevated, in: RoundedRectangle(cornerRadius: 8))
                } else {
                    Picker("Broker Type", selection: Binding(
                        get: { viewModel.brokerToolType ?? "" },
                        set: { newValue in
                            if newValue.isEmpty {
                                viewModel.removeBrokerTool()
                            } else {
                                viewModel.brokerToolType = newValue
                                viewModel.brokerToolConfig = [:]
                            }
                        }
                    )) {
                        Text("Select a broker...").tag("")
                        ForEach(viewModel.brokerTools) { tool in
                            Text(tool.name).tag(tool.toolType)
                        }
                    }
                    .pickerStyle(.menu)
                    .tint(.brandPrimary)
                    .padding(10)
                    .background(Color.surfaceElevated, in: RoundedRectangle(cornerRadius: 8))
                }
            }

            // Broker Config Form (dynamic based on selected broker)
            if let brokerType = viewModel.brokerToolType,
               !brokerType.isEmpty,
               let brokerTool = viewModel.brokerTools.first(where: { $0.toolType == brokerType }) {

                brokerConfigSection(brokerTool)
            }

            // Currently configured broker summary
            if let broker = viewModel.pipelineBrokerTool {
                currentBrokerSummary(broker)
            }

            // Remove broker button
            if viewModel.pipelineBrokerTool != nil {
                Button(role: .destructive) {
                    viewModel.removeBrokerTool()
                } label: {
                    Label("Remove Broker", systemImage: "trash")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.bordered)
                .controlSize(.regular)
            }

            // Info box
            infoBox
        }
    }

    // MARK: - Broker Config Section

    @ViewBuilder
    private func brokerConfigSection(_ tool: ToolMetadata) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Broker Configuration")
                .font(.subheadline.weight(.medium))

            if let schema = tool.configSchema,
               let properties = schema.dictValue?["properties"] as? [String: Any] {

                ForEach(properties.sorted(by: { $0.key < $1.key }), id: \.key) { key, value in
                    brokerConfigField(key: key, property: value)
                }

                // Save config button
                Button {
                    viewModel.setBrokerTool(
                        toolType: tool.toolType,
                        config: viewModel.brokerToolConfig
                    )
                } label: {
                    Label("Apply Broker Configuration", systemImage: "checkmark")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.regular)
            } else {
                // No config schema, just apply with empty config
                Button {
                    viewModel.setBrokerTool(
                        toolType: tool.toolType,
                        config: [:]
                    )
                } label: {
                    Label("Apply Broker", systemImage: "checkmark")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.regular)

                Text("This broker requires no additional configuration.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
    }

    // MARK: - Broker Config Field

    @ViewBuilder
    private func brokerConfigField(key: String, property: Any) -> some View {
        let propDict = property as? [String: Any] ?? [:]
        let title = propDict["title"] as? String ?? key.replacingOccurrences(of: "_", with: " ").capitalized
        let type = propDict["type"] as? String ?? "string"
        let description = propDict["description"] as? String

        VStack(alignment: .leading, spacing: 4) {
            Text(title)
                .font(.caption.weight(.medium))

            if let description {
                Text(description)
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }

            if type == "boolean" {
                Toggle(title, isOn: Binding(
                    get: { viewModel.brokerToolConfig[key]?.boolValue ?? false },
                    set: { newValue in
                        viewModel.brokerToolConfig[key] = AnyCodable(newValue)
                    }
                ))
                .labelsHidden()
                .tint(.brandPrimary)
            } else if let enumValues = propDict["enum"] as? [String] {
                Picker(title, selection: Binding(
                    get: { viewModel.brokerToolConfig[key]?.stringValue ?? "" },
                    set: { newValue in
                        viewModel.brokerToolConfig[key] = AnyCodable(newValue)
                    }
                )) {
                    Text("Select...").tag("")
                    ForEach(enumValues, id: \.self) { val in
                        Text(val).tag(val)
                    }
                }
                .pickerStyle(.menu)
                .tint(.brandPrimary)
            } else {
                TextField(title, text: Binding(
                    get: { viewModel.brokerToolConfig[key]?.stringValue ?? "" },
                    set: { newValue in
                        viewModel.brokerToolConfig[key] = AnyCodable(newValue)
                    }
                ))
                .textFieldStyle(.plain)
                .padding(10)
                .background(Color.surfaceElevated, in: RoundedRectangle(cornerRadius: 8))
                .if(key.lowercased().contains("key") || key.lowercased().contains("secret") || key.lowercased().contains("password")) { view in
                    view.textContentType(.password)
                }
            }
        }
    }

    // MARK: - Current Broker Summary

    private func currentBrokerSummary(_ broker: ToolInstance) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Active Broker")
                .font(.subheadline.weight(.medium))

            HStack(spacing: 12) {
                Image(systemName: "building.columns.fill")
                    .font(.title3)
                    .foregroundStyle(.statusSuccess)
                    .frame(width: 40, height: 40)
                    .background(Color.statusSuccess.opacity(0.12), in: RoundedRectangle(cornerRadius: 8))

                VStack(alignment: .leading, spacing: 2) {
                    Text(broker.metadata?.name ?? broker.toolType.replacingOccurrences(of: "_", with: " ").capitalized)
                        .font(.subheadline.weight(.medium))

                    Text("Configured and active")
                        .font(.caption)
                        .foregroundStyle(.statusSuccess)
                }

                Spacer()

                Image(systemName: "checkmark.circle.fill")
                    .foregroundStyle(.statusSuccess)
            }
            .padding(12)
            .background(Color.surfaceElevated, in: RoundedRectangle(cornerRadius: 8))
        }
    }

    // MARK: - Info Box

    private var infoBox: some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: "info.circle.fill")
                .foregroundStyle(.statusInfo)

            Text("The broker you configure here will be automatically enforced on the Risk Manager and Trade Manager agents. You do not need to add it manually to those agents.")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .padding(12)
        .background(Color.statusInfo.opacity(0.08), in: RoundedRectangle(cornerRadius: 8))
    }
}

#Preview {
    ScrollView {
        BrokerSettingsPane(viewModel: PipelineBuilderViewModel())
            .padding()
    }
    .preferredColorScheme(.dark)
}
