#!/usr/bin/env bun
/**
 * Forge CLI: up, down, status, doctor, quota, gen, mcp
 */
const { $ } = await import("bun");

const ROOT = new URL("..", import.meta.url).pathname.replaceAll("\\", "/").replace(/\/$/, "");
const ENV = { ...process.env, FORGE_ROOT: ROOT };

function die(msg: string): never {
  console.error(`forge: ${msg}`);
  process.exit(1);
}

async function cmdUp() {
  await $`bun x pm2 start ecosystem.config.cjs --env production`.env(ENV);
  console.log("forge up");
}

async function cmdDown() {
  await $`bun x pm2 stop ecosystem.config.cjs || true`;
  await $`bun x pm2 delete ecosystem.config.cjs || true`;
  console.log("forge down");
}

async function cmdStatus() {
  await $`bun x pm2 status`.env(ENV);
  const r = await fetch("http://127.0.0.1:4010/forge/health").catch(() => null);
  const c = await fetch("http://127.0.0.1:4020/forge/health").catch(() => null);
  console.log("router:", r?.ok ? "ok" : "offline");
  console.log("core:", c?.ok ? "ok" : "offline");
}

async function cmdDoctor() {
  console.log("python:", (await $`python --version`.quiet()).stdout.toString().trim());
  console.log("bun:", (await $`bun --version`.quiet()).stdout.toString().trim());
  console.log("node:", (await $`node --version`.quiet()).stdout.toString().trim());
  const tests = ["curl -s http://127.0.0.1:4010/v1/models", "curl -s http://127.0.0.1:4020/"];
  for (const t of tests) {
    const res = await $`${{ raw: t }}`.quiet();
    console.log(t, res.exitCode === 0 ? "ok" : "fail");
  }
}

async function cmdQuota() {
  const res = await fetch("http://127.0.0.1:4010/forge/quota");
  if (!res.ok) die("router offline");
  const d = await res.json();
  console.table(d.providers);
}

async function cmdGen(sub: string[], rest: string[]) {
  switch (sub[0]) {
    case "image": {
      if (!rest.length) die("usage: forge gen image <prompt> [aspect]");
      const [prompt, aspect] = rest;
      const r = await fetch("http://127.0.0.1:4020/v1/image", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ prompt, aspect: aspect ?? "1:1" }),
      });
      const j = await r.json();
      if (!r.ok) die(JSON.stringify(j));
      console.log(j.url, `(backend: ${j.backend})`);
      break;
    }
    case "tts": {
      if (!rest.length) die("usage: forge gen tts <text> [voice]");
      const [text, voice] = rest;
      const r = await fetch("http://127.0.0.1:4020/v1/tts", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ text, voice }),
      });
      const j = await r.json();
      if (!r.ok) die(JSON.stringify(j));
      console.log(j.url, `(backend: ${j.backend})`);
      break;
    }
    default: die(`unknown gen subcommand: ${sub[0]}`);
  }
}

async function cmdMcp() {
  const mcp = new URL("../mcp/dist/index.js", import.meta.url);
  Bun.spawnSync({ cmd: ["node", mcp.pathname], stdio: ["inherit", "inherit", "inherit"] });
}

const [cmd, ...args] = process.argv.slice(2);
switch (cmd) {
  case "up": await cmdUp(); break;
  case "down": await cmdDown(); break;
  case "status": await cmdStatus(); break;
  case "doctor": await cmdDoctor(); break;
  case "quota": await cmdQuota(); break;
  case "gen": await cmdGen(args.slice(0, 1), args.slice(1)); break;
  case "mcp": await cmdMcp(); break;
  default: die("usage: forge [up|down|status|doctor|quota|gen|mcp]");
}