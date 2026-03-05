import SwiftUI

struct ToolSelectorView: View {
    let availableTools: [ToolMetadata]
    @Binding var attachedTools: [ToolInstance]
    var excludeBrokerTools: Bool = true

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("Tools")
                    .font(.subheadline.weight(.semibold))

                Spacer()

                Text("\(enabledCount) enabled")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            if filteredTools.isEmpty {
                noToolsView
            } else {
                VStack(spacing: 0) {
                    ForEach(filteredTools) { tool in
                        let isEnabled = isToolEnabled(tool.toolType)

                        VStack(spacing: 0) {
                            toolRow(tool: tool, isEnabled: isEnabled)

                            // Expanded config if enabled and has config schema
                            if isEnabled, let configSchema = tool.configSchema,
                               let schemaDict = configSchema.dictValue,
                               !schemaDict.isEmpty {
                                toolConfigSection(toolType: tool.toolType, schemaDict: schemaDict)
                            }

                            if tool.id != filteredTools.last?.id {
                                Divider().padding(.horizontal)
                            }
                        }
                    }
                }
                .background(Color.surfaceCard, in: RoundedRectangle(cornerRadius: 12))
            }
        }
    }

    // MARK: - Tool Row

    @ViewBuilder
    private func toolRow(tool: ToolMetadata, isEnabled: Bool) -> some View {
        HStack(spacing: 12) {
            Image(systemName: toolIcon(tool.category))
                .font(.body)
                .foregroundStyle(isEnabled ? .brandPrimary : .secondary)
                .frame(width: 28, height: 28)
                .background(
                    (isEnabled ? Color.brandPrimary : Color.secondary).opacity(0.15),
                    in: Circle()
                )

            VStack(alignment: .leading, spacing: 2) {
                Text(tool.name)
                    .font(.subheadline.weight(.medium))
                    .foregroundStyle(isEnabled ? .primary : .secondary)

                Text(tool.description)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            }

            Spacer()

            Toggle("", isOn: Binding(
                get: { isEnabled },
                set: { newValue in
                    toggleTool(tool: tool, enabled: newValue)
                }
            ))
            .labelsHidden()
        }
        .padding(.horizontal)
        .padding(.vertical, 10)
    }

    // MARK: - Tool Config Section

    @ViewBuilder
    private func toolConfigSection(toolType: String, schemaDict: [String: Any]) -> some View {
        if let index = attachedTools.firstIndex(where: { $0.toolType == toolType }) {
            VStack(alignment: .leading, spacing: 8) {
                Text("Configuration")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)

                // Render simple key-value config fields from schema
                let properties = schemaDict["properties"] as? [String: Any] ?? [:]
                ForEach(properties.keys.sorted(), id: \.self) { key in
                    if let propDict = properties[key] as? [String: Any] {
                        let typeStr = propDict["type"] as? String ?? "string"
                        let label = (propDict["title"] as? String) ?? key.replacingOccurrences(of: "_", with: " ").capitalized

                        HStack {
                            Text(label)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            Spacer()

                            if typeStr == "boolean" {
                                Toggle("", isOn: Binding(
                                    get: { attachedTools[index].config[key]?.boolValue ?? false },
                                    set: { attachedTools[index].config[key] = AnyCodable($0) }
                                ))
                                .labelsHidden()
                            } else {
                                TextField("", text: Binding(
                                    get: { attachedTools[index].config[key]?.stringValue ?? "" },
                                    set: { attachedTools[index].config[key] = AnyCodable($0) }
                                ))
                                .font(.caption)
                                .textFieldStyle(.roundedBorder)
                                .frame(maxWidth: 160)
                            }
                        }
                    }
                }
            }
            .padding(.horizontal)
            .padding(.bottom, 12)
            .padding(.top, 4)
            .background(Color.surfaceElevated.opacity(0.5))
        }
    }

    // MARK: - No Tools View

    private var noToolsView: some View {
        VStack(spacing: 8) {
            Image(systemName: "wrench.and.screwdriver")
                .font(.title2)
                .foregroundStyle(.secondary)
            Text("No tools available")
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 24)
        .background(Color.surfaceCard, in: RoundedRectangle(cornerRadius: 12))
    }

    // MARK: - Helpers

    private var filteredTools: [ToolMetadata] {
        if excludeBrokerTools {
            return availableTools.filter { $0.isBroker != true }
        }
        return availableTools
    }

    private var enabledCount: Int {
        attachedTools.filter(\.enabled).count
    }

    private func isToolEnabled(_ toolType: String) -> Bool {
        attachedTools.first(where: { $0.toolType == toolType })?.enabled ?? false
    }

    private func toggleTool(tool: ToolMetadata, enabled: Bool) {
        if let index = attachedTools.firstIndex(where: { $0.toolType == tool.toolType }) {
            attachedTools[index].enabled = enabled
        } else if enabled {
            attachedTools.append(ToolInstance(
                toolType: tool.toolType,
                enabled: true,
                config: [:],
                metadata: tool
            ))
        }
    }

    private func toolIcon(_ category: String) -> String {
        switch category.lowercased() {
        case "market_data", "data":
            return "chart.bar"
        case "broker":
            return "building.columns"
        case "analysis":
            return "waveform.path.ecg"
        case "notification":
            return "bell"
        case "search":
            return "magnifyingglass"
        default:
            return "wrench"
        }
    }
}

#Preview {
    ScrollView {
        ToolSelectorView(
            availableTools: [
                ToolMetadata(toolType: "market_data", name: "Market Data", description: "Fetch real-time and historical market data", category: "data", configSchema: nil, isBroker: false),
                ToolMetadata(toolType: "technical_analysis", name: "Technical Analysis", description: "Calculate technical indicators like RSI, MACD, Bollinger Bands", category: "analysis", configSchema: nil, isBroker: false),
                ToolMetadata(toolType: "alpaca_broker", name: "Alpaca Broker", description: "Execute trades via Alpaca", category: "broker", configSchema: nil, isBroker: true),
            ],
            attachedTools: .constant([
                ToolInstance(toolType: "market_data", enabled: true, config: [:], metadata: nil),
            ]),
            excludeBrokerTools: true
        )
        .padding()
    }
    .background(Color.surfaceBackground)
    .preferredColorScheme(.dark)
}
