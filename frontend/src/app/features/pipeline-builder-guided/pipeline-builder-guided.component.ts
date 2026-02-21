/**
 * Guided Pipeline Builder Component
 *
 * A simpler, more reliable builder with a fixed agent chain and a details pane
 * for configuring instructions + tools per agent.
 */
import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';

import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatCardModule } from '@angular/material/card';
import { MatDividerModule } from '@angular/material/divider';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatChipsModule } from '@angular/material/chips';
import { MatAutocompleteModule } from '@angular/material/autocomplete';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { FormControl, ReactiveFormsModule } from '@angular/forms';
import { Observable } from 'rxjs';
import { map, startWith } from 'rxjs/operators';

import { NavbarComponent } from '../../core/components/navbar/navbar.component';
import { AgentService } from '../../core/services/agent.service';
import { PipelineService } from '../../core/services/pipeline.service';
import { ExecutionService } from '../../core/services/execution.service';
import { Agent, Pipeline, PipelineConfig, PipelineNode, TriggerMode } from '../../core/models/pipeline.model';
import { ToolMetadata, ToolService } from '../../core/services/tool.service';

import { AgentInstructionsComponent } from '../../shared/agent-instructions/agent-instructions.component';
import { ToolSelectorComponent, ToolInstance } from '../../shared/tool-selector/tool-selector.component';
import { JsonSchemaFormComponent } from '../../shared/json-schema-form/json-schema-form.component';
import { ScannerService } from '../../core/services/scanner.service';
import { Scanner, SignalType } from '../../core/models/scanner.model';

type ExecutionMode = 'paper' | 'live' | 'simulation' | 'validation';

interface GuidedAgentSlot {
  agent_type: string;
  title: string;
  subtitle: string;
  icon: string;
}

@Component({
  selector: 'app-pipeline-builder-guided',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    ReactiveFormsModule,
    MatButtonModule,
    MatIconModule,
    MatCardModule,
    MatDividerModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatSnackBarModule,
    MatChipsModule,
    MatAutocompleteModule,
    MatCheckboxModule,
    MatSlideToggleModule,
    NavbarComponent,
    AgentInstructionsComponent,
    ToolSelectorComponent,
    JsonSchemaFormComponent
  ],
  templateUrl: './pipeline-builder-guided.component.html',
  styleUrls: ['./pipeline-builder-guided.component.scss']
})
export class PipelineBuilderGuidedComponent implements OnInit {
  loading = false;
  saving = false;
  executing = false;

  currentPipelineId: string | null = null;
  currentPipeline: Pipeline | null = null;

  TriggerMode = TriggerMode;

  pipelineName = 'Untitled Pipeline';
  pipelineDescription = '';
  executionMode: ExecutionMode = 'paper';
  
  // Notification settings
  notificationEnabled = false;
  notificationEvents: string[] = [];
  availableNotificationEvents = [
    { value: 'trade_executed', label: 'Trade Executed', icon: 'check_circle' },
    { value: 'position_closed', label: 'Position Closed', icon: 'close' },
    { value: 'pipeline_failed', label: 'Pipeline Failed', icon: 'error' },
    { value: 'risk_rejected', label: 'Risk Rejected', icon: 'block' }
  ];

  // Trade approval settings
  requireApproval = false;
  approvalModes: string[] = ['live'];
  approvalTimeoutMinutes = 15;
  approvalChannels: string[] = ['web'];
  approvalPhone = '';

  triggerMode: TriggerMode = TriggerMode.PERIODIC;
  scannerId: string | null = null;
  signalSubscriptions: any[] | null = null; // backend shape: {signal_type,timeframe?,min_confidence?}[] | null

  agents: Agent[] = [];
  selectedItemKey: string = 'agent:market_data_agent';

  // Cache agent metadata-derived values to avoid expensive re-renders / schema identity churn
  private agentMetaByType = new Map<string, any>();
  private agentAdditionalSchemaByType = new Map<string, any | null>();
  private agentSupportedToolsByType = new Map<string, string[]>();

  // Pipeline-level broker configuration (injected into Risk/Trade managers)
  pipelineBrokerTool: ToolInstance | null = null;
  brokerToolType: string | null = null;
  brokerToolConfig: any = {};
  private brokerToolMetaByType = new Map<string, ToolMetadata>();
  brokerTools: ToolMetadata[] = [];
  brokerSetupRebuildKey = 0;

  private readonly BROKER_TOOL_TYPES = ['alpaca_broker', 'oanda_broker', 'tradier_broker'];

