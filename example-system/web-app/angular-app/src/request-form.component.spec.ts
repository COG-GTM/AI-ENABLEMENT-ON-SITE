import { TestBed } from "@angular/core/testing";
import { signal } from "@angular/core";
import { describe, expect, it, vi } from "vitest";
import { RequestFormComponent } from "./request-form.component";
import { RequestService } from "./request.service";

describe("RequestFormComponent", () => {
  it("rejects whitespace-only fields and checks justification length after trimming", async () => {
    const add = vi.fn();
    await TestBed.configureTestingModule({
      imports: [RequestFormComponent],
      providers: [{ provide: RequestService, useValue: { add, requests: signal([]) } }]
    }).compileComponents();
    const fixture = TestBed.createComponent(RequestFormComponent);
    const component = fixture.componentInstance;
    component.form.controls.title.setValue(" \t ");
    component.form.controls.type.setValue("repair");
    component.form.controls.priority.setValue("urgent");
    component.form.controls.serialNumber.setValue("  ");
    component.form.controls.justification.setValue(" 123456789012345678 ");
    component.submit();
    expect(component.form.controls.title.invalid).toBe(true);
    expect(component.form.controls.serialNumber.invalid).toBe(true);
    expect(component.form.controls.justification.invalid).toBe(true);
    expect(add).not.toHaveBeenCalled();
  });

  it("enforces conditional fields and accepts a valid request", async () => {
    const add = vi.fn();
    await TestBed.configureTestingModule({
      imports: [RequestFormComponent],
      providers: [{ provide: RequestService, useValue: { add, requests: signal([]) } }]
    }).compileComponents();
    const fixture = TestBed.createComponent(RequestFormComponent);
    const component = fixture.componentInstance;
    fixture.detectChanges();
    expect(component.summary()).toEqual([]);
    component.form.controls.title.markAsTouched();
    component.submit();
    expect(component.summary()).toContain("Enter a request title.");
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain("Enter a request title.");

    component.form.controls.title.setValue("Repair pump");
    component.form.controls.type.setValue("repair");
    component.form.controls.priority.setValue("urgent");
    component.submit();
    fixture.detectChanges();
    expect(component.summary()).toHaveLength(2);
    expect(fixture.nativeElement.textContent).toContain("20 characters");
    component.form.controls.serialNumber.setValue("EQ-555");
    component.form.controls.justification.setValue("Urgent repair before next shift");
    component.submit();
    fixture.detectChanges();
    expect(add).toHaveBeenCalledOnce();
    expect(component.created()).toBe(true);
  });
});
