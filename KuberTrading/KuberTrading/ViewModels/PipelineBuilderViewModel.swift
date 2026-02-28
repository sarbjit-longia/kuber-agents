import Foundation
import OSLog

@Observable
final class PipelineBuilderViewModel {
    // MARK: - Pipeline Metadata

    var pipelineName = "Untitled Pipeline"
    var pipelineDescription = ""
    var executionMode = "paper" // paper, live, simulation, validation
    var triggerMode = "periodic" // signal, periodic

    // MARK: - Agent Slots (fixed 5-agent chain)

    struct AgentSlot: Identifiable {
        let id = UUID()
        let agentType: String
        let title: String
        let icon: String
        var isConfigured: Bool = false
    }

    var slots: [AgentSlot] = [
        AgentSlot(agentType: "market_data_agent", title: "Market Data Agent", icon: "chart.xyaxis.line"),
        AgentSlot(agentType: "bias_agent", title: "Bias Agent", icon: "safari"),
        AgentSlot(agentType: "strategy_agent", title: "Strategy Agent", icon: "brain"),
        AgentSlot(agentType: "risk_manager_agent", title: "Risk Manager", icon: "shield"),
        AgentSlot(agentType: "trade_manager_agent", title: "Trade Manager", icon: "dollarsign.circle"),
    ]

    // MARK: - Setup Items

    enum SetupItem: String, CaseIterable, Identifiable {
        case pipelineSettings = "pipeline_settings"
        case brokerSettings = "broker_settings"
        case signalFilters = "signal_filters"
        case notificationSettings = "notification_settings"
        case approvalSettings = "approval_settings"
        var id: String { rawValue }
    }

    // MARK: - Selection State

    var selectedItemKey: String? = "pipeline_settings"
    var selectedAgentType: String?

    // MARK: - Signal / Trigger

    var scannerId: String?
    var signalSubscriptions: [SignalSubscription] = []
    var scanners: [Scanner] = []
    var signalTypes: [SignalType] = []

    // MARK: - Notification Settings

    var notificationEnabled = false
    var notificationEvents: [String] = []

    // MARK: - Approval Settings

    var requireApproval = false
    var approvalModes: [String] = ["live"]
    var approvalTimeoutMinutes = 15
    var approvalChannels: [String] = ["web"]
    var approvalPhone = ""

    // MARK: - Agent Configs

    var agentNodes: [String: PipelineNode] = [:]
    var editingConfig: [String: AnyCodable] = [:]

    // MARK: - Agent Metadata Cache

    var agentMetadataMap: [String: AgentMetadata] = [:]
    var allTools: [ToolMetadata] = []
    var brokerTools: [ToolMetadata] = []

    // MARK: - Pipeline-Level Broker

    var pipelineBrokerTool: ToolInstance?
    var brokerToolType: String?
    var brokerToolConfig: [String: AnyCodable] = [:]

    // MARK: - State

    var isLoading = false
    var isSaving = false
    var errorMessage: String?
    var currentPipelineId: String?
    var isEditing: Bool { currentPipelineId != nil }

    private let logger = Logger(subsystem: "com.kubertrading.app", category: "PipelineBuilderVM")

    // MARK: - Readiness

    struct ReadinessItem: Identifiable {
        let id = UUID()
        let label: String
        let isReady: Bool
    }

