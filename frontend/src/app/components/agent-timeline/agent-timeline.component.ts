import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';

import { AgentTimelineItem } from '../../models/research.model';

/** Live vertical timeline showing each agent activating in sequence. */
@Component({
  selector: 'app-agent-timeline',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="timeline">
      <div
        class="node"
        *ngFor="let item of items; let last = last"
        [class.is-active]="item.status === 'active'"
        [class.is-done]="item.status === 'done'"
        [class.is-error]="item.status === 'error'"
      >
        <div class="rail">
          <div class="dot">
            <span class="spinner" *ngIf="item.status === 'active'"></span>
            <span class="tick" *ngIf="item.status === 'done'">✓</span>
            <span class="bang" *ngIf="item.status === 'error'">!</span>
          </div>
          <div class="line" *ngIf="!last"></div>
        </div>
        <div class="content">
          <div class="head">
            <span class="name">{{ item.label }}</span>
            <span class="badge">{{ item.status }}</span>
          </div>
          <div class="desc">{{ item.description }}</div>
          <div class="msg" *ngIf="item.lastMessage">{{ item.lastMessage }}</div>
        </div>
      </div>
    </div>
  `,
  styles: [
    `
      .timeline {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 14px;
        padding: 1.5rem;
        box-shadow: var(--shadow);
      }
      .node {
        display: flex;
        gap: 1rem;
      }
      .rail {
        display: flex;
        flex-direction: column;
        align-items: center;
      }
      .dot {
        width: 30px;
        height: 30px;
        border-radius: 50%;
        border: 2px solid var(--border);
        background: var(--bg);
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 0.85rem;
        color: var(--text-muted);
        flex-shrink: 0;
        transition: all 0.2s;
      }
      .line {
        width: 2px;
        flex: 1;
        min-height: 28px;
        background: var(--border);
        margin: 2px 0;
      }
      .content {
        padding-bottom: 1.25rem;
      }
      .head {
        display: flex;
        align-items: center;
        gap: 0.6rem;
      }
      .name {
        font-weight: 600;
        color: var(--text);
      }
      .badge {
        font-size: 0.68rem;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        padding: 0.1rem 0.45rem;
        border-radius: 6px;
        background: var(--bg);
        border: 1px solid var(--border);
        color: var(--text-muted);
      }
      .desc {
        font-size: 0.85rem;
        color: var(--text-muted);
        margin-top: 0.15rem;
      }
      .msg {
        font-size: 0.85rem;
        color: var(--text);
        margin-top: 0.4rem;
        background: var(--bg);
        border-left: 3px solid var(--accent);
        padding: 0.45rem 0.7rem;
        border-radius: 0 8px 8px 0;
      }

      /* States */
      .is-active .dot {
        border-color: var(--accent);
        color: var(--accent);
      }
      .is-active .name {
        color: var(--accent);
      }
      .is-active .badge {
        border-color: var(--accent);
        color: var(--accent);
      }
      .is-done .dot {
        border-color: var(--success);
        background: var(--success);
        color: #fff;
      }
      .is-error .dot {
        border-color: var(--danger);
        background: var(--danger);
        color: #fff;
      }
      .is-error .badge {
        border-color: var(--danger);
        color: var(--danger);
      }

      .spinner {
        width: 14px;
        height: 14px;
        border: 2px solid var(--accent);
        border-top-color: transparent;
        border-radius: 50%;
        animation: spin 0.7s linear infinite;
      }
      @keyframes spin {
        to {
          transform: rotate(360deg);
        }
      }
    `,
  ],
})
export class AgentTimelineComponent {
  @Input() items: AgentTimelineItem[] = [];
}
