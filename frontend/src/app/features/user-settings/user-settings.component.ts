import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatDividerModule } from '@angular/material/divider';
import { Subject, takeUntil } from 'rxjs';
import { NavbarComponent } from '../../core/components/navbar/navbar.component';
import { FooterComponent } from '../../shared/components/footer/footer.component';
import { AuthService } from '../../core/services/auth.service';
import { UserService, TelegramConfig } from '../../core/services/user.service';
import { User, SubscriptionInfo } from '../../core/models/user.model';

interface NavSection {
  id: 'profile' | 'subscription' | 'notifications';
  label: string;
  icon: string;
}

@Component({
  selector: 'app-user-settings',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatCardModule,
    MatFormFieldModule,
    MatInputModule,
    MatButtonModule,
    MatIconModule,
    MatSlideToggleModule,
    MatProgressSpinnerModule,
    MatSnackBarModule,
    MatDividerModule,
    NavbarComponent,
    FooterComponent
  ],
  templateUrl: './user-settings.component.html',
  styleUrls: ['./user-settings.component.scss']
})
export class UserSettingsComponent implements OnInit, OnDestroy {
  private destroy$ = new Subject<void>();

  // Section navigation
  activeSection: 'profile' | 'subscription' | 'notifications' = 'profile';
  sections: NavSection[] = [
    { id: 'profile', label: 'Profile', icon: 'person' },
    { id: 'subscription', label: 'Subscription', icon: 'card_membership' },
    { id: 'notifications', label: 'Notifications', icon: 'notifications' }
  ];

  // Profile state
  user: User | null = null;
  editingName = false;
  editNameValue = '';
  isSavingName = false;
  showPasswordChange = false;
  newPassword = '';
  confirmPassword = '';
  isSavingPassword = false;

  // Subscription state
  subscription: SubscriptionInfo | null = null;
  isLoadingSubscription = false;

  // Telegram state (preserved from original)
  botToken = '';
  chatId = '';
  telegramConfig: TelegramConfig | null = null;
  isLoading = false;
  isTesting = false;
  isSaving = false;
  isDeleting = false;
  showTokenInput = false;

  constructor(
    private authService: AuthService,
    private userService: UserService,
    private snackBar: MatSnackBar
  ) {}

  ngOnInit(): void {
    this.authService.currentUser$
      .pipe(takeUntil(this.destroy$))
      .subscribe(user => {
        this.user = user;
        if (user && !this.editingName) {
          this.editNameValue = user.full_name || '';
        }
      });
    this.loadSubscriptionInfo();
    this.loadTelegramConfig();
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }

  // ── Section navigation ─────────────────────────────────────
  setSection(section: 'profile' | 'subscription' | 'notifications'): void {
    this.activeSection = section;
  }

  // ── Profile methods ────────────────────────────────────────
  startEditName(): void {
    this.editingName = true;
    this.editNameValue = this.user?.full_name || '';
  }

  cancelEditName(): void {
    this.editingName = false;
    this.editNameValue = this.user?.full_name || '';
  }

  saveName(): void {
    if (!this.editNameValue.trim()) return;
    this.isSavingName = true;
    this.userService.updateProfile({ full_name: this.editNameValue.trim() }).subscribe({
      next: () => {
        this.editingName = false;
        this.isSavingName = false;
        this.authService.getCurrentUser().subscribe(user => {
          this.user = user;
        });
        this.snackBar.open('Name updated successfully', 'Close', {
          duration: 3000,
          panelClass: ['success-snackbar']
        });
      },
      error: () => {
        this.isSavingName = false;
        this.snackBar.open('Failed to update name', 'Close', {
          duration: 3000,
          panelClass: ['error-snackbar']
        });
      }
    });
  }

  togglePasswordChange(): void {
    this.showPasswordChange = !this.showPasswordChange;
    if (!this.showPasswordChange) {
      this.newPassword = '';
      this.confirmPassword = '';
    }
  }

  get passwordsMatch(): boolean {
    return this.newPassword === this.confirmPassword;
  }

  get passwordValid(): boolean {
    return this.newPassword.length >= 8 && this.passwordsMatch;
  }

