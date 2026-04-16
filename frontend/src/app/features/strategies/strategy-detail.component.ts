import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatChipsModule } from '@angular/material/chips';

import { NavbarComponent } from '../../core/components/navbar/navbar.component';
import { FooterComponent } from '../../shared/components/footer/footer.component';
import { MarkdownToHtmlPipe } from '../../shared/pipes/markdown-to-html.pipe';
import { StrategyService } from '../../core/services/strategy.service';
import { AuthService } from '../../core/services/auth.service';
import { Strategy } from '../../core/models/strategy.model';
import { ConfirmDialogComponent, ConfirmDialogData } from '../../shared/confirm-dialog/confirm-dialog.component';

@Component({
  selector: 'app-strategy-detail',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    RouterLink,
    MatButtonModule,
    MatCardModule,
    MatDialogModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatProgressSpinnerModule,
    MatSnackBarModule,
    MatChipsModule,
    NavbarComponent,
    FooterComponent,
    MarkdownToHtmlPipe,
  ],
  templateUrl: './strategy-detail.component.html',
  styleUrls: ['./strategy-detail.component.scss'],
})
export class StrategyDetailComponent implements OnInit {
  loading = true;
  savingMetadata = false;
  reviewing = false;
  editingMetadata = false;
  strategy: Strategy | null = null;
  currentUserId: string | null = null;
  currentUserIsAdmin = false;
  editedTitle = '';
  editedSummary = '';
  private readonly hiddenConfigKeys = new Set([
    'instructions',
    'tools',
    'skills',
    'estimated_llm_cost',
    'estimated_tool_cost',
    'auto_detected_tools',
    'strategy_document_url',
  ]);

  constructor(
    private route: ActivatedRoute,
    private router: Router,
    private strategyService: StrategyService,
    private authService: AuthService,
    private dialog: MatDialog,
    private snackBar: MatSnackBar,
  ) {}

  ngOnInit(): void {
    this.currentUserId = this.normalizeId(this.authService.currentUserValue?.id);
    this.currentUserIsAdmin = !!this.authService.currentUserValue?.is_superuser;
    if (!this.currentUserId && this.authService.isAuthenticated()) {
      this.authService.getCurrentUser().subscribe({
        next: (user) => {
          this.currentUserId = this.normalizeId(user.id);
          this.currentUserIsAdmin = !!user.is_superuser;
        }
      });
    }

    const strategyId = this.route.snapshot.paramMap.get('id');
    if (!strategyId) {
      this.router.navigate(['/marketplace']);
      return;
    }
    this.strategyService.getStrategy(strategyId).subscribe({
      next: (strategy) => {
        this.strategy = strategy;
        this.resetMetadataDrafts();
        this.loading = false;
      },
      error: () => {
        this.loading = false;
        this.router.navigate(['/marketplace']);
      }
    });
  }

  get isOwner(): boolean {
    return !!this.strategy && !!this.currentUserId && this.currentUserId === this.normalizeId(this.strategy.user_id);
  }

  get canReviewStrategy(): boolean {
    return !!this.strategy && this.currentUserIsAdmin && this.strategy.publication_status === 'pending_review';
  }

  startMetadataEdit(): void {
    if (!this.strategy) {
      return;
    }

    this.editingMetadata = true;
    this.resetMetadataDrafts();
  }

  cancelMetadataEdit(): void {
    this.editingMetadata = false;
    this.resetMetadataDrafts();
  }

  saveMetadata(): void {
    if (!this.strategy) {
      return;
    }

    const title = this.editedTitle.trim();
    const summary = this.editedSummary.trim();
    if (!title) {
      this.snackBar.open('Strategy name is required', 'Close', { duration: 3000 });
      return;
    }

    this.savingMetadata = true;
    this.strategyService.updateStrategy(this.strategy.id, {
      title,
      summary: summary || undefined,
    }).subscribe({
      next: (updated) => {
        this.strategy = updated;
        this.savingMetadata = false;
        this.editingMetadata = false;
        this.resetMetadataDrafts();
        this.snackBar.open('Strategy details updated', 'Close', { duration: 3000 });
      },
      error: () => {
        this.savingMetadata = false;
        this.snackBar.open('Failed to update strategy details', 'Close', { duration: 3000 });
      }
    });
  }

  get pipelineSnapshot(): any {
    return this.strategy?.normalized_spec?.['pipeline'] || null;
  }

  get pipelineConfig(): any {
    return this.pipelineSnapshot?.config || null;
  }

  get pipelineNodes(): any[] {
    return this.pipelineConfig?.nodes || [];
  }

