import SwiftUI

struct PipelineBuilderView: View {
    let pipelineId: String?
    @State private var viewModel = PipelineBuilderViewModel()
    @Environment(NavigationRouter.self) private var router
    @Environment(\.horizontalSizeClass) private var sizeClass
    @State private var showSaveSuccess = false

    var body: some View {
        Group {
            if viewModel.isLoading && viewModel.agentMetadataMap.isEmpty {
                LoadingView(message: "Loading builder...")
            } else if sizeClass == .regular {
                iPadLayout
            } else {
                iPhoneLayout
            }
        }
        .navigationTitle(viewModel.isEditing ? "Edit Pipeline" : "New Pipeline")
        .navigationBarTitleDisplayMode(.inline)
        .overlay {
            if viewModel.isSaving {
                LoadingOverlay(message: "Saving pipeline...")
            }
        }
        .task {
            await viewModel.loadInitialData()
            if let pipelineId {
                await viewModel.loadPipeline(id: pipelineId)
            }
        }
    }

    // MARK: - iPad Layout (NavigationSplitView)

    private var iPadLayout: some View {
        NavigationSplitView {
            sidebarContent
                .navigationSplitViewColumnWidth(min: 280, ideal: 320, max: 360)
        } detail: {
            detailContent
        }
    }

    // MARK: - iPhone Layout (scrollable list -> detail)

    private var iPhoneLayout: some View {
        ScrollView {
            LazyVStack(spacing: 0) {
                // Error banner
                if let error = viewModel.errorMessage {
                    ErrorBanner(message: error) {
                        viewModel.errorMessage = nil
                    }
                    .padding(.bottom, 8)
                }

                // Success banner
                if showSaveSuccess {
                    SuccessBanner(message: "Pipeline saved successfully.") {
                        showSaveSuccess = false
                    }
                    .padding(.bottom, 8)
                }

                // Setup Items Section
                setupItemsSection

                // Agent Slots Section
                agentSlotsSection

                // Readiness Checklist
                ReadinessChecklistView(items: viewModel.readinessItems, isReady: viewModel.isReady)
                    .padding(.horizontal)
                    .padding(.top, 12)

                // Estimated Cost
                estimatedCostRow
                    .padding(.horizontal)
                    .padding(.top, 8)

                // Action Buttons
                actionButtons
                    .padding(.horizontal)
                    .padding(.vertical, 16)
            }
        }
    }

    // MARK: - Sidebar Content

    private var sidebarContent: some View {
        List(selection: Binding(
            get: { viewModel.selectedItemKey ?? viewModel.selectedAgentType },
            set: { newValue in
                guard let newValue else { return }
                if PipelineBuilderViewModel.SetupItem.allCases.contains(where: { $0.rawValue == newValue }) {
                    viewModel.selectSetupItem(newValue)
                } else {
                    viewModel.selectAgent(newValue)
                }
            }
        )) {
            // Error banner
            if let error = viewModel.errorMessage {
                Section {
                    ErrorBanner(message: error) {
                        viewModel.errorMessage = nil
                    }
                }
                .listRowInsets(EdgeInsets())
                .listRowBackground(Color.clear)
            }

            // Success banner
            if showSaveSuccess {
                Section {
                    SuccessBanner(message: "Pipeline saved successfully.") {
                        showSaveSuccess = false
                    }
                }
                .listRowInsets(EdgeInsets())
                .listRowBackground(Color.clear)
            }

            // Setup items
            Section("Setup") {
                ForEach(PipelineBuilderViewModel.SetupItem.allCases) { item in
                    setupItemRow(item)
                        .tag(item.rawValue)
                }
            }

            // Agent slots
            Section("Agents") {
                AgentSlotListView(
                    slots: viewModel.slots,
                    selectedAgentType: viewModel.selectedAgentType,
                    onSelect: { viewModel.selectAgent($0) }
                )
            }

            // Readiness
            Section("Readiness") {
                ReadinessChecklistView(
                    items: viewModel.readinessItems,
                    isReady: viewModel.isReady
                )
            }

            // Estimated Cost
            Section {
                estimatedCostRow
            }

            // Actions
            Section {
                actionButtons
            }
            .listRowBackground(Color.clear)
            .listRowInsets(EdgeInsets(top: 8, leading: 0, bottom: 8, trailing: 0))
        }
        .listStyle(.insetGrouped)
        .scrollContentBackground(.hidden)
    }

    // MARK: - Detail Content

    @ViewBuilder
    private var detailContent: some View {
        if let itemKey = viewModel.selectedItemKey {
            ScrollView {
                setupDetailPane(for: itemKey)
                    .padding()
            }
        } else if let agentType = viewModel.selectedAgentType {
            ScrollView {
                AgentConfigPane(
                    agentType: agentType,
                    viewModel: viewModel
                )
                .padding()
            }
        } else {
            EmptyStateView(
                icon: "sidebar.left",
                title: "Select an Item",
                message: "Choose a setup item or agent from the sidebar to configure it."
            )
        }
    }

    // MARK: - Setup Items Section (iPhone)

    private var setupItemsSection: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text("Setup")
                .sectionHeader()
                .padding(.horizontal)
                .padding(.top, 16)
                .padding(.bottom, 8)