  // Pipeline setup data
  scanners: Scanner[] = [];
  signalTypes: SignalType[] = [];
  setupLoading = false;

  estimatedPipelineCost = 0; // $/run estimate (tools + llm detection)

  // Signal filter catalog
  readonly SIGNAL_TIMEFRAMES: Array<{ value: string; label: string }> = [
    { value: '1', label: '1m' },
    { value: '5', label: '5m' },
    { value: '15', label: '15m' },
    { value: '60', label: '1h' },
    { value: '240', label: '4h' },
    { value: 'D', label: '1D' }
  ];
  readonly DEFAULT_MIN_CONFIDENCE = 80;
  bulkSelectedMinConfidenceCtrl = new FormControl<number>(this.DEFAULT_MIN_CONFIDENCE, { nonNullable: true });

  signalSearchCtrl = new FormControl<string>('');
  filteredSignalCatalog$!: Observable<SignalType[]>;

  // We keep configs per agent_type
  agentNodes: Record<string, PipelineNode> = {};
  editingConfig: Record<string, any> = {};

  readonly slots: GuidedAgentSlot[] = [
    {
      agent_type: 'market_data_agent',
      title: 'Market Data Agent',
      subtitle: 'Fetch candles for required timeframes',
      icon: 'insights'
    },
    {
      agent_type: 'bias_agent',
      title: 'Bias Agent',
      subtitle: 'HTF bias using indicators + context',
      icon: 'explore'
    },
    {
      agent_type: 'strategy_agent',
      title: 'Strategy Agent',
      subtitle: 'Generate actionable trade plan',
      icon: 'psychology'
    },
    {
      agent_type: 'risk_manager_agent',
      title: 'Risk Manager',
      subtitle: 'Position size + constraints',
      icon: 'shield'
    },
    {
      agent_type: 'trade_manager_agent',
      title: 'Trade Manager',
      subtitle: 'Execute + monitor (limit/bracket)',
      icon: 'currency_exchange'
    }
  ];

  readonly setupItems: Array<{ key: 'pipeline_settings' | 'signal_filters' | 'broker_settings' | 'notification_settings' | 'approval_settings'; title: string; subtitle: string; icon: string }> = [
    {
      key: 'pipeline_settings',
      title: 'Pipeline settings',
      subtitle: 'Trigger mode + scanner selection',
      icon: 'settings'
    },
    {
      key: 'broker_settings',
      title: 'Broker',
      subtitle: 'Configure broker once (used by Risk + Trade)',
      icon: 'account_balance'
    },
    {
      key: 'signal_filters',
      title: 'Signal filters',
      subtitle: 'Choose which signal types to accept',
      icon: 'tune'
    },
    {
      key: 'notification_settings',
      title: 'Notifications',
      subtitle: 'Telegram alerts for trades + events',
      icon: 'notifications'
    },
    {
      key: 'approval_settings',
      title: 'Trade Approval',
      subtitle: 'Require manual approval before trades',
      icon: 'verified_user'
    }
  ];

  constructor(
    private route: ActivatedRoute,
    private router: Router,
    private snackBar: MatSnackBar,
    private agentService: AgentService,
    private pipelineService: PipelineService,
    private executionService: ExecutionService,
    private scannerService: ScannerService,
    private toolService: ToolService
  ) {}

  ngOnInit(): void {
    this.loading = true;

    this.agentService.loadAgents().subscribe({
      next: (agents) => {
        this.agents = agents;
        this.buildAgentCaches();
        this.initEmptyNodes();
        this.recomputeEstimatedPipelineCost();
        this.loadBrokerTools();
        this.loadPipelineSetupData();
        this.loadPipelineIfNeeded();
      },
      error: (err) => {
        console.error('Failed to load agents', err);
        this.loading = false;
        this.showNotification('Failed to load agents', 'error');
      }
    });
  }

  private initEmptyNodes(): void {
    const defaults: Record<string, any> = {
      market_data_agent: {},
      bias_agent: { instructions: '' },
      strategy_agent: { instructions: '' },
      risk_manager_agent: { instructions: '' },
      trade_manager_agent: {}
    };

    for (const slot of this.slots) {
      const nodeId = `node-${slot.agent_type}`;
      this.agentNodes[slot.agent_type] = {
        id: nodeId,
        agent_type: slot.agent_type,
        config: defaults[slot.agent_type] || {}
      };
    }

    this.selectItem(this.selectedItemKey);
  }

