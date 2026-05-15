/**
 * HealthBadge — polished status pill with a pulsing live indicator.
 *
 * Renders one of three visual states (loading / online / offline) per
 * the UI spec. Uses Lucide icons for visual continuity with the rest
 * of the dashboard. Polls /api/health on mount and every 30 seconds.
 */

"use client";

import { clsx } from "clsx";
import { Loader2, ShieldCheck, ShieldAlert } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { getHealth } from "@/lib/api";

type Status = "loading" | "online" | "offline";

interface HealthBadgeProps {
  onStatusChange?: (status: Status) => void;
  pollIntervalMs?: number;
}

export function HealthBadge({
  onStatusChange,
  pollIntervalMs = 30_000,
}: HealthBadgeProps) {
  const [status, setStatus] = useState<Status>("loading");
  const [modelSummary, setModelSummary] = useState<string>("");
  const onStatusRef = useRef(onStatusChange);
  onStatusRef.current = onStatusChange;

  useEffect(() => {
    let cancelled = false;

    const tick = async () => {
      try {
        const body = await getHealth();
        if (cancelled) return;
        if (body.status === "ok") {
          setStatus("online");
          setModelSummary(body.model_name || "");
          onStatusRef.current?.("online");
        } else {
          setStatus("offline");
          setModelSummary("");
          onStatusRef.current?.("offline");
        }
      } catch {
        if (cancelled) return;
        setStatus("offline");
        setModelSummary("");
        onStatusRef.current?.("offline");
      }
    };

    void tick();
    const id = window.setInterval(tick, pollIntervalMs);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [pollIntervalMs]);

  const label =
    status === "loading"
      ? "Checking service"
      : status === "online"
        ? "Service online"
        : "Service offline";

  return (
    <span
      role="status"
      aria-live="polite"
      title={status === "online" && modelSummary ? modelSummary : undefined}
      className={clsx(
        "inline-flex items-center gap-2 rounded-full px-3.5 py-1.5 text-xs font-medium ring-1 ring-inset transition",
        status === "loading" &&
          "bg-slate-50 text-slate-600 ring-slate-200",
        status === "online" &&
          "bg-safe-50 text-safe-700 ring-safe-200",
        status === "offline" &&
          "bg-unsafe-50 text-unsafe-700 ring-unsafe-200",
      )}
    >
      {status === "loading" && (
        <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
      )}
      {status === "online" && (
        <span className="relative flex h-2 w-2" aria-hidden>
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-safe-500 opacity-60" />
          <span className="relative inline-flex h-2 w-2 rounded-full bg-safe-500" />
        </span>
      )}
      {status === "offline" && (
        <ShieldAlert className="h-3.5 w-3.5" aria-hidden />
      )}
      {status === "online" && (
        <ShieldCheck className="h-3.5 w-3.5" aria-hidden />
      )}
      <span>{label}</span>
    </span>
  );
}
