import { Component, OnDestroy, inject } from '@angular/core';
import { CommonModule } from '@angular/common';

import { ResearchService } from './services/research.service';
import {
  AGENT_DESCRIPTIONS,
  AGENT_LABELS,
  AGENT_SEQUENCE,
  AgentName,
  AgentTimelineItem,
  ProgressEvent,
  ResearchResult,
} from './models/research.model';
import { ResearchInputComponent } from './components/research-input/research-input.component';
import { AgentTimelineComponent } from './components/agent-timeline/agent-timeline.component';
import { ReportViewComponent } from './components/report-view/report-view.component';
import { SourceListComponent } from './components/source-list/source-list.component';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [
    CommonModule,
    ResearchInputComponent,
    AgentTimelineComponent,
    ReportViewComponent,
    SourceListComponent,
  ],
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App implements OnDestroy {
  private readonly research = inject(ResearchService);

  running = false;
  errorMessage = '';
  query = '';
  timeline: AgentTimelineItem[] = this.freshTimeline();
  result: ResearchResult | null = null;

  private disposeStream: (() => void) | null = null;

  /** Kick off a new research run. */
  async onResearch(query: string): Promise<void> {
    this.reset();
    this.query = query;
    this.running = true;

    try {
      const { research_id } = await this.research.startResearch(query);
      this.subscribe(research_id);
    } catch {
      this.fail('Could not start research. Is the backend running?');
    }
  }

  private subscribe(researchId: string): void {
    this.disposeStream = this.research.streamProgress(researchId, {
      onEvent: (ev) => this.applyEvent(ev),
      onDone: () => this.loadResult(researchId),
      onError: (msg) => this.fail(msg),
    });
  }

  /** Update the timeline from a streamed progress event. */
  private applyEvent(ev: ProgressEvent): void {
    if (ev.agent === 'system') {
      if (ev.status === 'error') this.fail(ev.message);
      return;
    }
    const item = this.timeline.find((t) => t.agent === ev.agent);
    if (!item) return;

    item.lastMessage = ev.message;
    item.messages.push(ev.message);

    if (ev.status === 'error') {
      item.status = 'error';
    } else if (ev.status === 'completed') {
      item.status = 'done';
    } else {
      item.status = 'active';
      // Mark earlier agents in the sequence as done once a later one starts.
      const idx = AGENT_SEQUENCE.indexOf(ev.agent);
      this.timeline.forEach((t, i) => {
        if (i < idx && t.status !== 'error') t.status = 'done';
      });
    }
  }

  private loadResult(researchId: string): void {
    this.research.getResult(researchId).subscribe({
      next: (res) => {
        this.result = res;
        this.running = false;
        if (res.status === 'error') {
          this.errorMessage = res.error || 'Research failed.';
        } else {
          // Ensure every agent shows complete once we have the final report.
          this.timeline.forEach((t) => {
            if (t.status === 'active' || t.status === 'idle') t.status = 'done';
          });
        }
      },
      error: () => this.fail('Could not load the final report.'),
    });
  }

  private fail(message: string): void {
    this.errorMessage = message;
    this.running = false;
  }

  private reset(): void {
    this.disposeStream?.();
    this.disposeStream = null;
    this.errorMessage = '';
    this.result = null;
    this.timeline = this.freshTimeline();
  }

  private freshTimeline(): AgentTimelineItem[] {
    return AGENT_SEQUENCE.map((agent: AgentName) => ({
      agent,
      label: AGENT_LABELS[agent],
      description: AGENT_DESCRIPTIONS[agent],
      status: 'idle',
      lastMessage: '',
      messages: [],
    }));
  }

  get hasStarted(): boolean {
    return this.running || this.result !== null || this.errorMessage !== '';
  }

  ngOnDestroy(): void {
    this.disposeStream?.();
  }
}
