import { Component, OnInit, inject } from "@angular/core";
import { RouterLink, RouterOutlet } from "@angular/router";
import { SettingsService } from "./settings.service";
import { RequestService } from "./request.service";

@Component({
  selector: "app-root",
  standalone: true,
  imports: [RouterLink, RouterOutlet],
  template: `
    <main class="app-shell">
      <header class="site-header">
        <div><p class="eyebrow">Equipment services</p><h1>Service request workspace</h1></div>
        <p data-testid="settings-summary">{{ settings.units() }} · {{ settings.dateFormat() }} dates</p>
      </header>
      <nav aria-label="Request navigation">
        <a routerLink="/">Requests</a>
        <a routerLink="/requests/new">New request</a>
      </nav>
      @if (requests.loadError()) { <p role="alert">{{ requests.loadError() }}</p> }
      <router-outlet />
    </main>
  `
})
export class AppComponent implements OnInit {
  readonly settings = inject(SettingsService);
  readonly requests = inject(RequestService);

  ngOnInit(): void {
    this.requests.load();
  }
}
