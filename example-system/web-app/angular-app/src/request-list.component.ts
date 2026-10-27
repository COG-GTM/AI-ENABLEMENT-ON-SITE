import { Component, computed, inject, input } from "@angular/core";
import { FormControl, ReactiveFormsModule } from "@angular/forms";
import { RouterLink } from "@angular/router";
import { toSignal } from "@angular/core/rxjs-interop";
import { debounceTime, startWith } from "rxjs";
import { RequestService } from "./request.service";
import type { ServiceRequest } from "./types";
import { StatusBadgeComponent } from "./status-badge.component";

// walkthrough:angular-list:start
@Component({
  selector: "app-request-list",
  standalone: true,
  imports: [ReactiveFormsModule, RouterLink, StatusBadgeComponent],
  template: `
    <section class="panel" data-testid="request-list">
      <h2>Service requests</h2>
      <label for="request-filter">Filter requests</label>
      <input id="request-filter" data-testid="request-filter" [formControl]="filter" />
      <label for="request-sort">Sort by date</label>
      <select id="request-sort" data-testid="request-sort" [formControl]="sort">
        <option value="newest">Newest first</option><option value="oldest">Oldest first</option>
      </select>
      @if (visible().length) {
        <ul class="request-list">
          @for (request of visible(); track request.id) {
            <li [attr.data-testid]="'request-row-' + request.id">
              <a [routerLink]="['/requests', request.id]">{{ request.title }} ({{ request.id }})</a>
              <app-status-badge [status]="request.status" />
            </li>
          }
        </ul>
      } @else { <p>No matching requests.</p> }
    </section>
  `
})
export class RequestListComponent {
  private readonly requestService = inject(RequestService);
  readonly requests = input<ServiceRequest[]>();
  readonly filter = new FormControl("", { nonNullable: true });
  readonly sort = new FormControl<"newest" | "oldest">("newest", { nonNullable: true });
  private readonly query = toSignal(this.filter.valueChanges.pipe(startWith(this.filter.value), debounceTime(150)), { initialValue: "" });
  private readonly sortOrder = toSignal(this.sort.valueChanges.pipe(startWith(this.sort.value)), { initialValue: "newest" });

  readonly visible = computed(() => {
    const rows = this.requests() ?? this.requestService.requests();
    const query = this.query().toLowerCase();
    return rows
      .filter((request) => `${request.title} ${request.id} ${request.type}`.toLowerCase().includes(query))
      .sort((left, right) => this.sortOrder() === "newest"
        ? right.createdAt.localeCompare(left.createdAt)
        : left.createdAt.localeCompare(right.createdAt));
  });
}
// walkthrough:angular-list:end
