/**
 * Dashboard Component
 * 
 * Main dashboard view showing pipeline overview and quick stats.
 */

import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ApiService } from '../../core/services/api.service';

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './dashboard.component.html',
  styleUrl: './dashboard.component.scss'
})
export class DashboardComponent implements OnInit {
  healthStatus: any = null;
  loading = true;

  constructor(private apiService: ApiService) {}

  ngOnInit(): void {
    this.checkHealth();
  }

  checkHealth(): void {
    this.apiService.healthCheck().subscribe({
      next: (response) => {
        this.healthStatus = response;
        this.loading = false;
      },
      error: (error) => {
        console.error('Health check failed:', error);
        this.loading = false;
      }
    });
  }
}

