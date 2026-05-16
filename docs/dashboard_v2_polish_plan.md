# Dashboard v2 — Pre-Presentation Polish Plan

**Status:** source of truth for the final UI pass before the Monday
presentation. Bundles four discrete improvements plus a polish sweep,
all targeted at one stakeholder: a K-5 school administrator (principal,
assistant principal, district health-and-safety lead) who needs to
make a recess/athletics decision in under 10 seconds.

This doc is what the Claude Code extension will work from. The audit
section is the diagnosis. The implementation plan is the prescription.
The prompt at the bottom is what to paste into Claude Code.

---

## Audit — what's wrong with v1

### 🐛 Issue 1 — Time zone confusion

**Symptom.** Today's screenshot at 11:42 AM Mountain Time shows the
trend chart's most recent data point at "3 PM." The dashboard is
rendering UTC hours throughout, but a Utah principal reads them as
Mountain Time.

**Where it lives in code.**

- `lib/plainLanguage.ts` → `formatHour(hour)` takes a raw integer
  hour (which is UTC because that's what the model's `hour_of_day`
  feature represents) and prints "8 AM", "3 PM", etc. — no time-zone
  suffix, no conversion.
- `lib/featurePrep.ts` — uses `target.getUTCHours()` everywhere,
  correctly, because the MODEL needs UTC. Don't touch this.
- `components/TrendChart.tsx` — `toLocaleString("en-US", { timeZone:
  "UTC" })` in the tooltip and x-axis tick formatter. Should be
  `"America/Denver"` for display.
- `components/HourlyPredictionStrip.tsx` — calls `formatHour` with
  `p.hour_of_day` (UTC). Each cell shows a UTC hour as if it were
  Mountain Time.
- `components/HourRangeSlider.tsx` — the user picks "8 AM" thinking
  it's 8 AM Mountain. The slider currently sends 8 to the backend,
  which interprets it as 8 UTC = 2 AM Mountain. The model is
  predicting for the wrong hours.
- `app/page.tsx` → `handleSubmit` builds
  ``from = `${date}T${pad(hourRange.start)}:00:00Z` `` — concatenates
  the user's "Mountain Time start hour" with a `Z` (UTC) suffix.

**Why it matters for the demo.** A principal looking at the
dashboard at 9 AM their time sees predictions for "12 PM" (which is
actually 6 AM their time) and "3 PM" (which is 9 AM). The verdict
the model produces is real but the hour label is six hours off,
making the dashboard look broken even though the math is correct.

### 🐛 Issue 2 — Date picker is the wrong UX for the stakeholder

**Symptom.** Current control is a native `<input type="date">`. A
principal making the morning recess call doesn't want to think
about a specific date — they want "Today," "Tomorrow," or "next
Friday." A horizontal pill row of weekday names is the right
mental model.

**Where it lives in code.**

- `components/DateTimePicker.tsx` — renders a single native date
  input bounded by `today - 30 days` and `today + 7 days`.
- `app/page.tsx` — `date` state is a YYYY-MM-DD string; the
  `dateBounds` memo builds min/max from JS `Date` (which uses
  the host's local time zone — works on a Mountain-Time laptop
  but not guaranteed elsewhere).

**Why it matters for the demo.** A principal opening the dashboard
on Monday morning should see "Mon May 19 · today" highlighted, with
"Tue May 20", "Wed May 21" etc. visible as choices. Zero clicks of
a date scrubber. The current calendar widget feels like a
data-entry form, not a decision tool.

### 🐛 Issue 3 — Recommendation copy is school-hours-blind

**Symptom.** When the model predicts "UNSAFE at 6 PM" the
PredictionCard says "We recommend indoor recess during those hours."
But school is over by 6 PM in any K-5 district — there IS no recess.
What the principal actually needs at 6 PM is "monitor after-school
sports / clubs for sensitive students" guidance.

**Where it lives in code.**

- `lib/plainLanguage.ts` → `plainLanguageHeadline` returns one of two
  hard-coded strings:
  - `"Outdoor activities should be fine."` (all-safe path)
  - `"We recommend indoor recess during those hours."` (unsafe path)
- `components/PredictionDetailPanel.tsx` → `visualFor(prediction)`
  has four hard-coded recommendation strings, all of which mention
  "indoor recess." No school-day awareness.

**Why it matters for the demo.** Recommendation language that
doesn't match the user's situation breaks trust. A principal who
sees "indoor recess" recommended for 7 PM rolls their eyes and
loses confidence in the rest of the dashboard.

### 🎨 Issue 4 — Stakeholder framing is generic, not directed

**Symptom.** The header says "AirAlert · Utah PM2.5 outlook" and the
tagline asks "Should kids have outdoor recess?" That's a self-help
question the SYSTEM is asking. The dashboard should speak TO the
principal, not pose generic questions.

**Where it lives in code.**

