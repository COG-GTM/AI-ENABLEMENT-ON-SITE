import { useReducer, useState, type FormEvent } from "react";
import type { Priority, RequestKind, ServiceRequest } from "../types";

type Errors = Partial<Record<"title" | "serialNumber" | "justification", string>>;
type ErrorAction = { type: "set"; errors: Errors } | { type: "clear" };

function errorReducer(_state: Errors, action: ErrorAction): Errors {
  return action.type === "clear" ? {} : action.errors;
}

export function RequestForm({ onCreate }: { onCreate: (request: Omit<ServiceRequest, "id" | "status" | "createdAt">) => void }) {
  const [title, setTitle] = useState("");
  const [kind, setKind] = useState<RequestKind>("inspection");
  const [priority, setPriority] = useState<Priority>("standard");
  const [serialNumber, setSerialNumber] = useState("");
  const [justification, setJustification] = useState("");
  const [errors, dispatch] = useReducer(errorReducer, {});
  const [created, setCreated] = useState(false);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const next: Errors = {};
    if (!title.trim()) next.title = "Enter a request title.";
    if (kind === "repair" && !serialNumber.trim()) next.serialNumber = "Enter the equipment serial number.";
    if (priority === "urgent" && justification.trim().length < 20) {
      next.justification = "Urgent requests need a justification of at least 20 characters.";
    }
    dispatch({ type: "set", errors: next });
    setCreated(false);
    if (Object.keys(next).length) return;
    onCreate({ title: title.trim(), type: kind, priority, serialNumber: serialNumber.trim(), justification: justification.trim() });
    dispatch({ type: "clear" });
    setCreated(true);
    setTitle("");
    setSerialNumber("");
    setJustification("");
    setKind("inspection");
    setPriority("standard");
  }

  return (
    <section className="panel">
      <h2>New service request</h2>
      {Object.keys(errors).length > 0 && (
        <div className="error-summary" role="alert" data-testid="validation-summary">
          <strong>Review the highlighted fields</strong>
          <ul>{Object.values(errors).map((message) => <li key={message}>{message}</li>)}</ul>
        </div>
      )}
      {created && <p role="status" data-testid="form-success">Request created.</p>}
      <form data-testid="request-form" onSubmit={submit} noValidate>
        <label htmlFor="request-title">Request title</label>
        <input id="request-title" data-testid="request-title" value={title} onChange={(event) => setTitle(event.target.value)} />
        {errors.title && <p className="field-error">{errors.title}</p>}

        <label htmlFor="request-type">Request type</label>
        <select id="request-type" data-testid="request-type" value={kind} onChange={(event) => setKind(event.target.value as RequestKind)}>
          <option value="inspection">Inspection</option>
          <option value="repair">Repair</option>
        </select>
        {kind === "repair" && (
          <>
            <label htmlFor="request-serial-number">Equipment serial number</label>
            <input id="request-serial-number" data-testid="request-serial-number" value={serialNumber} onChange={(event) => setSerialNumber(event.target.value)} />
            {errors.serialNumber && <p className="field-error">{errors.serialNumber}</p>}
          </>
        )}

        <label htmlFor="request-priority">Priority</label>
        <select id="request-priority" data-testid="request-priority" value={priority} onChange={(event) => setPriority(event.target.value as Priority)}>
          <option value="standard">Standard</option>
          <option value="urgent">Urgent</option>
        </select>
        {priority === "urgent" && (
          <>
            <label htmlFor="request-justification">Urgency justification</label>
            <textarea id="request-justification" data-testid="request-justification" value={justification} onChange={(event) => setJustification(event.target.value)} />
            {errors.justification && <p className="field-error">{errors.justification}</p>}
          </>
        )}
        <button type="submit" data-testid="request-submit">Create request</button>
      </form>
    </section>
  );
}