  private loadPipelineSetupData(): void {
    this.setupLoading = true;
    this.scannerService.getScanners(true).subscribe({
      next: (scanners) => {
        this.scanners = scanners;
        this.setupLoading = false;
      },
      error: (err) => {
        console.error('Failed to load scanners', err);
        this.setupLoading = false;
      }
    });

    this.scannerService.getSignalTypes().subscribe({
      next: (types) => {
        this.signalTypes = types;
        this.filteredSignalCatalog$ = this.signalSearchCtrl.valueChanges.pipe(
          startWith(''),
          map(value => (value || '').toLowerCase().trim()),
          map(query => {
            if (!query) return this.signalTypes;
            return this.signalTypes.filter(st => {
              const hay = `${st.name} ${st.signal_type} ${st.description || ''}`.toLowerCase();
              return hay.includes(query);
            });
          })
        );
      },
      error: (err) => {
        console.error('Failed to load signal types', err);
      }
    });
  }

  private loadPipelineIfNeeded(): void {
    const id = this.route.snapshot.paramMap.get('id');
    if (!id) {
      this.loading = false;
      return;
    }

    this.currentPipelineId = id;
    this.pipelineService.getPipeline(id).subscribe({
      next: (pipeline) => {
        this.currentPipeline = pipeline;
        this.pipelineName = pipeline.name || this.pipelineName;
        this.pipelineDescription = pipeline.description || '';
        this.executionMode = (pipeline.config?.mode as ExecutionMode) || this.executionMode;
        
        // Load notification settings
        this.notificationEnabled = pipeline.notification_enabled || false;
        this.notificationEvents = pipeline.notification_events || [];

        // Load approval settings
        this.requireApproval = pipeline.require_approval || false;
        this.approvalModes = pipeline.approval_modes || ['live'];
        this.approvalTimeoutMinutes = pipeline.approval_timeout_minutes || 15;
        this.approvalChannels = pipeline.approval_channels || ['web'];
        this.approvalPhone = pipeline.approval_phone || '';

        this.triggerMode = pipeline.trigger_mode || TriggerMode.PERIODIC;
        this.scannerId = pipeline.scanner_id || null;
        this.signalSubscriptions = pipeline.signal_subscriptions || null;

        // Load pipeline-level broker tool if present (guided builder source-of-truth)
        const cfgAny: any = pipeline.config || {};
        const brokerToolFromConfig = cfgAny?.broker_tool || null;

        // Map existing nodes by agent_type into fixed slots; preserve IDs.
        const nodesByType = new Map<string, PipelineNode>();
        for (const n of pipeline.config?.nodes || []) {
          nodesByType.set(n.agent_type, n);
        }
        for (const slot of this.slots) {
          const existing = nodesByType.get(slot.agent_type);
          if (existing) {
            this.agentNodes[slot.agent_type] = {
              id: existing.id,
              agent_type: existing.agent_type,
              config: existing.config || {}
            };
          }
        }

        // Back-compat inference: if broker_tool is missing, infer from Trade Manager tools (if present)
        const inferredBrokerTool =
          brokerToolFromConfig ||
          this.extractBrokerToolFromAgentConfig(this.agentNodes['trade_manager_agent']?.config) ||
          this.extractBrokerToolFromAgentConfig(this.agentNodes['risk_manager_agent']?.config) ||
          null;

        if (inferredBrokerTool) {
          this.setPipelineBrokerTool(inferredBrokerTool);
        }

        // Enforce: pipeline broker is the only broker used by Risk + Trade managers
        this.enforceBrokerOnAgents();

        this.selectItem(this.selectedItemKey);
        this.recomputeEstimatedPipelineCost();
        this.loading = false;
      },
      error: (err) => {
        console.error('Failed to load pipeline', err);
        this.loading = false;
        this.showNotification('Failed to load pipeline', 'error');
      }
    });
  }

  selectItem(itemKey: string): void {
    this.selectedItemKey = itemKey;
    if (itemKey.startsWith('agent:')) {
      const agentType = itemKey.replace('agent:', '');
      const node = this.agentNodes[agentType];
      this.editingConfig = { ...(node?.config || {}) };
    } else {
      // Non-agent items use direct bindings (trigger/scanner/subscriptions), so clear editing config.
      this.editingConfig = {};
    }
  }

  isAgentSelected(): boolean {
    return this.selectedItemKey.startsWith('agent:');
  }

