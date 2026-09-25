import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { SearchHit } from "./api";
import { roadsApi } from "./api";
import RoadSearch from "./RoadSearch";

vi.mock("./api", () => ({ roadsApi: { search: vi.fn() } }));

const HIT: SearchHit = { name: "North Usman Road", segments: 44, length_m: 2802, road_class: "secondary", bbox: [0, 0, 0, 0] };

beforeEach(() => {
  vi.mocked(roadsApi.search).mockReset();
});
afterEach(() => {
  vi.useRealTimers();
});

describe("RoadSearch", () => {
  it("does not search until at least two characters are typed", async () => {
    const user = userEvent.setup();
    render(<RoadSearch cityId="chennai" onPick={vi.fn()} />);
    await user.type(screen.getByPlaceholderText("Search a road by name…"), "N");
    await new Promise((r) => setTimeout(r, 300));
    expect(roadsApi.search).not.toHaveBeenCalled();
  });

  it("searches (debounced) and shows results", async () => {
    vi.mocked(roadsApi.search).mockResolvedValue([HIT]);
    const user = userEvent.setup();
    render(<RoadSearch cityId="chennai" onPick={vi.fn()} />);
    await user.type(screen.getByPlaceholderText("Search a road by name…"), "usman");

    await waitFor(() => expect(roadsApi.search).toHaveBeenCalledWith("chennai", "usman"));
    expect(await screen.findByText("North Usman Road")).toBeInTheDocument();
    expect(screen.getByText(/2.8 km/)).toBeInTheDocument();
    expect(screen.getByText(/44 segments/)).toBeInTheDocument();
  });

  it("calls onPick and fills the input when a result is chosen", async () => {
    vi.mocked(roadsApi.search).mockResolvedValue([HIT]);
    const onPick = vi.fn();
    const user = userEvent.setup();
    render(<RoadSearch cityId="chennai" onPick={onPick} />);
    await user.type(screen.getByPlaceholderText("Search a road by name…"), "usman");
    await user.click(await screen.findByText("North Usman Road"));

    expect(onPick).toHaveBeenCalledWith(HIT);
    expect(screen.getByPlaceholderText("Search a road by name…")).toHaveValue("North Usman Road");
    expect(screen.queryByText(/44 segments/)).not.toBeInTheDocument(); // list closed after pick
  });

  it("shows a no-match message when the search comes back empty", async () => {
    vi.mocked(roadsApi.search).mockResolvedValue([]);
    const user = userEvent.setup();
    render(<RoadSearch cityId="chennai" onPick={vi.fn()} />);
    await user.type(screen.getByPlaceholderText("Search a road by name…"), "zzzzz");
    expect(await screen.findByText(/No named road matches/)).toBeInTheDocument();
  });

  it("a failed search is treated as no results, not an error", async () => {
    vi.mocked(roadsApi.search).mockRejectedValue(new Error("network down"));
    const user = userEvent.setup();
    render(<RoadSearch cityId="chennai" onPick={vi.fn()} />);
    await user.type(screen.getByPlaceholderText("Search a road by name…"), "usman");
    expect(await screen.findByText(/No named road matches/)).toBeInTheDocument();
  });
});