- `app/page.tsx` — header markup and tagline.
- `components/PredictionCard.tsx` — outlook label is just "Outlook · UNSAFE."
- `components/PredictionDetailPanel.tsx` — verbose but still
  generic ("Outdoor recess is fine during this hour…").

**Why it matters for the demo.** The assignment grades us on
choosing a stakeholder and tailoring the deliverable to them. The
clearer the principal-voice in the copy, the more obvious the
stakeholder choice is to the grader.

---

## Implementation plan — what to change, file by file

### 1. New library — `lib/timezone.ts` (NEW FILE)

Houses every Mountain Time conversion helper. Single source of
truth so every component goes through the same logic. We add
`date-fns-tz` as a dependency (already aligned with the existing
`date-fns`).

```typescript
import { formatInTimeZone, zonedTimeToUtc } from "date-fns-tz";

/** Canonical IANA zone for Utah. America/Denver handles MST↔MDT automatically. */
export const TZ_MOUNTAIN = "America/Denver";

/** Format a UTC Date (or ISO string) as a wall-clock label in Mountain Time.
 *  e.g. mtFormat("2026-05-16T14:00:00Z", "h a") → "8 AM" */
export function mtFormat(input: Date | string, pattern: string): string {
  const d = typeof input === "string" ? new Date(input) : input;
  return formatInTimeZone(d, TZ_MOUNTAIN, pattern);
}

/** Format with the "MT" suffix so screen readers + visual readers
 *  both know the time zone. */
export function mtFormatLabeled(input: Date | string): string {
  return `${mtFormat(input, "h a")} MT`;
}

/** Convert a Mountain Time wall-clock (date + hour) to the UTC Date
 *  instant the model wants. Used by app/page.tsx when building the
 *  features-request payload from the user's picked range. */
export function mtWallClockToUtcDate(
  dateMT: string,    // "2026-05-16"
  hourMT: number,    // 8 (means 8:00 AM Mountain wall-clock time)
): Date {
  // zonedTimeToUtc interprets the string as wall-clock time in the
  // named zone and returns the corresponding UTC Date.
  return zonedTimeToUtc(`${dateMT} ${hourMT.toString().padStart(2, "0")}:00:00`, TZ_MOUNTAIN);
}

/** Today's date in Mountain Time as YYYY-MM-DD (NOT UTC). The host
 *  laptop's TZ shouldn't influence what "today" means for a Utah
 *  principal. */
export function mtTodayIsoDate(): string {
  return mtFormat(new Date(), "yyyy-MM-dd");
}

/** Convert any Date to its Mountain-Time YYYY-MM-DD calendar date. */
export function mtIsoDate(d: Date): string {
  return mtFormat(d, "yyyy-MM-dd");
}

/** Convert a UTC hour-of-day (0–23) on a specific date into the
 *  corresponding Mountain wall-clock hour (0–23). Handles DST and
 *  date-shift correctly (e.g. UTC 02:00 on a winter day = MST 19:00
 *  the previous day). */
export function utcHourToMtHour(
  utcHour: number,
  isoDateUtc: string,
): { hour: number; date: string } {
  const utcDate = new Date(`${isoDateUtc}T${utcHour.toString().padStart(2, "0")}:00:00Z`);
  return {
    hour: parseInt(mtFormat(utcDate, "H"), 10),
    date: mtFormat(utcDate, "yyyy-MM-dd"),
  };
}

/** Build the array of "next N days" the new DayPicker renders.
 *  Each entry is keyed by its Mountain-Time YYYY-MM-DD. */
export function nextNDaysMT(n: number, anchor?: Date): Array<{
  iso: string;
  weekday: string;     // "Mon", "Tue", ...
  monthDay: string;    // "May 19"
  isToday: boolean;
}> {
  const start = anchor ?? new Date();
  const out: Array<{ iso: string; weekday: string; monthDay: string; isToday: boolean }> = [];
  const todayIso = mtIsoDate(start);
  for (let i = 0; i < n; i++) {
    const d = new Date(start);
    d.setDate(d.getDate() + i);
    const iso = mtIsoDate(d);
    out.push({
      iso,
      weekday: mtFormat(d, "EEE"),
      monthDay: mtFormat(d, "MMM d"),
      isToday: iso === todayIso,
    });
  }
  return out;
}
```

Add `date-fns-tz` to `package.json`:

```json
"dependencies": {
  "clsx": "^2.1.1",
  "date-fns": "^3.6.0",
  "date-fns-tz": "^3.2.0",
  ...
}
```

### 2. `lib/plainLanguage.ts` — school-aware recommendations + MT formatHour

Three changes:

**2a.** `formatHour` now takes an optional second argument so callers
that pass UTC hour-of-day can specify which date the UTC hour
belongs to (needed for DST-correct conversion). Default behavior
unchanged for callers that just want simple AM/PM.

```typescript
export function formatHour(hour: number): string {
  const h = ((hour % 24) + 24) % 24;
  const period = h < 12 ? "AM" : "PM";
  const display = h % 12 === 0 ? 12 : h % 12;
  return `${display} ${period}`;
}
```