  getSelectedAgentType(): string | null {
    return this.isAgentSelected() ? this.selectedItemKey.replace('agent:', '') : null;
  }

  getAgentMetadata(agentType: string): any | undefined {
    return this.agentMetaByType.get(agentType);
  }

  getAgentAdditionalSchema(agentType: string): any | null {
    return this.agentAdditionalSchemaByType.get(agentType) ?? null;
  }

  getSelectedScanner(): Scanner | undefined {
    return this.scanners.find(s => s.id === this.scannerId);
  }

  getSignalTypeMeta(signalType: string): SignalType | undefined {
    return this.signalTypes.find(st => st.signal_type === signalType);
  }

  private findSubscriptionIndex(signalType: string, timeframe: string): number {
    const current = Array.isArray(this.signalSubscriptions) ? this.signalSubscriptions : [];
    return current.findIndex((s: any) => s.signal_type === signalType && (s.timeframe || null) === timeframe);
  }

  isSignalSubscribed(signalType: string, timeframe: string): boolean {
    return this.findSubscriptionIndex(signalType, timeframe) !== -1;
  }

  toggleSignalSubscription(signalType: string, timeframe: string): void {
    const current = Array.isArray(this.signalSubscriptions) ? [...this.signalSubscriptions] : [];
    const idx = current.findIndex((s: any) => s.signal_type === signalType && (s.timeframe || null) === timeframe);
    if (idx !== -1) {
      current.splice(idx, 1);
      this.signalSubscriptions = current.length ? current : null;
      return;
    }

    current.push({
      signal_type: signalType,
      timeframe,
      min_confidence: this.DEFAULT_MIN_CONFIDENCE
    });
    this.signalSubscriptions = current;
  }

  updateSubscriptionConfidence(index: number, value: number | null): void {
    const current = Array.isArray(this.signalSubscriptions) ? [...this.signalSubscriptions] : [];
    if (!current[index]) return;
    const v = value == null ? null : Math.max(0, Math.min(100, value));
    if (v == null) {
      delete current[index].min_confidence;
    } else {
      current[index].min_confidence = v;
    }
    this.signalSubscriptions = current.length ? current : null;
  }

  applyBulkSelectedMinConfidence(): void {
    const current = Array.isArray(this.signalSubscriptions) ? [...this.signalSubscriptions] : [];
    if (current.length === 0) return;
    const v = Math.max(0, Math.min(100, Number(this.bulkSelectedMinConfidenceCtrl.value)));
    for (const sub of current) {
      sub.min_confidence = v;
    }
    this.signalSubscriptions = current;
  }

  clearAllSignalSubscriptions(): void {
    this.signalSubscriptions = null;
  }

  formatTimeframe(tf: string): string {
    const found = this.SIGNAL_TIMEFRAMES.find(t => t.value === tf);
    return found ? found.label : tf;
  }

  removeSignalSubscriptionAt(index: number): void {
    const current = Array.isArray(this.signalSubscriptions) ? [...this.signalSubscriptions] : [];
    current.splice(index, 1);
    this.signalSubscriptions = current.length ? current : null;
  }
  
  toggleNotificationEvent(eventValue: string): void {
    const index = this.notificationEvents.indexOf(eventValue);
    if (index >= 0) {
      // Remove
      this.notificationEvents = this.notificationEvents.filter(e => e !== eventValue);
    } else {
      // Add
      this.notificationEvents = [...this.notificationEvents, eventValue];
    }
  }

  getSupportedTools(agentType: string): string[] {
    const raw = this.agentSupportedToolsByType.get(agentType) || [];
    // Enforce: broker tools must be configured via pipeline Broker step, not per-agent attachment
    if (agentType === 'risk_manager_agent' || agentType === 'trade_manager_agent') {
      return raw.filter(t => !this.BROKER_TOOL_TYPES.includes(t));
    }
    return raw;
  }

  private buildAgentCaches(): void {
    this.agentMetaByType.clear();
    this.agentAdditionalSchemaByType.clear();
    this.agentSupportedToolsByType.clear();

    for (const a of this.agents) {
      this.agentMetaByType.set(a.agent_type, a);
      const meta: any = a as any;
      this.agentSupportedToolsByType.set(a.agent_type, meta?.supported_tools || []);
      this.agentAdditionalSchemaByType.set(a.agent_type, this.computeAdditionalSchema(meta));
    }
  }

