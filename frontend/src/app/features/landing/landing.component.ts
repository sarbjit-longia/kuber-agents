/**
 * Landing Page Component
 *
 * Marketing-focused home page for onboarding new users.
 */

import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatCardModule } from '@angular/material/card';
import { NavbarComponent } from '../../core/components/navbar/navbar.component';

interface HowItWorksStep {
  step: number;
  icon: string;
  title: string;
  description: string;
}

interface Feature {
  icon: string;
  title: string;
  description: string;
}

interface Agent {
  name: string;
  icon: string;
  category: string;
  description: string;
  free: boolean;
}

interface Broker {
  name: string;
  description: string;
  icon: string;
}

interface PricingTier {
  name: string;
  price: string;
  period: string;
  highlight: boolean;
  features: string[];
  cta: string;
}

@Component({
  selector: 'app-landing',
  standalone: true,
  imports: [
    CommonModule,
    RouterLink,
    MatButtonModule,
    MatIconModule,
    MatCardModule,
    NavbarComponent
  ],
  templateUrl: './landing.component.html',
  styleUrls: ['./landing.component.scss']
})
export class LandingComponent {

  // ── How It Works ──────────────────────────────────────────────
  howItWorksSteps: HowItWorksStep[] = [
    {
      step: 1,
      icon: 'account_tree',
      title: 'Design Your Pipeline',
      description: 'Select and configure AI agents in a guided pipeline builder. Define your trading strategy flow in minutes.'
    },
    {
      step: 2,
      icon: 'tune',
      title: 'Configure Agents',
      description: 'Set parameters for each agent — timeframes, risk limits, indicators — using simple forms.'
    },
    {
      step: 3,
      icon: 'link',
      title: 'Connect Your Broker',
      description: 'Link your Tradier, Alpaca, or OANDA account. Start with paper trading for risk-free testing.'
    },
    {
      step: 4,
      icon: 'play_circle',
      title: 'Go Live',
      description: 'Activate your pipeline. AI agents analyse, decide, and execute trades 24/7 while you sleep.'
    }
  ];

  // ── Features ──────────────────────────────────────────────────
  features: Feature[] = [
    {
      icon: 'psychology',
      title: 'AI-Powered Analysis',
      description: 'GPT-4 agents analyse market bias, generate strategies, and adapt to changing conditions in real time.'
    },
    {
      icon: 'account_tree',
      title: 'Visual Pipeline Builder',
      description: 'Design complex strategies with a guided step-by-step pipeline builder. No coding required.'
    },
    {
      icon: 'schedule',
      title: '24/7 Automated Execution',
      description: 'Pipelines run around the clock, executing trades and monitoring positions automatically.'
    },
    {
      icon: 'shield',
      title: 'Built-in Risk Management',
      description: 'Position sizing, bracket orders (TP & SL), and per-pipeline budget caps keep your capital protected.'
    },
    {
      icon: 'trending_up',
      title: 'Multi-Timeframe Analysis',
      description: 'Bias agents scan higher timeframes while strategy agents pinpoint entries on lower timeframes.'
    },
    {
      icon: 'attach_money',
      title: 'Transparent Pricing',
      description: 'Pay-per-use model. Track token costs per execution and stay within your budget — no surprises.'
    }
  ];

  // ── Agent Showcase ────────────────────────────────────────────
  agents: Agent[] = [
    {
      name: 'Time Trigger',
      icon: 'schedule',
      category: 'trigger',
      description: 'Kick off pipelines on a cron schedule or at market open/close.',
      free: true
    },
    {
      name: 'Market Data',
      icon: 'candlestick_chart',
      category: 'data',
      description: 'Fetch real-time OHLCV candles across any timeframe.',
      free: true
    },
    {
      name: 'Bias Analysis',
      icon: 'psychology',
      category: 'analysis',
      description: 'AI determines bullish / bearish / neutral bias using multi-timeframe analysis.',
      free: false
    },
    {
      name: 'Strategy Generator',
      icon: 'auto_fix_high',
      category: 'analysis',
      description: 'GPT-4 produces actionable BUY / SELL / HOLD signals with entry, TP & SL.',
      free: false
    },
    {
      name: 'Risk Manager',
      icon: 'shield',
      category: 'risk',
      description: 'Validates position size, enforces max drawdown, and checks open exposure.',
      free: true
    },
    {
      name: 'Trade Manager',
      icon: 'swap_horiz',
      category: 'execution',
      description: 'Executes bracket orders via your broker and monitors fills in real time.',
      free: true
    }
  ];

  // ── Supported Brokers ─────────────────────────────────────────
  brokers: Broker[] = [
    {
      name: 'Tradier',
      description: 'US equities & options with native bracket (OTOCO) orders.',
      icon: 'account_balance'
    },
    {
      name: 'Alpaca',
      description: 'Commission-free US stock trading with bracket order support.',
      icon: 'trending_up'
    },
    {
      name: 'OANDA',
      description: 'Forex & CFD trading with 70+ currency pairs.',
      icon: 'currency_exchange'
    }
  ];

  // ── Pricing ───────────────────────────────────────────────────
  pricingTiers: PricingTier[] = [
    {
      name: 'Free',
      price: '$0',
      period: 'forever',
      highlight: false,
      features: [
        '$10 free AI credits',
        'Unlimited pipeline designs',
        'Paper trading on all brokers',
        'Free agents (Trigger, Data, Risk, Trade)',
        'Community support'
      ],
      cta: 'Get Started'
    },
    {
      name: 'Pro',
      price: '$29',
      period: '/month',
      highlight: true,
      features: [
        'Everything in Free',
        '$50 AI credits/month included',
        'Premium agents (Bias, Strategy)',
        'Live trading enabled',
        'Priority support',
        'Advanced analytics dashboard'
      ],
      cta: 'Start Free Trial'
    },
    {
      name: 'Enterprise',
      price: 'Custom',
      period: '',
      highlight: false,
      features: [
        'Everything in Pro',
        'Unlimited AI credits',
        'Custom agent development',
        'Dedicated infrastructure',
        'SLA & uptime guarantees',
        'White-glove onboarding'
      ],
      cta: 'Contact Us'
    }
  ];
}
