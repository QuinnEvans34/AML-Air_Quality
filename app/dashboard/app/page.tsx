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
import { useEffect, useMemo, useState } from "react";

import { DataSourceLegend } from "@/components/DataSourceLegend";
import { DayPicker } from "@/components/DayPicker";
import { HealthBadge } from "@/components/HealthBadge";
import { HourRangeSlider } from "@/components/HourRangeSlider";
import { HourlyPredictionStrip } from "@/components/HourlyPredictionStrip";
import { LocationPicker } from "@/components/LocationPicker";
import { PredictButton } from "@/components/PredictButton";
import { PredictionCard } from "@/components/PredictionCard";
import { PredictionDetailPanel } from "@/components/PredictionDetailPanel";
import { TodaysVerdictBadge } from "@/components/TodaysVerdictBadge";
import { TrendChart } from "@/components/TrendChart";

import { getTrend, predictRange } from "@/lib/api";
import {
  UNSAFE_THRESHOLD,
  type LocationKey,
} from "@/lib/constants";
import { plainLanguageHeadline } from "@/lib/plainLanguage";
import {
  mtFormat,
  mtTodayIsoDate,
  mtWallClockToUtcDate,
} from "@/lib/timezone";
import type {
  HourlyPrediction,
  PlainLanguageVerdict,
  TrendPoint,
} from "@/lib/types";

type PageState = "empty" | "loading" | "result" | "error";

interface PredictionResult {
  predictions: HourlyPrediction[];
  verdict: PlainLanguageVerdict;
  referenceWindowDays: number;
}

export default function Page() {
  /* ── form state ─────────────────────────────────────────────── */
  const [location, setLocation] = useState<LocationKey>("red_butte");
  const [date, setDate] = useState<string>(mtTodayIsoDate);
  const [hourRange, setHourRange] = useState({ start: 8, end: 18 });

  /* ── result state ───────────────────────────────────────────── */
  const [pageState, setPageState] = useState<PageState>("empty");
  const [result, setResult] = useState<PredictionResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedHourIdx, setSelectedHourIdx] = useState<number | null>(null);

  /* ── health state (gates the predict button) ────────────────── */
  const [serviceOnline, setServiceOnline] = useState(true);

  /* ── trend data (lifted from TrendChart so PredictionCard sees it too) ── */
  const [trendPoints, setTrendPoints] = useState<TrendPoint[]>([]);

  useEffect(() => {
    let cancelled = false;
    void getTrend(location, 7).then((r) => {
      if (!cancelled) setTrendPoints(r.points);
    });
    return () => {
      cancelled = true;
    };
  }, [location]);

  const yesterdayUnsafeHours = useMemo<number | null>(() => {
    if (trendPoints.length === 0) return null;
    const yesterdayIso = mtFormat(
      new Date(Date.now() - 86_400_000),
      "yyyy-MM-dd",
    );
    const yesterdayPoints = trendPoints.filter(
      (p) =>
        mtFormat(
          new Date(p.timestamp.replace(" ", "T")),
          "yyyy-MM-dd",
        ) === yesterdayIso,
    );
    if (yesterdayPoints.length === 0) return null;
    return yesterdayPoints.filter((p) => p.is_unsafe).length;
  }, [trendPoints]);

  const handleSubmit = async () => {
    setPageState("loading");
    setError(null);
    setSelectedHourIdx(null);
    try {
      const fromUtcDate = mtWallClockToUtcDate(date, hourRange.start);
      const fromIso = fromUtcDate.toISOString();
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
              Daily recess and athletics guidance for Utah K-5 administrators
            </p>
          </div>
        </div>
        <HealthBadge
          onStatusChange={(s) => setServiceOnline(s === "online")}
        />
      </header>

      {/* ── ONE-GLANCE VERDICT BADGE ───────────────────────── */}
      {pageState === "result" && result && (
        <section className="mb-4">
          <TodaysVerdictBadge predictions={result.predictions} />
        </section>
      )}

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
            <DayPicker
              value={date}
              onChange={setDate}
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
            location={location}
            verdict={result?.verdict}
            errorMessage={error}
            unsafeHours={unsafeHourCount}
            totalHours={result?.predictions.length}
            yesterdayUnsafeHours={yesterdayUnsafeHours}
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
        <TrendChart location={location} points={trendPoints} />
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
          Each location pairs an OpenAQ sensor with the public K-5 schools
          in its air shed. Times shown in Mountain (MST/MDT).
        </p>
      </footer>
    </main>
  );
}
