/**
 * quota-toast: omni-forge plugin that logs whenever the failover pool is
 * degraded, so exhausted-quota routing is never a mystery.
 *
 * The plugin hook surface is set by @opencode-ai/plugin; the module MUST
 * default-export a Plugin function (see packages/opencode-pack/README.md).
 * Auto-loaded from `.opencode/plugins/*.ts`; no config entry needed.
 */
import type { Plugin } from "@opencode-ai/plugin";

export default (async () => {
  return {
    "tool.execute.after": async (input) => {
      if (input.tool !== "forge_quota") return;
      try {
        const res = await fetch("http://127.0.0.1:4010/forge/quota");
        if (!res.ok) return;
        const data = (await res.json()) as {
          providers?: Array<{ name: string; healthy: boolean; cooling_reason?: string }>;
        };
        const down = (data.providers ?? []).filter((p) => !p.healthy);
        if (down.length) {
          console.log(
            `[omni-forge] providers unavailable: ${down
              .map((p) => `${p.name}${p.cooling_reason ? ` (${p.cooling_reason})` : ""}`)
              .join(", ")}. Remaining healthy: ${
              (data.providers ?? []).filter((p) => p.healthy).length
            }.`,
          );
        }
      } catch {
        /* router offline — nothing to monitor */
      }
    },
  };
}) satisfies Plugin;