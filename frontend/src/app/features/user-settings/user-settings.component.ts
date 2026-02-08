import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTabsModule } from '@angular/material/tabs';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { UserService } from '../../core/services/user.service';

interface TelegramConfig {
  enabled: boolean;
  chat_id: string | null;
  is_configured: boolean;
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
    MatTabsModule,
    MatSlideToggleModule,
    MatProgressSpinnerModule,
    MatSnackBarModule
  ],
  templateUrl: './user-settings.component.html',
  styleUrls: ['./user-settings.component.scss']
})
export class UserSettingsComponent implements OnInit {
  botToken: string = '';
  chatId: string = '';
  telegramConfig: TelegramConfig | null = null;
  isLoading = false;
  isTesting = false;
  isSaving = false;
  isDeleting = false;
  showTokenInput = false;

  constructor(
    private userService: UserService,
    private snackBar: MatSnackBar
  ) {}

  ngOnInit(): void {
    this.loadTelegramConfig();
  }

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
      next: (response) => {
        this.snackBar.open('✅ Test message sent! Check your Telegram', 'Close', {
          duration: 5000,
          panelClass: ['success-snackbar']
        });
        this.isTesting = false;
      },
      error: (error) => {
        const errorMsg = error.error?.detail || 'Test failed. Please check your credentials.';
        this.snackBar.open(`❌ ${errorMsg}`, 'Close', {
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
        this.snackBar.open('✅ Telegram configuration saved successfully!', 'Close', {
          duration: 3000,
          panelClass: ['success-snackbar']
        });
        this.showTokenInput = false;
        this.botToken = '';  // Clear token for security
        this.isSaving = false;
      },
      error: (error) => {
        const errorMsg = error.error?.detail || 'Failed to save configuration';
        this.snackBar.open(`❌ ${errorMsg}`, 'Close', {
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
