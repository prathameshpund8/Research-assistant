import { Component, EventEmitter, Input, Output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';

/** Query box + submit button. Disabled while a run is in progress. */
@Component({
  selector: 'app-research-input',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <form class="input-card" (ngSubmit)="submit()">
      <label class="label" for="query">Research topic</label>
      <div class="row">
        <input
          id="query"
          name="query"
          type="text"
          class="query"
          [(ngModel)]="query"
          [disabled]="running"
          placeholder="e.g. The impact of large language models on software testing"
          autocomplete="off"
        />
        <button class="btn" type="submit" [disabled]="running || !query.trim()">
          {{ running ? 'Researching…' : 'Research' }}
        </button>
      </div>
      <div class="examples" *ngIf="!running">
        <span>Try:</span>
        <button type="button" class="chip" (click)="useExample(ex)" *ngFor="let ex of examples">
          {{ ex }}
        </button>
      </div>
    </form>
  `,
  styles: [
    `
      .input-card {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 14px;
        padding: 1.25rem 1.5rem;
        box-shadow: var(--shadow);
      }
      .label {
        display: block;
        font-size: 0.8rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: var(--text-muted);
        margin-bottom: 0.5rem;
      }
      .row {
        display: flex;
        gap: 0.75rem;
      }
      .query {
        flex: 1;
        padding: 0.85rem 1rem;
        border: 1px solid var(--border);
        border-radius: 10px;
        background: var(--bg);
        color: var(--text);
        font-size: 1rem;
        outline: none;
        transition: border-color 0.15s;
      }
      .query:focus {
        border-color: var(--accent);
      }
      .btn {
        padding: 0.85rem 1.5rem;
        border: none;
        border-radius: 10px;
        background: var(--accent);
        color: #fff;
        font-weight: 600;
        font-size: 1rem;
        cursor: pointer;
        transition: background 0.15s, opacity 0.15s;
        white-space: nowrap;
      }
      .btn:hover:not(:disabled) {
        background: var(--accent-strong);
      }
      .btn:disabled {
        opacity: 0.55;
        cursor: not-allowed;
      }
      .examples {
        margin-top: 0.85rem;
        display: flex;
        flex-wrap: wrap;
        gap: 0.5rem;
        align-items: center;
        font-size: 0.85rem;
        color: var(--text-muted);
      }
      .chip {
        border: 1px solid var(--border);
        background: var(--bg);
        color: var(--text-muted);
        border-radius: 999px;
        padding: 0.3rem 0.75rem;
        font-size: 0.8rem;
        cursor: pointer;
      }
      .chip:hover {
        border-color: var(--accent);
        color: var(--accent);
      }
    `,
  ],
})
export class ResearchInputComponent {
  @Input() running = false;
  @Output() research = new EventEmitter<string>();

  query = '';
  examples = [
    'Health benefits of intermittent fasting',
    'How CRISPR gene editing works',
    'State of fusion energy research',
  ];

  submit(): void {
    const q = this.query.trim();
    if (q && !this.running) {
      this.research.emit(q);
    }
  }

  useExample(ex: string): void {
    this.query = ex;
  }
}