Leave this as-is. Add a NEW function next to it:

```typescript
/** Format a UTC hour-of-day for display to a Mountain-Time user.
 *  Returns "8 AM MT" / "2 PM MT" etc. */
export function formatHourMT(
  utcHourOfDay: number,
  isoDateUtc: string,
): string {
  const { hour } = utcHourToMtHour(utcHourOfDay, isoDateUtc);
  return `${formatHour(hour)} MT`;
}
```

**2b.** `plainLanguageHeadline` takes one additional parameter
indicating the user's selected date (Mountain Time) so the range
strings can be Mountain-localized. The internal grouping logic stays
in UTC (consecutive UTC hours are consecutive Mountain hours).

**2c.** A new helper picks the right recommendation language based on
when the unsafe window falls relative to the school day. Mountain
school hours convention: 8 AM – 3 PM is "core recess window."
3 PM – 7 PM is "after-school clubs and athletics." 7 PM+ is
"evening; outside school operations."

```typescript
export type SchoolPeriod = "core" | "after_school" | "outside_hours";

/** Utah K-5 school-day boundaries (confirmed with the team):
 *    08:00 – 15:59 Mountain  → core recess window
 *    16:00 – 18:59 Mountain  → after-school clubs, sports, latchkey
 *    everything else         → outside school operations
 *  Boundaries are exclusive at the upper end: 4 PM (hour 16) is the
 *  start of after-school; 7 PM (hour 19) is the start of outside_hours. */
export function schoolPeriodFor(mtHour: number): SchoolPeriod {
  if (mtHour >= 8 && mtHour <= 15) return "core";
  if (mtHour >= 16 && mtHour <= 18) return "after_school";
  return "outside_hours";
}

/** Recommendation copy tailored to a K-5 principal. The decision they
 *  need to make differs by time of day; the language should reflect
 *  that. */
export function recommendationFor(
  any_unsafe: boolean,
  periods: Set<SchoolPeriod>,
): string {
  if (!any_unsafe) {
    return "Outdoor recess and after-school activities are clear to proceed.";
  }
  const hasCore = periods.has("core");
  const hasAfter = periods.has("after_school");
  const hasOutside = periods.has("outside_hours");
  if (hasCore && hasAfter) {
    return "Hold recess indoors during those hours, and have after-school staff monitor sensitive students closely.";
  }
  if (hasCore) {
    return "Hold recess indoors during those hours.";
  }
  if (hasAfter) {
    return "After-school staff and coaches should monitor outdoor activities; consider moving practice indoors for students with asthma or other respiratory sensitivities.";
  }
  if (hasOutside) {
    return "Air quality is forecast to be unsafe outside school hours. No recess action needed, but flag to families with sensitive students.";
  }
  return "Hold recess indoors during those hours.";
}
```

Wire `recommendationFor` into `plainLanguageHeadline`. After
identifying the unsafe ranges, collect the unique school periods
each range falls into (using the Mountain-Time hour for each
prediction) and pass the set to `recommendationFor`.

### 3. `components/DayPicker.tsx` — NEW FILE, replaces DateTimePicker

```tsx
"use client";

import { clsx } from "clsx";
import { CalendarDays } from "lucide-react";

import { nextNDaysMT } from "@/lib/timezone";

interface DayPickerProps {
  value: string;  // ISO date "YYYY-MM-DD" in Mountain Time
  onChange: (next: string) => void;
  disabled?: boolean;
  daysAhead?: number;  // default 7
}

export function DayPicker({ value, onChange, disabled, daysAhead = 7 }: DayPickerProps) {
  const days = nextNDaysMT(daysAhead);
  return (
    <div>
      <div className="mb-2.5 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-slate-500">
        <CalendarDays className="h-3.5 w-3.5" aria-hidden />
        <span id="day-label">Day</span>
      </div>
      <div
        role="radiogroup"
        aria-labelledby="day-label"
        className="grid grid-cols-7 gap-1.5"
      >
        {days.map((d) => {
          const isSelected = d.iso === value;
          return (
            <button
              key={d.iso}
              role="radio"
              aria-checked={isSelected}
              disabled={disabled}
              onClick={() => onChange(d.iso)}
              className={clsx(
                "flex flex-col items-center rounded-xl border px-1 py-2 transition",
                "focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2",
                isSelected
                  ? "border-brand-600 bg-brand-600 text-white shadow-soft"
                  : "border-slate-200 bg-white text-slate-900 hover:border-slate-300",
                disabled && "cursor-not-allowed opacity-60",
              )}
            >
              <span className={clsx(
                "text-[10px] font-semibold uppercase tracking-wider",
                isSelected ? "text-brand-100" : "text-slate-500",
              )}>
                {d.weekday}
              </span>
              <span className="text-sm font-semibold tabular-nums">
                {d.monthDay}
              </span>
              {d.isToday && (
                <span className={clsx(
                  "mt-0.5 text-[9px] font-medium",
                  isSelected ? "text-brand-100" : "text-brand-600",
                )}>
                  TODAY
                </span>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
```

