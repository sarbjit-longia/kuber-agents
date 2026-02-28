/**
 * Execution Report Component
 *
 * Full-page report viewer for completed pipeline executions.
 * Full-width layout with sticky left sidebar navigation for jumping between sections.
 */

import { Component, OnInit, OnDestroy, HostListener } from '@angular/core';
import { CommonModule, ViewportScroller } from '@angular/common';
import { ActivatedRoute, Router, RouterModule } from '@angular/router';
import { HttpClient } from '@angular/common/http';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatDividerModule } from '@angular/material/divider';
import { MatChipsModule } from '@angular/material/chips';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatCardModule } from '@angular/material/card';
import { MatTooltipModule } from '@angular/material/tooltip';

import { MonitoringService } from '../../../core/services/monitoring.service';
import { NavbarComponent } from '../../../core/components/navbar/navbar.component';
import { FooterComponent } from '../../../shared/components/footer/footer.component';
import { TradingChartComponent } from '../../../shared/components/trading-chart/trading-chart.component';
import { MarkdownToHtmlPipe } from '../../../shared/pipes/markdown-to-html.pipe';
import { environment } from '../../../../environments/environment';

interface NavSection {
  id: string;
  label: string;
  icon: string;
  visible: boolean;
  indent?: boolean; // sub-item under a group
}

interface AgentReportEntry {
  key: string;
  report: any;
  sectionId: string;
  label: string;
  icon: string;
}

@Component({
  selector: 'app-execution-report',
  standalone: true,
  imports: [
    CommonModule,
    RouterModule,
    MatButtonModule,
    MatIconModule,
    MatDividerModule,
    MatChipsModule,
    MatProgressSpinnerModule,
    MatCardModule,
    MatTooltipModule,
    NavbarComponent,
    FooterComponent,
    TradingChartComponent,
    MarkdownToHtmlPipe,
  ],
  templateUrl: './execution-report.component.html',
  styleUrls: ['./execution-report.component.scss'],
})
export class ExecutionReportComponent implements OnInit, OnDestroy {
  executionId = '';
  execution: any = null;
  executiveReport: any = null;
  tradeAnalysis: any = null;
  loading = true;
  reportLoading = true;
  analysisLoading = true;
  error: string | null = null;
  activeSection = 'summary';
  sidebarCollapsed = false;

  navSections: NavSection[] = [];
  agentReports: AgentReportEntry[] = [];

  constructor(
    private route: ActivatedRoute,
    private router: Router,
    private monitoringService: MonitoringService,
    private http: HttpClient,
    private viewportScroller: ViewportScroller
  ) {}

  ngOnInit(): void {
    this.executionId = this.route.snapshot.paramMap.get('id') || '';
    if (this.executionId) {
      this.loadExecution();
    } else {
      this.error = 'No execution ID provided';
      this.loading = false;
    }
  }

  ngOnDestroy(): void {}

  @HostListener('window:scroll')
  onScroll(): void {
    this.updateActiveSection();
  }

  private updateActiveSection(): void {
    const sections = this.navSections.filter(s => s.visible);
    const scrollY = window.scrollY + 120; // offset for navbar + header

    for (let i = sections.length - 1; i >= 0; i--) {
      const el = document.getElementById(sections[i].id);
      if (el && el.offsetTop <= scrollY) {
        this.activeSection = sections[i].id;
        return;
      }
    }
    if (sections.length) {
      this.activeSection = sections[0].id;
    }
  }

  buildNavSections(): void {
    const sections: NavSection[] = [
      { id: 'summary', label: 'Executive Summary', icon: 'stars', visible: true },
      { id: 'strategy', label: 'Strategy Analysis', icon: 'psychology', visible: !!this.getStrategy() },
      { id: 'risk', label: 'Risk Assessment', icon: 'security', visible: !!this.getRiskAssessment() },
      { id: 'execution', label: 'Trade Execution', icon: 'swap_horiz', visible: !!this.getTradeExecution() },
      { id: 'pnl', label: 'P&L Summary', icon: 'account_balance', visible: !!(this.getTradeOutcome()?.pnl !== null && this.getTradeOutcome()?.pnl !== undefined) },
      { id: 'analysis', label: 'AI Trade Analysis', icon: 'school', visible: true },
    ];

    // Build per-agent report entries and nav links
    this.buildAgentReports();
    for (const agent of this.agentReports) {
      sections.push({ id: agent.sectionId, label: agent.label, icon: agent.icon, visible: true, indent: true });
    }

    sections.push(
      { id: 'timeline', label: 'Execution Timeline', icon: 'timeline', visible: !!this.execution?.agent_states?.length },
      { id: 'costs', label: 'Cost Breakdown', icon: 'payments', visible: true },
    );

    this.navSections = sections;
  }

