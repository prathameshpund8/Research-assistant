import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MarkdownComponent } from 'ngx-markdown';

import { ResearchResult } from '../../models/research.model';

/** Renders the final cited Markdown report with a copy/download toolbar. */
@Component({
  selector: 'app-report-view',
  standalone: true,
  imports: [CommonModule, MarkdownComponent],
  template: `
    <div class="report" *ngIf="result">
      <div class="toolbar">
        <div class="meta">
          <span class="pill">{{ result.sources.length }} sources</span>
          <span class="pill">{{ result.facts.length }} facts</span>
          <span class="pill">{{ result.rounds_used }} research round(s)</span>
        </div>
        <div class="actions">
          <button class="ghost" (click)="copy()">{{ copied ? 'Copied!' : 'Copy' }}</button>
          <button class="ghost" (click)="download()">Download .md</button>
        </div>
      </div>

      <!-- ngx-markdown renders the report; links open in a new tab (see app styles). -->
      <markdown class="markdown-body" [data]="result.report_markdown"></markdown>
    </div>
  `,
  styles: [
    `
      .report {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 14px;
        padding: 1.75rem 2rem;
        box-shadow: var(--shadow);
      }
      .toolbar {
        display: flex;
        justify-content: space-between;
        align-items: center;
        flex-wrap: wrap;
        gap: 0.75rem;
        padding-bottom: 1rem;
        margin-bottom: 1rem;
        border-bottom: 1px solid var(--border);
      }
      .meta {
        display: flex;
        gap: 0.5rem;
        flex-wrap: wrap;
      }
      .pill {
        font-size: 0.75rem;
        color: var(--text-muted);
        background: var(--bg);
        border: 1px solid var(--border);
        border-radius: 999px;
        padding: 0.2rem 0.7rem;
      }
      .actions {
        display: flex;
        gap: 0.5rem;
      }
      .ghost {
        border: 1px solid var(--border);
        background: var(--bg);
        color: var(--text);
        border-radius: 8px;
        padding: 0.4rem 0.85rem;
        font-size: 0.82rem;
        cursor: pointer;
      }
      .ghost:hover {
        border-color: var(--accent);
        color: var(--accent);
      }
    `,
  ],
})
export class ReportViewComponent {
  @Input() result: ResearchResult | null = null;
  copied = false;

  copy(): void {
    if (!this.result) return;
    navigator.clipboard.writeText(this.result.report_markdown).then(() => {
      this.copied = true;
      setTimeout(() => (this.copied = false), 1500);
    });
  }

  download(): void {
    if (!this.result) return;
    const blob = new Blob([this.result.report_markdown], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `research-${this.result.research_id}.md`;
    a.click();
    URL.revokeObjectURL(url);
  }
}