Update `app/page.tsx`:
- Replace `import { DateTimePicker }` with `import { DayPicker }`.
- Replace the `<DateTimePicker ... />` JSX with `<DayPicker value={date} onChange={setDate} disabled={pageState === "loading"} />`.
- Remove the `dateBounds` memo (no longer needed).
- Replace `const [date, setDate] = useState<string>(todayIsoDate);` with `const [date, setDate] = useState<string>(mtTodayIsoDate);` and remove the local `todayIsoDate` helper.

Delete `components/DateTimePicker.tsx` (or keep it for the audit
trail; doesn't matter, just not imported anywhere).

### 4. `components/HourRangeSlider.tsx` — Mountain Time labels

```tsx
// At the top of the formatHour usage:
import { formatHour } from "@/lib/plainLanguage";

// In the label render:
<span className="text-xs tabular-nums text-slate-600">
  <span className="font-semibold text-slate-900">
    {formatHour(start)}
  </span>
  <span className="mx-1.5 text-slate-400">→</span>
  <span className="font-semibold text-slate-900">
    {formatHour(end)}
  </span>
  <span className="ml-1 text-slate-400">MT</span>
</span>
```

The slider's start/end values now mean "wall-clock Mountain hour."
`app/page.tsx` is responsible for converting them to UTC for the
features request.

### 5. `app/page.tsx` — Mountain-to-UTC conversion at submit time

In `handleSubmit`:

```typescript
import { mtWallClockToUtcDate, mtTodayIsoDate } from "@/lib/timezone";

// REPLACE the existing fromIso construction:
const fromUtcDate = mtWallClockToUtcDate(date, hourRange.start);
const fromIso = fromUtcDate.toISOString();
const hours = hourRange.end - hourRange.start + 1;
```

So when the user picks "Monday, May 19 · 8 AM – 6 PM Mountain Time,"
the request that hits `/api/features` is anchored at the correct
UTC instant (14:00 UTC on May 19 in May because of MDT).

Header tagline + framing changes in `app/page.tsx`:

```tsx
<h1 className="text-3xl font-semibold tracking-tight text-slate-900 sm:text-4xl">
  AirAlert
</h1>
<p className="mt-1 text-sm text-slate-500 sm:text-base">
  Daily recess and athletics guidance for Utah K-5 administrators
</p>
```

Footer update — add a stakeholder note:

```tsx
<p className="mt-1.5 text-slate-400">
  All times Mountain (MST/MDT). Locations are the closest OpenAQ
  sensors to public K-5 schools in each district.
</p>
```

### 6. `components/PredictionCard.tsx` — sharper outlook copy

Change the outlook label so the verdict is the headline, not "Outlook":

```tsx
// Was:
<p className={clsx("text-xs font-semibold uppercase tracking-wider", v.accent)}>
  Outlook · {v.label}
</p>

// Becomes:
<p className={clsx("text-xs font-semibold uppercase tracking-wider", v.accent)}>
  Recess outlook · {v.label}
</p>
```

The "X of Y hours predicted unsafe" sub-label gets a sharper
principal-voice variant:

```tsx
{typeof unsafeHours === "number" && typeof totalHours === "number" && (
  <span className="text-xs tabular-nums text-slate-600">
    {unsafeHours === 0
      ? `All ${totalHours} hours in range predicted safe`
      : unsafeHours === 1
        ? `1 hour of ${totalHours} predicted unsafe`
        : `${unsafeHours} of ${totalHours} hours predicted unsafe`}
  </span>
)}
```

When the `verdict.recommendation` comes back from
`plainLanguageHeadline` it'll now reflect the school-day logic from
step 2c.

### 7. `components/HourlyPredictionStrip.tsx` — Mountain-Time labels + school-day shading

**7a.** Hour labels use `formatHourMT(p.hour_of_day, p.timestamp.slice(0,10))`:

```tsx
import { formatHourMT } from "@/lib/plainLanguage";

// In the cell render:
<span className="text-xs font-semibold tabular-nums text-slate-700">
  {formatHourMT(p.hour_of_day, p.timestamp.slice(0, 10))}
</span>
```

Note: `p.timestamp` is already an ISO UTC string; we slice to get
the date portion.

**7b.** Add a subtle school-day shading overlay. Inside the strip's
grid, before the cells, add a horizontal banner labeling the
"Recess window" and "After-school" periods based on the cells'
Mountain hours. This makes it visually obvious which hours are the
principal's primary decision window.

```tsx
import { schoolPeriodFor, utcHourToMtHour } from "@/lib/timezone";

// Compute period for each cell's Mountain hour.
// Render a thin tinted band BEHIND the cells indicating period.
// (Use absolute-positioned underlay with grid-column-spanning, or
// just add a small ring/badge to cells in the after-school window.)
```

Concretely — simplest visual: under the cells, add a small caption
row that labels which cells are in which school period:

```tsx
{/* School-day period labels (small caption row below cells) */}
<div className="mt-1 flex justify-around text-[10px] uppercase tracking-wider text-slate-400">
  <span>Recess window</span>
  <span>After-school</span>
</div>
```

### 8. `components/PredictionDetailPanel.tsx` — Mountain-Time hours + period-aware recommendations

Replace every `formatHour(prediction.hour_of_day)` with
`formatHourMT(prediction.hour_of_day, prediction.timestamp.slice(0, 10))`.

Replace the hard-coded recommendation strings in `visualFor()` with
calls to `recommendationFor(any_unsafe=is_unsafe, periods=...)` so
the detail panel uses the same school-aware logic as the headline.

The "Hour" detail tile should show Mountain-Time + add a small "UTC"
hover line for power users:

```tsx
{
  k: "Hour",
  v: formatHourMT(prediction.hour_of_day, prediction.timestamp.slice(0, 10)),
  hint: "Times shown in Mountain (MST/MDT). The model's underlying clock is UTC.",
}
```

### 9. `components/TrendChart.tsx` — Mountain-Time x-axis + tooltip

Change two occurrences of `timeZone: "UTC"` to `timeZone: "America/Denver"`:

```tsx
// Was (line ~273):
return d.toLocaleDateString("en-US", {
  month: "short",
  day: "numeric",
  timeZone: "UTC",
});

// Becomes:
return d.toLocaleDateString("en-US", {
  month: "short",
  day: "numeric",
  timeZone: "America/Denver",
});

// Was (line ~294, in tooltip):
const time = dt.toLocaleString("en-US", {
  month: "short",
  day: "numeric",
  hour: "numeric",
  timeZone: "UTC",
});

// Becomes:
const time = dt.toLocaleString("en-US", {
  month: "short",
  day: "numeric",
  hour: "numeric",
  timeZone: "America/Denver",
});
```

Update the chart's accessibility label and header sub-line to say
"local time":

```tsx
<p className="mt-1 flex items-center gap-1.5 text-xs text-slate-500">
  <Activity className="h-3 w-3" aria-hidden />
  <span>
    Real hourly sensor readings · last {days} days · μg/m³ · Mountain Time
  </span>
</p>
```

### 10. `components/DataSourceLegend.tsx` — stakeholder-specific language

Change the label "Where the inputs came from" to "How we filled in
the inputs" — the existing language is engineer-speak. The
principal cares about whether they're looking at observed data or a
forecast estimate, not where data "came from."

```tsx
<span className="font-semibold uppercase tracking-wider text-slate-500">
  How we filled in the inputs
</span>
```

Pill labels:

- "Measured" → keep
- "Estimated from {N}-day hourly patterns" → keep (already clear)
- "Sparse — fewer than 7 reference observations" → keep

Add a one-sentence note after the pills:

```tsx
<span className="ml-auto text-slate-400">
  Estimates are typical-day patterns, not your specific day&apos;s sensor readings.
</span>
```

### 11. NEW `components/TodaysVerdictBadge.tsx` — one-glance answer at the top of the page

The single most useful thing for a principal at 8 AM is a giant
pill that says GO / HOLD / INDOORS for the entire requested range.
This sits above the controls and is what they see first.

**Visual.** Full-width tinted card with a single oversized verdict
token (3–4 inch text on desktop) plus a one-line subtitle. Renders
only when `pageState === "result"`. Hidden in empty / loading /
error states (the PredictionCard handles those).

**Logic.**

```typescript
type VerdictTier = "go" | "hold" | "indoors" | "monitor";

function todaysVerdictTier(
  predictions: HourlyPrediction[],
): { tier: VerdictTier; headline: string; sub: string } {
  const unsafeCount = predictions.filter((p) => p.is_unsafe === 1).length;
  const totalCount = predictions.length;

  // Identify whether the unsafe hours fall in the core school window.
  const coreUnsafe = predictions.filter((p) => {
    if (p.is_unsafe !== 1) return false;
    const { hour } = utcHourToMtHour(p.hour_of_day, p.timestamp.slice(0, 10));
    return schoolPeriodFor(hour) === "core";
  }).length;
  const afterUnsafe = predictions.filter((p) => {
    if (p.is_unsafe !== 1) return false;
    const { hour } = utcHourToMtHour(p.hour_of_day, p.timestamp.slice(0, 10));
    return schoolPeriodFor(hour) === "after_school";
  }).length;

  if (unsafeCount === 0) {
    return {
      tier: "go",
      headline: "GO",
      sub: `Outdoor recess is clear across all ${totalCount} hours.`,
    };
  }
  if (coreUnsafe === 0 && afterUnsafe > 0) {
    return {
      tier: "monitor",
      headline: "MONITOR",
      sub: `Recess is clear; ${afterUnsafe} after-school hour${afterUnsafe > 1 ? "s" : ""} need watching.`,
    };
  }
  if (coreUnsafe >= Math.ceil(totalCount * 0.5)) {
    return {
      tier: "indoors",
      headline: "INDOORS",
      sub: `${coreUnsafe} of the recess hours predicted unsafe. Plan an indoor day.`,
    };
  }
  return {
    tier: "hold",
    headline: "HOLD",
    sub: `${coreUnsafe} recess hour${coreUnsafe > 1 ? "s" : ""} predicted unsafe. Watch the strip below.`,
  };
}
```

**Color map.**

| Tier | Card bg | Text | Icon |
|---|---|---|---|
| go | safe-50 | safe-700 | `ShieldCheck` |
| monitor | caution-50 | caution-700 | `Eye` |
| hold | caution-50 | caution-700 | `AlertTriangle` |
| indoors | unsafe-50 | unsafe-700 | `AlertOctagon` |

**Placement.** In `app/page.tsx`, render the badge immediately
BELOW the header and ABOVE the controls + hero section, only when
`pageState === "result"`. This gives the principal a 1-second
read.

### 12. `components/PredictionCard.tsx` — vs-yesterday callout

Add a small "yesterday vs today" comparison line under the
PredictionCard headline. Reuses the trend chart's already-fetched
data so no extra request is needed.

**Plumbing.** `app/page.tsx` already calls `getTrend(location, 7)`
inside `TrendChart`. Lift the fetch to the page level so both the
chart and the PredictionCard see the same data, OR have the
PredictionCard take a `yesterdayUnsafeHours: number | null` prop
that `app/page.tsx` computes from a side fetch.

Simplest: lift the trend fetch into the page. In `app/page.tsx`:

```typescript
const [trendPoints, setTrendPoints] = useState<TrendPoint[]>([]);

useEffect(() => {
  void getTrend(location, 7).then((r) => setTrendPoints(r.points));
}, [location]);

const yesterdayUnsafeHours = useMemo(() => {
  if (trendPoints.length === 0) return null;
  const yesterdayIso = mtFormat(new Date(Date.now() - 86400000), "yyyy-MM-dd");
  const yesterdayPoints = trendPoints.filter(
    (p) => mtFormat(p.timestamp, "yyyy-MM-dd") === yesterdayIso,
  );
  if (yesterdayPoints.length === 0) return null;
  return yesterdayPoints.filter((p) => p.is_unsafe).length;
}, [trendPoints]);
```

Pass `yesterdayUnsafeHours` to `PredictionCard`. Inside the card,
under the recommendation row:

```tsx
{yesterdayUnsafeHours !== null && typeof unsafeHours === "number" && (
  <p className="mt-2 text-xs text-slate-500">
    <span className="font-medium text-slate-700">vs yesterday:</span>{" "}
    {compareYesterday(yesterdayUnsafeHours, unsafeHours)}
  </p>
)}
```

Helper:

```typescript
function compareYesterday(yesterday: number, today: number): string {
  if (yesterday === 0 && today === 0) return "Yesterday was clear; today is forecast clear too.";
  if (yesterday === 0 && today > 0) return `Yesterday was clear; today is forecast to have ${today} unsafe hour${today > 1 ? "s" : ""}.`;
  if (yesterday > 0 && today === 0) return `Yesterday had ${yesterday} unsafe hour${yesterday > 1 ? "s" : ""}; today is forecast to be clear.`;
  if (today > yesterday) return `Yesterday had ${yesterday} unsafe hour${yesterday > 1 ? "s" : ""}; today is forecast worse (${today}).`;
  if (today < yesterday) return `Yesterday had ${yesterday} unsafe hour${yesterday > 1 ? "s" : ""}; today is forecast better (${today}).`;
  return `Today's forecast matches yesterday (${today} unsafe hour${today > 1 ? "s" : ""}).`;
}
```

Pass `trendPoints` to `TrendChart` as well (instead of letting it
fetch independently), to avoid the double request. Or keep the
chart's local fetch — both work. Lifting is cleaner.

### 13. `components/HourlyPredictionStrip.tsx` — school-day shading

Tint each cell's bottom strip differently by school period so the
principal sees at a glance which cells fall in the recess window
vs after-school.

**Visual.** Inside each cell's flex column, after the hour label,
add a 3px-tall bottom-band element whose background is keyed to
the school period:

| Period | Band color | Label below strip |
|---|---|---|
| core | `bg-slate-300` | "Recess" |
| after_school | `bg-slate-200` | "After-school" |
| outside_hours | `bg-slate-100` | "Off-hours" |

**Implementation.** In the cell render, compute the school period
once per cell:

```tsx
const { hour: mtHour } = utcHourToMtHour(p.hour_of_day, p.timestamp.slice(0, 10));
const period = schoolPeriodFor(mtHour);
```

Then at the bottom of the cell button, before the closing tag:

```tsx
<span
  className={clsx(
    "absolute inset-x-0 bottom-0 h-1 rounded-b-2xl",
    period === "core" && "bg-slate-300",
    period === "after_school" && "bg-slate-200",
    period === "outside_hours" && "bg-slate-100",
  )}
  aria-hidden
