import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";
import "@testing-library/jest-dom/vitest";

// testing-library's auto-cleanup only registers itself when `afterEach` is a global
// (vitest `globals: true`); we don't enable that, so unmount explicitly between tests.
afterEach(() => {
  cleanup();
});