    var readinessItems: [ReadinessItem] {
        var items: [ReadinessItem] = []

        // Pipeline name must not be empty
        items.append(ReadinessItem(
            label: "Pipeline name",
            isReady: !pipelineName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                && pipelineName != "Untitled Pipeline"
        ))

        // Scanner required if trigger mode is "signal"
        if triggerMode == "signal" {
            items.append(ReadinessItem(
                label: "Scanner selected",
                isReady: scannerId != nil && !scannerId!.isEmpty
            ))
        }

        // Instructions for bias_agent
        let biasNode = agentNodes["bias_agent"]
        let biasInstructions = biasNode?.config["instructions"]?.stringValue ?? ""
        items.append(ReadinessItem(
            label: "Bias Agent instructions",
            isReady: !biasInstructions.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        ))

        // Instructions for strategy_agent
        let strategyNode = agentNodes["strategy_agent"]
        let strategyInstructions = strategyNode?.config["instructions"]?.stringValue ?? ""
        items.append(ReadinessItem(
            label: "Strategy Agent instructions",
            isReady: !strategyInstructions.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        ))

        // Instructions for risk_manager_agent
        let riskNode = agentNodes["risk_manager_agent"]
        let riskInstructions = riskNode?.config["instructions"]?.stringValue ?? ""
        items.append(ReadinessItem(
            label: "Risk Manager instructions",
            isReady: !riskInstructions.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        ))

        // Broker configured
        items.append(ReadinessItem(
            label: "Broker configured",
            isReady: pipelineBrokerTool != nil
        ))

        return items
    }

    var isReady: Bool {
        readinessItems.allSatisfy(\.isReady)
    }

    var estimatedCost: Double {
        var total = 0.0
        for agentType in slots.map(\.agentType) {
            if let metadata = agentMetadataMap[agentType] {
                total += metadata.pricingRate
            }
        }
        return total
    }

    // MARK: - Load Initial Data

    @MainActor
    func loadInitialData() async {
        isLoading = true
        errorMessage = nil

        do {
            async let agentsResult = AgentService.shared.listAgents()
            async let toolsResult = ToolService.shared.listTools()
            async let scannersResult = ScannerService.shared.listScanners()
            async let signalTypesResult = ScannerService.shared.getSignalTypes()

            let (agents, tools, loadedScanners, loadedSignalTypes) = try await (
                agentsResult, toolsResult, scannersResult, signalTypesResult
            )

            // Build agent metadata map
            for agent in agents {
                agentMetadataMap[agent.agentType] = agent
            }

            // Store tools and filter broker tools
            allTools = tools
            brokerTools = tools.filter { $0.isBroker == true }

            // Store scanners and signal types
            scanners = loadedScanners
            signalTypes = loadedSignalTypes

            // Initialize agent nodes for each slot if not already present
            for slot in slots {
                if agentNodes[slot.agentType] == nil {
                    agentNodes[slot.agentType] = PipelineNode(
                        id: slot.agentType,
                        agentType: slot.agentType,
                        config: [:],
                        position: nil
                    )
                }
            }
        } catch let error as APIError {
            errorMessage = error.errorDescription
            logger.error("Failed to load initial data: \(error.errorDescription ?? "Unknown")")
        } catch {
            errorMessage = error.localizedDescription
            logger.error("Failed to load initial data: \(error.localizedDescription)")
        }

        isLoading = false
    }

    // MARK: - Load Existing Pipeline for Editing