  savePassword(): void {
    if (!this.passwordValid) return;
    this.isSavingPassword = true;
    this.userService.updateProfile({ password: this.newPassword }).subscribe({
      next: () => {
        this.isSavingPassword = false;
        this.showPasswordChange = false;
        this.newPassword = '';
        this.confirmPassword = '';
        this.snackBar.open('Password updated successfully', 'Close', {
          duration: 3000,
          panelClass: ['success-snackbar']
        });
      },
      error: () => {
        this.isSavingPassword = false;
        this.snackBar.open('Failed to update password', 'Close', {
          duration: 3000,
          panelClass: ['error-snackbar']
        });
      }
    });
  }

  // ── Subscription methods ───────────────────────────────────
  loadSubscriptionInfo(): void {
    this.isLoadingSubscription = true;
    this.userService.getSubscriptionInfo().subscribe({
      next: (info) => {
        this.subscription = info;
        this.isLoadingSubscription = false;
      },
      error: () => {
        this.isLoadingSubscription = false;
      }
    });
  }

  get usagePercent(): number {
    if (!this.subscription) return 0;
    return Math.round(
      (this.subscription.current_active_pipelines / this.subscription.max_active_pipelines) * 100
    );
  }

  // ── Telegram methods (preserved from original) ─────────────
  loadTelegramConfig(): void {
    this.isLoading = true;
    this.userService.getTelegramConfig().subscribe({
      next: (config) => {
        this.telegramConfig = config;
        this.chatId = config.chat_id || '';
        this.isLoading = false;
      },
      error: (error) => {
        console.error('Failed to load Telegram config:', error);
        this.snackBar.open('Failed to load Telegram configuration', 'Close', {
          duration: 3000,
          panelClass: ['error-snackbar']
        });
        this.isLoading = false;
      }
    });
  }

  testConnection(): void {
    if (!this.botToken || !this.chatId) {
      this.snackBar.open('Please enter both Bot Token and Chat ID', 'Close', {
        duration: 3000,
        panelClass: ['error-snackbar']
      });
      return;
    }

    this.isTesting = true;
    this.userService.testTelegramConnection(this.botToken, this.chatId).subscribe({
      next: () => {
        this.snackBar.open('Test message sent! Check your Telegram', 'Close', {
          duration: 5000,
          panelClass: ['success-snackbar']
        });
        this.isTesting = false;
      },
      error: (error) => {
        const errorMsg = error.error?.detail || 'Test failed. Please check your credentials.';
        this.snackBar.open(errorMsg, 'Close', {
          duration: 5000,
          panelClass: ['error-snackbar']
        });
        this.isTesting = false;
      }
    });
  }

  saveTelegramConfig(): void {
    if (!this.botToken || !this.chatId) {
      this.snackBar.open('Please enter both Bot Token and Chat ID', 'Close', {
        duration: 3000,
        panelClass: ['error-snackbar']
      });
      return;
    }

    this.isSaving = true;
    this.userService.updateTelegramConfig(this.botToken, this.chatId, true).subscribe({
      next: (config) => {
        this.telegramConfig = config;
        this.snackBar.open('Telegram configuration saved successfully', 'Close', {
          duration: 3000,
          panelClass: ['success-snackbar']
        });
        this.showTokenInput = false;
        this.botToken = '';
        this.isSaving = false;
      },
      error: (error) => {
        const errorMsg = error.error?.detail || 'Failed to save configuration';
        this.snackBar.open(errorMsg, 'Close', {
          duration: 5000,
          panelClass: ['error-snackbar']
        });
        this.isSaving = false;
      }
    });
  }

  deleteTelegramConfig(): void {
    if (!confirm('Are you sure you want to remove your Telegram configuration?')) {
      return;
    }

    this.isDeleting = true;
    this.userService.deleteTelegramConfig().subscribe({
      next: () => {
        this.telegramConfig = {
          enabled: false,
          chat_id: null,
          is_configured: false
        };
        this.botToken = '';
        this.chatId = '';
        this.showTokenInput = false;
        this.snackBar.open('Telegram configuration removed', 'Close', {
          duration: 3000
        });
        this.isDeleting = false;
      },
      error: (error) => {
        console.error('Failed to delete Telegram config:', error);
        this.snackBar.open('Failed to remove configuration', 'Close', {
          duration: 3000,
          panelClass: ['error-snackbar']
        });
        this.isDeleting = false;
      }
    });
  }

  toggleTokenInput(): void {
    this.showTokenInput = !this.showTokenInput;
    if (!this.showTokenInput) {
      this.botToken = '';
    }
  }
}
