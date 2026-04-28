import { Component } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { BetaBannerComponent } from './core/components/beta-banner/beta-banner.component';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [RouterOutlet, BetaBannerComponent],
  templateUrl: './app.component.html',
  styleUrl: './app.component.scss'
})
export class AppComponent {
  title = 'Clover Charts';
}