  private computeAdditionalSchema(meta: any): any | null {
    const schema = meta?.config_schema;
    if (!schema || !schema.properties) return null;

    // Avoid duplicate "instructions" UI: instructions + document URL are handled by AgentInstructionsComponent
    const hiddenKeys = new Set([
      'instructions',
      'strategy_document_url',
      'auto_detected_tools',
      'estimated_tool_cost',
      'tools'
    ]);

    const properties: Record<string, any> = {};
    for (const [k, v] of Object.entries(schema.properties || {})) {
      if (hiddenKeys.has(k)) continue;
      properties[k] = v;
    }

    const required = Array.isArray(schema.required)
      ? schema.required.filter((k: string) => !hiddenKeys.has(k))
      : [];

    if (Object.keys(properties).length === 0) return null;

    // Important: return a stable object reference per agent_type (cached above),
    // otherwise JsonSchemaForm will treat schema as "changed" every CD and rebuild repeatedly.
    return {
      ...schema,
      properties,
      required
    };
  }

  onInstructionsChange(evt: any): void {
    // Keep current editing config in sync; saving happens via explicit Save.
    this.editingConfig['instructions'] = evt?.instructions ?? this.editingConfig['instructions'];
    if (evt?.documentUrl !== undefined) {
      this.editingConfig['strategy_document_url'] = evt.documentUrl;
    }

    // Wire tool detection results into config so they can be saved & shown in ToolSelector
    if (Array.isArray(evt?.detectedTools)) {
      this.editingConfig['auto_detected_tools'] = evt.detectedTools;
      this.editingConfig['estimated_tool_cost'] = evt.totalCost ?? this.editingConfig['estimated_tool_cost'];
      this.editingConfig['estimated_llm_cost'] = evt.llmCost ?? this.editingConfig['estimated_llm_cost'];

      const autoTools: ToolInstance[] = evt.detectedTools.map((t: any) => ({
        tool_type: t.tool,
        enabled: true,
        config: t.params || {}
      }));

      const existing: ToolInstance[] = Array.isArray(this.editingConfig['tools']) ? this.editingConfig['tools'] : [];
      const existingByType = new Map(existing.map(t => [t.tool_type, t]));
      for (const t of autoTools) {
        if (!existingByType.has(t.tool_type)) {
          existingByType.set(t.tool_type, t);
        }
      }
      this.editingConfig['tools'] = Array.from(existingByType.values());
    }

    this.recomputeEstimatedPipelineCost();
  }

  onConfigChange(data: any): void {
    // Merge additional-schema fields into existing config so that fields managed by
    // other sub-components (instructions, tools, strategy_document_url, etc.) are preserved.
    this.editingConfig = { ...this.editingConfig, ...(data || {}) };
    this.recomputeEstimatedPipelineCost();
  }

  onToolsChange(tools: ToolInstance[]): void {
    this.editingConfig['tools'] = tools || [];
    this.recomputeEstimatedPipelineCost();
  }

  /**
   * The right pane edits are staged in `editingConfig` until Apply is clicked.
   * Users often hit Save directly; in that case we must flush the staged edits into `agentNodes`
   * so the payload reflects the current UI.
   */
  private flushRightPaneEditsToSelectedNode(): void {
    if (!this.isAgentSelected()) return;
    const agentType = this.getSelectedAgentType();
    if (!agentType) return;
    const node = this.agentNodes[agentType];
    if (!node) return;
    node.config = { ...(this.editingConfig || {}) };
  }

  agentNeedsInstructions(agentType: string): boolean {
    return agentType === 'bias_agent' || agentType === 'strategy_agent' || agentType === 'risk_manager_agent';
  }

  applyRightPaneChanges(): void {
    if (this.isAgentSelected()) {
      const agentType = this.getSelectedAgentType()!;
      const node = this.agentNodes[agentType];
      if (!node) return;
      node.config = { ...(this.editingConfig || {}) };
      // Always enforce pipeline broker after agent edits (prevents accidental broker attachment)
      this.enforceBrokerOnAgents();
      this.showNotification('Agent settings applied', 'success');
      this.recomputeEstimatedPipelineCost();
      // Persist to backend (common expectation: Apply shouldn't be lost)
      if (this.currentPipelineId) this.savePipeline(false);
      return;
    }
    if (this.selectedItemKey === 'pipeline_settings') {
      this.showNotification('Pipeline settings applied', 'success');
      if (this.currentPipelineId) this.savePipeline(false);
      return;
    }
    if (this.selectedItemKey === 'broker_settings') {
      // Normalize + enforce broker on agent configs
      this.pipelineBrokerTool = this.buildPipelineBrokerTool();
      this.enforceBrokerOnAgents();
      this.showNotification('Broker settings applied', 'success');
      if (this.currentPipelineId) this.savePipeline(false);
      return;
    }
    if (this.selectedItemKey === 'signal_filters') {
      this.showNotification('Signal filters applied', 'success');
      if (this.currentPipelineId) this.savePipeline(false);
      return;
    }
    if (this.selectedItemKey === 'approval_settings') {
      this.showNotification('Approval settings applied', 'success');
      if (this.currentPipelineId) this.savePipeline(false);
      return;
    }
  }

