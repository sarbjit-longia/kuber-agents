import SwiftUI

struct PipelineListView: View {
    @State private var viewModel = PipelineListViewModel()
    @Environment(NavigationRouter.self) private var router
    @State private var showDeleteConfirm = false
    @State private var pipelineToDelete: Pipeline?
    @State private var showExecuteSheet = false
    @State private var pipelineToExecute: Pipeline?
    @State private var selectedExecutionMode = "paper"

    private let executionModes = ["paper", "live", "simulation", "validation"]

    var body: some View {
        Group {
            if viewModel.isLoading && viewModel.pipelines.isEmpty {
                LoadingView(message: "Loading pipelines...")
            } else if let error = viewModel.errorMessage, viewModel.pipelines.isEmpty {
                EmptyStateView(
                    icon: "exclamationmark.triangle",
                    title: "Failed to Load",
                    message: error,
                    actionTitle: "Retry"
                ) {
                    Task { await viewModel.loadPipelines() }
                }
            } else if viewModel.pipelines.isEmpty {
                EmptyStateView(
                    icon: "arrow.triangle.branch",
                    title: "No Pipelines",
                    message: "Create your first trading pipeline to get started.",
                    actionTitle: "Create Pipeline"
                ) {
                    router.pipelinesPath.append(PipelineDestination.builder(id: nil))
                }
            } else {
                pipelineList
            }
        }
        .navigationTitle("Pipelines")
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button {
                    router.pipelinesPath.append(PipelineDestination.builder(id: nil))
                } label: {
                    Image(systemName: "plus")
                }
            }
        }
        .refreshable {
            await viewModel.loadPipelines()
        }
        .task {
            await viewModel.loadPipelines()
        }
        .alert("Delete Pipeline", isPresented: $showDeleteConfirm) {
            Button("Cancel", role: .cancel) {
                pipelineToDelete = nil
            }
            Button("Delete", role: .destructive) {
                if let pipeline = pipelineToDelete {
                    Task { await viewModel.deletePipeline(id: pipeline.id) }
                }
                pipelineToDelete = nil
            }
        } message: {
            if let pipeline = pipelineToDelete {
                Text("Are you sure you want to delete \"\(pipeline.name)\"? This action cannot be undone.")
            }
        }
        .sheet(isPresented: $showExecuteSheet) {
            executeModeSheet
        }
    }

    // MARK: - Pipeline List

    private var pipelineList: some View {
        List {
            if let error = viewModel.errorMessage {
                Section {
                    ErrorBanner(message: error) {
                        viewModel.errorMessage = nil
                    }
                }
                .listRowInsets(EdgeInsets())
                .listRowBackground(Color.clear)
            }

            ForEach(viewModel.pipelines) { pipeline in
                PipelineRowView(
                    pipeline: pipeline,
                    onToggleActive: {
                        Task { await viewModel.toggleActive(pipeline: pipeline) }
                    }
                )
                .contentShape(Rectangle())
                .onTapGesture {
                    router.pipelinesPath.append(PipelineDestination.builder(id: pipeline.id))
                }
                .swipeActions(edge: .trailing, allowsFullSwipe: false) {
                    Button(role: .destructive) {
                        pipelineToDelete = pipeline
                        showDeleteConfirm = true
                    } label: {
                        Label("Delete", systemImage: "trash")
                    }

                    Button {
                        router.pipelinesPath.append(PipelineDestination.builder(id: pipeline.id))
                    } label: {
                        Label("Edit", systemImage: "pencil")
                    }
                    .tint(.brandPrimary)
                }
                .swipeActions(edge: .leading, allowsFullSwipe: true) {
                    Button {
                        pipelineToExecute = pipeline
                        showExecuteSheet = true
                    } label: {
                        Label("Execute", systemImage: "play.fill")
                    }
                    .tint(.statusSuccess)
                }
                .listRowBackground(Color.surfaceCard)
            }
        }
        .listStyle(.insetGrouped)
        .scrollContentBackground(.hidden)
    }

    // MARK: - Execute Mode Sheet

    private var executeModeSheet: some View {
        NavigationStack {
            VStack(spacing: 24) {
                if let pipeline = pipelineToExecute {
                    VStack(spacing: 8) {
                        Image(systemName: "play.circle.fill")
                            .font(.system(size: 48))
                            .foregroundStyle(.brandPrimary)

                        Text("Execute Pipeline")
                            .font(.title3.weight(.semibold))

                        Text(pipeline.name)
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                    }
                    .padding(.top, 24)

                    VStack(alignment: .leading, spacing: 12) {
                        Text("Execution Mode")
                            .font(.headline)

                        Picker("Mode", selection: $selectedExecutionMode) {
                            ForEach(executionModes, id: \.self) { mode in
                                Text(mode.capitalized).tag(mode)
                            }
                        }
                        .pickerStyle(.segmented)

                        Text(executionModeDescription)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    .padding(.horizontal)

                    Spacer()

                    Button {
                        showExecuteSheet = false
                        Task {
                            if let executionId = await viewModel.executePipeline(
                                id: pipeline.id,
                                mode: selectedExecutionMode
                            ) {
                                router.navigateToExecution(id: executionId)
                            }
                        }
                    } label: {
                        Label("Start Execution", systemImage: "play.fill")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.large)
                    .padding(.horizontal)
                    .padding(.bottom)
                }
            }
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") {
                        showExecuteSheet = false
                        pipelineToExecute = nil
                    }
                }
            }
        }
        .presentationDetents([.medium])
        .presentationDragIndicator(.visible)
    }

    private var executionModeDescription: String {
        switch selectedExecutionMode {
        case "paper": return "Simulated trading with no real money. Perfect for testing strategies."
        case "live": return "Real trading with real money. Use with caution."
        case "simulation": return "Full simulation with historical data replay."
        case "validation": return "Validates the pipeline configuration without executing trades."
        default: return ""
        }
    }
}

#Preview {
    NavigationStack {
        PipelineListView()
    }
    .environment(NavigationRouter.shared)
    .preferredColorScheme(.dark)
}
