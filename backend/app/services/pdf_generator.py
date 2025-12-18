"""
PDF Report Generation Service

Generates professional PDF reports for pipeline executions using WeasyPrint.
"""
import os
from typing import Dict, Any, Optional
from pathlib import Path
from datetime import datetime
import structlog
from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML, CSS

from app.config import settings

logger = structlog.get_logger(__name__)


class PDFReportGenerator:
    """
    Generates professional PDF reports from execution data.
    
    Uses HTML templates with Jinja2 and WeasyPrint for high-quality PDF output.
    """
    
    def __init__(self):
        """Initialize PDF generator with template environment."""
        # Setup Jinja2 template environment
        template_dir = Path(__file__).parent / 'templates'
        template_dir.mkdir(exist_ok=True)
        
        self.env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            autoescape=True
        )
        
        # PDF storage directory
        self.pdf_dir = Path(settings.PDF_STORAGE_PATH if hasattr(settings, 'PDF_STORAGE_PATH') else '/app/data/reports')
        self.pdf_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info("pdf_generator_initialized", pdf_dir=str(self.pdf_dir))
    
    def generate_execution_report(
        self,
        execution_id: str,
        execution_data: Dict[str, Any],
        executive_summary: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Generate PDF report for a pipeline execution.
        
        Args:
            execution_id: Execution UUID
            execution_data: Complete execution data
            executive_summary: Optional AI-generated summary
            
        Returns:
            Relative path to generated PDF file
        """
        try:
            logger.info("generating_pdf_report", execution_id=execution_id)
            
            # Prepare template context
            context = self._prepare_context(execution_data, executive_summary)
            
            # Render HTML from template
            html_content = self._render_template(context)
            
            # Generate PDF filename
            symbol = execution_data.get('symbol', 'unknown')
            timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
            filename = f"execution-report-{symbol}-{timestamp}.pdf"
            filepath = self.pdf_dir / filename
            
            # Convert HTML to PDF
            self._html_to_pdf(html_content, filepath)
            
            # Return relative path for database storage
            relative_path = f"reports/{filename}"
            
            logger.info(
                "pdf_report_generated",
                execution_id=execution_id,
                filepath=str(filepath),
                filesize=filepath.stat().st_size
            )
            
            return relative_path
            
        except Exception as e:
            logger.error("pdf_generation_failed", execution_id=execution_id, error=str(e))
            raise
    
    def _prepare_context(
        self,
        execution_data: Dict[str, Any],
        executive_summary: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Prepare template context from execution data."""
        result = execution_data.get('result', {})
        
        context = {
            'execution_id': execution_data.get('id'),
            'pipeline_name': execution_data.get('pipeline_name', 'Unknown'),
            'symbol': execution_data.get('symbol', 'N/A'),
            'mode': execution_data.get('mode', 'paper').upper(),
            'status': execution_data.get('status', 'unknown').upper(),
            'started_at': self._format_datetime(execution_data.get('started_at')),
            'completed_at': self._format_datetime(execution_data.get('completed_at')),
            'duration': self._format_duration(execution_data.get('duration_seconds')),
            'cost': execution_data.get('cost', 0),
            'trigger_source': execution_data.get('trigger_source', 'N/A'),
            
            # Executive summary (if available)
            'executive_summary': executive_summary.get('executive_summary') if executive_summary else None,
            'key_takeaways': executive_summary.get('key_takeaways', []) if executive_summary else [],
            'final_recommendation': executive_summary.get('final_recommendation') if executive_summary else None,
            'risk_notes': executive_summary.get('risk_notes') if executive_summary else None,
            
            # Agent reports
            'reports': execution_data.get('reports', {}),
            
            # Results
            'biases': result.get('biases'),
            'strategy': result.get('strategy'),
            'risk_assessment': result.get('risk_assessment'),
            'trade_execution': result.get('trade_execution'),
            
            # Execution artifacts (charts, images, etc.)
            'execution_artifacts': result.get('execution_artifacts', {}),
            
            # Metadata
            'generated_at': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC'),
        }
        
        return context
    
    def _render_template(self, context: Dict[str, Any]) -> str:
        """Render HTML template with context."""
        try:
            template = self.env.get_template('execution_report.html')
            return template.render(**context)
        except Exception as e:
            logger.warning("template_not_found_using_fallback", error=str(e))
            # Use inline fallback template
            return self._generate_fallback_html(context)
    
    def _html_to_pdf(self, html_content: str, output_path: Path):
        """Convert HTML to PDF using WeasyPrint."""
        # Custom CSS for better PDF rendering
        css = CSS(string='''
            @page {
                size: A4;
                margin: 2cm;
            }
            body {
                font-family: Arial, sans-serif;
                font-size: 10pt;
                line-height: 1.6;
                color: #333;
            }
            h1 {
                color: #667eea;
                font-size: 24pt;
                margin-bottom: 10pt;
            }
            h2 {
                color: #667eea;
                font-size: 18pt;
                margin-top: 20pt;
                margin-bottom: 10pt;
                border-bottom: 2px solid #667eea;
                padding-bottom: 5pt;
            }
            h3 {
                color: #555;
                font-size: 14pt;
                margin-top: 15pt;
                margin-bottom: 8pt;
            }
            .header {
                text-align: center;
                margin-bottom: 30pt;
            }
            .summary-box {
                background: #e8f5e9;
                padding: 15pt;
                border-radius: 5pt;
                margin: 15pt 0;
            }
            .recommendation-box {
                background: #e3f2fd;
                padding: 15pt;
                border-radius: 5pt;
                margin: 15pt 0;
                border-left: 4pt solid #2196f3;
            }
            .risk-box {
                background: #fff3e0;
                padding: 15pt;
                border-radius: 5pt;
                margin: 15pt 0;
                border-left: 4pt solid #ff9800;
            }
            .meta-info {
                display: flex;
                justify-content: space-between;
                background: #f8f9fa;
                padding: 10pt;
                border-radius: 5pt;
                margin-bottom: 20pt;
            }
            .meta-item {
                margin: 5pt 0;
            }
            .meta-label {
                font-weight: bold;
                color: #666;
            }
            table {
                width: 100%;
                border-collapse: collapse;
                margin: 15pt 0;
            }
            th, td {
                padding: 8pt;
                text-align: left;
                border-bottom: 1pt solid #ddd;
            }
            th {
                background: #667eea;
                color: white;
                font-weight: bold;
            }
            .agent-report {
                background: #fafafa;
                padding: 12pt;
                margin: 10pt 0;
                border-left: 3pt solid #667eea;
            }
            .footer {
                margin-top: 30pt;
                padding-top: 10pt;
                border-top: 1pt solid #ddd;
                text-align: center;
                font-size: 8pt;
                color: #999;
            }
            ul {
                margin: 10pt 0;
                padding-left: 20pt;
            }
            li {
                margin: 5pt 0;
            }
            code, pre {
                background: #f5f5f5;
                padding: 2pt 4pt;
                border-radius: 3pt;
                font-family: 'Courier New', monospace;
                font-size: 9pt;
            }
        ''')
        
        # Generate PDF
        HTML(string=html_content).write_pdf(output_path, stylesheets=[css])
    
    def _generate_fallback_html(self, context: Dict[str, Any]) -> str:
        """Generate simple HTML fallback if template is missing."""
        html = f'''
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Execution Report - {context['symbol']}</title>
        </head>
        <body>
            <div class="header">
                <h1>Trading Execution Report</h1>
                <p><strong>{context['symbol']}</strong> | {context['pipeline_name']}</p>
            </div>
            
            <div class="meta-info">
                <div class="meta-item">
                    <span class="meta-label">Status:</span> {context['status']}
                </div>
                <div class="meta-item">
                    <span class="meta-label">Mode:</span> {context['mode']}
                </div>
                <div class="meta-item">
                    <span class="meta-label">Started:</span> {context['started_at']}
                </div>
                <div class="meta-item">
                    <span class="meta-label">Duration:</span> {context['duration']}
                </div>
                <div class="meta-item">
                    <span class="meta-label">Cost:</span> ${context['cost']:.4f}
                </div>
            </div>
        '''
        
        if context.get('executive_summary'):
            html += f'''
            <h2>Executive Summary</h2>
            <div class="summary-box">
                <p>{context['executive_summary']}</p>
            </div>
            '''
        
        if context.get('key_takeaways'):
            html += '<h2>Key Takeaways</h2><ul>'
            for takeaway in context['key_takeaways']:
                html += f'<li>{takeaway}</li>'
            html += '</ul>'
        
        if context.get('final_recommendation'):
            html += f'''
            <h2>Final Recommendation</h2>
            <div class="recommendation-box">
                <p>{context['final_recommendation']}</p>
            </div>
            '''
        
        # Add agent reports
        if context.get('reports'):
            html += '<h2>Agent Reports</h2>'
            for agent_id, report in context['reports'].items():
                html += f'''
                <div class="agent-report">
                    <h3>{report.get('title', agent_id)}</h3>
                    <p>{report.get('summary', 'No summary available')}</p>
                </div>
                '''
        
        if context.get('risk_notes') and context['risk_notes'] != 'None':
            html += f'''
            <h2>Risk Notes</h2>
            <div class="risk-box">
                <p>{context['risk_notes']}</p>
            </div>
            '''
        
        html += f'''
            <div class="footer">
                <p>Generated on {context['generated_at']} | Execution ID: {context['execution_id']}</p>
            </div>
        </body>
        </html>
        '''
        
        return html
    
    def _format_datetime(self, dt) -> str:
        """Format datetime for display."""
        if not dt:
            return 'N/A'
        if isinstance(dt, str):
            try:
                dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
            except:
                return dt
        return dt.strftime('%Y-%m-%d %H:%M:%S UTC')
    
    def _format_duration(self, seconds) -> str:
        """Format duration in human-readable format."""
        if not seconds:
            return 'N/A'
        
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        
        if hours > 0:
            return f"{hours}h {minutes}m {secs}s"
        elif minutes > 0:
            return f"{minutes}m {secs}s"
        else:
            return f"{secs}s"


# Singleton instance
pdf_generator = PDFReportGenerator()