/>
```

And below the strip, replace the existing time-of-day rail with
the school-period labels:

```tsx
<div className="mt-2 flex justify-around text-[10px] font-medium uppercase tracking-wider text-slate-400">
  <span>Recess window</span>
  <span>After-school</span>
</div>
```

The principal scans the strip and immediately sees "the red cells
land in the recess window" or "the red cells are all after-school
hours, recess is fine."

---

## Out-of-scope items (deliberately deferred)

- **Multi-time-zone support.** The dashboard is Mountain-Time-only.
  Auto-detecting the user's browser zone is over-engineering for a
  Utah K-5 use case.
- **District / school name mapping.** Each location is a sensor name,
  not a school name. A future v2.1 could add a `school_directory.json`
  mapping sensor IDs to district names. Out of scope for Monday.
- **Recess scheduler integration.** A real product would let
  principals send notifications to teachers. We don't have a
  scheduler; the dashboard is read-only.
- **Multi-day forecast horizon.** Currently 1 day per request. A
  "5-day outlook at a glance" view is a v2.1 idea.

---

## Acceptance checklist for the Claude Code session

After implementation, verify:

**Core fixes (steps 1–10):**

- [ ] `npm run typecheck` passes clean.
- [ ] `npm run dev` boots without warnings.
- [ ] Picking "Mon May 19" + "8 AM – 6 PM" sends a request whose `from`
  parameter is `2026-05-19T14:00:00.000Z` (8 AM MDT = 14:00 UTC).
- [ ] Hourly strip cells render Mountain-Time labels: "8 AM MT",
  "9 AM MT", ..., "6 PM MT" — not UTC hours.
- [ ] Trend chart x-axis ticks render Mountain-Time dates and the
  tooltip shows Mountain-Time hours.
- [ ] When the model predicts unsafe at 5 PM Mountain, the
  PredictionCard says "After-school staff and coaches should
  monitor outdoor activities…" — NOT "indoor recess."
- [ ] When the model predicts unsafe at 10 AM Mountain, the
  PredictionCard says "Hold recess indoors during those hours."
- [ ] When the model predicts unsafe at 9 PM Mountain, the
  PredictionCard says "Air quality is forecast to be unsafe outside
  school hours…"
- [ ] The DayPicker shows 7 pills: today first (with a "TODAY"
  badge), then the next 6 days, each with weekday + month/day.
- [ ] Header tagline reads "Daily recess and athletics guidance for
  Utah K-5 administrators."
- [ ] Footer line includes "All times Mountain (MST/MDT)."

**Add-ons (steps 11–13):**

- [ ] `TodaysVerdictBadge` renders above the controls only when
  pageState === "result." Hidden in empty / loading / error states.
- [ ] When all hours are safe, the badge says "GO" in green.
- [ ] When some core-recess hours are unsafe, the badge says "HOLD"
  in amber; if ≥ 50% of core hours are unsafe, it says "INDOORS" in red.
- [ ] When only after-school hours are unsafe, the badge says "MONITOR"
  in amber — distinct from "HOLD" because the recess window itself is clear.
- [ ] PredictionCard renders a small "vs yesterday: …" line under the
  recommendation when yesterday's data is available; gracefully hides
  if the trend fetch hasn't resolved yet.
- [ ] Each strip cell has a thin bottom-band tinted by school period:
  slate-300 for core, slate-200 for after-school, slate-100 for off-hours.
- [ ] Below the strip, the caption row now reads
  "Recess window" on the left half and "After-school" on the right.

---

## Prompt for the Claude Code extension

Paste this whole block into Claude Code (or paste a link to this
file and say "implement the plan in `docs/dashboard_v2_polish_plan.md`").

```
Implement the dashboard v2 polish per the spec at
docs/dashboard_v2_polish_plan.md. The goal is a Monday-presentation-
ready dashboard targeted at one stakeholder: a K-5 school
administrator in Utah making the morning recess decision.

