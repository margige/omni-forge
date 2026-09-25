#!/usr/bin/env bun
/**
 * Forge CLI: up, down, status, doctor, quota, gen, mcp.
 *
 * I18N: messages follow FORGE_LANG, LANG or LC_ALL (zh/ja/ko detected, else en).
 */
const { $ } = await import("bun");

const LANG = pickLang();

const MSG: Record<string, Record<string, string>> = {
  en: {
    usage: "usage: forge [up|down|status|doctor|quota|gen|mcp]",
    usageGenImage: "usage: forge gen image <prompt> [aspect]",
    usageGenTts: "usage: forge gen tts <text> [voice]",
    unknownSub: "unknown gen subcommand: {0}",
    routerOffline: "router offline",
    router: "router",
    core: "core",
    ok: "ok",
    offline: "offline",
    upDone: "forge up",
    downDone: "forge down",
  },
  zh: {
    usage: "用法: forge [up|down|status|doctor|quota|gen|mcp]",
    usageGenImage: "用法: forge gen image <提示词> [宽高比]",
    usageGenTts: "用法: forge gen tts <文本> [音色]",
    unknownSub: "未知的 gen 子命令: {0}",
    routerOffline: "路由器离线",
    router: "路由器",
    core: "核心服务",
    ok: "正常",
    offline: "离线",
    upDone: "forge up",
    downDone: "forge down",
  },
  ja: {
    usage: "使い方: forge [up|down|status|doctor|quota|gen|mcp]",
    usageGenImage: "使い方: forge gen image <プロンプト> [アスペクト比]",
    usageGenTts: "使い方: forge gen tts <テキスト> [音声]",
    unknownSub: "不明な gen サブコマンド: {0}",
    routerOffline: "ルーター停止中",
    router: "ルーター",
    core: "コア",
    ok: "正常",
    offline: "停止中",
    upDone: "forge up",
    downDone: "forge down",
  },
  ko: {
    usage: "사용법: forge [up|down|status|doctor|quota|gen|mcp]",
    usageGenImage: "사용법: forge gen image <프롬프트> [비율]",
    usageGenTts: "사용법: forge gen tts <텍스트> [음성]",
    unknownSub: "알 수 없는 gen 하위 명령: {0}",
    routerOffline: "라우터 오프라인",
    router: "라우터",
    core: "코어",
    ok: "정상",
    offline: "오프라인",
    upDone: "forge up",
    downDone: "forge down",
  },
};

function pickLang(): "en" | "zh" | "ja" | "ko" {
  const raw = (
    process.env.FORGE_LANG || process.env.LANG || process.env.LC_ALL || "en"
  ).toLowerCase();
  if (raw.startsWith("zh")) return "zh";
  if (raw.startsWith("ja")) return "ja";
  if (raw.startsWith("ko") || raw.startsWith("kr")) return "ko";
  return "en";
}

function t(key: string, ...args: string[]): string {
  let s = MSG[LANG]?.[key] ?? MSG.en[key] ?? key;
  args.forEach((a, i) => {
    s = s.split(`{${i}}`).join(a);
  });
  return s;
}

const ROOT = new URL("..", import.meta.url).pathname.replaceAll("\\", "/").replace(/\/$/, "");
const ENV = { ...process.env, FORGE_ROOT: ROOT };

function die(msg: string): never {
  console.error(`forge: ${msg}`);
  process.exit(1);
}

async function cmdUp() {
  await $`bun x pm2 start ecosystem.config.cjs --env production`.env(ENV);
  console.log(t("upDone"));
}

async function cmdDown() {
  await $`bun x pm2 stop ecosystem.config.cjs || true`;
  await $`bun x pm2 delete ecosystem.config.cjs || true`;
  console.log(t("downDone"));
}

async function cmdStatus() {
  await $`bun x pm2 status`.env(ENV);
  const r = await fetch("http://127.0.0.1:4010/forge/health").catch(() => null);
  const c = await fetch("http://127.0.0.1:4020/forge/health").catch(() => null);
  console.log(`${t("router")}: ${r?.ok ? t("ok") : t("offline")}`);
  console.log(`${t("core")}: ${c?.ok ? t("ok") : t("offline")}`);
}

async function cmdDoctor() {
  const mk = async (label: string, cmd: string[]) => {
    const row = await $`${{ raw: cmd.join(" ") }}`.quiet().nothrow();
    console.log(`${label}: ${row.stdout.toString().trim() || row.stderr.toString().trim() || "?"} ${row.exitCode === 0 ? "✓" : t("offline")}`);
  };
  mk("python", ["python", "--version"]);
  mk("bun", ["bun", "--version"]);
  mk("node", ["node", "--version"]);
  const tests = [
    ["router", "curl", "-s", "http://127.0.0.1:4010/v1/models"],
    ["core", "curl", "-s", "http://127.0.0.1:4020/"],
  ];
  for (const [name, ...cmd] of tests) {
    const res = await $`${{ raw: cmd.join(" ") }}`.quiet().nothrow();
    console.log(`${name}: ${res.exitCode === 0 ? t("ok") : t("offline")}`);
  }
}

async function cmdQuota() {
  const res = await fetch("http://127.0.0.1:4010/forge/quota");
  if (!res.ok) die(t("routerOffline"));
  const d = await res.json();
  console.table(d.providers);
}

async function cmdGen(sub: string[], rest: string[]) {
  switch (sub[0]) {
    case "image": {
      if (!rest.length) die(t("usageGenImage"));
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
      if (!rest.length) die(t("usageGenTts"));
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
    default: die(t("unknownSub", sub[0] ?? ""));
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
  default: die(t("usage"));
}