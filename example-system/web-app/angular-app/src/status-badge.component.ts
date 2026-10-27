import { Component, input } from "@angular/core";

@Component({
  selector: "app-status-badge",
  standalone: true,
  template: `<span class="status" data-testid="status-badge">{{ status() }}</span>`
})
export class StatusBadgeComponent {
  readonly status = input.required<string>();
}