  private buildAgentReports(): void {
    const reports = this.execution?.reports;
    if (!reports) {
      this.agentReports = [];
      return;
    }

    // Desired agent order
    const order = ['bias_agent', 'strategy_agent', 'risk_manager_agent', 'trade_manager_agent'];
    const entries: AgentReportEntry[] = [];

    for (const key of Object.keys(reports)) {
      const report = reports[key];
      const agentType = report.agent_type || key;
      entries.push({
        key,
        report,
        sectionId: `agent-${agentType.replace(/_/g, '-')}`,
        label: this.formatAgentName(agentType),
        icon: this.getAgentIcon(agentType),
      });
    }

    // Sort by the defined order; unknowns go last
    entries.sort((a, b) => {
      const aIdx = order.indexOf(a.report.agent_type || a.key);
      const bIdx = order.indexOf(b.report.agent_type || b.key);
      return (aIdx === -1 ? 999 : aIdx) - (bIdx === -1 ? 999 : bIdx);
    });

    this.agentReports = entries;
  }

  formatAgentName(agentType: string): string {
    return agentType
      .replace(/_/g, ' ')
      .replace(/\b\w/g, c => c.toUpperCase());
  }

  /**
   * Classify a data value as short (for grid display) or long (for full-width block).
   * Short = numbers, booleans, or strings under 80 chars without newlines/markdown/separators.
   */
  isShortValue(value: any): boolean {
    if (value === null || value === undefined) return true;
    if (typeof value === 'number' || typeof value === 'boolean') return true;
    if (typeof value === 'string') {
      return value.length < 80 && !value.includes('\n') && !value.includes('**') && !value.includes(' | ');
    }
    return false;
  }

  /**
   * Get data entries split into short (grid) and long (block) groups.
   * Filters out chart keys and internal fields.
   */
  getAgentDataEntries(data: any): { short: {key: string, value: any}[], long: {key: string, value: any}[] } {
    const skipKeys = new Set(['chart', 'strategy_chart', 'candles']);
    const short: {key: string, value: any}[] = [];
    const long: {key: string, value: any}[] = [];

    if (!data || typeof data !== 'object') return { short, long };

    for (const [key, value] of Object.entries(data)) {
      if (skipKeys.has(key)) continue;
      if (this.isShortValue(value)) {
        short.push({ key, value });
      } else {
        long.push({ key, value });
      }
    }
    return { short, long };
  }

  scrollToSection(sectionId: string): void {
    this.activeSection = sectionId;
    const el = document.getElementById(sectionId);
    if (el) {
      const offset = 80; // navbar height
      const top = el.getBoundingClientRect().top + window.scrollY - offset;
      window.scrollTo({ top, behavior: 'smooth' });
    }
  }

  loadExecution(): void {
    this.monitoringService.getExecutionDetail(this.executionId).subscribe({
      next: (data) => {
        this.execution = data;
        this.loading = false;
        this.buildNavSections();
        this.loadExecutiveReport();
        this.loadTradeAnalysis();
      },
      error: (err) => {
        console.error('Failed to load execution:', err);
        this.error = 'Failed to load execution details';
        this.loading = false;
      },
    });
  }

  loadExecutiveReport(): void {
    const timeout = setTimeout(() => {
      if (this.reportLoading) {
        this.executiveReport = {
          executive_summary: 'Report available - AI summary generation in progress...',
          agent_reports: this.execution.reports || {},
          execution_artifacts: this.execution.result?.execution_artifacts || {},
        };
        this.reportLoading = false;
      }
    }, 5000);

    this.monitoringService.getExecutiveReport(this.executionId).subscribe({
      next: (report) => {
        clearTimeout(timeout);
        this.executiveReport = report;
        this.reportLoading = false;
      },
      error: (err) => {
        clearTimeout(timeout);
        console.error('Failed to load executive report:', err);
        this.executiveReport = {
          executive_summary: 'AI summary generation failed - showing basic report',
          agent_reports: this.execution.reports || {},
          execution_artifacts: this.execution.result?.execution_artifacts || {},
        };
        this.reportLoading = false;
      },
    });
  }

  loadTradeAnalysis(): void {
    this.monitoringService.getTradeAnalysis(this.executionId).subscribe({
      next: (analysis) => {
        this.tradeAnalysis = analysis;
        this.analysisLoading = false;
        // Update nav visibility now that we know if analysis is available
        const analysisNav = this.navSections.find(s => s.id === 'analysis');
        if (analysisNav) {
          analysisNav.visible = !!(analysis?.available);
        }
      },
      error: () => {
        this.tradeAnalysis = { available: false };
        this.analysisLoading = false;
        const analysisNav = this.navSections.find(s => s.id === 'analysis');
        if (analysisNav) {
          analysisNav.visible = false;
        }
      },
    });
  }