    @MainActor
    func loadPipeline(id: String) async {
        isLoading = true
        errorMessage = nil

        do {
            let pipeline = try await PipelineService.shared.getPipeline(id: id)
            currentPipelineId = pipeline.id
            pipelineName = pipeline.name
            pipelineDescription = pipeline.description ?? ""
            executionMode = pipeline.config.mode ?? "paper"
            triggerMode = pipeline.triggerMode
            scannerId = pipeline.scannerId
            signalSubscriptions = pipeline.signalSubscriptions ?? []
            notificationEnabled = pipeline.notificationEnabled
            notificationEvents = pipeline.notificationEvents ?? []
            requireApproval = pipeline.requireApproval
            approvalModes = pipeline.approvalModes ?? ["live"]
            approvalTimeoutMinutes = pipeline.approvalTimeoutMinutes
            approvalChannels = pipeline.approvalChannels ?? ["web"]
            approvalPhone = pipeline.approvalPhone ?? ""

            // Restore broker tool from pipeline config
            if let brokerToolData = pipeline.config.brokerTool,
               let brokerDict = brokerToolData.dictValue {
                let toolType = brokerDict["tool_type"] as? String ?? brokerDict["toolType"] as? String
                if let toolType {
                    var configDict: [String: AnyCodable] = [:]
                    if let rawConfig = brokerDict["config"] as? [String: Any] {
                        for (key, val) in rawConfig {
                            configDict[key] = AnyCodable(val)
                        }
                    }
                    let metadata = allTools.first { $0.toolType == toolType }
                    pipelineBrokerTool = ToolInstance(
                        toolType: toolType,
                        enabled: true,
                        config: configDict,
                        metadata: metadata
                    )
                    brokerToolType = toolType
                    brokerToolConfig = configDict
                }
            }

            // Restore agent nodes from pipeline config
            for node in pipeline.config.nodes {
                agentNodes[node.agentType] = node
            }

            // Update slot configured status
            updateSlotConfiguredStatus()
        } catch let error as APIError {
            errorMessage = error.errorDescription
            logger.error("Failed to load pipeline: \(error.errorDescription ?? "Unknown")")
        } catch {
            errorMessage = error.localizedDescription
            logger.error("Failed to load pipeline: \(error.localizedDescription)")
        }

        isLoading = false
    }

    // MARK: - Selection

    func selectSetupItem(_ key: String) {
        selectedItemKey = key
        selectedAgentType = nil
    }

    func selectAgent(_ agentType: String) {
        selectedAgentType = agentType
        selectedItemKey = nil

        // Load the current config for editing
        if let node = agentNodes[agentType] {
            editingConfig = node.config
        } else {
            editingConfig = [:]
        }
    }

    // MARK: - Agent Config Updates

    func updateAgentConfig(agentType: String, config: [String: AnyCodable]) {
        if var node = agentNodes[agentType] {
            // Merge new config into existing
            for (key, value) in config {
                node.config[key] = value
            }
            agentNodes[agentType] = node
        } else {
            agentNodes[agentType] = PipelineNode(
                id: agentType,
                agentType: agentType,
                config: config,
                position: nil
            )
        }
        updateSlotConfiguredStatus()
    }

    func updateAgentInstructions(agentType: String, instructions: String) {
        var config = agentNodes[agentType]?.config ?? [:]
        config["instructions"] = AnyCodable(instructions)
        updateAgentConfig(agentType: agentType, config: config)
    }

    func updateAgentTools(agentType: String, tools: [ToolInstance]) {
        var config = agentNodes[agentType]?.config ?? [:]

        // Encode tools as array of dictionaries
        let toolDicts: [[String: Any]] = tools.map { tool in
            var dict: [String: Any] = [
                "tool_type": tool.toolType,
                "enabled": tool.enabled,
            ]
            var configDict: [String: Any] = [:]
            for (key, value) in tool.config {
                configDict[key] = value.value
            }
            dict["config"] = configDict
            return dict
        }

        config["tools"] = AnyCodable(toolDicts)
        updateAgentConfig(agentType: agentType, config: config)
    }

    // MARK: - Broker Tool Management

    func setBrokerTool(toolType: String, config: [String: AnyCodable]) {
        let metadata = allTools.first { $0.toolType == toolType }
        pipelineBrokerTool = ToolInstance(
            toolType: toolType,
            enabled: true,
            config: config,
            metadata: metadata
        )
        brokerToolType = toolType
        brokerToolConfig = config
        enforceBrokerOnAgents()
    }

    func removeBrokerTool() {
        pipelineBrokerTool = nil
        brokerToolType = nil
        brokerToolConfig = [:]

        // Remove broker tools from risk_manager and trade_manager
        removeBrokerToolFromAgent("risk_manager_agent")
        removeBrokerToolFromAgent("trade_manager_agent")
    }

