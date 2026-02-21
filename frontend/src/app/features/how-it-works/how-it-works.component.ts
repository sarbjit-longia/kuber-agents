/**
 * How It Works Page Component
 *
 * Detailed walkthrough of the platform for new users.
 */

import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatCardModule } from '@angular/material/card';
import { NavbarComponent } from '../../core/components/navbar/navbar.component';

interface Step {
  number: number;
  icon: string;
  title: string;
  subtitle: string;
  description: string;
  details: string[];
}

interface Agent {
  icon: string;
  name: string;
  category: string;
  description: string;
  free: boolean;
}

interface Faq {
  question: string;
  answer: string;
  open: boolean;
}

@Component({
  selector: 'app-how-it-works',
  standalone: true,
  imports: [
    CommonModule,
    RouterLink,
    MatButtonModule,
    MatIconModule,
    MatCardModule,
    NavbarComponent
  ],
  templateUrl: './how-it-works.component.html',
  styleUrls: ['./how-it-works.component.scss']
})
export class HowItWorksComponent {

  // ── Steps ────────────────────────────────────────────────────
  steps: Step[] = [
    {
      number: 1,
      icon: 'account_tree',
      title: 'Create Your Pipeline',
      subtitle: 'Guided setup. No coding required.',
      description:
        'Open the Pipeline Builder and give your strategy a name. ' +
        'A ready-made chain of five specialist agents is already wired up for you — ' +
        'Market Data → Bias → Strategy → Risk → Trade Manager — so you only need to configure each one.',
      details: [
        'Choose a trigger mode — run on a schedule or react to market signals',
        'Create a Ticker Scanner to define which symbols your pipeline monitors',
        'A readiness checklist shows exactly what\'s left to configure',
        'Save and reuse pipeline templates for different symbols or markets'
      ]
    },
    {
      number: 2,
      icon: 'tune',
      title: 'Configure Each Agent',
      subtitle: 'Click a block. Fill out the form.',
      description:
        'Click any agent in the chain to open its settings panel. ' +
        'Each agent has its own tailored form — pick timeframes, choose analysis indicators, write a custom AI prompt, ' +
        'or attach specialised trading tools.',
      details: [
        'Available analysis tools: FVG detector, market structure, RSI, MACD, Bollinger Bands, VWAP, and more',
        'Supported timeframes: 1 min, 5 min, 15 min, 1 hour, 4 hour, and daily',
        'Write natural-language prompts to personalise AI strategy behaviour',
        'Set risk parameters: max position size, drawdown limit, and daily budget cap',
        'See estimated cost per run before going live'
      ]
    },
    {
      number: 3,
      icon: 'link',
      title: 'Connect Your Broker',
      subtitle: 'Tradier · Alpaca · OANDA',
      description:
        'Enter your brokerage credentials in the Broker settings — they\'re encrypted and never stored in plain text. ' +
        'Every broker supports paper trading, so you can test risk-free before committing real capital.',
      details: [
        'Tradier — US equities & options with bracket orders (OTOCO)',
        'Alpaca — commission-free US stocks with bracket order support',
        'OANDA — 70+ forex & CFD pairs with built-in take-profit & stop-loss',
        'Switch between paper and live trading with a single toggle'
      ]
    },
    {
      number: 4,
      icon: 'play_circle',
      title: 'Activate & Monitor',
      subtitle: '24 / 7 automation.',
      description:
        'Hit "Run" to execute your pipeline immediately, or activate it for scheduled runs. ' +
        'Agents run one after another — analysing the market, generating signals, checking risk, and placing orders — ' +
        'while you monitor everything from a real-time dashboard.',
      details: [
        'Live execution dashboard with real-time status updates',
        'Every agent logs its reasoning so you can see why a trade was taken or skipped',
        'Automatic position monitoring — the Trade Manager re-checks fills and manages exits',
        'Token and cost tracking per execution — no surprise bills',
        'Pause, resume, or cancel any pipeline at any time'
      ]
    }
  ];