Four problems to fix, all documented in the spec:

  1. The dashboard renders UTC hours everywhere but the user reads
     them as Mountain Time. Result: every hour label is six hours
     off from the principal's wall clock.
  2. The date picker is a calendar input. Replace with a horizontal
     row of weekday pills (Mon May 19 · Tue May 20 · etc.) for the
     next 7 days, defaulting to today.
  3. The recommendation copy is hard-coded "indoor recess" regardless
     of what hour the unsafe prediction falls in. Add school-day
     awareness: 8 AM – 3 PM Mountain = "Hold recess indoors";
     3 PM – 7 PM Mountain = "Monitor after-school activities";
     7 PM+ = "Outside school hours; flag to families."
  4. Header and copy throughout are generic. Sharpen to a K-5
     principal voice — tagline becomes "Daily recess and athletics
     guidance for Utah K-5 administrators."

Implement every section of docs/dashboard_v2_polish_plan.md's
"Implementation plan" verbatim (steps 1–13). Specifically:

  - Add date-fns-tz to package.json dependencies; run npm install.
  - Create lib/timezone.ts with the helpers listed in step 1.
  - Update lib/plainLanguage.ts per step 2 (formatHourMT,
    schoolPeriodFor, recommendationFor, wire into plainLanguageHeadline).
  - Create components/DayPicker.tsx per step 3 and delete
    components/DateTimePicker.tsx after removing every import.
  - Update components/HourRangeSlider.tsx per step 4 (add "MT" suffix).
  - Update app/page.tsx per step 5 (mtWallClockToUtcDate at submit,
    DayPicker import, new tagline + footer line).
  - Update components/PredictionCard.tsx per step 6 ("Recess outlook",
    new unsafe-hour-count copy).
  - Update components/HourlyPredictionStrip.tsx per step 7
    (Mountain-Time cell labels, school-period caption row).
  - Update components/PredictionDetailPanel.tsx per step 8
    (formatHourMT everywhere, recommendationFor instead of
    hard-coded strings, MT hint on the Hour tile).
  - Update components/TrendChart.tsx per step 9 (timeZone:
    "America/Denver" in two places, "Mountain Time" in the header
    sub-line).
  - Update components/DataSourceLegend.tsx per step 10 (relabel
    "Where the inputs came from" → "How we filled in the inputs",
    add the estimates note).
  - Create components/TodaysVerdictBadge.tsx per step 11 (one-glance
    GO / MONITOR / HOLD / INDOORS pill above the controls).
  - Update components/PredictionCard.tsx per step 12 (vs-yesterday
    callout). Lift the getTrend fetch out of TrendChart into
    app/page.tsx so both the chart and the PredictionCard see the
    same data — this is the cleanest plumbing.
  - Update components/HourlyPredictionStrip.tsx per step 13 (per-cell
    school-period bottom band + "Recess window / After-school"
    caption row replacing the sunrise/sun/sunset rail).

