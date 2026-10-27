import { HttpClient } from "@angular/common/http";
import { Injectable, inject, signal } from "@angular/core";
import type { ServiceRequest } from "./types";

@Injectable({ providedIn: "root" })
export class RequestService {
  private readonly http = inject(HttpClient);
  readonly requests = signal<ServiceRequest[]>([]);

  load(): void {
    this.http.get<ServiceRequest[]>("/requests.json").subscribe((items) => this.requests.set(items));
  }

  add(input: Omit<ServiceRequest, "id" | "status" | "createdAt">): void {
    this.requests.update((items) => [{
      ...input,
      id: `REQ-${Date.now()}`,
      status: "open",
      createdAt: new Date().toISOString()
    }, ...items]);
  }
}