  private recomputeEstimatedPipelineCost(): void {
    let total = 0;
    for (const slot of this.slots) {
      const cfg: any = this.agentNodes[slot.agent_type]?.config || {};
      const toolCost = typeof cfg.estimated_tool_cost === 'number' ? cfg.estimated_tool_cost : 0;
      const llmCost = typeof cfg.estimated_llm_cost === 'number' ? cfg.estimated_llm_cost : 0;
      total += toolCost + llmCost;
    }
    this.estimatedPipelineCost = total;
  }

  // Pipeline settings are now inline in the Setup pane

  private buildConfigForSave(): PipelineConfig {
    // Ensure broker enforcement before snapshotting config
    this.pipelineBrokerTool = this.buildPipelineBrokerTool();
    this.enforceBrokerOnAgents();

    const nodes: PipelineNode[] = this.slots.map(slot => ({
      id: this.agentNodes[slot.agent_type].id,
      agent_type: slot.agent_type,
      config: this.agentNodes[slot.agent_type].config || {}
    }));

    const edges = [];
    for (let i = 0; i < this.slots.length - 1; i++) {
      edges.push({ from: this.agentNodes[this.slots[i].agent_type].id, to: this.agentNodes[this.slots[i + 1].agent_type].id });
    }

    return {
      broker_tool: this.pipelineBrokerTool ? this.stripToolInstanceMetadata(this.pipelineBrokerTool) : null,
      nodes,
      edges,
      mode: this.executionMode
    };
  }

  savePipeline(showNotification: boolean = true): void {
    const token = localStorage.getItem('auth_token');
    if (!token) {
      this.showNotification('Please login to save pipelines', 'warning');
      this.router.navigate(['/login']);
      return;
    }

    // Ensure staged right-pane edits are included in payload even if user didn't click "Apply"
    this.flushRightPaneEditsToSelectedNode();

    // Enforce broker consistency on every save
    this.pipelineBrokerTool = this.buildPipelineBrokerTool();
    this.enforceBrokerOnAgents();

    this.saving = true;
    const pipelineData: any = {
      name: this.pipelineName,
      description: this.pipelineDescription,
      config: this.buildConfigForSave(),
      trigger_mode: this.triggerMode,
      notification_enabled: this.notificationEnabled,
      notification_events: this.notificationEvents,
      // Scanner can be used for both periodic and signal pipelines; for SIGNAL it is required.
      scanner_id: this.scannerId,
      // Approval settings
      require_approval: this.requireApproval,
      approval_modes: this.approvalModes,
      approval_timeout_minutes: this.approvalTimeoutMinutes,
      approval_channels: this.approvalChannels,
      approval_phone: this.approvalPhone || null,
    };
    // Only set is_active when creating a new pipeline; don't accidentally deactivate existing pipelines on every save
    if (!this.currentPipelineId) {
      pipelineData.is_active = false;
    }

    // Important: don't clear existing signal subscriptions when trigger mode isn't SIGNAL.
    // If the user switches to PERIODIC temporarily, we keep filters in DB unless explicitly cleared.
    if (this.triggerMode === TriggerMode.SIGNAL) {
      pipelineData.signal_subscriptions = this.signalSubscriptions;
    } else if (!this.currentPipelineId) {
      // For new pipelines, keep it null unless SIGNAL
      pipelineData.signal_subscriptions = null;
    }

    const op = this.currentPipelineId
      ? this.pipelineService.updatePipeline(this.currentPipelineId, pipelineData)
      : this.pipelineService.createPipeline(pipelineData);

    op.subscribe({
      next: (pipeline: any) => {
        this.saving = false;
        this.currentPipeline = pipeline;
        if (!this.currentPipelineId && pipeline?.id) {
          this.currentPipelineId = pipeline.id;
          this.router.navigate(['/pipeline-builder', pipeline.id], { replaceUrl: true });
        }
        if (showNotification) this.showNotification('Pipeline saved', 'success');
      },
      error: (err) => {
        console.error('Save failed', err);
        this.saving = false;
        this.showNotification('Failed to save pipeline', 'error');
      }
    });
  }

