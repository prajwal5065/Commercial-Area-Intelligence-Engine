import { useEffect, useRef, useState } from "react";
import { api, type SessionStatus } from "../lib/api";

/**
 * Creates (or resumes) a session against the FastAPI backend and polls
 * /sessions/{id}/status on an interval - the direct equivalent of the
 * original Streamlit app's st.rerun() loop while a background thread runs.
 *
 * The session id is kept in memory only for this component tree (not
 * localStorage - artifacts/browser storage restrictions aside, a fresh
 * session per page load matches the original app's per-browser-tab model
 * closely enough and avoids stale session_id 404s after a backend restart).
 */
export function usePipelineSession() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [status, setStatus] = useState<SessionStatus | null>(null);
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const runningRef = useRef(false);

  useEffect(() => {
    let cancelled = false;
    api
      .createSession()
      .then((r) => {
        if (!cancelled) setSessionId(r.session_id);
      })
      .catch((e) => {
        if (!cancelled) setConnectionError(e instanceof Error ? e.message : "Failed to connect");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!sessionId) return;
    let cancelled = false;

    async function poll() {
      try {
        const s = await api.getStatus(sessionId!);
        if (cancelled) return;
        setStatus(s);
        runningRef.current = s.running;
        setConnectionError(null);
      } catch (e) {
        if (cancelled) return;
        setConnectionError(e instanceof Error ? e.message : "Connection failed");
      } finally {
        if (!cancelled) {
          timerRef.current = setTimeout(poll, runningRef.current ? 1500 : 4000);
        }
      }
    }

    poll();
    return () => {
      cancelled = true;
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [sessionId]);

  const refresh = async () => {
    if (!sessionId) return null;
    const s = await api.getStatus(sessionId);
    setStatus(s);
    return s;
  };

  return { sessionId, status, connectionError, refresh };
}
