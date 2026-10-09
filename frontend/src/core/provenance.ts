// How much to trust a number, shown the same way everywhere in the app.
export type WidthSource = "estimated" | "measured" | "verified";

export const CONFIDENCE: Record<WidthSource, { label: string; color: string; badge: string; help: string }> = {
  estimated: {
    label: "Estimated",
    color: "#9ca3af",
    badge: "bg-slate-200 text-slate-700",
    help: "Typical width for this type of road. Rough; not measured.",
  },
  measured: {
    label: "Measured",
    color: "#eab308",
    badge: "bg-yellow-100 text-yellow-800",
    help: "Measured from building footprints on either side. Good, not exact.",
  },
  verified: {
    label: "Verified",
    color: "#16a34a",
    badge: "bg-green-100 text-green-800",
    help: "From a survey, official record or on-site measurement.",
  },
};

// How much a 'measured' width's own samples agreed with each other (IQR relative to width).
// Only applies within width_source === "measured" — estimated/verified don't carry this.
export type WidthConfidence = "reliable" | "check" | "unreliable";

export const MEASURED_CONFIDENCE: Record<WidthConfidence, { label: string; color: string; badge: string; help: string }> = {
  reliable: {
    label: "Reliable",
    color: "#65a30d",
    badge: "bg-lime-100 text-lime-800",
    help: "The width samples along this road agreed closely (IQR ≤ 15% of the width). Trust it.",
  },
  check: {
    label: "Check first",
    color: "#f59e0b",
    badge: "bg-amber-100 text-amber-800",
    help: "The width samples disagreed somewhat (IQR 15–30% of the width). Worth a second look before relying on it.",
  },
  unreliable: {
    label: "Unreliable",
    color: "#dc2626",
    badge: "bg-red-100 text-red-800",
    help: "The width samples disagreed a lot (IQR over 30% of the width). Don't design against this — get it surveyed.",
  },
};