  executePipeline(): void {
    if (!this.currentPipelineId) {
      // Save first then execute
      this.savePipeline();
      // caller can hit Run again; keep flow simple for MVP
      this.showNotification('Saved. Click Run again to execute.', 'info');
      return;
    }

    // Ensure staged right-pane edits are included even if user didn't click "Apply"
    this.flushRightPaneEditsToSelectedNode();

    // Enforce broker consistency on every run
    this.pipelineBrokerTool = this.buildPipelineBrokerTool();
    this.enforceBrokerOnAgents();

    this.executing = true;
    const executionData: any = {
      pipeline_id: this.currentPipelineId,
      mode: this.executionMode
    };

    this.executionService.startExecution(executionData).subscribe({
      next: (execution: any) => {
        this.executing = false;
        this.showNotification('Execution started', 'success');
        setTimeout(() => this.router.navigate(['/monitoring', execution.id]), 800);
      },
      error: (err) => {
        console.error('Execute failed', err);
        this.executing = false;
        this.showNotification('Failed to start execution', 'error');
      }
    });
  }

  getReadiness(): { ready: boolean; missing: string[] } {
    const missing: string[] = [];

    if (!this.pipelineName || !this.pipelineName.trim()) missing.push('Pipeline name');

    if (this.triggerMode === TriggerMode.SIGNAL) {
      if (!this.scannerId) missing.push('Scanner (required for Signal mode)');
    }

    const needsInstructions = ['bias_agent', 'strategy_agent', 'risk_manager_agent'];
    for (const at of needsInstructions) {
      const instr = (this.agentNodes[at]?.config as any)?.['instructions'];
      if (!instr || !String(instr).trim()) missing.push(`${at.replace('_agent', '').replace('_', ' ')} instructions`);
    }

    if (!this.isPipelineBrokerConfigured()) missing.push('Broker (required)');

    return { ready: missing.length === 0, missing };
  }

  toggleApprovalMode(mode: string): void {
    const index = this.approvalModes.indexOf(mode);
    if (index >= 0) {
      this.approvalModes = this.approvalModes.filter(m => m !== mode);
    } else {
      this.approvalModes = [...this.approvalModes, mode];
    }
  }

  toggleApprovalChannel(channel: string): void {
    const index = this.approvalChannels.indexOf(channel);
    if (index >= 0) {
      this.approvalChannels = this.approvalChannels.filter(c => c !== channel);
    } else {
      this.approvalChannels = [...this.approvalChannels, channel];
    }
  }

  getSetupItemStatus(key: 'pipeline_settings' | 'signal_filters' | 'broker_settings' | 'notification_settings' | 'approval_settings'): 'READY' | 'SETUP' | 'TODO' {
    if (key === 'pipeline_settings') {
      if (this.triggerMode === TriggerMode.SIGNAL && !this.scannerId) return 'SETUP';
      return 'READY';
    }
    if (key === 'broker_settings') {
      return this.isPipelineBrokerConfigured() ? 'READY' : 'SETUP';
    }
    if (key === 'signal_filters') {
      if (this.triggerMode !== TriggerMode.SIGNAL) return 'TODO';
      return (this.signalSubscriptions && this.signalSubscriptions.length > 0) ? 'READY' : 'SETUP';
    }
    if (key === 'notification_settings') {
      // Notification settings are optional, so always return READY if enabled or SETUP if disabled
      return this.notificationEnabled ? 'READY' : 'SETUP';
    }
    if (key === 'approval_settings') {
      return this.requireApproval ? 'READY' : 'SETUP';
    }
    return 'TODO';
  }

  getSlotStatus(agentType: string): 'READY' | 'SETUP' | 'TODO' {
    const cfg = this.agentNodes[agentType]?.config || {};
    if (agentType === 'market_data_agent') return 'READY';
    if (agentType === 'trade_manager_agent') return (this.isPipelineBrokerConfigured() ? 'READY' : 'TODO');
    if (agentType === 'bias_agent' || agentType === 'strategy_agent' || agentType === 'risk_manager_agent') {
      const hasInstr = !!((cfg as any)?.['instructions'] && String((cfg as any)?.['instructions']).trim().length > 0);
      return hasInstr ? 'READY' : 'SETUP';
    }
    return 'TODO';
  }

