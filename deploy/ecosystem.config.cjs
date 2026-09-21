module.exports = { apps: [{
  name: "m5", script: ".venv/bin/python", args: "-m mach5.server.app --host 127.0.0.1 --port 8751",
  cwd: "/root/match5", autorestart: true, max_restarts: 10,
  env: { PYTHONUNBUFFERED: "1" }
}]};