  // ── Pipeline walkthrough agents ──────────────────────────────
  pipelineAgents: Agent[] = [
    {
      icon: 'schedule',
      name: 'Time Trigger',
      category: 'trigger',
      description: 'Fires at a scheduled interval (e.g. every 5 minutes during market hours).',
      free: true
    },
    {
      icon: 'candlestick_chart',
      name: 'Market Data',
      category: 'data',
      description: 'Fetches live OHLCV candles across the timeframes your strategy needs.',
      free: true
    },
    {
      icon: 'psychology',
      name: 'Bias Analysis',
      category: 'analysis',
      description: 'AI determines bullish / bearish / neutral bias from higher-timeframe data.',
      free: false
    },
    {
      icon: 'auto_fix_high',
      name: 'Strategy Generator',
      category: 'analysis',
      description: 'GPT-4 produces a BUY / SELL / HOLD signal with entry, TP, and SL prices.',
      free: false
    },
    {
      icon: 'shield',
      name: 'Risk Manager',
      category: 'risk',
      description: 'Validates position size, enforces max drawdown, and checks open exposure.',
      free: true
    },
    {
      icon: 'swap_horiz',
      name: 'Trade Manager',
      category: 'execution',
      description: 'Executes a native bracket order on your broker and monitors the fill.',
      free: true
    }
  ];

  // ── FAQ ──────────────────────────────────────────────────────
  faqs: Faq[] = [
    {
      question: 'Do I need to know how to code?',
      answer:
        'Not at all. The Pipeline Builder gives you a ready-made agent chain — just click each block and fill out a simple form. ' +
        'No programming, scripting, or terminal commands required.',
      open: false
    },
    {
      question: 'Is my brokerage account safe?',
      answer:
        'Yes. Broker credentials are encrypted at rest using industry-standard encryption. ' +
        'We never store passwords in plain text, and you can revoke access from Settings at any time.',
      open: false
    },
    {
      question: 'Can I test without risking real money?',
      answer:
        'Absolutely. Every supported broker offers a paper-trading mode. You can build, test, and refine ' +
        'your pipelines with simulated capital before switching to live trading.',
      open: false
    },
    {
      question: 'How much does it cost?',
      answer:
        'Getting started is free — you receive $10 in AI credits and can use free agents (Time Trigger, Market Data, ' +
        'Risk Manager, Trade Manager) at no cost. Premium AI agents (Bias Analysis, Strategy Generator) ' +
        'consume credits on a pay-per-use basis. You can see estimated and actual costs per execution in your dashboard.',
      open: false
    },
    {
      question: 'Which brokers do you support?',
      answer:
        'Currently Tradier (US equities & options), Alpaca (commission-free US stocks), and OANDA (forex & CFDs). ' +
        'More brokers are on the roadmap.',
      open: false
    },
    {
      question: 'What happens if the AI makes a bad trade?',
      answer:
        'Every pipeline includes a Risk Manager agent that enforces your risk rules — maximum position size, drawdown limits, ' +
        'and budget caps. Bracket orders with take-profit and stop-loss levels are placed automatically to limit downside on every trade.',
      open: false
    },
    {
      question: 'What analysis tools are available?',
      answer:
        'AI agents can use a growing library of trading tools including Fair Value Gap (FVG) detection, market structure analysis, ' +
        'RSI, MACD, Bollinger Bands, VWAP, Fibonacci levels, and volume profile. You choose which tools to attach when configuring your strategy.',
      open: false
    },
    {
      question: 'What timeframes can I trade on?',
      answer:
        'The platform supports 1-minute, 5-minute, 15-minute, 1-hour, 4-hour, and daily timeframes. ' +
        'The Bias Agent analyses higher timeframes for market direction while the Strategy Agent pinpoints entries on your chosen lower timeframe.',
      open: false
    },
    {
      question: 'What is a Ticker Scanner?',
      answer:
        'A Scanner is a reusable list of ticker symbols your pipeline will monitor. You can create multiple scanners ' +
        '(e.g. "Tech Large Caps", "Forex Majors") and attach any one of them to a pipeline. ' +
        'When your pipeline runs, it cycles through the scanner\'s tickers automatically.',
      open: false
    },
    {
      question: 'How are orders executed?',
      answer:
        'The Trade Manager places bracket orders directly through your broker — a main entry order paired with a take-profit ' +
        'and a stop-loss order. This means your exits are always set the moment you enter a trade. ' +
        'Supported order types include market, limit, and bracket (Tradier OTOCO, Alpaca bracket, OANDA TP/SL).',
      open: false
    }
  ];

  toggleFaq(faq: Faq): void {
    faq.open = !faq.open;
  }
}