  get signalFilters(): any[] {
    return this.pipelineSnapshot?.signal_subscriptions || [];
  }

  get strategyBrief(): string {
    return this.strategy?.body_markdown || '';
  }

  get hasNarrativeBrief(): boolean {
    const brief = this.strategyBrief.trim();
    if (!brief) {
      return false;
    }

    const legacyMarkers = [
      '**PIPELINE OVERVIEW:**',
      '**OPERATIONAL SETTINGS:**',
      '**SIGNAL FILTERS:**',
      '**AGENT CONFIGURATION:**',
      '• Step 1:',
      '## Thesis',
      '## Entry Rules',
      '## Risk Management',
      '## Operational Notes',
    ];

    return !legacyMarkers.some(marker => brief.includes(marker));
  }

  get brokerTool(): any | null {
    const directTool = this.pipelineConfig?.broker_tool;
    if (directTool) {
      return directTool;
    }

    for (const node of this.pipelineNodes) {
      const brokerTool = (node?.config?.tools || []).find((tool: any) =>
        String(tool?.tool_type || '').includes('broker')
      );
      if (brokerTool) {
        return brokerTool;
      }
    }

    return null;
  }

  get runtimeModeLabel(): string {
    return this.formatStatusLabel(this.pipelineConfig?.mode || 'paper');
  }

  get triggerModeLabel(): string {
    return this.formatStatusLabel(this.pipelineSnapshot?.trigger_mode || 'periodic');
  }

  get approvalLabel(): string {
    return this.pipelineSnapshot?.require_approval ? 'Required' : 'Optional';
  }

  get notificationsLabel(): string {
    return this.pipelineSnapshot?.notification_enabled ? 'Enabled' : 'Off';
  }

  get activeHoursLabel(): string {
    return this.pipelineSnapshot?.schedule_enabled ? 'Scheduled' : 'Manual';
  }

  get scannerLabel(): string {
    return this.pipelineSnapshot?.scanner_id ? 'Attached' : 'Not set';
  }

  get blockedSessions(): string[] {
    const tradeManager = this.pipelineNodes.find(node => node.agent_type === 'trade_manager_agent');
    return tradeManager?.config?.no_entry_sessions || [];
  }

  get noEntryAfter(): string {
    const tradeManager = this.pipelineNodes.find(node => node.agent_type === 'trade_manager_agent');
    return tradeManager?.config?.no_entry_after || '';
  }

  get approvalModes(): string[] {
    return this.pipelineSnapshot?.approval_modes || [];
  }

  get notificationEvents(): string[] {
    return this.pipelineSnapshot?.notification_events || [];
  }

  formatToolList(tools: any[] | null | undefined): string {
    if (!tools?.length) {
      return 'None attached';
    }
    return tools.map((tool) => {
      if (typeof tool === 'string') {
        return tool;
      }
      return tool?.tool_type || tool?.type || tool?.name || 'tool';
    }).join(', ');
  }

  formatSkillList(skills: any[] | null | undefined): string {
    if (!skills?.length) {
      return 'None attached';
    }
    return skills.map((skill) => {
      if (typeof skill === 'string') {
        return skill;
      }
      return skill?.skill_id || skill?.name || 'skill';
    }).join(', ');
  }

  getNodeTools(node: any): any[] {
    return node?.config?.tools || [];
  }

  getNodeSkills(node: any): any[] {
    return node?.config?.skills || [];
  }

  getNodeAdvancedEntries(node: any): Array<{ key: string; value: string }> {
    const config = node?.config || {};
    return Object.entries(config)
      .filter(([key, value]) => !this.hiddenConfigKeys.has(key) && value !== null && value !== undefined && value !== '')
      .map(([key, value]) => ({
        key: this.formatConfigKey(key),
        value: this.formatConfigValue(key, value),
      }));
  }

  getAgentIcon(agentType: string): string {
    const icons: Record<string, string> = {
      market_data_agent: 'candlestick_chart',
      bias_agent: 'insights',
      strategy_agent: 'route',
      risk_manager_agent: 'shield',
      trade_review_agent: 'fact_check',
      trade_manager_agent: 'swap_horiz',
    };
    return icons[agentType] || 'smart_toy';
  }

  getAgentLabel(agentType: string): string {
    const labels: Record<string, string> = {
      market_data_agent: 'Market Data',
      bias_agent: 'Bias',
      strategy_agent: 'Strategy',
      risk_manager_agent: 'Risk Manager',
      trade_review_agent: 'Senior Review',
      trade_manager_agent: 'Trade Manager',
    };
    return labels[agentType] || this.formatConfigKey(agentType);
  }

