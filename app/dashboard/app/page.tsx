/**
 * AirAlert dashboard — main page composition.
 *
 * Visual structure:
 *
 *   HEADER          AirAlert wordmark + tagline + HealthBadge
 *   CONTROLS  ──┐
 *   HERO CARD ──┤   side-by-side on lg+, stacked on smaller
 *   HOURLY STRIP    full-width forecast row
 *   DETAIL PANEL    appears below the strip when a cell is selected
 *   TREND CHART     measured-data block with "MEASURED" badge
 *   LEGEND          where the inputs came from
 *   FOOTER          attribution + disclaimer
 */

"use client";

import { Wind } from "lucide-react";
import { useMemo, useState } from "react";

import { DataSourceLegend } from "@/components/DataSourceLegend";
import { DateTimePicker } from "@/components/DateTimePicker";
import { HealthBadge } from "@/components/HealthBadge";
import { HourRangeSlider } from "@/components/HourRangeSlider";
import { HourlyPredictionStrip } from "@/components/HourlyPredictionStrip";
import { LocationPicker } from "@/components/LocationPicker";
import { PredictButton } from "@/components/PredictButton";
import { PredictionCard } from "@/components/PredictionCard";
import { PredictionDetailPanel } from "@/components/PredictionDetailPanel";
import { TrendChart } from "@/components/TrendChart";

import { predictRange } from "@/lib/api";
import {
  REFERENCE_WINDOW_DAYS,
  UNSAFE_THRESHOLD,
  type LocationKey,
} from "@/lib/constants";
import { plainLanguageHeadline } from "@/lib/plainLanguage";
import type { HourlyPrediction, PlainLanguageVerdict } from "@/lib/types";

type PageState = "empty" | "loading" | "result" | "error";

interface PredictionResult {
  predictions: HourlyPrediction[];
  verdict: PlainLanguageVerdict;
  referenceWindowDays: number;
}

