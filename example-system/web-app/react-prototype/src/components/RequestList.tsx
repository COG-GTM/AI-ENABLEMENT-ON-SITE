import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useDebounce } from "../useDebounce";
import type { ServiceRequest } from "../types";
import { StatusBadge } from "./StatusBadge";

export function RequestList({ requests }: { requests: ServiceRequest[] }) {
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<"newest" | "oldest">("newest");
  const settledQuery = useDebounce(query);
  const visible = useMemo(() => requests
    .filter((request) => `${request.title} ${request.id} ${request.type}`.toLowerCase().includes(settledQuery.toLowerCase()))
    .sort((left, right) => sort === "newest"
      ? right.createdAt.localeCompare(left.createdAt)
      : left.createdAt.localeCompare(right.createdAt)), [requests, settledQuery, sort]);

  return (
    <section className="panel" data-testid="request-list">
      <h2>Service requests</h2>
      <label htmlFor="request-filter">Filter requests</label>
      <input id="request-filter" data-testid="request-filter" value={query} onChange={(event) => setQuery(event.target.value)} />
      <label htmlFor="request-sort">Sort by date</label>
      <select id="request-sort" data-testid="request-sort" value={sort} onChange={(event) => setSort(event.target.value as "newest" | "oldest")}>
        <option value="newest">Newest first</option>
        <option value="oldest">Oldest first</option>
      </select>
      {visible.length ? (
        <ul className="request-list">{visible.map((request) => (
          <li key={request.id} data-testid={`request-row-${request.id}`}>
            <Link to={`/requests/${request.id}`}>{request.title} ({request.id})</Link>
            <StatusBadge status={request.status} />
          </li>
        ))}</ul>
      ) : <p>No matching requests.</p>}
    </section>
  );
}
