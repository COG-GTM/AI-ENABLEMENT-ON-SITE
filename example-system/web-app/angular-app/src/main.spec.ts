import { describe, expect, it } from "vitest";
import { signal } from "@angular/core";
import { ComponentFixture, TestBed } from "@angular/core/testing";
import { provideRouter } from "@angular/router";
import { vi } from "vitest";
import { AppComponent } from "./app.component";
import { routes } from "./app.routes";
import { RequestService } from "./request.service";

describe("application routes", () => {
  it("provides list, form, and parameterized detail routes", () => {
    expect(routes.map((route) => route.path)).toEqual(["", "requests/new", "requests/:id", "**"]);
  });

  it("loads request data and renders default settings", async () => {
    const load = vi.fn();
    await TestBed.configureTestingModule({
      imports: [AppComponent],
      providers: [
        provideRouter([]),
        { provide: RequestService, useValue: { load, loadError: signal("Request list could not be loaded.") } }
      ]
    }).compileComponents();
    const fixture: ComponentFixture<AppComponent> = TestBed.createComponent(AppComponent);
    fixture.detectChanges();
    expect(load).toHaveBeenCalledOnce();
    expect(fixture.nativeElement.textContent).toContain("metric · iso dates");
    expect(fixture.nativeElement.querySelector('[role="alert"]')?.textContent).toBe("Request list could not be loaded.");
  });
});
