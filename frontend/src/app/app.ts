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
import { PaperInputComponent, PaperRequestInput } from './components/paper-input/paper-input.component';
import { PaperViewComponent } from './components/paper-view/paper-view.component';
import { PaperResult } from './models/paper.model';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [
    CommonModule,
    ResearchInputComponent,
    AgentTimelineComponent,
    ReportViewComponent,
    SourceListComponent,
    PaperInputComponent,
    PaperViewComponent,
  ],
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App implements OnDestroy {
  private readonly research = inject(ResearchService);

  mode: 'report' | 'paper' = 'report';
  running = false;
  errorMessage = '';
  query = '';
  timeline: AgentTimelineItem[] = this.freshTimeline();
  result: ResearchResult | null = null;
  paper: PaperResult | null = null;
  paperDocxUrl = '';

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

  setMode(mode: 'report' | 'paper'): void {
    if (this.running || this.mode === mode) return;
    this.mode = mode;
    this.reset();
    this.paper = null;
  }

  /** Kick off an IEEE paper generation run. */
  async onGeneratePaper(req: PaperRequestInput): Promise<void> {
    this.reset();
    this.paper = null;
    this.query = req.topic;
    this.running = true;
    try {
      const { paper_id } = await this.research.startPaper(req.topic, req.details, req.authors);
      this.paperDocxUrl = this.research.paperDocxUrl(paper_id);
      this.disposeStream = this.research.streamPaperProgress(paper_id, {
        onEvent: (ev) => this.applyEvent(ev),
        onDone: () => this.loadPaper(paper_id),
        onError: (msg) => this.fail(msg),
      });
    } catch {
      this.fail('Could not start paper generation. Is the backend running?');
    }
  }

  private loadPaper(paperId: string): void {
    this.research.getPaper(paperId).subscribe({
      next: (res) => {
        this.paper = res;
        this.running = false;
        if (res.status === 'error') {
          this.errorMessage = res.error || 'Paper generation failed.';
        } else {
          this.timeline.forEach((t) => {
            if (t.status === 'active' || t.status === 'idle') t.status = 'done';
          });
        }
      },
      error: () => this.fail('Could not load the generated paper.'),
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
    return this.running || this.result !== null || this.paper !== null || this.errorMessage !== '';
  }

  ngOnDestroy(): void {
    this.disposeStream?.();
  }
}
