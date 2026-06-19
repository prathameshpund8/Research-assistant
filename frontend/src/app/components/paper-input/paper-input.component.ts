import { Component, EventEmitter, Input, Output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';

import { Author } from '../../models/paper.model';

export interface PaperRequestInput {
  topic: string;
  details: string;
  authors: Author[];
}

/** Input form for the IEEE paper generator: topic + scope details + author. */
@Component({
  selector: 'app-paper-input',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <form class="card" (ngSubmit)="submit()">
      <label class="label" for="topic">Paper topic</label>
      <input
        id="topic"
        class="field"
        type="text"
        [(ngModel)]="topic"
        name="topic"
        [disabled]="running"
        placeholder="e.g. Use of AI in the Mechanical Field"
        autocomplete="off"
      />

      <label class="label" for="details">Scope / specifics <span>(optional)</span></label>
      <textarea
        id="details"
        class="field area"
        [(ngModel)]="details"
        name="details"
        [disabled]="running"
        rows="3"
        placeholder="Focus areas, sub-topics, angle, target venue… helps tailor the paper."
      ></textarea>

      <div class="authors">
        <div class="col">
          <label class="label" for="aname">Author name</label>
          <input id="aname" class="field" [(ngModel)]="authorName" name="aname"
                 [disabled]="running" placeholder="Your Name" autocomplete="off" />
        </div>
        <div class="col">
          <label class="label" for="aorg">Affiliation</label>
          <input id="aorg" class="field" [(ngModel)]="authorOrg" name="aorg"
                 [disabled]="running" placeholder="Institution / Company" autocomplete="off" />
        </div>
      </div>

      <button class="btn" type="submit" [disabled]="running || !topic.trim()">
        {{ running ? 'Generating paper…' : 'Generate IEEE Paper' }}
      </button>
      <p class="hint">
        Runs the full agent pipeline: outline → research → write → verify → originality check →
        IEEE references. Takes longer than a quick report.
      </p>
    </form>
  `,
  styles: [
    `
      .card {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 14px;
        padding: 1.25rem 1.5rem;
        box-shadow: var(--shadow);
        display: flex;
        flex-direction: column;
        gap: 0.4rem;
      }
      .label {
        font-size: 0.78rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: var(--text-muted);
        margin-top: 0.5rem;
      }
      .label span {
        text-transform: none;
        font-weight: 400;
      }
      .field {
        padding: 0.7rem 0.9rem;
        border: 1px solid var(--border);
        border-radius: 10px;
        background: var(--bg);
        color: var(--text);
        font-size: 0.95rem;
        outline: none;
        font-family: inherit;
      }
      .field:focus {
        border-color: var(--accent);
      }
      .area {
        resize: vertical;
      }
      .authors {
        display: flex;
        gap: 0.75rem;
      }
      .authors .col {
        flex: 1;
        display: flex;
        flex-direction: column;
        gap: 0.4rem;
      }
      .btn {
        margin-top: 0.9rem;
        padding: 0.85rem 1.5rem;
        border: none;
        border-radius: 10px;
        background: var(--accent);
        color: #fff;
        font-weight: 600;
        font-size: 1rem;
        cursor: pointer;
      }
      .btn:hover:not(:disabled) {
        background: var(--accent-strong);
      }
      .btn:disabled {
        opacity: 0.55;
        cursor: not-allowed;
      }
      .hint {
        font-size: 0.8rem;
        color: var(--text-muted);
        margin: 0.25rem 0 0;
      }
      @media (max-width: 560px) {
        .authors {
          flex-direction: column;
        }
      }
    `,
  ],
})
export class PaperInputComponent {
  @Input() running = false;
  @Output() generate = new EventEmitter<PaperRequestInput>();

  topic = '';
  details = '';
  authorName = '';
  authorOrg = '';

  submit(): void {
    const topic = this.topic.trim();
    if (!topic || this.running) return;
    const authors: Author[] = [
      {
        name: this.authorName.trim() || 'Anonymous Author',
        organization: this.authorOrg.trim() || 'Institution',
      },
    ];
    this.generate.emit({ topic, details: this.details.trim(), authors });
  }
}
