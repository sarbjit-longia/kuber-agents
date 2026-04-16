import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { forkJoin, of } from 'rxjs';
import { catchError } from 'rxjs/operators';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';

import { NavbarComponent } from '../../core/components/navbar/navbar.component';
import { FooterComponent } from '../../shared/components/footer/footer.component';
import { StrategyService } from '../../core/services/strategy.service';
import { Strategy } from '../../core/models/strategy.model';
import { ConfirmDialogComponent, ConfirmDialogData } from '../../shared/confirm-dialog/confirm-dialog.component';
import { AuthService } from '../../core/services/auth.service';

@Component({
  selector: 'app-my-strategies',
  standalone: true,
  imports: [
    CommonModule,
    RouterLink,
    MatButtonModule,
    MatCardModule,
    MatDialogModule,
    MatIconModule,
    MatProgressSpinnerModule,
    MatSnackBarModule,
    NavbarComponent,
    FooterComponent,
  ],
  templateUrl: './my-strategies.component.html',
  styleUrls: ['./my-strategies.component.scss'],
})
export class MyStrategiesComponent implements OnInit {
  loading = true;
  strategies: Strategy[] = [];
  adminPendingStrategies: Strategy[] = [];
  private adminEnabled = false;

  constructor(
    private strategyService: StrategyService,
    private dialog: MatDialog,
    private authService: AuthService,
    private snackBar: MatSnackBar,
  ) {}

  ngOnInit(): void {
    const cachedUser = this.authService.currentUserValue;
    if (cachedUser) {
      this.adminEnabled = !!cachedUser.is_superuser;
      this.loadStrategies();
      return;
    }

    if (!this.authService.isAuthenticated()) {
      this.loadStrategies();
      return;
    }

    this.authService.getCurrentUser().subscribe({
      next: (user) => {
        this.adminEnabled = !!user.is_superuser;
        this.loadStrategies();
      },
      error: () => {
        this.loadStrategies();
      }
    });
  }

  private loadStrategies(): void {
    forkJoin({
      mine: this.strategyService.getMyStrategies(),
      adminPending: this.isAdmin
        ? this.strategyService.getAdminPendingStrategies().pipe(catchError(() => of({ strategies: [], total: 0 })))
        : of({ strategies: [], total: 0 }),
    }).subscribe({
      next: ({ mine, adminPending }) => {
        this.strategies = mine.strategies;
        this.adminPendingStrategies = adminPending.strategies;
        this.loading = false;
      },
      error: () => {
        this.loading = false;
      }
    });
  }

  get isAdmin(): boolean {
    return this.adminEnabled;
  }

  byStatus(status: string): Strategy[] {
    if (status === 'private') {
      return this.strategies.filter(strategy => strategy.visibility === 'private' && strategy.publication_status !== 'pending_review');
    }
    if (status === 'published') {
      return this.strategies.filter(strategy => strategy.publication_status === 'published');
    }
    return this.strategies.filter(strategy => strategy.publication_status === status);
  }

  deleteStrategy(strategy: Strategy, event: Event): void {
    event.preventDefault();
    event.stopPropagation();

    const dialogRef = this.dialog.open(ConfirmDialogComponent, {
      width: '440px',
      data: {
        title: 'Delete Strategy',
        message: `Delete strategy "${strategy.title}"? This cannot be undone.`,
        confirmText: 'Delete',
        cancelText: 'Cancel',
      } as ConfirmDialogData
    });

    dialogRef.afterClosed().subscribe(confirmed => {
      if (!confirmed) {
        return;
      }

      this.strategyService.deleteStrategy(strategy.id).subscribe({
        next: () => {
          this.strategies = this.strategies.filter(item => item.id !== strategy.id);
          this.adminPendingStrategies = this.adminPendingStrategies.filter(item => item.id !== strategy.id);
        }
      });
    });
  }

  reviewStrategy(strategy: Strategy, approved: boolean, event: Event): void {
    event.preventDefault();
    event.stopPropagation();

    const actionLabel = approved ? 'Approve' : 'Reject';
    const dialogRef = this.dialog.open(ConfirmDialogComponent, {
      width: '440px',
      data: {
        title: `${actionLabel} Strategy`,
        message: `${actionLabel} strategy "${strategy.title}" for marketplace publication?`,
        confirmText: actionLabel,
        cancelText: 'Cancel',
      } as ConfirmDialogData
    });

    dialogRef.afterClosed().subscribe(confirmed => {
      if (!confirmed) {
        return;
      }

      this.strategyService.reviewStrategy(strategy.id, approved).subscribe({
        next: (updated) => {
          this.adminPendingStrategies = this.adminPendingStrategies.filter(item => item.id !== strategy.id);
          this.strategies = this.strategies.map(item => item.id === updated.id ? updated : item);
          this.snackBar.open(
            approved ? 'Strategy approved' : 'Strategy rejected',
            'Close',
            { duration: 3000 }
          );
        },
        error: () => {
          this.snackBar.open(`Failed to ${approved ? 'approve' : 'reject'} strategy`, 'Close', {
            duration: 3000,
          });
        }
      });
    });
  }
}
