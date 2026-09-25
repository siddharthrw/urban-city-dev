import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import CrossSection from "./CrossSection";
import type { DesignElement, ElementKind } from "./api";

const el = (kind: ElementKind, width_cm: number, side: DesignElement["side"] = "left"): DesignElement => ({
  kind, label: kind === "tree_strip" ? "Trees" : kind[0].toUpperCase() + kind.slice(1).replace("_", " "),
  side, width_cm, width_m: width_cm / 100, rule_ids: [], fallback_minimum: false,
});

// The plan's 18 m "Balanced" example.
const ELEMENTS = [el("footpath", 200), el("tree_strip", 150), el("cycle_track", 200), el("lane", 350),
  el("lane", 350), el("cycle_track", 200), el("tree_strip", 150), el("footpath", 200)];

describe("CrossSection", () => {
  it("draws one rectangle per element", () => {
    render(<CrossSection elements={ELEMENTS} rowCm={1800} />);
    expect(screen.getAllByTestId("element")).toHaveLength(8);
  });

  it("draws every rectangle to scale: width is exactly its share of the right-of-way", () => {
    render(<CrossSection elements={ELEMENTS} rowCm={1800} />);
    const rects = screen.getAllByTestId("element");
    rects.forEach((r) => {
      const cm = Number(r.getAttribute("data-width-cm"));
      expect(Number(r.getAttribute("width"))).toBeCloseTo((cm / 1800) * 1000, 6);
    });
    const total = rects.reduce((s, r) => s + Number(r.getAttribute("width")), 0);
    expect(total).toBeCloseTo(1000, 6); // fills the whole drawing, no gaps or overflow
  });

  it("places rectangles edge to edge from left to right", () => {
    render(<CrossSection elements={ELEMENTS} rowCm={1800} />);
    const rects = screen.getAllByTestId("element");
    let expected = 0;
    rects.forEach((r) => {
      expect(Number(r.getAttribute("x"))).toBeCloseTo(expected, 6);
      expected += Number(r.getAttribute("width"));
    });
  });

  it("labels the overall width and each element's width in metres", () => {
    const { container } = render(<CrossSection elements={ELEMENTS} rowCm={1800} />);
    expect(screen.getByText("18 m right-of-way")).toBeInTheDocument();
    const texts = [...container.querySelectorAll("text")].map((t) => t.textContent);
    expect(texts.filter((t) => t === "2")).toHaveLength(4); // four 2 m elements
    expect(texts.filter((t) => t === "3.5")).toHaveLength(2);
    expect(texts.filter((t) => t === "1.5")).toHaveLength(2);
  });

  it("gives screen readers the full description", () => {
    render(<CrossSection elements={ELEMENTS} rowCm={1800} title="Balanced" />);
    const label = screen.getByRole("img").getAttribute("aria-label")!;
    expect(label).toContain("Balanced cross-section, 18 m");
    expect(label).toContain("Cycle track 2 m");
    expect(label).toContain("Lane 3.5 m");
  });

  it("shows a legend with each kind once", () => {
    render(<CrossSection elements={ELEMENTS} rowCm={1800} />);
    const items = screen.getAllByRole("listitem").map((i) => i.textContent);
    expect(items).toEqual(["Footpath", "Trees", "Cycle track", "Lane"]);
  });

  it("omits text inside slivers too narrow to read but still draws them", () => {
    const thin = [el("footpath", 30), el("lane", 5970)];
    const { container } = render(<CrossSection elements={thin} rowCm={6000} />);
    expect(screen.getAllByTestId("element")).toHaveLength(2);
    const texts = [...container.querySelectorAll("text")].map((t) => t.textContent);
    expect(texts).not.toContain("0.3");
  });

  it("scales a different road width correctly", () => {
    render(<CrossSection elements={[el("footpath", 300), el("lane", 300), el("footpath", 300)]} rowCm={900} />);
    screen.getAllByTestId("element").forEach((r) => expect(Number(r.getAttribute("width"))).toBeCloseTo(1000 / 3, 6));
    expect(screen.getByText("9 m right-of-way")).toBeInTheDocument();
  });
});