    private func enforceBrokerOnAgents() {
        guard let brokerTool = pipelineBrokerTool else { return }

        let agentTypes = ["risk_manager_agent", "trade_manager_agent"]
        for agentType in agentTypes {
            var config = agentNodes[agentType]?.config ?? [:]

            // Get existing tools, removing any existing broker tools
            var existingTools: [[String: Any]] = []
            if let toolsAnyCodable = config["tools"],
               let toolsArray = toolsAnyCodable.arrayValue as? [[String: Any]] {
                existingTools = toolsArray.filter { toolDict in
                    let tt = toolDict["tool_type"] as? String ?? toolDict["toolType"] as? String ?? ""
                    return !isBrokerToolType(tt)
                }
            }

            // Add the pipeline-level broker tool
            var brokerDict: [String: Any] = [
                "tool_type": brokerTool.toolType,
                "enabled": true,
            ]
            var brokerConfig: [String: Any] = [:]
            for (key, value) in brokerTool.config {
                brokerConfig[key] = value.value
            }
            brokerDict["config"] = brokerConfig
            existingTools.append(brokerDict)

            config["tools"] = AnyCodable(existingTools)
            updateAgentConfig(agentType: agentType, config: config)
        }
    }

    private func removeBrokerToolFromAgent(_ agentType: String) {
        guard var config = agentNodes[agentType]?.config else { return }

        if let toolsAnyCodable = config["tools"],
           let toolsArray = toolsAnyCodable.arrayValue as? [[String: Any]] {
            let filtered = toolsArray.filter { toolDict in
                let tt = toolDict["tool_type"] as? String ?? toolDict["toolType"] as? String ?? ""
                return !isBrokerToolType(tt)
            }
            config["tools"] = AnyCodable(filtered)
            agentNodes[agentType]?.config = config
        }
    }

    private func isBrokerToolType(_ toolType: String) -> Bool {
        brokerTools.contains { $0.toolType == toolType }
    }

    // MARK: - Signal Subscriptions

    func addSignalSubscription(_ subscription: SignalSubscription) {
        signalSubscriptions.append(subscription)
    }

    func removeSignalSubscription(at index: Int) {
        guard index >= 0 && index < signalSubscriptions.count else { return }
        signalSubscriptions.remove(at: index)
    }

    // MARK: - Save Pipeline

    @MainActor
    func savePipeline() async -> String? {
        guard isReady else {
            errorMessage = "Pipeline is not ready. Please complete all required fields."
            return nil
        }

        isSaving = true
        errorMessage = nil

        do {
            enforceBrokerOnAgents()

            let savedPipeline: Pipeline
            if let pipelineId = currentPipelineId {
                let update = buildPipelineUpdate()
                savedPipeline = try await PipelineService.shared.updatePipeline(id: pipelineId, update)
            } else {
                let create = buildPipelineCreate()
                savedPipeline = try await PipelineService.shared.createPipeline(create)
            }

            currentPipelineId = savedPipeline.id
            isSaving = false
            return savedPipeline.id
        } catch let error as APIError {
            errorMessage = error.errorDescription
            logger.error("Failed to save pipeline: \(error.errorDescription ?? "Unknown")")
        } catch {
            errorMessage = error.localizedDescription
            logger.error("Failed to save pipeline: \(error.localizedDescription)")
        }

        isSaving = false
        return nil
    }

    // MARK: - Save and Execute

    @MainActor
    func saveAndExecute() async -> String? {
        guard let pipelineId = await savePipeline() else { return nil }

        do {
            let execution = try await ExecutionService.shared.createExecution(
                pipelineId: pipelineId,
                mode: executionMode
            )
            return execution.id
        } catch let error as APIError {
            errorMessage = error.errorDescription
            logger.error("Failed to execute pipeline: \(error.errorDescription ?? "Unknown")")
        } catch {
            errorMessage = error.localizedDescription
            logger.error("Failed to execute pipeline: \(error.localizedDescription)")
        }

        return nil
    }

    // MARK: - Build Pipeline Config

