/* pm2 definition behind `forge up` / `forge down`. */
const python = process.env.FORGE_PYTHON || "python";

module.exports = {
  apps: [
    {
      name: "forge-router",
      cwd: `${__dirname}/apps/router`,
      script: python,
      args: "-m uvicorn forge_router.main:app --host 127.0.0.1 --port 4010",
      interpreter: "none",
      autorestart: true,
      env: { PYTHONPATH: `${__dirname}/apps/router` },
    },
    {
      name: "forge-core",
      cwd: `${__dirname}/apps/core`,
      script: python,
      args: "-m uvicorn forge_core.main:app --host 127.0.0.1 --port 4020",
      interpreter: "none",
      autorestart: true,
      env: { PYTHONPATH: `${__dirname}/apps/core` },
    },
  ],
};