import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, getJson, postForm, sendJson } from "./api";

describe("getJson", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("returns the parsed body on success", async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ ok: true }), { status: 200 }));
    expect(await getJson("/api/x")).toEqual({ ok: true });
  });

  it("throws ApiError with the backend's detail message on failure", async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ detail: "Roads have not been built" }), { status: 404 }));
    await expect(getJson("/api/x")).rejects.toMatchObject(
      new ApiError(404, "Roads have not been built"),
    );
  });

  it("falls back to a generic message when the error body isn't JSON", async () => {
    vi.mocked(fetch).mockResolvedValue(new Response("oops", { status: 500 }));
    await expect(getJson("/api/x")).rejects.toThrow("HTTP 500");
  });

  it("sendJson POSTs a JSON body with the right header", async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ id: 1 }), { status: 200 }));
    await sendJson("/api/x", "POST", { a: 1 });
    const [, init] = vi.mocked(fetch).mock.calls[0];
    expect(init?.method).toBe("POST");
    expect(init?.headers).toEqual({ "Content-Type": "application/json" });
    expect(init?.body).toBe(JSON.stringify({ a: 1 }));
  });

  it("sendJson without a body sends no body or content-type (used for DELETE)", async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ ok: true }), { status: 200 }));
    await sendJson("/api/x", "DELETE");
    const [, init] = vi.mocked(fetch).mock.calls[0];
    expect(init?.body).toBeUndefined();
    expect(init?.headers).toBeUndefined();
  });

  it("postForm posts multipart form data", async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ source_id: "s1" }), { status: 200 }));
    const form = new FormData();
    form.append("topic", "roads");
    const result = await postForm<{ source_id: string }>("/api/inbox/chennai/upload", form);
    expect(result.source_id).toBe("s1");
    const [, init] = vi.mocked(fetch).mock.calls[0];
    expect(init?.method).toBe("POST");
    expect(init?.body).toBe(form);
  });
});
