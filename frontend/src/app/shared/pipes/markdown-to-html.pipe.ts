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

    // Step 1: Convert **TEXT:** to bold headers with larger font (all-caps labels)
    // Must be done before general bold conversion to avoid conflicts
    html = html.replace(/\*\*([A-Z\s&]+):\*\*/g, '<div class="section-header">$1:</div>');

    // Step 1b: Convert remaining **text** to <strong>text</strong> (mixed-case bold)
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');

    // Step 2: Convert bullet points (• text) to styled list items
    // Handle bullets with leading whitespace
    html = html.replace(/^\s*•\s+(.+)$/gm, '<div class="bullet-item">• $1</div>');

    // Step 3: Convert remaining line breaks to <br> tags
    // BUT preserve the structure created by divs
    html = html.replace(/\n(?!<div)/g, '<br>');
    
    // Step 4: Clean up any extra <br> tags before/after section headers
    html = html.replace(/<br>\s*<div class="section-header">/g, '<div class="section-header">');
    html = html.replace(/<\/div><br>/g, '</div>');

    return this.sanitizer.bypassSecurityTrustHtml(html);
  }
}

