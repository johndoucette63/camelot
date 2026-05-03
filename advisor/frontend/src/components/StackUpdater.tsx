import { useEffect, useState } from "react";

interface StackInfo {
  key: string;
  label: string;
  host: string;
  warning: string | null;
  running: boolean;
  last_status: "running" | "success" | "failed" | "timeout" | null;
  last_started_at: string | null;
  last_finished_at: string | null;
}

interface UpdateRun {
  id: number;
  stack_key: string;
  status: "running" | "success" | "failed" | "timeout";
  output: string;
  exit_code: number | null;
  error: string | null;
  started_at: string;
  finished_at: string | null;
}

const LIST_POLL_INTERVAL = 5_000;
const RUN_POLL_INTERVAL = 3_000;

export function StackUpdater() {
  const [stacks, setStacks] = useState<StackInfo[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [confirmKey, setConfirmKey] = useState<string | null>(null);
  const [openOutput, setOpenOutput] = useState<string | null>(null);
  const [runs, setRuns] = useState<Record<string, UpdateRun | null>>({});

  async function fetchStacks() {
    try {
      const res = await fetch("/api/infra/stacks");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setStacks(data.stacks);
      setError(null);
    } catch (err) {
      setError(String(err));
    }
  }

  async function fetchLatestRun(key: string) {
    try {
      const res = await fetch(`/api/infra/stacks/${key}/runs/latest`);
      if (!res.ok) return;
      const run = (await res.json()) as UpdateRun | null;
      setRuns((prev) => ({ ...prev, [key]: run }));
    } catch {
      // ignore — list polling will surface the error
    }
  }

  async function triggerUpdate(key: string) {
    setConfirmKey(null);
    try {
      const res = await fetch(`/api/infra/stacks/${key}/update`, { method: "POST" });
      if (!res.ok) {
        const body = await res.text();
        throw new Error(body || `HTTP ${res.status}`);
      }
      const run = (await res.json()) as UpdateRun;
      setRuns((prev) => ({ ...prev, [key]: run }));
      setOpenOutput(key);
      fetchStacks();
    } catch (err) {
      setError(`Failed to start update: ${err}`);
    }
  }

  useEffect(() => {
    fetchStacks();
    const id = setInterval(fetchStacks, LIST_POLL_INTERVAL);
    return () => clearInterval(id);
  }, []);

  // While any stack is running, poll its latest run for live output.
  useEffect(() => {
    const runningKeys = stacks.filter((s) => s.running).map((s) => s.key);
    if (runningKeys.length === 0) return;
    const id = setInterval(() => {
      runningKeys.forEach(fetchLatestRun);
    }, RUN_POLL_INTERVAL);
    return () => clearInterval(id);
  }, [stacks]);

  // When a stack transitions running → done, the cached run row is still
  // the initial 'running' snapshot from the POST response. Refetch once
  // so the output panel shows the final status + tail.
  useEffect(() => {
    for (const s of stacks) {
      const cached = runs[s.key];
      if (!s.running && cached?.status === "running") {
        fetchLatestRun(s.key);
      }
    }
  }, [stacks]);

  // When user opens output panel, fetch latest run for that stack.
  useEffect(() => {
    if (openOutput && !runs[openOutput]) {
      fetchLatestRun(openOutput);
    }
  }, [openOutput]);

  const grouped: Record<string, StackInfo[]> = {};
  for (const s of stacks) {
    (grouped[s.host] ||= []).push(s);
  }

  const confirmStack = stacks.find((s) => s.key === confirmKey) || null;

  return (
    <div>
      <h2 className="text-lg font-semibold text-gray-800 mb-3">Stack Updates</h2>
      <p className="text-xs text-gray-500 mb-4">
        Runs <code>docker compose pull &amp;&amp; up -d &amp;&amp; image prune -f</code> on the
        target host. Pinned image tags (e.g. <code>gluetun:v3.40.0</code>) won't move — pull
        re-fetches the same tag.
      </p>

      {error && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded text-red-700 text-sm">
          {error}
        </div>
      )}

      {Object.entries(grouped).map(([host, hostStacks]) => (
        <div key={host} className="mb-6">
          <div className="text-xs uppercase tracking-wide text-gray-500 mb-2">{host}</div>
          <div className="border border-gray-200 rounded overflow-hidden">
            {hostStacks.map((stack, idx) => {
              const run = runs[stack.key];
              const isOpen = openOutput === stack.key;
              return (
                <div
                  key={stack.key}
                  className={idx > 0 ? "border-t border-gray-200" : ""}
                >
                  <div className="flex items-center justify-between px-4 py-3 bg-white">
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium text-gray-900 truncate">
                        {stack.label}
                      </div>
                      <div className="text-xs text-gray-500 mt-0.5">
                        <LastRunSummary stack={stack} />
                      </div>
                    </div>
                    <div className="flex items-center gap-2 ml-4">
                      <button
                        type="button"
                        onClick={() => setOpenOutput(isOpen ? null : stack.key)}
                        className="text-xs text-gray-600 hover:text-gray-900 underline"
                      >
                        {isOpen ? "Hide output" : "Show output"}
                      </button>
                      <button
                        type="button"
                        onClick={() => setConfirmKey(stack.key)}
                        disabled={stack.running}
                        className="px-3 py-1.5 text-sm rounded bg-blue-600 text-white hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed"
                      >
                        {stack.running ? "Updating…" : "Update"}
                      </button>
                    </div>
                  </div>
                  {isOpen && (
                    <div className="px-4 py-3 bg-gray-50 border-t border-gray-200">
                      {run ? (
                        <RunOutput run={run} />
                      ) : (
                        <p className="text-xs text-gray-500 italic">No runs yet for this stack.</p>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      ))}

      {confirmStack && (
        <ConfirmDialog
          stack={confirmStack}
          onCancel={() => setConfirmKey(null)}
          onConfirm={() => triggerUpdate(confirmStack.key)}
        />
      )}
    </div>
  );
}

function LastRunSummary({ stack }: { stack: StackInfo }) {
  if (stack.running) {
    return <span className="text-blue-600">Update in progress…</span>;
  }
  if (!stack.last_status || !stack.last_finished_at) {
    return <span>No updates run yet</span>;
  }
  const finished = parseBackendDate(stack.last_finished_at);
  const ago = relativeTime(finished);
  const color =
    stack.last_status === "success"
      ? "text-green-600"
      : stack.last_status === "failed" || stack.last_status === "timeout"
        ? "text-red-600"
        : "text-gray-600";
  return (
    <span>
      Last run: <span className={color}>{stack.last_status}</span> · {ago}
    </span>
  );
}

function RunOutput({ run }: { run: UpdateRun }) {
  return (
    <div>
      <div className="text-xs text-gray-600 mb-2">
        Run #{run.id} · status: <strong>{run.status}</strong>
        {run.exit_code !== null && <> · exit {run.exit_code}</>}
        {run.error && <> · {run.error}</>}
      </div>
      <pre className="text-xs font-mono bg-white border border-gray-200 rounded p-2 max-h-96 overflow-auto whitespace-pre-wrap">
        {run.output || (run.status === "running" ? "(waiting for output…)" : "(no output)")}
      </pre>
    </div>
  );
}

function ConfirmDialog({
  stack,
  onCancel,
  onConfirm,
}: {
  stack: StackInfo;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl max-w-md w-full mx-4 p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-2">Update {stack.label}?</h3>
        <p className="text-sm text-gray-700 mb-3">
          This will pull new images and recreate containers on <strong>{stack.host}</strong>. Volumes
          are preserved.
        </p>
        {stack.warning && (
          <div className="mb-4 p-3 bg-yellow-50 border border-yellow-200 rounded text-xs text-yellow-900">
            {stack.warning}
          </div>
        )}
        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 rounded"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            className="px-4 py-2 text-sm bg-blue-600 text-white rounded hover:bg-blue-700"
          >
            Update
          </button>
        </div>
      </div>
    </div>
  );
}

// Backend emits naive UTC ISO strings (e.g. "2026-05-03T22:44:12.866602").
// Without a tz suffix the browser interprets them as local time — append
// `Z` so they're parsed as UTC.
function parseBackendDate(iso: string): Date {
  return new Date(/[zZ]|[+-]\d{2}:?\d{2}$/.test(iso) ? iso : iso + "Z");
}

function relativeTime(date: Date): string {
  const seconds = Math.max(0, Math.floor((Date.now() - date.getTime()) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}
