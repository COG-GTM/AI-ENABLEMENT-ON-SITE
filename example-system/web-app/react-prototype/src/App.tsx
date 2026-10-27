import { Link, Route, Routes } from "react-router-dom";
import { SettingsProvider, useSettings } from "./SettingsContext";
import { RequestForm } from "./components/RequestForm";
import { RequestList } from "./components/RequestList";
import { RequestDetail } from "./components/RequestDetail";
import { useRequests } from "./useRequests";

// walkthrough:react-router:start
function Workspace() {
  const { requests, addRequest, loadError } = useRequests();
  const settings = useSettings();
  return (
    <main className="app-shell">
      <header className="site-header">
        <div><p className="eyebrow">Equipment services</p><h1>Service request workspace</h1></div>
        <p data-testid="settings-summary">{settings.units} · {settings.dateFormat} dates</p>
      </header>
      <nav aria-label="Request navigation">
        <Link to="/">Requests</Link>
        <Link to="/requests/new">New request</Link>
      </nav>
      {loadError && <p role="alert">{loadError}</p>}
      <Routes>
        <Route path="/" element={<RequestList requests={requests} />} />
        <Route path="/requests/new" element={<RequestForm onCreate={addRequest} />} />
        <Route path="/requests/:id" element={<RequestDetail requests={requests} />} />
      </Routes>
    </main>
  );
}

export function App() {
  return <SettingsProvider><Workspace /></SettingsProvider>;
}
// walkthrough:react-router:end
