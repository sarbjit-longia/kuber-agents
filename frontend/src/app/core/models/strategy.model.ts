export type StrategyVisibility = 'private' | 'public';
export type StrategyPublicationStatus = 'draft' | 'pending_review' | 'published' | 'rejected';

export interface Strategy {
  id: string;
  user_id: string;
  source_pipeline_id?: string;
  title: string;
  slug: string;
  summary?: string;
  visibility: StrategyVisibility;
  publication_status: StrategyPublicationStatus;
  category?: string;
  style?: string;
  difficulty?: string;
  tags: string[];
  markets: string[];
  timeframes: string[];
  risk_notes?: string;
  body_markdown: string;
  normalized_spec: Record<string, unknown>;
  current_version: number;
  published_version: number;
  use_count: number;
  vote_count: number;
  review_notes?: string;
  submitted_at?: string;
  published_at?: string;
  created_at: string;
  updated_at: string;
  has_voted: boolean;
  is_runnable: boolean;
}

export interface StrategyListResponse {
  strategies: Strategy[];
  total: number;
}

export interface StrategyCreate {
  title: string;
  summary?: string;
  visibility: StrategyVisibility;
  category?: string;
  style?: string;
  difficulty?: string;
  tags?: string[];
  markets?: string[];
  timeframes?: string[];
  risk_notes?: string;
  body_markdown?: string;
  normalized_spec?: Record<string, unknown>;
  source_pipeline_id?: string;
}

export interface StrategyUpdate extends Partial<StrategyCreate> {}

export interface StrategyVoteResponse {
  vote_count: number;
  has_voted: boolean;
}
