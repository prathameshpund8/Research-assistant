import { Injectable, NgZone, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, firstValueFrom } from 'rxjs';

import { environment } from '../../environments/environment';
import { ProgressEvent, ResearchResult } from '../models/research.model';
import { Author, PaperResult } from '../models/paper.model';

/** Callbacks for a live research stream. */
export interface ResearchStreamHandlers {
  onEvent: (event: ProgressEvent) => void;
  onDone: () => void;
  onError: (message: string) => void;
}

/**
 * Talks to the FastAPI backend: starts a research job (REST) and streams the
 * per-agent progress events (Server-Sent Events via the native EventSource).
 */
@Injectable({ providedIn: 'root' })
export class ResearchService {
  private readonly http = inject(HttpClient);
  private readonly zone = inject(NgZone);
  private readonly base = environment.apiBaseUrl;

  /** Start a research job; resolves with the new research_id. */
  startResearch(query: string): Promise<{ research_id: string }> {
    return firstValueFrom(
      this.http.post<{ research_id: string }>(`${this.base}/api/research`, { query }),
    );
  }

  /** Fetch the final result (Markdown report + structured sources/facts). */
  getResult(researchId: string): Observable<ResearchResult> {
    return this.http.get<ResearchResult>(`${this.base}/api/research/${researchId}`);
  }

  // --- IEEE paper endpoints -------------------------------------------
  startPaper(topic: string, details: string, authors: Author[]): Promise<{ paper_id: string }> {
    return firstValueFrom(
      this.http.post<{ paper_id: string }>(`${this.base}/api/paper`, { topic, details, authors }),
    );
  }

  getPaper(paperId: string): Observable<PaperResult> {
    return this.http.get<PaperResult>(`${this.base}/api/paper/${paperId}`);
  }

  /** URL the browser can hit directly to download the .docx. */
  paperDocxUrl(paperId: string): string {
    return `${this.base}/api/paper/${paperId}/docx`;
  }

  streamPaperProgress(paperId: string, handlers: ResearchStreamHandlers): () => void {
    return this.openStream(`${this.base}/api/paper/${paperId}/stream`, handlers);
  }

  /**
   * Open an SSE connection for live agent progress. Returns a disposer that
   * closes the stream. EventSource callbacks run outside Angular, so we hop
   * back into the zone to keep change detection working.
   */
  streamProgress(researchId: string, handlers: ResearchStreamHandlers): () => void {
    return this.openStream(`${this.base}/api/research/${researchId}/stream`, handlers);
  }

  private openStream(url: string, handlers: ResearchStreamHandlers): () => void {
    const source = new EventSource(url);

    source.addEventListener('progress', (ev: MessageEvent) => {
      this.zone.run(() => {
        try {
          handlers.onEvent(JSON.parse(ev.data) as ProgressEvent);
        } catch {
          /* ignore malformed frames */
        }
      });
    });

    source.addEventListener('done', () => {
      this.zone.run(() => {
        source.close();
        handlers.onDone();
      });
    });

    // 'ping' frames are heartbeats — intentionally ignored.

    source.onerror = () => {
      // EventSource auto-reconnects; if the job already finished the 'done'
      // handler closed the stream, so only surface a real connection failure.
      if (source.readyState === EventSource.CLOSED) {
        this.zone.run(() => handlers.onError('Connection to the research stream was lost.'));
      }
    };

    return () => source.close();
  }
}
