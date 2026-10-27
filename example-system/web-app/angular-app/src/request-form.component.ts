import { Component, inject, signal } from "@angular/core";
import { FormControl, FormGroup, ReactiveFormsModule, Validators } from "@angular/forms";
import { RequestService } from "./request.service";
import type { Priority, RequestKind } from "./types";

@Component({
  selector: "app-request-form",
  standalone: true,
  imports: [ReactiveFormsModule],
  template: `
    <section class="panel">
      <h2>New service request</h2>
      @if (summary()) {
        <div class="error-summary" role="alert" data-testid="validation-summary">
          <strong>Review the highlighted fields</strong>
          <ul>@for (message of summary(); track message) { <li>{{ message }}</li> }</ul>
        </div>
      }
      @if (created()) { <p role="status" data-testid="form-success">Request created.</p> }
      <form [formGroup]="form" (ngSubmit)="submit()" data-testid="request-form" novalidate>
        <label for="request-title">Request title</label>
        <input id="request-title" data-testid="request-title" formControlName="title" />
        @if (showError("title")) { <p class="field-error">Enter a request title.</p> }
        <label for="request-type">Request type</label>
        <select id="request-type" data-testid="request-type" formControlName="type" (change)="updateConditionalValidation()">
          <option value="inspection">Inspection</option><option value="repair">Repair</option>
        </select>
        @if (form.controls.type.value === "repair") {
          <label for="request-serial-number">Equipment serial number</label>
          <input id="request-serial-number" data-testid="request-serial-number" formControlName="serialNumber" />
          @if (showError("serialNumber")) { <p class="field-error">Enter the equipment serial number.</p> }
        }
        <label for="request-priority">Priority</label>
        <select id="request-priority" data-testid="request-priority" formControlName="priority" (change)="updateConditionalValidation()">
          <option value="standard">Standard</option><option value="urgent">Urgent</option>
        </select>
        @if (form.controls.priority.value === "urgent") {
          <label for="request-justification">Urgency justification</label>
          <textarea id="request-justification" data-testid="request-justification" formControlName="justification"></textarea>
          @if (showError("justification")) { <p class="field-error">Urgent requests need a justification of at least 20 characters.</p> }
        }
        <button type="submit" data-testid="request-submit">Create request</button>
      </form>
    </section>
  `
})
export class RequestFormComponent {
  private readonly requests = inject(RequestService);
  readonly created = signal(false);
  readonly form = new FormGroup({
    title: new FormControl("", { nonNullable: true, validators: [Validators.required] }),
    type: new FormControl<RequestKind>("inspection", { nonNullable: true }),
    priority: new FormControl<Priority>("standard", { nonNullable: true }),
    serialNumber: new FormControl("", { nonNullable: true }),
    justification: new FormControl("", { nonNullable: true })
  });

  updateConditionalValidation(): void {
    const serial = this.form.controls.serialNumber;
    const reason = this.form.controls.justification;
    if (this.form.controls.type.value === "repair") serial.setValidators(Validators.required);
    else serial.clearValidators();
    if (this.form.controls.priority.value === "urgent") reason.setValidators([Validators.required, Validators.minLength(20)]);
    else reason.clearValidators();
    serial.updateValueAndValidity();
    reason.updateValueAndValidity();
  }

  showError(name: "title" | "serialNumber" | "justification"): boolean {
    const control = this.form.controls[name];
    return control.invalid && (control.touched || control.dirty || this.formSubmitted);
  }

  private formSubmitted = false;

  summary(): string[] {
    if (!this.formSubmitted || this.form.valid) return [];
    const messages: string[] = [];
    if (this.showError("title")) messages.push("Enter a request title.");
    if (this.form.controls.type.value === "repair" && this.showError("serialNumber")) messages.push("Enter the equipment serial number.");
    if (this.form.controls.priority.value === "urgent" && this.showError("justification")) {
      messages.push("Urgent requests need a justification of at least 20 characters.");
    }
    return messages;
  }

  submit(): void {
    this.formSubmitted = true;
    this.updateConditionalValidation();
    if (this.form.invalid) return;
    const value = this.form.getRawValue();
    this.requests.add({
      title: value.title.trim(),
      type: value.type,
      priority: value.priority,
      serialNumber: value.serialNumber.trim(),
      justification: value.justification.trim()
    });
    this.form.reset({ title: "", type: "inspection", priority: "standard", serialNumber: "", justification: "" });
    this.formSubmitted = false;
    this.created.set(true);
  }
}
