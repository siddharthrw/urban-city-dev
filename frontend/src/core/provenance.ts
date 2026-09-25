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