    private func buildPipelineConfig() -> PipelineConfig {
        var nodes: [PipelineNode] = []
        for slot in slots {
            if let node = agentNodes[slot.agentType] {
                nodes.append(node)
            } else {
                nodes.append(PipelineNode(
                    id: slot.agentType,
                    agentType: slot.agentType,
                    config: [:],
                    position: nil
                ))
            }
        }

        // Build edges for the linear chain
        var edges: [PipelineEdge] = []
        for i in 0 ..< (slots.count - 1) {
            edges.append(PipelineEdge(
                from: slots[i].agentType,
                to: slots[i + 1].agentType
            ))
        }

        // Build broker tool representation
        var brokerToolAnyCodable: AnyCodable?
        if let brokerTool = pipelineBrokerTool {
            var brokerDict: [String: Any] = [
                "tool_type": brokerTool.toolType,
                "enabled": true,
            ]
            var configDict: [String: Any] = [:]
            for (key, value) in brokerTool.config {
                configDict[key] = value.value
            }
            brokerDict["config"] = configDict
            brokerToolAnyCodable = AnyCodable(brokerDict)
        }

        return PipelineConfig(
            symbol: nil,
            mode: executionMode,
            brokerTool: brokerToolAnyCodable,
            nodes: nodes,
            edges: edges
        )
    }

    private func buildPipelineCreate() -> PipelineCreate {
        PipelineCreate(
            name: pipelineName.trimmingCharacters(in: .whitespacesAndNewlines),
            description: pipelineDescription.isEmpty ? nil : pipelineDescription,
            config: buildPipelineConfig(),
            isActive: true,
            triggerMode: triggerMode,
            scannerId: triggerMode == "signal" ? scannerId : nil,
            signalSubscriptions: triggerMode == "signal" && !signalSubscriptions.isEmpty
                ? signalSubscriptions : nil,
            notificationEnabled: notificationEnabled,
            notificationEvents: notificationEnabled && !notificationEvents.isEmpty
                ? notificationEvents : nil,
            requireApproval: requireApproval,
            approvalModes: requireApproval ? approvalModes : nil,
            approvalTimeoutMinutes: approvalTimeoutMinutes,
            approvalChannels: requireApproval ? approvalChannels : nil,
            approvalPhone: requireApproval && !approvalPhone.isEmpty ? approvalPhone : nil
        )
    }

    private func buildPipelineUpdate() -> PipelineUpdate {
        PipelineUpdate(
            name: pipelineName.trimmingCharacters(in: .whitespacesAndNewlines),
            description: pipelineDescription.isEmpty ? nil : pipelineDescription,
            config: buildPipelineConfig(),
            isActive: nil,
            triggerMode: triggerMode,
            scannerId: triggerMode == "signal" ? scannerId : nil,
            signalSubscriptions: triggerMode == "signal" && !signalSubscriptions.isEmpty
                ? signalSubscriptions : nil,
            notificationEnabled: notificationEnabled,
            notificationEvents: notificationEnabled && !notificationEvents.isEmpty
                ? notificationEvents : nil,
            requireApproval: requireApproval,
            approvalModes: requireApproval ? approvalModes : nil,
            approvalTimeoutMinutes: approvalTimeoutMinutes,
            approvalChannels: requireApproval ? approvalChannels : nil,
            approvalPhone: requireApproval && !approvalPhone.isEmpty ? approvalPhone : nil
        )
    }

    // MARK: - Helpers

    private func updateSlotConfiguredStatus() {
        for i in 0 ..< slots.count {
            let agentType = slots[i].agentType
            if let node = agentNodes[agentType] {
                let hasInstructions = !(node.config["instructions"]?.stringValue ?? "").isEmpty
                let hasTools = node.config["tools"]?.arrayValue?.isEmpty == false
                let hasAnyConfig = !node.config.isEmpty
                slots[i].isConfigured = hasInstructions || hasTools || hasAnyConfig
            } else {
                slots[i].isConfigured = false
            }
        }
    }
}
