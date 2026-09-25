import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { readFile } from "node:fs/promises";
import { z } from "zod";
const CORE = process.env.FORGE_CORE_URL ?? "http://127.0.0.1:4020";
const ROUTER = process.env.FORGE_ROUTER_URL ?? "http://127.0.0.1:4010";
const server = new McpServer({ name: "omni-forge", version: "0.1.0" });
async function postJson(url, body) {
    const res = await fetch(url, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
    });
    if (!res.ok)
        throw new Error(`forge ${res.status}: ${await res.text()}`);
    return res.json();
}
async function textReply(data) {
    return { content: [{ type: "text", text: JSON.stringify(data, null, 2) }] };
}
server.tool("forge_image", "Generate an image via the omni-forge core (ComfyUI → Pollinations free fallback).", { prompt: z.string().describe("Detailed image prompt"), aspect: z.string().optional() }, async ({ prompt, aspect }) => textReply(await postJson(`${CORE}/v1/image`, { prompt, aspect: aspect ?? "1:1" })));
server.tool("forge_video", "Submit a short-video generation job (Wan 2.1). Returns a job_id to poll.", { prompt: z.string().describe("Shot description") }, async ({ prompt }) => textReply(await postJson(`${CORE}/v1/video`, { prompt })));
server.tool("forge_video_status", "Poll a video job until 'done' or 'error'.", { job_id: z.string() }, async ({ job_id }) => {
    const res = await fetch(`${CORE}/v1/video/${job_id}`);
    if (!res.ok)
        throw new Error(`forge ${res.status}`);
    return textReply(await res.json());
});
server.tool("forge_tts", "Synthesize speech to an mp3 file.", { text: z.string(), voice: z.string().optional() }, async ({ text, voice }) => textReply(await postJson(`${CORE}/v1/tts`, { text, voice })));
server.tool("forge_asr", "Transcribe an audio file to text.", { path: z.string().describe("Absolute path to an audio file") }, async ({ path }) => {
    const audio = await readFile(path);
    const form = new FormData();
    form.append("file", new Blob([audio]), path.split(/[\\/]/).pop() ?? "audio.wav");
    const res = await fetch(`${CORE}/v1/asr`, { method: "POST", body: form });
    if (!res.ok)
        throw new Error(`forge ${res.status}: ${await res.text()}`);
    return textReply(await res.json());
});
server.tool("forge_vision", "Ask questions about an image file (vision-language model via the router).", { path: z.string(), prompt: z.string() }, async ({ path, prompt }) => {
    const image = await readFile(path);
    const base64 = image.toString("base64");
    return textReply(await postJson(`${CORE}/v1/vision`, { prompt, image_base64: base64 }));
});
server.tool("forge_search", "Search the web (SearXNG or DuckDuckGo fallback).", { q: z.string(), limit: z.number().int().optional() }, async ({ q, limit }) => textReply(await postJson(`${CORE}/v1/search`, { q, limit })));
server.tool("forge_quota", "Show free-tier quota/health of every failover provider.", {}, async () => {
    const res = await fetch(`${ROUTER}/forge/quota`);
    if (!res.ok)
        throw new Error(`forge ${res.status}`);
    return textReply(await res.json());
});
const transport = new StdioServerTransport();
await server.connect(transport);
