import { useEffect, useRef, useState } from "react";
import { api, type SessionStatus } from "../lib/api";

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
      .then((r) => { if (!cancelled) setSessionId(r.session_id); })
      .catch((e) => {
        if (!cancelled)
          setConnectionError(e instanceof Error ? e.message : "Failed to connect to backend");
      });
    return () => { cancelled = true; };
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
          // Poll faster when running (1s), slower when idle (5s)
          timerRef.current = setTimeout(poll, runningRef.current ? 1000 : 5000);
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
