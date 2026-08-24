import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import { api, ApiError } from "./api.ts";

const originalFetch = globalThis.fetch;

describe("api client", () => {
  afterEach(() => { globalThis.fetch = originalFetch; });

  it("returns parsed JSON", async () => {
    globalThis.fetch = async () => new Response(JSON.stringify({ status: "ok" }), { status: 200 });
    assert.deepEqual(await api<{ status: string }>("/health"), { status: "ok" });
  });

  it("surfaces backend detail without leaking response internals", async () => {
    globalThis.fetch = async () => new Response(JSON.stringify({ detail: "Источник не подключён" }), { status: 409 });
    await assert.rejects(api("/search/plan"), (error: unknown) => error instanceof ApiError && error.status === 409 && error.message === "Источник не подключён");
  });
});
