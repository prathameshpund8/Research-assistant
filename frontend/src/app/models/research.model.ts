// Shared types mirroring the FastAPI backend's Pydantic schemas.

export type AgentName =
  | 'planner'
  | 'searcher'
  | 'summarizer'
  | 'critic'
  | 'writer'
  | 'system';

export type EventStatus = 'started' | 'progress' | 'completed' | 'error';

/** One Server-Sent Event describing an agent's activity. */
export interface ProgressEvent {
  agent: AgentName;
  status: EventStatus;
  message: string;
  data: Record<string, unknown>;
  timestamp: string;
}

export interface Source {
  id: string;
  title: string;
  url: string;
  snippet: string;
  sub_question: string;
  score: number;
}

export interface ExtractedFact {
  text: string;
  source_id: string;
}

export interface ResearchResult {
  research_id: string;
  query: string;
  status: 'running' | 'completed' | 'error';
  sub_questions: string[];
  sources: Source[];
  facts: ExtractedFact[];
  gaps: string[];
  rounds_used: number;
  report_markdown: string;
  error?: string | null;
  created_at?: string;
}

/** Ordered list of agents for rendering the timeline. */
export const AGENT_SEQUENCE: AgentName[] = [
  'planner',
  'searcher',
  'summarizer',
  'critic',
  'writer',
];

export const AGENT_LABELS: Record<AgentName, string> = {
  planner: 'Planner',
  searcher: 'Searcher',
  summarizer: 'Summarizer',
  critic: 'Critic',
  writer: 'Writer',
  system: 'System',
};

export const AGENT_DESCRIPTIONS: Record<AgentName, string> = {
  planner: 'Decomposes the topic into sub-questions',
  searcher: 'Searches the web for each sub-question',
  summarizer: 'Extracts attributed facts from sources',
  critic: 'Cross-checks claims and flags gaps',
  writer: 'Compiles the final cited report',
  system: 'Orchestration',
};

/** Per-agent UI state derived from the event stream. */
export type AgentRunStatus = 'idle' | 'active' | 'done' | 'error';

export interface AgentTimelineItem {
  agent: AgentName;
  label: string;
  description: string;
  status: AgentRunStatus;
  lastMessage: string;
  messages: string[];
}
