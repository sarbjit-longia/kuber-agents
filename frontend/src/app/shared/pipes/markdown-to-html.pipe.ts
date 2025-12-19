import { Pipe, PipeTransform } from '@angular/core';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';

@Pipe({
  name: 'markdownToHtml',
  standalone: true
})
export class MarkdownToHtmlPipe implements PipeTransform {
  constructor(private sanitizer: DomSanitizer) {}

  transform(value: unknown): SafeHtml {
    // Handle null, undefined, or non-string values
    if (!value || typeof value !== 'string') {
      return '';
    }

    let html = value;

    // Convert **TEXT:** to bold headers with larger font
    html = html.replace(/\*\*([A-Z\s&]+):\*\*/g, '<div class="section-header">$1:</div>');

    // Convert bullet points (• text) to styled list items
    html = html.replace(/^\s*•\s+(.+)$/gm, '<div class="bullet-item">• $1</div>');

    // Convert line breaks to <br> tags
    html = html.replace(/\n/g, '<br>');

    return this.sanitizer.bypassSecurityTrustHtml(html);
  }
}

