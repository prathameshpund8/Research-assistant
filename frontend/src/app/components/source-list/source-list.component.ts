import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';

import { Source } from '../../models/research.model';

/** Sidebar list of collected sources with external links. */
@Component({
  selector: 'app-source-list',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="sources">
      <div class="head">
        <h3>Sources</h3>
        <span class="count">{{ sources.length }}</span>
      </div>

      <p class="empty" *ngIf="sources.length === 0">No sources collected yet.</p>

      <ul>
        <li *ngFor="let s of sources">
          <a [href]="s.url" target="_blank" rel="noopener noreferrer" class="src">
            <span class="cite">{{ s.id }}</span>
            <span class="title">{{ s.title }}</span>
          </a>
          <p class="snippet" *ngIf="s.snippet">{{ s.snippet }}</p>
        </li>
      </ul>
    </div>
  `,
  styles: [
    `
      .sources {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 14px;
        padding: 1.25rem;
        box-shadow: var(--shadow);
        position: sticky;
        top: 1rem;
      }
      .head {
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 0.75rem;
      }
      h3 {
        margin: 0;
        font-size: 1rem;
      }
      .count {
        background: var(--accent);
        color: #fff;
        border-radius: 999px;
        font-size: 0.75rem;
        padding: 0.1rem 0.55rem;
        font-weight: 600;
      }
      .empty {
        color: var(--text-muted);
        font-size: 0.88rem;
      }
      ul {
        list-style: none;
        margin: 0;
        padding: 0;
        display: flex;
        flex-direction: column;
        gap: 0.85rem;
        max-height: 70vh;
        overflow-y: auto;
      }
      .src {
        display: flex;
        gap: 0.5rem;
        align-items: baseline;
        text-decoration: none;
      }
      .cite {
        font-size: 0.72rem;
        font-weight: 700;
        color: var(--accent);
        background: var(--bg);
        border: 1px solid var(--border);
        border-radius: 6px;
        padding: 0.05rem 0.4rem;
        flex-shrink: 0;
      }
      .title {
        color: var(--text);
        font-size: 0.9rem;
        line-height: 1.3;
      }
      .src:hover .title {
        color: var(--accent);
        text-decoration: underline;
      }
      .snippet {
        margin: 0.3rem 0 0 2rem;
        font-size: 0.8rem;
        color: var(--text-muted);
        line-height: 1.4;
        display: -webkit-box;
        -webkit-line-clamp: 2;
        -webkit-box-orient: vertical;
        overflow: hidden;
      }
    `,
  ],
})
export class SourceListComponent {
  @Input() sources: Source[] = [];
}
