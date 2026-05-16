# Dashboard v3 — Nearby Schools Integration Plan

**Status:** sequential follow-up to `docs/dashboard_v2_polish_plan.md`.
Apply ONLY after v2 (Mountain Time + DayPicker + period-aware
recommendations + verdict badge + vs-yesterday + school-day shading)
has landed on `feat/dashboard`.

**Stakeholder cue this delivers.** Each PM2.5 sensor maps to multiple
public K-5 schools in its air shed. Naming those schools in the
dashboard makes the stakeholder choice ("we built this for K-5 admins
in Utah") concrete instead of abstract — a principal sees their
school in the location picker or the outlook card and knows the tool
is for them.

---

## The school data (drop straight into `lib/constants.ts`)

These are public elementaries closest to each OpenAQ sensor by air
shed. **Confidence is "high" unless flagged otherwise** — meaning the
school exists at the address shown as of my last verification, and
its location places it inside the sensor's likely PM2.5 footprint.
For Monday's demo any name in this list is defensible; a Tuesday-or-
later production rollout should re-verify against district directories.

### Red Butte sensor (3318370 · Salt Lake City School District)

The sensor sits on the east bench near Red Butte Garden / University
of Utah. Wind patterns mean it represents air for the eastern slice
of the SLC SD service area.

| School | Address | Confidence |
|---|---|---|
| Bonneville Elementary | 1145 S 1900 E, Salt Lake City, UT 84108 | high |
| Indian Hills Elementary | 1340 E St Marys Way, Salt Lake City, UT 84108 | high |
| Wasatch Elementary | 30 R St, Salt Lake City, UT 84103 | high |
| Uintah Elementary | 1571 E 1300 S, Salt Lake City, UT 84105 | high |

**Primary school (used as the LocationPicker headline label):**
Bonneville Elementary.

**District:** Salt Lake City School District.

### Smithfield sensor (305 · Cache County School District)

Small-town Cache Valley sensor; the in-town elementaries all sit
within the sensor's footprint.

| School | Address | Confidence |
|---|---|---|
| Summit Elementary | 100 N 200 W, Smithfield, UT 84335 | high |
| Birch Creek Elementary | 825 S Main St, Smithfield, UT 84335 | medium — verify address |
| Heritage Elementary | 75 N Main St, Smithfield, UT 84335 | medium — verify address |

**Primary school:** Summit Elementary (most central, oldest in town).

**District:** Cache County School District.

### Ledges sensor (6158842 · Washington County School District)

The Ledges golf community is in the Ivins / Snow Canyon corridor
just north of St. George. Closest elementaries:

| School | Address | Confidence |
|---|---|---|
| Red Mountain Elementary | 940 N 200 W, Ivins, UT 84738 | high |
| Diamond Valley Elementary | 5530 N Diamond Valley Dr, St. George, UT 84770 | medium — verify address |
| Coral Cliffs Elementary | 1955 W 530 N, St. George, UT 84770 | medium |
| Vista Elementary (Ivins) | Northern St. George area | low — verify entirely |

**Primary school:** Red Mountain Elementary (closest to Snow Canyon).

**District:** Washington County School District.

### Verification step (5 minutes before merging)

For any school flagged medium/low confidence, paste the school name
into Google Maps to confirm it (a) exists, (b) is at the address
shown, and (c) is still a public K-5 elementary (not a K-8, charter,
or closed). Each district's website also publishes a directory:

- slcschools.org/schools
- ccsdut.org/schools
- washk12.org/schools

If a school doesn't verify, replace it in the constants file with the
next-closest verified school from the same district before merging.

---

## Implementation plan — file by file

### 1. `lib/constants.ts` — extend the TARGET_LOCATIONS type

The v2 polish established `TARGET_LOCATIONS` keyed by `LocationKey`
with at minimum `{id, label, region}`. Extend the type:

```typescript
export interface School {
  name: string;
  address: string;
}

export interface LocationMeta {
  id: number;
  label: string;            // existing — kept as fallback for places
                            //   the dashboard hasn't been refactored
                            //   to show school names yet
  region: string;           // existing
  primary_school: string;   // NEW — used as the headline in LocationPicker
  district: string;         // NEW — used as the subtitle
  sensor_label: string;     // NEW — what to show when we DO want to surface
                            //   the underlying sensor (e.g. tooltips, the
                            //   detail panel, the footer microcopy)
  nearby_schools: School[]; // NEW — full list rendered as chips in
                            //   PredictionCard + PredictionDetailPanel
}

export const TARGET_LOCATIONS: Record<LocationKey, LocationMeta> = {
  red_butte: {
    id: 3318370,
    label: "Red Butte",
    region: "Salt Lake County",
    primary_school: "Bonneville Elementary",
    district: "Salt Lake City School District",
    sensor_label: "Red Butte sensor",
    nearby_schools: [
      { name: "Bonneville Elementary",   address: "1145 S 1900 E, Salt Lake City, UT 84108" },
      { name: "Indian Hills Elementary", address: "1340 E St Marys Way, Salt Lake City, UT 84108" },
      { name: "Wasatch Elementary",      address: "30 R St, Salt Lake City, UT 84103" },
      { name: "Uintah Elementary",       address: "1571 E 1300 S, Salt Lake City, UT 84105" },
    ],
  },
  smithfield: {
    id: 305,
    label: "Smithfield",
    region: "Cache Valley",
    primary_school: "Summit Elementary",
    district: "Cache County School District",
    sensor_label: "Smithfield sensor",
    nearby_schools: [
      { name: "Summit Elementary",      address: "100 N 200 W, Smithfield, UT 84335" },
      { name: "Birch Creek Elementary", address: "825 S Main St, Smithfield, UT 84335" },
      { name: "Heritage Elementary",    address: "75 N Main St, Smithfield, UT 84335" },
    ],
  },
  ledges: {
    id: 6158842,
    label: "Ledges",
    region: "Snow Canyon · St. George",
    primary_school: "Red Mountain Elementary",
    district: "Washington County School District",
    sensor_label: "Ledges sensor",
    nearby_schools: [
      { name: "Red Mountain Elementary",   address: "940 N 200 W, Ivins, UT 84738" },
      { name: "Diamond Valley Elementary", address: "5530 N Diamond Valley Dr, St. George, UT 84770" },
      { name: "Coral Cliffs Elementary",   address: "1955 W 530 N, St. George, UT 84770" },
    ],
  },
};
```

**Backward compatibility.** Every existing reference to
`TARGET_LOCATIONS[key].label` / `.region` keeps working. New fields
are additive. No callsite needs to change unless we want it to show
school information.

### 2. `components/LocationPicker.tsx` — show the school, not the sensor

Each of the three location buttons currently shows:

```
[ Red Butte ]
  Salt Lake County
```

Change it to show the school as primary, the district as subtitle, and
the sensor as a tiny footnote:

```
[ Bonneville Elementary ]
  Salt Lake City School District
  + 3 nearby schools · Red Butte sensor
```

Implementation:

```tsx
<span className="block text-sm font-medium leading-tight">
  {meta.primary_school}
</span>
<span className={clsx(
  "mt-0.5 block text-xs leading-tight",
  isActive ? "text-brand-100" : "text-slate-500",
)}>
  {meta.district}
</span>
<span className={clsx(
  "mt-1 block text-[10px] leading-tight",
  isActive ? "text-brand-200" : "text-slate-400",
)}>
  + {meta.nearby_schools.length - 1} nearby · {meta.sensor_label}
</span>
```

The "+3 nearby" copy makes it obvious to a principal that the
location serves more than one school — they don't think "this is
only for Bonneville."

### 3. NEW `components/NearbySchoolsChips.tsx` — chip row

A small reusable component used inside the PredictionCard and the
PredictionDetailPanel. Renders the schools as compact pills, with
the primary visually emphasized.

```tsx
"use client";

import { clsx } from "clsx";
import { School } from "lucide-react";

import type { LocationKey } from "@/lib/constants";
import { TARGET_LOCATIONS } from "@/lib/constants";

interface NearbySchoolsChipsProps {
  location: LocationKey;
  /** Compact mode skips the lead-in label and shrinks padding;
   *  used inside dense cards like the detail panel. */
  compact?: boolean;
}

export function NearbySchoolsChips({
  location,
  compact = false,
}: NearbySchoolsChipsProps) {
  const meta = TARGET_LOCATIONS[location];
  const primary = meta.primary_school;
  return (
    <div className={clsx(
      "flex flex-wrap items-center gap-1.5",
      compact ? "text-[11px]" : "text-xs",
    )}>
      {!compact && (
        <span className="inline-flex items-center gap-1 font-semibold uppercase tracking-wider text-slate-500">
          <School className="h-3 w-3" aria-hidden />
          Schools served
        </span>
      )}
      {meta.nearby_schools.map((s) => {
        const isPrimary = s.name === primary;
        return (
          <span
            key={s.name}
            title={s.address}
            className={clsx(
              "inline-flex items-center rounded-full px-2.5 py-0.5 ring-1 ring-inset",
              isPrimary
                ? "bg-brand-50 text-brand-700 ring-brand-200 font-semibold"
                : "bg-slate-50 text-slate-700 ring-slate-200",
            )}
          >
            {s.name}
          </span>
        );
      })}
    </div>
  );
}
```

### 4. `components/PredictionCard.tsx` — surface the schools

Below the recommendation row + vs-yesterday callout the v2 polish
added, append the chip row:

```tsx
import { NearbySchoolsChips } from "./NearbySchoolsChips";
// ...

{verdict && (
  <div className="mt-5 border-t border-slate-200/70 pt-4">
    <NearbySchoolsChips location={location} />
  </div>
)}
```

(`location` is already in scope — `PredictionCard` receives it from
`app/page.tsx`. If v2 didn't pass it, add it as a prop.)

### 5. `components/PredictionDetailPanel.tsx` — context for the hour drill-down

Below the existing detail tiles, before the "What the model saw"
section, add a one-line chip row in compact mode:

```tsx
import { NearbySchoolsChips } from "./NearbySchoolsChips";
// ...

<div className="mt-5">
  <NearbySchoolsChips location={location} compact />
</div>
```

This grounds the per-hour deep-dive in concrete schools so a
principal looking at the 2 PM prediction sees "Bonneville · Indian
Hills · Wasatch · Uintah" right there.

### 6. `lib/plainLanguage.ts` — verdict copy that names the primary school

The current headline uses `meta.label` ("Air quality at **Red Butte**
is predicted to be UNSAFE…"). Change it to use the primary school:

```typescript
const locationLabel = meta ? meta.primary_school : locationKey;
```

Result: "Air quality at **Bonneville Elementary** is predicted to be
UNSAFE between 2 PM and 4 PM."

This is the single most impactful copy change — the principal sees
their school by name in the verdict.

### 7. `app/page.tsx` — footer microcopy

Replace the existing footer line about "OpenAQ sensors near K-5
schools" with a more confident version now that we actually have the
school names baked in:

```tsx
<p className="mt-1.5 text-slate-400">
  Each location pairs an OpenAQ sensor with the public K-5 schools
  in its air shed. Times shown in Mountain (MST/MDT).
</p>
```

### 8. `lib/types.ts` — TypeScript hygiene

If a `LocationMeta` type alias was added in step 1 (recommended),
export it from `lib/types.ts` too for components that want to type
their props as `LocationMeta` instead of indexing into
`TARGET_LOCATIONS`. Re-export from `constants.ts` works fine if
preferred.

---

## Out of scope (deliberate)

- **Address resolution / geocoding.** We hard-code addresses; no
  client-side lookup. A future v3.1 could use Google Maps Static API
  to render a small inset map, but the licensing burden isn't worth
  it for Monday.
- **District-level switching.** The dashboard still presents three
  fixed locations; a principal in a non-listed district doesn't get
  coverage. That's a Decision-6 amendment, not a UI fix.
- **School-specific predictions.** All four schools at the Red Butte
  sensor share the same forecast — that's how air sheds work. The
  chips communicate "your school is served by this prediction," not
  "we predicted for each school individually."

---

## Acceptance checklist

After Claude Code finishes:

- [ ] `npm run typecheck` passes clean.
- [ ] `npm run dev` boots without warnings.
- [ ] LocationPicker buttons show school name (large), district name
      (medium), and "+ N nearby · Red Butte sensor" (small).
- [ ] PredictionCard headline reads "Air quality at Bonneville
      Elementary is predicted to be SAFE/UNSAFE …" — the school name,
      not the sensor name.
- [ ] PredictionCard footer shows a "Schools served" chip row with
      the primary school visually emphasized (brand color) and the
      remaining schools in slate.
- [ ] PredictionDetailPanel includes the same chip row in compact
      mode, immediately above the "What the model saw" section.
- [ ] Hovering a school chip reveals its address as a tooltip.
- [ ] Switching locations changes the chip row, the picker label, the
      verdict headline, AND the trend chart title in lockstep.
- [ ] Footer microcopy reflects the new "schools in its air shed"
      framing.

---

## Prompt for the Claude Code extension

Paste this into Claude Code (or attach a link to this file and say
"implement docs/dashboard_v3_schools_plan.md").

```
Implement the nearby-schools integration per
docs/dashboard_v3_schools_plan.md. This is a follow-up to the v2
polish that already landed on feat/dashboard — assume v2 is in
place (Mountain Time helpers, DayPicker, period-aware
recommendations, today's-verdict badge, vs-yesterday callout,
school-day shading).

What changes (in order):

  1. Extend TARGET_LOCATIONS in app/dashboard/lib/constants.ts to
     include primary_school, district, sensor_label, and
     nearby_schools per the data table in §"The school data" of
     the plan. The existing label / region fields stay for
     backward compat. Define and export a LocationMeta interface.

  2. Update components/LocationPicker.tsx so each button shows the
     primary_school as the headline, district as subtitle, and
     "+N nearby · {sensor_label}" as a footnote. Three-line label
     per button.

  3. Create components/NearbySchoolsChips.tsx — a reusable chip row
     that renders meta.nearby_schools, with the primary school
     highlighted via brand color and the rest in slate. Compact
     mode skips the "Schools served" lead-in label. Schools show
     their address on hover via the title attribute.

  4. Update components/PredictionCard.tsx to render
     <NearbySchoolsChips location={location} /> below the
     recommendation + vs-yesterday content. Add a top border-line
     separator so the chips feel like a footer section, not part
     of the verdict.

  5. Update components/PredictionDetailPanel.tsx to render
     <NearbySchoolsChips location={location} compact /> above the
     "What the model saw" feature snapshot.

  6. Update lib/plainLanguage.ts so plainLanguageHeadline uses
     meta.primary_school as the location label instead of
     meta.label. Result: "Air quality at Bonneville Elementary is
     predicted to be UNSAFE between 2 PM and 4 PM."

  7. Update app/page.tsx footer microcopy to the new "Each location
     pairs an OpenAQ sensor with the public K-5 schools in its air
     shed. Times shown in Mountain (MST/MDT)." string.

  8. Verify type safety. The new fields are additive; existing
     consumers of TARGET_LOCATIONS[key].label keep working unchanged.

Do NOT:

  - Add a geocoding API call, a map, or any external service.
  - Change the model, FastAPI surface, or any Python code.
  - Refactor v2 components beyond the touchpoints listed above.

After implementation:

  - Run `npm run typecheck` (must pass with zero errors).
  - Walk every item in the §"Acceptance checklist" of the spec doc.
  - Print a one-line summary of files changed and what visible
    difference each one makes for the principal stakeholder.
```

---

## Risk register

| Risk | Likelihood | Mitigation |
|---|---|---|
| Some school addresses are stale or schools have closed | Medium | Pre-merge verification step against each district's directory (5 min). Replace any school that doesn't verify with the next-closest from the same district. |
| Chip row gets too long on mobile and wraps awkwardly | Low | Tailwind `flex-wrap gap-1.5` already handles this. If still ugly, truncate to top-3 with "+1 more." |
| Headline change ("Bonneville Elementary" instead of "Red Butte") could confuse a TA who knows the architecture | Low | The PR description's "Stakeholder framing" section explicitly notes that the user-facing names are schools, not sensors. |
| Adding `primary_school` makes Decision 6 reasoning subtly different | Low | Decision 6 names locations, not schools. The schools are stakeholder UX, not architectural decisions. No INTERFACE.md change needed. |

---

## Time budget

| Step | Estimate |
|---|---|
| Address verification (Google Maps for medium/low confidence rows) | 10 min |
| `lib/constants.ts` type + data extension | 15 min |
| `components/NearbySchoolsChips.tsx` (new) | 20 min |
| `LocationPicker.tsx` three-line label refactor | 15 min |
| `PredictionCard.tsx` + `PredictionDetailPanel.tsx` chip integration | 15 min |
| `lib/plainLanguage.ts` headline label change | 5 min |
| `app/page.tsx` footer copy | 5 min |
| Typecheck + acceptance walkthrough | 10 min |
| **Total** | **~95 min** |
