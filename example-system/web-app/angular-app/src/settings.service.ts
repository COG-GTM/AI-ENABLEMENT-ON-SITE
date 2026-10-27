import { Injectable, signal } from "@angular/core";

// walkthrough:angular-settings:start
@Injectable({ providedIn: "root" })
export class SettingsService {
  readonly units = signal<"metric" | "imperial">("metric");
  readonly dateFormat = signal<"iso" | "local">("iso");
}
// walkthrough:angular-settings:end
