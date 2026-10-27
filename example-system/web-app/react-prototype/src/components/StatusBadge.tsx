// walkthrough:react-badge:start
export function StatusBadge({ status }: { status: string }) {
  return <span className={`status status-${status}`} data-testid="status-badge">{status}</span>;
}
// walkthrough:react-badge:end
