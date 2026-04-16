import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatChipsModule } from '@angular/material/chips';

import { NavbarComponent } from '../../core/components/navbar/navbar.component';
import { FooterComponent } from '../../shared/components/footer/footer.component';
import { StrategyService } from '../../core/services/strategy.service';
import { Strategy } from '../../core/models/strategy.model';

@Component({
  selector: 'app-strategies-marketplace',
  standalone: true,
  imports: [
    CommonModule,
    RouterLink,
    FormsModule,
    MatButtonModule,
    MatCardModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatProgressSpinnerModule,
    MatChipsModule,
    NavbarComponent,
    FooterComponent,
  ],
  templateUrl: './strategies-marketplace.component.html',
  styleUrls: ['./strategies-marketplace.component.scss'],
})
export class StrategiesMarketplaceComponent implements OnInit {
  loading = true;
  query = '';
  mostVoted: Strategy[] = [];
  mostUsed: Strategy[] = [];
  newest: Strategy[] = [];
  myStrategies: Strategy[] = [];

  constructor(private strategyService: StrategyService) {}

  ngOnInit(): void {
    this.loadAll();
  }

  loadAll(): void {
    this.loading = true;
    this.strategyService.getMarketplace('most_voted').subscribe({
      next: (response) => {
        this.mostVoted = response.strategies;
        this.strategyService.getMarketplace('most_used').subscribe({
          next: (used) => {
            this.mostUsed = used.strategies;
            this.strategyService.getMarketplace('newest').subscribe({
              next: (newest) => {
                this.newest = newest.strategies;
                this.strategyService.getMyStrategies().subscribe({
                  next: (mine) => {
                    this.myStrategies = mine.strategies.slice(0, 4);
                    this.loading = false;
                  },
                  error: () => {
                    this.loading = false;
                  }
                });
              },
              error: () => {
                this.loading = false;
              }
            });
          },
          error: () => {
            this.loading = false;
          }
        });
      },
      error: () => {
        this.loading = false;
      }
    });
  }

  get featuredCount(): number {
    return new Set([...this.mostVoted, ...this.mostUsed, ...this.newest].map(strategy => strategy.id)).size;
  }

  get privateDraftCount(): number {
    return this.myStrategies.filter(strategy => strategy.visibility === 'private').length;
  }

  search(): void {
    this.loading = true;
    this.strategyService.getMarketplace('most_voted', this.query).subscribe({
      next: (response) => {
        this.mostVoted = response.strategies;
        this.loading = false;
      },
      error: () => {
        this.loading = false;
      }
    });
  }
}
