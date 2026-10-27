import { Component, inject, signal } from "@angular/core";
import { FormControl, FormGroup, ReactiveFormsModule, Validators } from "@angular/forms";
import { RequestService } from "./request.service";
import type { Priority, RequestKind } from "./types";

// walkthrough:angular-form:start
@Component({
  selector: "app-request-form",
  standalone: true,
  imports: [ReactiveFormsModule],
  template: `
    <section class="panel">
      <header class="form-header">
        <div><p class="eyebrow">Equipment services</p><h2>New service request</h2></div>
        <p>Complete the details to route this work.</p>
      </header>
      <div class="request-layout">
        <div class="request-card">
          @if (summary().length) {
            <div class="error-summary" role="alert" aria-labelledby="summary-title" data-testid="validation-summary">
              <strong id="summary-title">Review the highlighted fields</strong>
              <ul>
                @if (showError("title")) { <li><a href="#request-title">Enter a request title.</a></li> }
                @if (showError("serialNumber")) { <li><a href="#request-serial-number">Enter the equipment serial number.</a></li> }
                @if (showError("justification")) { <li><a href="#request-justification">Urgent requests need a justification of at least 20 characters.</a></li> }
              </ul>
            </div>
          }
          @if (created()) { <p role="status" data-testid="form-success">Request created.</p> }
          <form [formGroup]="form" (ngSubmit)="submit()" data-testid="request-form" novalidate>
            <div class="form-fields">
              <div class="field wide">
                <label for="request-title">Request title</label>
                <input id="request-title" data-testid="request-title" formControlName="title"
                  [attr.aria-invalid]="showError('title')"
                  [attr.aria-describedby]="showError('title') ? 'title-hint title-error' : 'title-hint'" />
                <p class="hint" id="title-hint">Use a short description of the work.</p>
                @if (showError("title")) { <p class="field-error" id="title-error">Enter a request title.</p> }
              </div>
              <div class="field">
                <label for="request-type">Request type</label>
                <select id="request-type" data-testid="request-type" formControlName="type" (change)="updateConditionalValidation()">
                  <option value="inspection">Inspection</option><option value="repair">Repair</option>
                </select>
              </div>
              <div class="field">
                <label for="request-priority">Priority</label>
                <select id="request-priority" data-testid="request-priority" formControlName="priority" (change)="updateConditionalValidation()">
                  <option value="standard">Standard</option><option value="urgent">Urgent</option>
                </select>
              </div>
              @if (form.controls.type.value === "repair") {
                <div class="field wide">
                  <label for="request-serial-number">Equipment serial number <span aria-hidden="true">*</span></label>
                  <input id="request-serial-number" data-testid="request-serial-number" formControlName="serialNumber"
                    [attr.aria-invalid]="showError('serialNumber')"
                    [attr.aria-describedby]="showError('serialNumber') ? 'serial-hint serial-error' : 'serial-hint'" />
                  <p class="hint" id="serial-hint">Enter the serial number shown on the equipment plate.</p>
                  @if (showError("serialNumber")) { <p class="field-error" id="serial-error">Enter the equipment serial number.</p> }
                </div>
              }
              @if (form.controls.priority.value === "urgent") {
                <div class="field wide">
                  <label for="request-justification">Why is this urgent? <span aria-hidden="true">*</span></label>
                  <textarea id="request-justification" data-testid="request-justification" formControlName="justification"
                    [attr.aria-invalid]="showError('justification')"
                    [attr.aria-describedby]="showError('justification') ? 'reason-hint reason-error' : 'reason-hint'"></textarea>
                  <p class="hint" id="reason-hint">At least 20 characters. This helps the service team prioritize.</p>
                  @if (showError("justification")) { <p class="field-error" id="reason-error">Urgent requests need a justification of at least 20 characters.</p> }
                </div>
              }
              <div class="wide"><button type="submit" data-testid="request-submit">Create request</button></div>
            </div>
          </form>
        </div>
        <section class="request-card form-aside" aria-labelledby="submission-notes">
          <h3 id="submission-notes">Before you submit</h3>
          <ul><li>Repair requests need an equipment serial number.</li><li>Urgent requests need a clear reason of 20 or more characters.</li><li>Your draft stays in this local example.</li></ul>
        </section>
      </div>
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
// walkthrough:angular-form:end
