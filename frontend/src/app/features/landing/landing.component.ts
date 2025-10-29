/**
 * Landing Page Component
 */

import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatCardModule } from '@angular/material/card';
import { NavbarComponent } from '../../core/components/navbar/navbar.component';

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
  features = [
    {
      icon: 'psychology',
      title: 'AI-Powered Agents',
      description: 'Leverage cutting-edge AI agents powered by GPT-4 for market analysis and strategy generation.'
    },
    {
      icon: 'account_tree',
      title: 'Visual Pipeline Builder',
      description: 'Design complex trading strategies with an intuitive drag-and-drop interface. No coding required.'
    },
    {
      icon: 'schedule',
      title: 'Automated Execution',
      description: 'Set it and forget it. Your pipelines run 24/7, executing trades based on your strategy.'
    },
    {
      icon: 'shield',
      title: 'Risk Management',
      description: 'Built-in risk controls ensure your capital is protected with position sizing and stop losses.'
    },
    {
      icon: 'trending_up',
      title: 'Multi-Timeframe Analysis',
      description: 'Analyze markets across multiple timeframes for better entry and exit decisions.'
    },
    {
      icon: 'attach_money',
      title: 'Cost Transparent',
      description: 'Pay only for what you use. Track costs per execution and stay within your budget.'
    }
  ];

  agents = [
    { name: 'Time Trigger', type: 'Schedule', free: true },
    { name: 'Market Data', type: 'Real-time', free: true },
    { name: 'Bias Analysis', type: 'AI Agent', free: false },
    { name: 'Strategy Generator', type: 'AI Agent', free: false },
    { name: 'Risk Manager', type: 'Rules', free: true },
    { name: 'Trade Executor', type: 'Live/Paper', free: true }
  ];
}

