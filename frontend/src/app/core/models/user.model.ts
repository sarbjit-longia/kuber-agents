/**
 * User model interfaces
 */

export interface User {
  id: string;
  email: string;
  full_name: string | null;
  is_active: boolean;
  is_superuser: boolean;
  subscription_tier: string;
  max_active_pipelines: number;
  subscription_expires_at: string | null;
  telegram_enabled: boolean;
  telegram_chat_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface UserCreate {
  email: string;
  password: string;
  full_name?: string;
}

export interface UserUpdate {
  full_name?: string;
  password?: string;
}

export interface UserLogin {
  email: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface SubscriptionInfo {
  tier: string;
  max_active_pipelines: number;
  current_active_pipelines: number;
  total_pipelines: number;
  pipelines_remaining: number;
  available_signals: string[];
  subscription_expires_at: string | null;
  is_limit_enforced: boolean;
}