  getToolChipLabel(tool: any): string {
    const raw = typeof tool === 'string' ? tool : tool?.tool_type || tool?.type || tool?.name || 'tool';
    return this.formatConfigKey(raw);
  }

  getSkillChipLabel(skill: any): string {
    const raw = typeof skill === 'string' ? skill : skill?.name || skill?.skill_id || 'skill';
    return this.formatConfigKey(raw);
  }

  private formatConfigKey(value: string): string {
    return value
      .replace(/_/g, ' ')
      .replace(/\b\w/g, (match) => match.toUpperCase());
  }

  private formatConfigValue(key: string, value: any): string {
    if (key.toLowerCase().includes('token') || key.toLowerCase().includes('secret')) {
      return 'Configured';
    }
    if (Array.isArray(value)) {
      return value.map((entry) => this.formatPrimitive(entry)).join(', ');
    }
    if (typeof value === 'object') {
      return 'Configured';
    }
    return this.formatPrimitive(value);
  }

  private formatPrimitive(value: any): string {
    if (typeof value === 'boolean') {
      return value ? 'Yes' : 'No';
    }
    return String(value);
  }

  private formatStatusLabel(value: string): string {
    return this.formatConfigKey(value);
  }

  private normalizeId(value: string | null | undefined): string | null {
    const normalized = String(value || '').trim();
    return normalized || null;
  }

  useStrategy(): void {
    if (!this.strategy) {
      return;
    }
    this.strategyService.createPipelineFromStrategy(this.strategy.id).subscribe({
      next: ({ pipeline_id }) => {
        this.snackBar.open('Pipeline created from strategy', 'Close', { duration: 3000 });
        this.router.navigate(['/pipeline-builder', pipeline_id], {
          queryParams: { namePrompt: '1' }
        });
      }
    });
  }

  toggleVote(): void {
    if (!this.strategy) {
      return;
    }
    this.strategyService.voteForStrategy(this.strategy.id).subscribe({
      next: (response) => {
        if (!this.strategy) {
          return;
        }
        this.strategy.vote_count = response.vote_count;
        this.strategy.has_voted = response.has_voted;
      }
    });
  }

  submitForReview(): void {
    if (!this.strategy) {
      return;
    }
    this.strategyService.submitStrategy(this.strategy.id).subscribe({
      next: (updated) => {
        this.strategy = updated;
        this.snackBar.open('Strategy submitted for review', 'Close', { duration: 3000 });
      }
    });
  }

  reviewStrategy(approved: boolean): void {
    if (!this.strategy || !this.canReviewStrategy) {
      return;
    }

    const actionLabel = approved ? 'Approve' : 'Reject';
    const dialogRef = this.dialog.open(ConfirmDialogComponent, {
      width: '440px',
      data: {
        title: `${actionLabel} Strategy`,
        message: `${actionLabel} strategy "${this.strategy.title}" for marketplace publication?`,
        confirmText: actionLabel,
        cancelText: 'Cancel',
      } as ConfirmDialogData
    });

    dialogRef.afterClosed().subscribe(confirmed => {
      if (!confirmed || !this.strategy) {
        return;
      }

      this.reviewing = true;
      this.strategyService.reviewStrategy(this.strategy.id, approved).subscribe({
        next: (updated) => {
          this.strategy = updated;
          this.reviewing = false;
          this.snackBar.open(
            approved ? 'Strategy approved' : 'Strategy rejected',
            'Close',
            { duration: 3000 }
          );
        },
        error: () => {
          this.reviewing = false;
          this.snackBar.open(`Failed to ${approved ? 'approve' : 'reject'} strategy`, 'Close', {
            duration: 3000,
          });
        }
      });
    });
  }

  deleteStrategy(): void {
    if (!this.strategy) {
      return;
    }

    const dialogRef = this.dialog.open(ConfirmDialogComponent, {
      width: '440px',
      data: {
        title: 'Delete Strategy',
        message: `Delete strategy "${this.strategy.title}"? This cannot be undone.`,
        confirmText: 'Delete',
        cancelText: 'Cancel',
      } as ConfirmDialogData
    });

    dialogRef.afterClosed().subscribe(confirmed => {
      if (!confirmed || !this.strategy) {
        return;
      }

      this.strategyService.deleteStrategy(this.strategy.id).subscribe({
        next: () => {
          this.snackBar.open('Strategy deleted', 'Close', { duration: 3000 });
          this.router.navigate(['/strategies']);
        }
      });
    });
  }

  private resetMetadataDrafts(): void {
    this.editedTitle = this.strategy?.title || '';
    this.editedSummary = this.strategy?.summary || '';
  }
}