export default function Page() {
  /* ── form state ─────────────────────────────────────────────── */
  const [location, setLocation] = useState<LocationKey>("red_butte");
  const [date, setDate] = useState<string>(todayIsoDate);
  const [hourRange, setHourRange] = useState({ start: 8, end: 18 });

  /* ── result state ───────────────────────────────────────────── */
  const [pageState, setPageState] = useState<PageState>("empty");
  const [result, setResult] = useState<PredictionResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedHourIdx, setSelectedHourIdx] = useState<number | null>(null);

  /* ── health state (gates the predict button) ────────────────── */
  const [serviceOnline, setServiceOnline] = useState(true);

  const dateBounds = useMemo(() => {
    const today = new Date();
    today.setUTCHours(0, 0, 0, 0);
    const minDate = new Date(today);
    minDate.setUTCDate(minDate.getUTCDate() - 30);
    const maxDate = new Date(today);
    maxDate.setUTCDate(maxDate.getUTCDate() + 7);
    return {
      min: minDate.toISOString().slice(0, 10),
      max: maxDate.toISOString().slice(0, 10),
    };
  }, []);

  const handleSubmit = async () => {
    setPageState("loading");
    setError(null);
    setSelectedHourIdx(null);
    try {
      const fromIso = `${date}T${pad(hourRange.start)}:00:00Z`;
      const hours = hourRange.end - hourRange.start + 1;
      const { rows, reference_window_days } = await predictRange(
        location,
        fromIso,
        hours,
      );
      const verdict = plainLanguageHeadline(location, rows);
      setResult({
        predictions: rows,
        verdict,
        referenceWindowDays: reference_window_days,
      });
      setPageState("result");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
      setResult(null);
      setPageState("error");
    }
  };

  const predictButtonState =
    pageState === "loading"
      ? "loading"
      : serviceOnline
        ? "default"
        : "disabled";

  const todayHuman = new Date().toLocaleDateString("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
  });

  const unsafeHourCount = result?.predictions.filter((p) => p.is_unsafe === 1)
    .length;

  return (
    <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6 sm:py-12 lg:py-16">
      {/* ── HEADER ─────────────────────────────────────────── */}
      <header className="mb-10 flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-start gap-3.5">
          <div className="flex-shrink-0 rounded-2xl bg-gradient-to-br from-brand-500 to-brand-700 p-2.5 shadow-soft">
            <Wind className="h-6 w-6 text-white" aria-hidden />
          </div>
          <div>
            <h1 className="text-3xl font-semibold tracking-tight text-slate-900 sm:text-4xl">
              AirAlert
            </h1>
            <p className="mt-1 text-sm text-slate-500 sm:text-base">
              {todayHuman} · Utah PM2.5 outlook
            </p>
          </div>
        </div>
        <HealthBadge
          onStatusChange={(s) => setServiceOnline(s === "online")}
        />
      </header>

      {/* ── CONTROLS + HERO ────────────────────────────────── */}
      <section className="grid gap-4 lg:grid-cols-5">
        {/* Controls (2/5) */}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (predictButtonState !== "disabled") handleSubmit();
          }}
          className="rounded-3xl border border-slate-200 bg-white p-6 shadow-soft lg:col-span-2"
        >
          <div className="space-y-5">
            <LocationPicker
              value={location}
              onChange={setLocation}
              disabled={pageState === "loading"}
            />
            <DateTimePicker
              value={date}
              onChange={setDate}
              minDate={dateBounds.min}
              maxDate={dateBounds.max}
              disabled={pageState === "loading"}
            />
            <HourRangeSlider
              value={hourRange}
              onChange={setHourRange}
              disabled={pageState === "loading"}
            />
            <PredictButton
              state={predictButtonState}
              onClick={handleSubmit}
            />
            {!serviceOnline && (
              <p className="rounded-xl bg-unsafe-50 px-3 py-2 text-xs text-unsafe-700 ring-1 ring-inset ring-unsafe-200">
                The prediction service is offline. Predictions will be
                available once the service is back.
              </p>
            )}
          </div>
        </form>

        {/* Hero / PredictionCard (3/5) */}
        <div className="lg:col-span-3">
          <PredictionCard
            state={pageState}
            verdict={result?.verdict}
            errorMessage={error}
            unsafeHours={unsafeHourCount}
            totalHours={result?.predictions.length}
          />
        </div>
      </section>

      {/* ── HOURLY STRIP ───────────────────────────────────── */}
      {(pageState === "loading" || pageState === "result") && (
        <section className="mt-4 rounded-3xl border border-slate-200 bg-white px-6 py-6 shadow-soft sm:px-8">
          <HourlyPredictionStrip
            predictions={result?.predictions ?? []}
            loading={pageState === "loading"}
            selectedIndex={selectedHourIdx}
            onSelect={setSelectedHourIdx}
          />
        </section>
      )}

      {/* ── DETAIL PANEL (only when a cell is selected) ────── */}
      {pageState === "result" &&
        result &&
        selectedHourIdx !== null &&
        result.predictions[selectedHourIdx] && (
          <section className="mt-4">
            <PredictionDetailPanel
              prediction={result.predictions[selectedHourIdx]}
              location={location}
              onClose={() => setSelectedHourIdx(null)}
            />
          </section>
        )}

      {/* ── TREND CHART ────────────────────────────────────── */}
      <section className="mt-4">
        <TrendChart location={location} />
      </section>

      {/* ── DATA SOURCE LEGEND ─────────────────────────────── */}
      {pageState === "result" && result && (
        <section className="mt-4">
          <DataSourceLegend
            predictions={result.predictions}
            referenceWindowDays={result.referenceWindowDays}
          />
        </section>
      )}

      {/* ── FOOTER ─────────────────────────────────────────── */}
      <footer className="mt-12 border-t border-slate-200 pt-6 text-xs leading-relaxed text-slate-500">
        <p>
          AirAlert is a class project. PM2.5 unsafe threshold of{" "}
          <span className="font-semibold text-slate-700">
            {UNSAFE_THRESHOLD} μg/m³
          </span>{" "}
          follows EPA&apos;s &quot;unhealthy for sensitive groups&quot;
          boundary. Predictions are advisory; this is not medical advice.
        </p>
        <p className="mt-1.5 text-slate-400">
          Data via OpenAQ · MLflow · FastAPI · Next.js
        </p>
      </footer>
    </main>
  );
}

/* ── helpers ─────────────────────────────────────────────────── */

function pad(n: number) {
  return n.toString().padStart(2, "0");
}

function todayIsoDate(): string {
  const d = new Date();
  d.setUTCHours(0, 0, 0, 0);
  return d.toISOString().slice(0, 10);
}
