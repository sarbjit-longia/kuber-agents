/**
 * Cost Estimation Service
 *
 * Frontend-only cost estimation for LLM agents.
 * Fetches model pricing once, then computes estimates locally
 * (no backend round-trips) as the user types.
 */
import { Injectable } from '@angular/core';
import { Subject } from 'rxjs';
import { ApiService } from './api.service';

export interface ModelPricing {
  model_id: string;
  display_name: string;
  provider: string;
  cost_per_1m_input_tokens: number;
  cost_per_1m_output_tokens: number;
  cost_per_1m_cached_tokens: number;
}

export interface LLMCostEstimate {
  inputCost: number;
  outputCost: number;
  totalLLMCost: number;
  inputTokens: number;
  outputTokens: number;
}

/**
 * Estimated output tokens per agent type.
 * Output size is roughly fixed regardless of prompt length:
 *  - strategy_agent: long analysis + full trade plan (~2048 tokens)
 *  - bias_agent: moderate analysis with bias direction (~1536 tokens)
 *  - risk_manager_agent: structured position sizing response (~1024 tokens)
 *  - default for any other LLM agent: 1024 tokens
 */
const ESTIMATED_OUTPUT_TOKENS: Record<string, number> = {
  strategy_agent: 2048,
  bias_agent: 1536,
  risk_manager_agent: 1024,
};

@Injectable({ providedIn: 'root' })
export class CostEstimationService {
  private pricingMap = new Map<string, ModelPricing>();
  private loaded = false;

  /** Emits once when pricing data has been fetched successfully. */
  pricingLoaded$ = new Subject<void>();

  constructor(private api: ApiService) {}

  /** Fetch pricing from backend once; subsequent calls are no-ops. */
  loadPricing(): void {
    if (this.loaded) return;
    this.loaded = true;
    this.api.get<ModelPricing[]>('/api/v1/agents/models/pricing').subscribe({
      next: (models) => {
        this.pricingMap.clear();
        for (const m of models) {
          this.pricingMap.set(m.model_id, m);
        }
        this.pricingLoaded$.next();
      },
      error: (err) => {
        console.error('Failed to load model pricing', err);
        this.loaded = false; // allow retry
      },
    });
  }

  /** Whether pricing data is available. */
  get isLoaded(): boolean {
    return this.pricingMap.size > 0;
  }

  /** ~4 chars per token heuristic */
  estimateTokenCount(text: string): number {
    if (!text) return 0;
    return Math.ceil(text.length / 4);
  }

  /** Return cached pricing for a model_id (or undefined). */
  getModelPricing(modelId: string): ModelPricing | undefined {
    return this.pricingMap.get(modelId);
  }

  /**
   * Compute an LLM cost estimate entirely on the frontend.
   *
   * @param promptText  User-written instructions / prompt
   * @param modelId     Selected LLM model id (e.g. "gpt-4o")
   * @param agentType   Agent type key (e.g. "strategy_agent")
   */
  estimateLLMCost(
    promptText: string,
    modelId: string,
    agentType: string
  ): LLMCostEstimate {
    const zero: LLMCostEstimate = {
      inputCost: 0,
      outputCost: 0,
      totalLLMCost: 0,
      inputTokens: 0,
      outputTokens: 0,
    };

    const outputTokens = ESTIMATED_OUTPUT_TOKENS[agentType];
    if (!outputTokens) return zero; // non-LLM agent

    const pricing = this.pricingMap.get(modelId);
    if (!pricing) return zero;

    const inputTokens = this.estimateTokenCount(promptText);

    const inputCost = (inputTokens / 1_000_000) * pricing.cost_per_1m_input_tokens;
    const outputCost = (outputTokens / 1_000_000) * pricing.cost_per_1m_output_tokens;

    return {
      inputCost,
      outputCost,
      totalLLMCost: inputCost + outputCost,
      inputTokens,
      outputTokens,
    };
  }
}
