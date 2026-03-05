import SwiftUI

struct JsonSchemaFormView: View {
    let schema: AgentConfigSchema
    @Binding var config: [String: AnyCodable]

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            if let title = schema.description {
                Text(title)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            ForEach(sortedProperties, id: \.key) { key, propValue in
                let prop = extractPropertyDict(propValue)
                let isRequired = schema.required?.contains(key) ?? false

                propertyField(key: key, prop: prop, isRequired: isRequired)
            }
        }
    }

    // MARK: - Property Field Router

    @ViewBuilder
    private func propertyField(key: String, prop: [String: Any], isRequired: Bool) -> some View {
        let typeString = prop["type"] as? String ?? "string"
        let label = (prop["title"] as? String) ?? formatLabel(key)
        let description = prop["description"] as? String

        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 4) {
                Text(label)
                    .font(.subheadline.weight(.medium))
                if isRequired {
                    Text("*")
                        .font(.subheadline)
                        .foregroundStyle(.statusError)
                }
            }

            if let description {
                Text(description)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            // Check if it has enum values (select/picker)
            if let enumValues = prop["enum"] as? [Any] {
                enumPicker(key: key, values: enumValues)
            } else {
                switch typeString {
                case "string":
                    stringField(key: key, prop: prop)
                case "number", "integer":
                    numberField(key: key, prop: prop, isInteger: typeString == "integer")
                case "boolean":
                    booleanField(key: key)
                case "array":
                    arrayField(key: key, prop: prop)
                default:
                    stringField(key: key, prop: prop)
                }
            }
        }
    }

    // MARK: - String Field

    @ViewBuilder
    private func stringField(key: String, prop: [String: Any]) -> some View {
        let currentValue = config[key]?.stringValue ?? ""
        let placeholder = prop["default"] as? String ?? ""
        let isMultiline = (prop["format"] as? String) == "textarea"
            || key.lowercased().contains("instruction")
            || key.lowercased().contains("description")

        if isMultiline {
            let binding = Binding<String>(
                get: { config[key]?.stringValue ?? "" },
                set: { config[key] = AnyCodable($0) }
            )
            TextEditor(text: binding)
                .font(.subheadline)
                .frame(minHeight: 80)
                .padding(8)
                .background(Color.surfaceElevated, in: RoundedRectangle(cornerRadius: 8))
        } else {
            TextField(placeholder.isEmpty ? "Enter \(formatLabel(key).lowercased())" : placeholder, text: Binding<String>(
                get: { currentValue },
                set: { config[key] = AnyCodable($0) }
            ))
            .font(.subheadline)
            .textFieldStyle(.roundedBorder)
        }
    }

    // MARK: - Number Field

    @ViewBuilder
    private func numberField(key: String, prop: [String: Any], isInteger: Bool) -> some View {
        let numberString = Binding<String>(
            get: {
                if let dbl = config[key]?.doubleValue {
                    return isInteger ? String(format: "%.0f", dbl) : String(dbl)
                }
                if let intVal = config[key]?.intValue {
                    return "\(intVal)"
                }
                return ""
            },
            set: { newValue in
                if newValue.isEmpty {
                    config.removeValue(forKey: key)
                } else if isInteger, let intVal = Int(newValue) {
                    config[key] = AnyCodable(intVal)
                } else if let dblVal = Double(newValue) {
                    config[key] = AnyCodable(dblVal)
                }
            }
        )

        let minVal = prop["minimum"] as? Double
        let maxVal = prop["maximum"] as? Double
        let placeholder = buildNumberPlaceholder(minVal: minVal, maxVal: maxVal, defaultVal: prop["default"])

        TextField(placeholder, text: numberString)
            .font(.subheadline)
            .keyboardType(isInteger ? .numberPad : .decimalPad)
            .textFieldStyle(.roundedBorder)
    }

    // MARK: - Boolean Field

    @ViewBuilder
    private func booleanField(key: String) -> some View {
        Toggle(isOn: Binding<Bool>(
            get: { config[key]?.boolValue ?? false },
            set: { config[key] = AnyCodable($0) }
        )) {
            EmptyView()
        }
    }

    // MARK: - Enum Picker

    @ViewBuilder
    private func enumPicker(key: String, values: [Any]) -> some View {
        let stringValues = values.compactMap { "\($0)" }
        let currentSelection = Binding<String>(
            get: { config[key]?.stringValue ?? stringValues.first ?? "" },
            set: { config[key] = AnyCodable($0) }
        )

        Picker("", selection: currentSelection) {
            ForEach(stringValues, id: \.self) { value in
                Text(value.replacingOccurrences(of: "_", with: " ").capitalized)
                    .tag(value)
            }
        }
        .pickerStyle(.menu)
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    // MARK: - Array Field (tag input for array of strings)

    @ViewBuilder
    private func arrayField(key: String, prop: [String: Any]) -> some View {
        let items = Binding<[String]>(
            get: {
                if let array = config[key]?.arrayValue as? [String] {
                    return array
                }
                if let array = config[key]?.arrayValue {
                    return array.compactMap { "\($0)" }
                }
                return []
            },
            set: { newItems in
                config[key] = AnyCodable(newItems)
            }
        )

        ArrayTagInput(items: items, placeholder: "Add item")
    }

    // MARK: - Sorted Properties

    private var sortedProperties: [(key: String, value: AnyCodable)] {
        let required = schema.required ?? []
        return schema.properties
            .sorted { a, b in
                let aRequired = required.contains(a.key)
                let bRequired = required.contains(b.key)
                if aRequired != bRequired { return aRequired }
                return a.key < b.key
            }
    }

    // MARK: - Helpers

    private func extractPropertyDict(_ value: AnyCodable) -> [String: Any] {
        value.dictValue ?? [:]
    }

    private func formatLabel(_ key: String) -> String {
        key.replacingOccurrences(of: "_", with: " ")
            .replacingOccurrences(of: "([a-z])([A-Z])", with: "$1 $2", options: .regularExpression)
            .capitalized
    }

    private func buildNumberPlaceholder(minVal: Double?, maxVal: Double?, defaultVal: Any?) -> String {
        var parts: [String] = []
        if let min = minVal { parts.append("min: \(formatNumber(min))") }
        if let max = maxVal { parts.append("max: \(formatNumber(max))") }
        if let def = defaultVal { parts.append("default: \(def)") }
        return parts.isEmpty ? "Enter number" : parts.joined(separator: ", ")
    }

    private func formatNumber(_ value: Double) -> String {
        value == value.rounded() ? String(format: "%.0f", value) : String(value)
    }
}