Verification: run `npm run typecheck` (must pass with zero errors)
and walk the Acceptance checklist at the bottom of the spec doc.
Both the "Core fixes" and "Add-ons" sub-checklists must pass.
If any acceptance item fails, fix it before declaring done.

Constraints:
  - Do not touch anything outside app/dashboard/.
  - Do not change the model, the FastAPI surface, the API route
    contracts, or any Python code. Time zone conversion happens
    in the dashboard, never in the model — the model continues to
    receive UTC hour_of_day values.
  - Keep all existing Lucide icons. Add new ones from lucide-react
    as needed (CalendarDays is the only one this plan calls for).
  - Use clsx for conditional classes everywhere; no inline style={{}}.
  - Use Tailwind utility classes; do not add new entries to
    tailwind.config.ts unless absolutely required.
  - Preserve the Apple-Health × iOS-Weather × Duolingo aesthetic
    direction established in the previous redesign — generous
    whitespace, rounded-3xl hero cards, soft shadows, semantic
    color tokens (safe/caution/unsafe/brand).

When done, summarize: file count changed, lines added/removed,
typecheck result, and a quick walkthrough of how a principal would
use the new dashboard at 8 AM Monday Mountain Time to decide on
recess.
```

---

## Risk register

| Risk | Likelihood | Mitigation |
|---|---|---|
| `date-fns-tz` install increases bundle size noticeably | Low | The library is tree-shakable and we use only two functions; bundle hit < 10 KB gzipped |
| Mountain-Time conversion breaks during DST changeover (Nov / Mar) | Low | `America/Denver` IANA zone handles DST automatically; never hard-code an offset |
| Existing screenshots in the PR become misleading | Medium | Re-take screenshots after v2 ships; the audit will note timezone in the new captions |
| School-period boundaries (8/15/19) feel arbitrary | Low | Pulled from typical Utah K-5 schedules; if a teammate prefers different hours, the constants in `schoolPeriodFor` are one-line tweaks |
| Recommendation copy reads stilted | Medium | Have Quinn + Gracelyn both read the strings out loud before submitting; the spec calls for principal-voice but exact phrasing benefits from human polish |

---

## Time budget

| Step | Estimate |
|---|---|
| Install date-fns-tz, build lib/timezone.ts | 15 min |
| Update lib/plainLanguage.ts (formatHourMT + school logic) | 25 min |
| Build DayPicker.tsx, swap in page.tsx | 20 min |
| HourRangeSlider + page.tsx (MT label + UTC conversion at submit) | 20 min |
| PredictionCard + HourlyPredictionStrip + DetailPanel copy + MT hours | 40 min |
| TrendChart timezone fix | 5 min |
| DataSourceLegend copy + footer + header tagline | 10 min |
| **Add-on: TodaysVerdictBadge** | 20 min |
| **Add-on: vs-yesterday callout (lift trend fetch)** | 20 min |
| **Add-on: school-day shading on strip** | 15 min |
| Typecheck + acceptance walkthrough | 20 min |
| **Total** | **~3.5 hours** |