  private loadBrokerTools(): void {
    this.toolService.getToolsByCategory('broker').subscribe({
      next: (tools) => {
        this.brokerTools = Array.isArray(tools) ? tools : [];
        this.brokerToolMetaByType.clear();
        for (const t of this.brokerTools) {
          this.brokerToolMetaByType.set(t.tool_type, t);
        }
      },
      error: (err) => {
        console.error('Failed to load broker tools', err);
      }
    });
  }

  onBrokerToolTypeChange(toolType: string | null): void {
    this.brokerToolType = toolType;
    this.brokerToolConfig = {};
    this.pipelineBrokerTool = this.buildPipelineBrokerTool();
    this.enforceBrokerOnAgents();
    this.brokerSetupRebuildKey++;
  }

  onBrokerConfigChange(cfg: any): void {
    this.brokerToolConfig = { ...(cfg || {}) };
    this.pipelineBrokerTool = this.buildPipelineBrokerTool();
    this.enforceBrokerOnAgents();
  }

  getSelectedBrokerMeta(): ToolMetadata | null {
    if (!this.brokerToolType) return null;
    return this.brokerToolMetaByType.get(this.brokerToolType) || null;
  }

  private buildPipelineBrokerTool(): ToolInstance | null {
    if (!this.brokerToolType) return null;
    const meta = this.brokerToolMetaByType.get(this.brokerToolType);
    if (!meta) return null;
    return {
      tool_type: this.brokerToolType,
      enabled: true,
      config: { ...(this.brokerToolConfig || {}) }
    };
  }

  private isPipelineBrokerConfigured(): boolean {
    const tool = this.buildPipelineBrokerTool() || this.pipelineBrokerTool;
    if (!tool || !tool.tool_type) return false;
    const meta = this.brokerToolMetaByType.get(tool.tool_type);
    const required: string[] = (meta as any)?.config_schema?.required || [];
    if (!required.length) {
      // If schema doesn't specify required, accept presence of any config (or none)
      return true;
    }
    const cfg = tool.config || {};
    return required.every(k => cfg[k] !== undefined && cfg[k] !== null && String(cfg[k]).trim() !== '');
  }

  private extractBrokerToolFromAgentConfig(agentConfig: any): ToolInstance | null {
    const tools: ToolInstance[] = Array.isArray(agentConfig?.tools) ? agentConfig.tools : [];
    const broker = tools.find(t => this.BROKER_TOOL_TYPES.includes(t.tool_type));
    return broker ? { tool_type: broker.tool_type, enabled: true, config: { ...(broker.config || {}) } } : null;
  }

  private setPipelineBrokerTool(tool: ToolInstance): void {
    this.brokerToolType = tool.tool_type;
    this.brokerToolConfig = { ...(tool.config || {}) };
    this.pipelineBrokerTool = { tool_type: tool.tool_type, enabled: true, config: { ...(tool.config || {}) } };
    this.brokerSetupRebuildKey++;
  }

  private enforceBrokerOnAgents(): void {
    const broker = this.buildPipelineBrokerTool() || this.pipelineBrokerTool;
    for (const agentType of ['risk_manager_agent', 'trade_manager_agent']) {
      const node = this.agentNodes[agentType];
      if (!node) continue;
      const cfg: any = node.config || {};
      const tools: ToolInstance[] = Array.isArray(cfg.tools) ? cfg.tools : [];
      const nonBroker = tools.filter(t => !this.BROKER_TOOL_TYPES.includes(t.tool_type));
      const newTools = broker ? [this.stripToolInstanceMetadata(broker), ...nonBroker] : nonBroker;
      node.config = {
        ...cfg,
        tools: newTools
      };
      // If the currently edited agent is one of these, keep pane in sync
      if (this.getSelectedAgentType() === agentType) {
        this.editingConfig = { ...(node.config || {}) };
      }
    }
  }

  private stripToolInstanceMetadata(tool: ToolInstance): ToolInstance {
    return {
      tool_type: tool.tool_type,
      enabled: tool.enabled,
      config: tool.config || {}
    };
  }

  private showNotification(message: string, type: 'success' | 'error' | 'info' | 'warning'): void {
    this.snackBar.open(message, 'Close', {
      duration: 2500,
      horizontalPosition: 'right',
      verticalPosition: 'top',
      panelClass: [`snackbar-${type}`]
    });
  }
}

