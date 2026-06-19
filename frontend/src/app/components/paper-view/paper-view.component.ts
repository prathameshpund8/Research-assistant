import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MarkdownComponent } from 'ngx-markdown';

import { PaperResult } from '../../models/paper.model';

/** Renders the generated IEEE paper: quality reports, preview, .docx download. */
@Component({
  selector: 'app-paper-view',
  standalone: true,
  imports: [CommonModule, MarkdownComponent],
  template: `
    <div class="paper" *ngIf="paper">
      <div class="toolbar">
        <div class="metrics">
          <span class="metric" [class.good]="paper.originality.score >= 80"
                [class.warn]="paper.originality.score < 80">
            Originality {{ paper.originality.score }}%
          </span>
          <span class="metric">
            {{ paper.verification.supported_claims }}/{{ paper.verification.total_claims }} claims verified
          </span>
          <span class="metric">{{ paper.references.length }} references</span>
          <span class="metric">{{ paper.sections.length }} sections</span>
        </div>
        <a class="download" [href]="docxUrl" target="_blank" rel="noopener">⬇ Download .docx</a>
      </div>

      <!-- Quality reports -->
      <details class="report" *ngIf="paper.originality.flagged.length || paper.verification.notes.length">
        <summary>Quality &amp; originality report</summary>
        <div class="report-body">
          <p>
            <strong>Originality check</strong> ({{ paper.originality.method }}):
            rewrote {{ paper.originality.rewritten }} near-duplicate passage(s).
          </p>
          <ul *ngIf="paper.originality.flagged.length">
            <li *ngFor="let f of paper.originality.flagged">
              <em>{{ f.section }}</em> — {{ (f.similarity * 100) | number:'1.0-0' }}% overlap with {{ f.source_id }}:
              “{{ f.passage }}…”
            </li>
          </ul>
          <p *ngIf="paper.verification.notes.length"><strong>Verification notes:</strong></p>
          <ul>
            <li *ngFor="let n of paper.verification.notes">{{ n }}</li>
          </ul>
        </div>
      </details>

      <div class="disclaimer">
        ⚠ AI-generated draft grounded in cited web sources. Review and verify all claims,
        add original analysis, and disclose AI assistance before any submission — this is a
        starting draft, not a publication-ready paper.
      </div>

      <markdown class="markdown-body paper-body" [data]="paper.paper_markdown"></markdown>
    </div>
  `,
  styles: [
    `
      .paper {
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
      .metrics {
        display: flex;
        gap: 0.5rem;
        flex-wrap: wrap;
      }
      .metric {
        font-size: 0.75rem;
        color: var(--text-muted);
        background: var(--bg);
        border: 1px solid var(--border);
        border-radius: 999px;
        padding: 0.2rem 0.7rem;
      }
      .metric.good {
        color: #fff;
        background: var(--success);
        border-color: var(--success);
      }
      .metric.warn {
        color: #fff;
        background: #d97706;
        border-color: #d97706;
      }
      .download {
        background: var(--accent);
        color: #fff;
        text-decoration: none;
        border-radius: 8px;
        padding: 0.5rem 1rem;
        font-size: 0.85rem;
        font-weight: 600;
      }
      .download:hover {
        background: var(--accent-strong);
      }
      .report {
        margin-bottom: 1rem;
        border: 1px solid var(--border);
        border-radius: 10px;
        padding: 0.5rem 0.9rem;
        background: var(--bg);
      }
      .report summary {
        cursor: pointer;
        font-weight: 600;
        font-size: 0.9rem;
      }
      .report-body {
        font-size: 0.85rem;
        color: var(--text-muted);
        margin-top: 0.5rem;
      }
      .report-body li {
        margin: 0.25rem 0;
      }
      .disclaimer {
        background: color-mix(in srgb, #d97706 12%, transparent);
        border: 1px solid #d97706;
        color: var(--text);
        border-radius: 10px;
        padding: 0.7rem 0.9rem;
        font-size: 0.82rem;
        margin-bottom: 1.5rem;
      }
      .paper-body {
        column-count: 1;
      }
    `,
  ],
})
export class PaperViewComponent {
  @Input() paper: PaperResult | null = null;
  @Input() docxUrl = '';
}
