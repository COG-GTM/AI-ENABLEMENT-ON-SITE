import { signal } from "@angular/core";
import { TestBed } from "@angular/core/testing";
import { provideHttpClient } from "@angular/common/http";
import { HttpTestingController, provideHttpClientTesting } from "@angular/common/http/testing";
import { ActivatedRoute, convertToParamMap, provideRouter } from "@angular/router";
import { describe, expect, it } from "vitest";
import { of } from "rxjs";
import { RequestDetailComponent } from "./request-detail.component";
import { RequestListComponent } from "./request-list.component";
import { RequestService } from "./request.service";
import { StatusBadgeComponent } from "./status-badge.component";
import type { ServiceRequest } from "./types";

const request: ServiceRequest = {
  id: "REQ-101",
  title: "Replace drive belt",
  type: "repair",
  priority: "standard",
  status: "open",
  serialNumber: "EQ-2048",
  justification: "Scheduled repair",
  createdAt: "2026-10-20T09:00:00.000Z"
};

describe("RequestListComponent", () => {
  it("filters and sorts requests from the service", async () => {
    await TestBed.configureTestingModule({
      imports: [RequestListComponent],
      providers: [
        provideRouter([]),
        { provide: RequestService, useValue: { requests: signal([request, { ...request, id: "REQ-102", title: "Inspect panel", createdAt: "2026-10-21T09:00:00.000Z" }]) } }
      ]
    }).compileComponents();
    const fixture = TestBed.createComponent(RequestListComponent);
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain("Replace drive belt");
    fixture.componentInstance.filter.setValue("panel");
    await new Promise((resolve) => setTimeout(resolve, 180));
    expect(fixture.componentInstance.visible().map((item) => item.id)).toEqual(["REQ-102"]);
    fixture.componentInstance.filter.setValue("");
    fixture.componentInstance.sort.setValue("oldest");
    await new Promise((resolve) => setTimeout(resolve, 180));
    expect(fixture.componentInstance.visible()[0].id).toBe("REQ-101");
  });

  it("uses a provided request input", async () => {
    await TestBed.configureTestingModule({
      imports: [RequestListComponent],
      providers: [provideRouter([]), { provide: RequestService, useValue: { requests: signal([]) } }]
    }).compileComponents();
    const fixture = TestBed.createComponent(RequestListComponent);
    fixture.componentRef.setInput("requests", [request]);
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain("Replace drive belt");
  });
});

describe("RequestDetailComponent", () => {
  async function renderDetail(id: string, items: ServiceRequest[]) {
    await TestBed.configureTestingModule({
      imports: [RequestDetailComponent],
      providers: [
        provideRouter([]),
        { provide: ActivatedRoute, useValue: { paramMap: of(convertToParamMap({ id })) } },
        { provide: RequestService, useValue: { requests: signal(items) } }
      ]
    }).compileComponents();
    const fixture = TestBed.createComponent(RequestDetailComponent);
    fixture.detectChanges();
    return fixture;
  }

  it("shows the selected request and optional fields", async () => {
    const fixture = await renderDetail("REQ-101", [request]);
    expect(fixture.nativeElement.textContent).toContain("EQ-2048");
    expect(fixture.nativeElement.textContent).toContain("Scheduled repair");
  });

  it("shows a not-found state", async () => {
    const missing = await renderDetail("REQ-404", []);
    expect(missing.nativeElement.textContent).toContain("Request not found");
  });

  it("omits empty optional fields", async () => {
    const noOptionals = await renderDetail("REQ-102", [{ ...request, id: "REQ-102", serialNumber: "", justification: "" }]);
    expect(noOptionals.nativeElement.textContent).not.toContain("Serial number:");
    expect(noOptionals.nativeElement.textContent).not.toContain("Justification:");
  });
});

describe("StatusBadgeComponent", () => {
  it("renders its required status input", async () => {
    await TestBed.configureTestingModule({ imports: [StatusBadgeComponent] }).compileComponents();
    const fixture = TestBed.createComponent(StatusBadgeComponent);
    fixture.componentRef.setInput("status", "open");
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain("open");
  });
});

describe("RequestService", () => {
  it("loads the shared fixture and adds a new request", async () => {
    await TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()]
    }).compileComponents();
    const service = TestBed.inject(RequestService);
    const http = TestBed.inject(HttpTestingController);
    service.load();
    http.expectOne("/requests.json").flush([request]);
    expect(service.requests()).toEqual([request]);
    service.add({
      title: "Inspect valve",
      type: "inspection",
      priority: "standard",
      serialNumber: "",
      justification: ""
    });
    expect(service.requests()).toHaveLength(2);
    expect(service.requests()[0].title).toBe("Inspect valve");
    expect(service.requests()[0].status).toBe("open");
    http.verify();
  });
});