            ForEach(PipelineBuilderViewModel.SetupItem.allCases) { item in
                NavigationLink {
                    ScrollView {
                        setupDetailPane(for: item.rawValue)
                            .padding()
                    }
                    .navigationTitle(setupItemTitle(item))
                    .navigationBarTitleDisplayMode(.inline)
                } label: {
                    setupItemRow(item)
                }
                .buttonStyle(.plain)

                if item != PipelineBuilderViewModel.SetupItem.allCases.last {
                    Divider().padding(.leading, 56)
                }
            }
        }
    }

    // MARK: - Agent Slots Section (iPhone)

    private var agentSlotsSection: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text("Agents")
                .sectionHeader()
                .padding(.horizontal)
                .padding(.top, 16)
                .padding(.bottom, 8)

            ForEach(viewModel.slots) { slot in
                NavigationLink {
                    ScrollView {
                        AgentConfigPane(
                            agentType: slot.agentType,
                            viewModel: viewModel
                        )
                        .padding()
                    }
                    .navigationTitle(slot.title)
                    .navigationBarTitleDisplayMode(.inline)
                } label: {
                    agentSlotRow(slot)
                }
                .buttonStyle(.plain)

                if slot.id != viewModel.slots.last?.id {
                    Divider().padding(.leading, 56)
                }
            }
        }
    }

    // MARK: - Setup Item Row

    private func setupItemRow(_ item: PipelineBuilderViewModel.SetupItem) -> some View {
        HStack(spacing: 12) {
            Image(systemName: setupItemIcon(item))
                .font(.body)
                .foregroundStyle(.brandPrimary)
                .frame(width: 32, height: 32)
                .background(Color.brandPrimary.opacity(0.12), in: RoundedRectangle(cornerRadius: 8))

            Text(setupItemTitle(item))
                .font(.subheadline)
                .foregroundStyle(.primary)

            Spacer()

            Image(systemName: "chevron.right")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .padding(.horizontal)
        .padding(.vertical, 10)
    }

    // MARK: - Agent Slot Row (iPhone)

    private func agentSlotRow(_ slot: PipelineBuilderViewModel.AgentSlot) -> some View {
        HStack(spacing: 12) {
            Image(systemName: slot.icon)
                .font(.body)
                .foregroundStyle(slot.isConfigured ? .statusSuccess : .secondary)
                .frame(width: 32, height: 32)
                .background(
                    (slot.isConfigured ? Color.statusSuccess : Color.secondary).opacity(0.12),
                    in: RoundedRectangle(cornerRadius: 8)
                )

            VStack(alignment: .leading, spacing: 2) {
                Text(slot.title)
                    .font(.subheadline)
                    .foregroundStyle(.primary)

                Text(slot.isConfigured ? "Configured" : "Not configured")
                    .font(.caption)
                    .foregroundStyle(slot.isConfigured ? .statusSuccess : .secondary)
            }

            Spacer()

            Image(systemName: "chevron.right")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .padding(.horizontal)
        .padding(.vertical, 10)
    }

    // MARK: - Setup Detail Panes

    @ViewBuilder
    private func setupDetailPane(for key: String) -> some View {
        switch key {
        case "pipeline_settings":
            PipelineSettingsPane(viewModel: viewModel)
        case "broker_settings":
            BrokerSettingsPane(viewModel: viewModel)
        case "signal_filters":
            SignalFiltersPane(viewModel: viewModel)
        case "notification_settings":
            NotificationSettingsPane(viewModel: viewModel)
        case "approval_settings":
            ApprovalSettingsPane(viewModel: viewModel)
        default:
            EmptyView()
        }
    }

    // MARK: - Estimated Cost Row

    private var estimatedCostRow: some View {
        HStack {
            Label("Estimated Cost", systemImage: "dollarsign.circle")
                .font(.subheadline)
                .foregroundStyle(.secondary)

            Spacer()

            Text(viewModel.estimatedCost.costFormatted)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(.statusWarning)

            Text("/ run")
                .font(.caption)
                .foregroundStyle(.tertiary)
        }
    }

    // MARK: - Action Buttons

    private var actionButtons: some View {
        VStack(spacing: 12) {
            Button {
                Task {
                    if let _ = await viewModel.savePipeline() {
                        showSaveSuccess = true
                    }
                }
            } label: {
                Label("Save Pipeline", systemImage: "square.and.arrow.down")
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
            .disabled(!viewModel.isReady || viewModel.isSaving)

            Button {
                Task {
                    if let executionId = await viewModel.saveAndExecute() {
                        router.navigateToExecution(id: executionId)
                    }
                }
            } label: {
                Label("Save & Execute", systemImage: "play.fill")
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.bordered)
            .controlSize(.large)
            .disabled(!viewModel.isReady || viewModel.isSaving)
        }
    }

    // MARK: - Helpers

    private func setupItemIcon(_ item: PipelineBuilderViewModel.SetupItem) -> String {
        switch item {
        case .pipelineSettings: return "gearshape"
        case .brokerSettings: return "building.columns"
        case .signalFilters: return "antenna.radiowaves.left.and.right"
        case .notificationSettings: return "bell"
        case .approvalSettings: return "checkmark.shield"
        }
    }

    private func setupItemTitle(_ item: PipelineBuilderViewModel.SetupItem) -> String {
        switch item {
        case .pipelineSettings: return "Pipeline Settings"
        case .brokerSettings: return "Broker"
        case .signalFilters: return "Signal Filters"
        case .notificationSettings: return "Notifications"
        case .approvalSettings: return "Trade Approval"
        }
    }
}

#Preview {
    NavigationStack {
        PipelineBuilderView(pipelineId: nil)
    }
    .environment(NavigationRouter.shared)
    .preferredColorScheme(.dark)
}