// MARK: - Array Tag Input

struct ArrayTagInput: View {
    @Binding var items: [String]
    var placeholder: String = "Add item"
    @State private var inputText = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            // Input row
            HStack {
                TextField(placeholder, text: $inputText)
                    .font(.subheadline)
                    .textFieldStyle(.roundedBorder)
                    .onSubmit { addItem() }

                Button {
                    addItem()
                } label: {
                    Image(systemName: "plus.circle.fill")
                        .foregroundStyle(.brandPrimary)
                }
                .disabled(inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }

            // Tags
            if !items.isEmpty {
                FlowLayout(spacing: 6) {
                    ForEach(Array(items.enumerated()), id: \.offset) { index, item in
                        HStack(spacing: 4) {
                            Text(item)
                                .font(.caption.weight(.medium))
                            Button {
                                items.remove(at: index)
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
                }
            }
        }
    }

    private func addItem() {
        let trimmed = inputText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, !items.contains(trimmed) else {
            inputText = ""
            return
        }
        items.append(trimmed)
        inputText = ""
    }
}

#Preview {
    NavigationStack {
        ScrollView {
            JsonSchemaFormView(
                schema: AgentConfigSchema(
                    type: "object",
                    title: "Strategy Config",
                    description: "Configure the strategy agent",
                    properties: [
                        "timeframe": AnyCodable(["type": "string", "title": "Timeframe", "enum": ["1m", "5m", "15m", "1h", "4h", "1d"]]),
                        "max_position_size": AnyCodable(["type": "number", "title": "Max Position Size", "minimum": 0.0, "maximum": 100000.0]),
                        "enable_shorting": AnyCodable(["type": "boolean", "title": "Enable Shorting"]),
                        "indicators": AnyCodable(["type": "array", "title": "Indicators"]),
                        "description": AnyCodable(["type": "string", "title": "Description", "format": "textarea"]),
                    ],
                    required: ["timeframe"]
                ),
                config: .constant([:])
            )
            .padding()
        }
    }
    .preferredColorScheme(.dark)
}
