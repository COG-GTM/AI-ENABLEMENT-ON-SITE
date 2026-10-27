import { Component, computed, inject } from "@angular/core";
import { ActivatedRoute, RouterLink } from "@angular/router";
import { toSignal } from "@angular/core/rxjs-interop";
import { map } from "rxjs";
import { RequestService } from "./request.service";
import { StatusBadgeComponent } from "./status-badge.component";

@Component({
  selector: "app-request-detail",
  standalone: true,
  imports: [RouterLink, StatusBadgeComponent],
  template: `
    @if (request(); as item) {
      <section class="panel" data-testid="request-detail">
        <h2>{{ item.title }}</h2>
        <p>Request ID: {{ item.id }}</p><p>Type: {{ item.type }}</p><p>Priority: {{ item.priority }}</p>
        @if (item.serialNumber) { <p>Serial number: {{ item.serialNumber }}</p> }
        @if (item.justification) { <p>Justification: {{ item.justification }}</p> }
        <app-status-badge [status]="item.status" />
        <p><a routerLink="/">Back to requests</a></p>
      </section>
    } @else {
      <section class="panel" data-testid="request-detail"><h2>Request not found</h2><a routerLink="/">Back to requests</a></section>
    }
  `
})
export class RequestDetailComponent {
  private readonly service = inject(RequestService);
  private readonly id = toSignal(inject(ActivatedRoute).paramMap.pipe(map((params) => params.get("id"))), { initialValue: null });
  readonly request = computed(() => this.service.requests().find((item) => item.id === this.id()));
}
