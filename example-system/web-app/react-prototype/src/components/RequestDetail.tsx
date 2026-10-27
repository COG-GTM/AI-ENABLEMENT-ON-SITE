import { Link, useParams } from "react-router-dom";
import type { ServiceRequest } from "../types";
import { StatusBadge } from "./StatusBadge";

export function RequestDetail({ requests }: { requests: ServiceRequest[] }) {
  const { id } = useParams();
  const request = requests.find((item) => item.id === id);
  if (!request) return <section className="panel"><h2>Request not found</h2><Link to="/">Back to requests</Link></section>;
  return (
    <section className="panel" data-testid="request-detail">
      <h2>{request.title}</h2>
      <p>Request ID: {request.id}</p>
      <p>Type: {request.type}</p>
      <p>Priority: {request.priority}</p>
      {request.serialNumber && <p>Serial number: {request.serialNumber}</p>}
      {request.justification && <p>Justification: {request.justification}</p>}
      <StatusBadge status={request.status} />
      <p><Link to="/">Back to requests</Link></p>
    </section>
  );
}
