import { Injectable, signal } from "@angular/core";

@Injectable({ providedIn: "root" })
export class SettingsService {
  readonly units = signal<"metric" | "imperial">("metric");
  readonly dateFormat = signal<"iso" | "local">("iso");
}