  downloadReport(): void {
    const url = `${environment.apiUrl}/api/v1/executions/${this.executionId}/report.pdf`;
    this.http.get(url, { responseType: 'blob' }).subscribe({
      next: (blob: Blob) => {
        const downloadUrl = window.URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = downloadUrl;
        link.download = `execution-report-${this.execution?.symbol || 'unknown'}.pdf`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        window.URL.revokeObjectURL(downloadUrl);
      },
      error: (err) => {
        const msg =
          err.status === 404
            ? 'PDF not yet generated for this execution'
            : 'Failed to download PDF';
        alert(msg);
      },
    });
  }

  goBack(): void {
    this.router.navigate(['/monitoring', this.executionId]);
  }

  toggleSidebar(): void {
    this.sidebarCollapsed = !this.sidebarCollapsed;
  }

  // --- Chart helpers ---
  hasChart(): boolean {
    return !!this.execution?.result?.execution_artifacts?.strategy_chart;
  }

  getChartData(): any {
    return this.execution?.result?.execution_artifacts?.strategy_chart;
  }

  hasAgentChart(agentReport: any): boolean {
    if (!agentReport?.data) return false;
    return !!(agentReport.data.chart || agentReport.data.strategy_chart);
  }

  getAgentChartData(agentReport: any): any {
    if (!agentReport?.data) return null;
    return agentReport.data.chart || agentReport.data.strategy_chart || null;
  }

  // --- Format helpers ---
  formatDuration(seconds: number | undefined): string {
    if (!seconds) return '-';
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    if (hours > 0) return `${hours}h ${minutes}m ${secs}s`;
    if (minutes > 0) return `${minutes}m ${secs}s`;
    return `${secs}s`;
  }

  formatDate(date: string | null | undefined): string {
    if (!date) return 'N/A';
    try {
      let isoString = date;
      if (!date.endsWith('Z') && !date.match(/[+-]\d{2}:\d{2}$/)) {
        isoString = date + 'Z';
      }
      return new Date(isoString).toLocaleString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return 'Invalid date';
    }
  }

  formatPnL(pnl: number | null | undefined): string {
    if (pnl === null || pnl === undefined) return '-';
    const sign = pnl >= 0 ? '+' : '';
    return `${sign}$${pnl.toFixed(2)}`;
  }

  formatCost(cost: number | null | undefined): string {
    if (cost === null || cost === undefined) return '-';
    return `$${cost.toFixed(4)}`;
  }

  // --- Data access helpers ---
  getStrategy(): any {
    return this.execution?.result?.strategy;
  }

  getRiskAssessment(): any {
    return this.execution?.result?.risk_assessment;
  }

  getTradeExecution(): any {
    return this.execution?.result?.trade_execution;
  }

  getTradeOutcome(): any {
    return this.execution?.result?.trade_outcome;
  }

  getMarketBias(): any {
    return this.execution?.result?.market_bias || this.execution?.result?.biases;
  }

  getSlippage(): number | null {
    const strategy = this.getStrategy();
    const tradeExec = this.getTradeExecution();
    if (strategy?.entry_price && tradeExec?.filled_price) {
      return Math.abs(tradeExec.filled_price - strategy.entry_price);
    }
    return null;
  }

  getDurationSeconds(): number | null {
    if (this.execution?.started_at && this.execution?.completed_at) {
      const start = new Date(this.execution.started_at).getTime();
      const end = new Date(this.execution.completed_at).getTime();
      return (end - start) / 1000;
    }
    return null;
  }

  getGradeColor(grade: string): string {
    const colors: Record<string, string> = {
      A: '#22c55e',
      B: '#84cc16',
      C: '#eab308',
      D: '#f97316',
      F: '#ef4444',
    };
    return colors[grade] || '#6b7280';
  }

  getAgentIcon(agentType: string): string {
    const icons: Record<string, string> = {
      bias_agent: 'analytics',
      strategy_agent: 'psychology',
      risk_manager_agent: 'security',
      trade_manager_agent: 'swap_horiz',
    };
    return icons[agentType] || 'smart_toy';
  }

  getAgentStateColor(status: string): string {
    const colors: Record<string, string> = {
      completed: '#4caf50',
      failed: '#f44336',
      running: '#2196f3',
      pending: '#ff9800',
      skipped: '#9e9e9e',
    };
    return colors[status] || '#9e9e9e';
  }

  getAgentInstructions(agentType: string): string | null {
    const nodes = this.execution?.pipeline_config?.nodes;
    if (!nodes || !Array.isArray(nodes)) return null;
    const node = nodes.find((n: any) => n.agent_type === agentType);
    return node?.config?.instructions || null;
  }

  isArray(value: any): boolean {
    return Array.isArray(value);
  }

  isObject(value: any): boolean {
    return value !== null && typeof value === 'object' && !Array.isArray(value);
  }
}
