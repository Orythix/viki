import { useCallback, useState } from "react";

const API_KEY = import.meta.env.VITE_LAB_API_KEY ?? "dev-lab-change-me";
const ROLE = import.meta.env.VITE_LAB_ROLE ?? "lab_admin";

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      "X-Lab-API-Key": API_KEY,
      "X-Lab-Role": ROLE,
      ...(init?.headers || {}),
    },
  });
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json() as Promise<T>;
}

type Summary = {
  metrics?: Record<string, number>;
  resources?: Record<string, unknown>;
  alerts?: Array<Record<string, unknown>>;
  recent_tool_events?: Array<{ id: string; ts: number; payload: Record<string, unknown> }>;
  ts?: number;
};

export default function App() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [audit, setAudit] = useState<unknown>(null);
  const [harnessInj, setHarnessInj] = useState<unknown>(null);
  const [harnessJb, setHarnessJb] = useState<unknown>(null);
  const [harnessTools, setHarnessTools] = useState<unknown>(null);
  const [analyzeInput, setAnalyzeInput] = useState("What is SSRF?");
  const [analyzeOut, setAnalyzeOut] = useState<unknown>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const loadCore = useCallback(async () => {
    setError(null);
    try {
      const [s, a] = await Promise.all([
        api<Summary>("/api/v1/monitoring/summary?audit_limit=60"),
        api<{ items: unknown[] }>("/api/v1/audit?limit=40"),
      ]);
      setSummary(s);
      setAudit(a);
    } catch (e) {
      setError(String(e));
    }
  }, []);

  const runHarness = useCallback(async () => {
    setError(null);
    setBusy(true);
    try {
      const [i, j, t] = await Promise.all([
        api("/api/v1/security/harness/injection"),
        api("/api/v1/security/harness/jailbreak"),
        api("/api/v1/security/harness/tools"),
      ]);
      setHarnessInj(i);
      setHarnessJb(j);
      setHarnessTools(t);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }, []);

  const runAnalyze = useCallback(async () => {
    setError(null);
    setBusy(true);
    try {
      const out = await api("/api/v1/security/analyze", {
        method: "POST",
        body: JSON.stringify({ message: analyzeInput }),
      });
      setAnalyzeOut(out);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }, [analyzeInput]);

  return (
    <div className="lab-shell">
      <header className="lab-header">
        <h1>AI Security Learning Lab</h1>
        <p className="lab-lede">
          Local defensive research dashboard. API on <code>:8000</code>; Vite proxies{" "}
          <code>/api</code>. Bind Docker to <code>127.0.0.1</code> only.
        </p>
        <div className="lab-actions">
          <button type="button" onClick={loadCore} disabled={busy}>
            Refresh monitoring &amp; audit
          </button>
          <button type="button" onClick={runHarness} disabled={busy}>
            Run test harnesses
          </button>
        </div>
      </header>

      {error && (
        <div className="lab-error" role="alert">
          {error}
        </div>
      )}

      <section className="lab-panel" aria-labelledby="overview-heading">
        <h2 id="overview-heading">Overview</h2>
        {summary ? (
          <div className="lab-grid">
            <div>
              <h3>Request counters</h3>
              <pre className="lab-pre">{JSON.stringify(summary.metrics, null, 2)}</pre>
            </div>
            <div>
              <h3>Host resources</h3>
              <pre className="lab-pre">{JSON.stringify(summary.resources, null, 2)}</pre>
            </div>
          </div>
        ) : (
          <p className="lab-muted">Load data with &quot;Refresh monitoring &amp; audit&quot;.</p>
        )}
      </section>

      <section className="lab-panel" aria-labelledby="alerts-heading">
        <h2 id="alerts-heading">Security alerts</h2>
        {summary?.alerts && summary.alerts.length > 0 ? (
          <ul className="lab-alerts">
            {summary.alerts.map((a, i) => (
              <li key={`${String(a.ts)}-${i}`}>
                <span className={`lab-badge lab-badge-${String(a.level)}`}>{String(a.level)}</span>{" "}
                <strong>{String(a.summary)}</strong>
                <pre className="lab-pre lab-pre-tight">{JSON.stringify(a.detail, null, 2)}</pre>
              </li>
            ))}
          </ul>
        ) : (
          <p className="lab-muted">No derived alerts yet (blocked chats / failed tools appear here).</p>
        )}
      </section>

      <section className="lab-panel" aria-labelledby="tools-heading">
        <h2 id="tools-heading">Recent tool executions</h2>
        {summary?.recent_tool_events && summary.recent_tool_events.length > 0 ? (
          <table className="lab-table">
            <thead>
              <tr>
                <th>Time</th>
                <th>Tool</th>
                <th>OK</th>
                <th>Output chars</th>
              </tr>
            </thead>
            <tbody>
              {summary.recent_tool_events.map((row) => (
                <tr key={row.id}>
                  <td>{new Date(row.ts * 1000).toLocaleString()}</td>
                  <td>{String(row.payload.tool ?? "")}</td>
                  <td>{String(row.payload.ok ?? "")}</td>
                  <td>{String(row.payload.output_chars ?? "")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="lab-muted">No tool rows in the recent audit window.</p>
        )}
      </section>

      <section className="lab-panel" aria-labelledby="harness-heading">
        <h2 id="harness-heading">Defensive test harnesses</h2>
        <p className="lab-muted">
          Safe regression strings only — no weaponized jailbreak payloads shipped in-repo.
        </p>
        <div className="lab-grid">
          <div>
            <h3>Injection suite</h3>
            <pre className="lab-pre">{JSON.stringify(harnessInj, null, 2)}</pre>
          </div>
          <div>
            <h3>Policy-boundary suite</h3>
            <pre className="lab-pre">{JSON.stringify(harnessJb, null, 2)}</pre>
          </div>
          <div>
            <h3>Tool / SSRF policy checks</h3>
            <pre className="lab-pre">{JSON.stringify(harnessTools, null, 2)}</pre>
          </div>
        </div>
      </section>

      <section className="lab-panel" aria-labelledby="analyze-heading">
        <h2 id="analyze-heading">Adversarial prompt analysis</h2>
        <p className="lab-muted">
          Combines sanitizer + injection heuristic + memory-store hygiene (no LLM call).
        </p>
        <div className="lab-analyze">
          <label htmlFor="analyze-prompt">Sample prompt</label>
          <textarea
            id="analyze-prompt"
            rows={3}
            value={analyzeInput}
            onChange={(e) => setAnalyzeInput(e.target.value)}
            disabled={busy}
          />
          <button type="button" onClick={runAnalyze} disabled={busy}>
            Analyze
          </button>
        </div>
        {analyzeOut != null ? (
          <pre className="lab-pre">{JSON.stringify(analyzeOut, null, 2)}</pre>
        ) : null}
      </section>

      <section className="lab-panel" aria-labelledby="audit-heading">
        <h2 id="audit-heading">Raw audit (recent)</h2>
        <pre className="lab-pre">{JSON.stringify(audit, null, 2)}</pre>
      </section>
    </div>
  );
}
