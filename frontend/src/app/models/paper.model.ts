// Types mirroring the backend IEEE paper schemas.

export interface Author {
  name: string;
  department?: string;
  organization?: string;
  city?: string;
  email?: string;
}

export interface PaperSection {
  heading: string;
  body: string;
}

export interface Reference {
  number: number;
  source_id: string;
  text: string;
  url: string;
}

export interface FlaggedPassage {
  section: string;
  passage: string;
  source_id: string;
  similarity: number;
}

export interface OriginalityReport {
  score: number;
  flagged: FlaggedPassage[];
  rewritten: number;
  method: string;
}

export interface VerificationReport {
  total_claims: number;
  supported_claims: number;
  unsupported_removed: number;
  notes: string[];
}

export interface PaperResult {
  paper_id: string;
  topic: string;
  details: string;
  status: 'running' | 'completed' | 'error';
  title: string;
  authors: Author[];
  abstract: string;
  keywords: string[];
  sections: PaperSection[];
  references: Reference[];
  originality: OriginalityReport;
  verification: VerificationReport;
  paper_markdown: string;
  rounds_used: number;
  error?: string | null;
}
