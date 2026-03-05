import SwiftUI

struct AgentConfigPane: View {
    let agentType: String
    @Bindable var viewModel: PipelineBuilderViewModel

    @State private var instructions: String = ""
    @State private var documentUrl: String = ""

    private var metadata: AgentMetadata? {
        viewModel.agentMetadataMap[agentType]
    }

    private var currentNode: PipelineNode? {
        viewModel.agentNodes[agentType]
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            // Header
            agentHeader

            Divider()

            // Instructions
            instructionsSection

            // Document URL
            documentUrlSection

            // Config Form
            if let metadata, !metadata.configSchema.properties.isEmpty {
                configFormSection(metadata)
            }

            // Tools
            toolsSection

            // Pricing
            pricingSection
        }
        .onAppear {
            loadCurrentConfig()
        }
        .onChange(of: agentType) {
            loadCurrentConfig()
        }
    }

    // MARK: - Agent Header

    private var agentHeader: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 12) {
                if let metadata {
                    Image(systemName: slotIcon)
                        .font(.title2)
                        .foregroundStyle(.brandPrimary)
                        .frame(width: 44, height: 44)
                        .background(Color.brandPrimary.opacity(0.12), in: RoundedRectangle(cornerRadius: 10))

                    VStack(alignment: .leading, spacing: 2) {
                        Text(metadata.name)
                            .font(.headline)

                        Text(metadata.category.capitalized)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }

                    Spacer()

                    if metadata.isFree {
                        Text("Free")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(.statusSuccess)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 4)
                            .background(Color.statusSuccess.opacity(0.12), in: Capsule())
                    }
                } else {
                    Text(agentType.replacingOccurrences(of: "_", with: " ").capitalized)
                        .font(.headline)
                }
            }

            if let description = metadata?.description {
                Text(description)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }
        }
    }

    // MARK: - Instructions Section

    private var instructionsSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label("Instructions", systemImage: "doc.text")
                .font(.subheadline.weight(.semibold))

            Text("Tell this agent what to do. Be specific about your trading strategy, rules, and preferences.")
                .font(.caption)
                .foregroundStyle(.secondary)

            TextEditor(text: $instructions)
                .font(.body)
                .scrollContentBackground(.hidden)
                .padding(8)
                .frame(minHeight: 120, maxHeight: 240)
                .background(Color.surfaceElevated, in: RoundedRectangle(cornerRadius: 8))
                .onChange(of: instructions) {
                    viewModel.updateAgentInstructions(agentType: agentType, instructions: instructions)
                }
        }
    }

    // MARK: - Document URL Section

    private var documentUrlSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label("Document URL", systemImage: "link")
                .font(.subheadline.weight(.semibold))

            Text("Optional: Link to a trading plan or strategy document.")
                .font(.caption)
                .foregroundStyle(.secondary)

            TextField("https://...", text: $documentUrl)
                .textFieldStyle(.plain)
                .padding(10)
                .background(Color.surfaceElevated, in: RoundedRectangle(cornerRadius: 8))
                .keyboardType(.URL)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
                .onChange(of: documentUrl) {
                    var config = currentNode?.config ?? [:]
                    config["document_url"] = AnyCodable(documentUrl)
                    viewModel.updateAgentConfig(agentType: agentType, config: config)
                }
        }
    }

    // MARK: - Config Form Section

    @ViewBuilder
    private func configFormSection(_ metadata: AgentMetadata) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Label("Configuration", systemImage: "slider.horizontal.3")
                .font(.subheadline.weight(.semibold))

            if let schemaDescription = metadata.configSchema.description {
                Text(schemaDescription)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            // Render config properties as form fields
            ForEach(sortedProperties(metadata.configSchema), id: \.key) { key, propValue in
                configField(key: key, property: propValue, required: metadata.configSchema.required ?? [])
            }
        }
    }

    // MARK: - Tools Section

    private var toolsSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label("Tools", systemImage: "wrench.and.screwdriver")
                .font(.subheadline.weight(.semibold))

            Text("Select tools this agent can use during execution.")
                .font(.caption)
                .foregroundStyle(.secondary)

            let agentTools = availableToolsForAgent
            if agentTools.isEmpty {
                Text("No tools available for this agent type.")
                    .font(.caption)
                    .foregroundStyle(.tertiary)
                    .padding(.vertical, 8)
            } else {
                ForEach(agentTools) { tool in
                    toolToggleRow(tool)
                }
            }
        }
    }

    // MARK: - Pricing Section

    private var pricingSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label("Pricing", systemImage: "dollarsign.circle")
                .font(.subheadline.weight(.semibold))

            if let metadata {
                HStack {
                    Text("Rate per execution")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)

                    Spacer()

                    Text(metadata.pricingRate.costFormatted)
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(.statusWarning)
                }
                .padding(12)
                .background(Color.surfaceElevated, in: RoundedRectangle(cornerRadius: 8))
            }
        }
    }

    // MARK: - Tool Toggle Row

    private func toolToggleRow(_ tool: ToolMetadata) -> some View {
        let isEnabled = isToolEnabled(tool.toolType)

        return HStack(spacing: 12) {
            Image(systemName: "wrench")
                .font(.callout)
                .foregroundStyle(isEnabled ? .brandPrimary : .secondary)
                .frame(width: 28, height: 28)
                .background(
                    (isEnabled ? Color.brandPrimary : Color.secondary).opacity(0.12),
                    in: RoundedRectangle(cornerRadius: 6)
                )

            VStack(alignment: .leading, spacing: 2) {
                Text(tool.name)
                    .font(.subheadline)

                Text(tool.description)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            }

            Spacer()

            Toggle("", isOn: Binding(
                get: { isEnabled },
                set: { newValue in toggleTool(tool.toolType, enabled: newValue) }
            ))
            .labelsHidden()
            .tint(.brandPrimary)
        }
        .padding(8)
        .background(Color.surfaceElevated, in: RoundedRectangle(cornerRadius: 8))
    }

    // MARK: - Config Field

    @ViewBuilder
    private func configField(key: String, property: AnyCodable, required: [String]) -> some View {
        let propDict = property.dictValue ?? [:]
        let title = propDict["title"] as? String ?? key.replacingOccurrences(of: "_", with: " ").capitalized
        let type = propDict["type"] as? String ?? "string"
        let description = propDict["description"] as? String
        let isRequired = required.contains(key)

        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 4) {
                Text(title)
                    .font(.caption.weight(.medium))

                if isRequired {
                    Text("*")
                        .font(.caption)
                        .foregroundStyle(.statusError)
                }
            }

            if let description {
                Text(description)
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }

            switch type {
            case "boolean":
                Toggle(title, isOn: Binding(
                    get: { currentNode?.config[key]?.boolValue ?? false },
                    set: { newValue in
                        viewModel.updateAgentConfig(agentType: agentType, config: [key: AnyCodable(newValue)])
                    }
                ))
                .labelsHidden()
                .tint(.brandPrimary)

            case "number", "integer":
                TextField(title, text: Binding(
                    get: {
                        if let val = currentNode?.config[key]?.doubleValue {
                            return String(val)
                        }
                        if let val = currentNode?.config[key]?.intValue {
                            return String(val)
                        }
                        return ""
                    },
                    set: { newValue in
                        if type == "integer", let intVal = Int(newValue) {
                            viewModel.updateAgentConfig(agentType: agentType, config: [key: AnyCodable(intVal)])
                        } else if let doubleVal = Double(newValue) {
                            viewModel.updateAgentConfig(agentType: agentType, config: [key: AnyCodable(doubleVal)])
                        }
                    }
                ))
                .textFieldStyle(.plain)
                .padding(10)
                .background(Color.surfaceElevated, in: RoundedRectangle(cornerRadius: 8))
                .keyboardType(.decimalPad)

            default:
                // String or fallback
                if let enumValues = propDict["enum"] as? [String] {
                    Picker(title, selection: Binding(
                        get: { currentNode?.config[key]?.stringValue ?? "" },
                        set: { newValue in
                            viewModel.updateAgentConfig(agentType: agentType, config: [key: AnyCodable(newValue)])
                        }
                    )) {
                        Text("Select...").tag("")
                        ForEach(enumValues, id: \.self) { val in
                            Text(val.replacingOccurrences(of: "_", with: " ").capitalized).tag(val)
                        }
                    }
                    .pickerStyle(.menu)
                    .tint(.brandPrimary)
                } else {
                    TextField(title, text: Binding(
                        get: { currentNode?.config[key]?.stringValue ?? "" },
                        set: { newValue in
                            viewModel.updateAgentConfig(agentType: agentType, config: [key: AnyCodable(newValue)])
                        }
                    ))
                    .textFieldStyle(.plain)
                    .padding(10)
                    .background(Color.surfaceElevated, in: RoundedRectangle(cornerRadius: 8))
                }
            }
        }
    }

    // MARK: - Helpers

    private var slotIcon: String {
        viewModel.slots.first(where: { $0.agentType == agentType })?.icon ?? "cpu"
    }

    private var availableToolsForAgent: [ToolMetadata] {
        // Filter out broker tools (managed at pipeline level) and show non-broker tools
        viewModel.allTools.filter { tool in
            tool.isBroker != true
        }
    }

    private func isToolEnabled(_ toolType: String) -> Bool {
        guard let toolsAnyCodable = currentNode?.config["tools"],
              let toolsArray = toolsAnyCodable.arrayValue as? [[String: Any]] else {
            return false
        }
        return toolsArray.contains { dict in
            let tt = dict["tool_type"] as? String ?? dict["toolType"] as? String ?? ""
            let enabled = dict["enabled"] as? Bool ?? true
            return tt == toolType && enabled
        }
    }

    private func toggleTool(_ toolType: String, enabled: Bool) {
        var currentTools: [ToolInstance] = []

        if let toolsAnyCodable = currentNode?.config["tools"],
           let toolsArray = toolsAnyCodable.arrayValue as? [[String: Any]] {
            currentTools = toolsArray.compactMap { dict in
                guard let tt = dict["tool_type"] as? String ?? dict["toolType"] as? String else { return nil }
                let isEnabled = dict["enabled"] as? Bool ?? true
                var config: [String: AnyCodable] = [:]
                if let rawConfig = dict["config"] as? [String: Any] {
                    for (key, val) in rawConfig {
                        config[key] = AnyCodable(val)
                    }
                }
                return ToolInstance(toolType: tt, enabled: isEnabled, config: config, metadata: nil)
            }
        }

        if enabled {
            // Add tool if not present
            if !currentTools.contains(where: { $0.toolType == toolType }) {
                currentTools.append(ToolInstance(toolType: toolType, enabled: true, config: [:], metadata: nil))
            }
        } else {
            // Remove tool
            currentTools.removeAll { $0.toolType == toolType }
        }

        viewModel.updateAgentTools(agentType: agentType, tools: currentTools)
    }

    private func loadCurrentConfig() {
        instructions = currentNode?.config["instructions"]?.stringValue ?? ""
        documentUrl = currentNode?.config["document_url"]?.stringValue ?? ""
    }

    private func sortedProperties(_ schema: AgentConfigSchema) -> [(key: String, value: AnyCodable)] {
        // Filter out "instructions", "tools", "document_url" as they have dedicated sections
        let excluded = ["instructions", "tools", "document_url"]
        return schema.properties
            .filter { !excluded.contains($0.key) }
            .sorted { $0.key < $1.key }
    }
}

#Preview {
    ScrollView {
        AgentConfigPane(
            agentType: "strategy_agent",
            viewModel: PipelineBuilderViewModel()
        )
        .padding()
    }
    .preferredColorScheme(.dark)
}
