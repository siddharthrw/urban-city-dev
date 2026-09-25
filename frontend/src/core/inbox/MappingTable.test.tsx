import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { FieldSpec, Preview } from "./api";
import MappingTable, { mappingProblems, type Mapping } from "./MappingTable";

const FIELDS: FieldSpec[] = [
  { field: "cars", label: "Cars", type: "int", min: 0 },
  { field: "width_m", label: "Width", type: "float", required: true, min: 2, max: 150 },
  { field: "road_name", label: "Road name", type: "string" },
  { field: "latitude", label: "Latitude", type: "float" },
  { field: "longitude", label: "Longitude", type: "float" },
];

const COLUMNS: Preview["columns"] = [
  { name: "Cars", type: "number", filled: 5 },
  { name: "ROW (m)", type: "number", filled: 5 },
  { name: "Road", type: "text", filled: 5 },
];

describe("mappingProblems", () => {
  it("flags a missing required field", () => {
    const problems = mappingProblems(FIELDS, {}, false);
    expect(problems.some((p) => p.includes("Width"))).toBe(true);
  });
  it("requires a location: lat+lon or road name", () => {
    const mapping: Mapping = { width_m: { column: "ROW (m)", method: "auto", score: 100 } };
    expect(mappingProblems(FIELDS, mapping, false).some((p) => p.includes("location"))).toBe(true);
  });
  it("is satisfied by a road name alone", () => {
    const mapping: Mapping = {
      width_m: { column: "ROW (m)", method: "auto", score: 100 },
      road_name: { column: "Road", method: "auto", score: 100 },
    };
    expect(mappingProblems(FIELDS, mapping, false)).toEqual([]);
  });
  it("rejects latitude without longitude", () => {
    const mapping: Mapping = {
      width_m: { column: "ROW (m)", method: "auto", score: 100 },
      latitude: { column: "Cars", method: "manual", score: null },
    };
    expect(mappingProblems(FIELDS, mapping, false).some((p) => p.includes("both Latitude"))).toBe(true);
  });
  it("skips the location check when the file already has geometry", () => {
    const mapping: Mapping = { width_m: { column: "ROW (m)", method: "auto", score: 100 } };
    expect(mappingProblems(FIELDS, mapping, true)).toEqual([]);
  });
});

describe("MappingTable", () => {
  it("shows required fields marked, and lets you change a column", async () => {
    const onChange = vi.fn();
    render(
      <MappingTable
        fields={FIELDS}
        columns={COLUMNS}
        mapping={{ width_m: { column: "ROW (m)", method: "auto", score: 92 } }}
        hasGeometry={false}
        onChange={onChange}
      />,
    );
    expect(screen.getByText("*")).toBeInTheDocument(); // required marker on Width
    expect(screen.getByLabelText("Column for Width")).toHaveValue("ROW (m)");

    await userEvent.selectOptions(screen.getByLabelText("Column for Cars"), "Cars");
    expect(onChange).toHaveBeenCalledWith("cars", "Cars");
  });

  it("disables a column already used by another field", () => {
    render(
      <MappingTable
        fields={FIELDS}
        columns={COLUMNS}
        mapping={{
          width_m: { column: "ROW (m)", method: "auto", score: 92 },
          cars: { column: "Cars", method: "auto", score: 100 },
        }}
        hasGeometry={false}
        onChange={vi.fn()}
      />,
    );
    const roadSelect = screen.getByLabelText("Column for Road name") as HTMLSelectElement;
    const carsOption = [...roadSelect.options].find((o) => o.value === "Cars")!;
    expect(carsOption.disabled).toBe(true);
  });

  it("hides latitude/longitude rows when the file already has geometry", () => {
    render(
      <MappingTable fields={FIELDS} columns={COLUMNS} mapping={{}} hasGeometry={true} onChange={vi.fn()} />,
    );
    expect(screen.queryByLabelText("Column for Latitude")).not.toBeInTheDocument();
  });
});
