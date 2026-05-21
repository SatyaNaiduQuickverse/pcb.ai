# Deploying the coordination server (nova-coord)

How to stand up this project's own coordination instance so the master and worker
Claude sessions can talk and the project owner can watch from any device.

## What nova-coord is

A small FastAPI + HTML dashboard. It:
- tails each Claude session's transcript file (read-only) and renders a group chat;
- injects messages into a session's input via `tmux send-keys`;
- exposes `POST /send/<name>` over HTTP and serves the dashboard UI on a port.

Code: `github.com/SatyaNaiduQuickverse/nova-coord` (clone it with `gh` auth). Follow
that repo's own README for the exact config format and run command — the steps
below are the project-level setup around it.

## Topology for this project

The project owner's decision: **master, worker, and coord all run on the same
machine** (novatics64), each in its own tmux session.

That makes this simpler than a split-machine setup — **everything is local, no SSH.**
coord reads the two local tmux sessions' transcripts and sends to them directly.

```
novatics64
├── tmux session: master   (Claude — orchestrates)
├── tmux session: worker   (Claude — executes)
└── nova-coord             (reads both transcripts; injects into both tmux sessions;
                             serves dashboard + /send on its own port)
```

## Deploy steps

1. **Clone nova-coord** on novatics64 (`gh repo clone SatyaNaiduQuickverse/nova-coord`).
2. **Pick a free port — distinct from every other coord instance.** If another
   project's coord is already running (e.g. on 8765), use a different one (e.g.
   8766). Two coord instances on the same machine must not share a port.
3. **Configure it** for this project: the port; the master tmux session name + its
   JSONL transcript path; the worker tmux session name + its transcript path. (All
   local — no SSH host needed, unlike a split-machine deployment.)
4. **Run it** (background).
5. **Dashboard link:** `http://<novatics64-tailscale-name>:<port>/` — a *separate*
   link from any other project's dashboard.
6. **Record the chosen port + link** at the top of `docs/MASTER_WORKER_PROTOCOL.md`
   so both Claudes and the owner have one committed source for it.

## Verify before real work

Round-trip both directions:

```
# master -> worker
curl -X POST http://localhost:<port>/send/worker \
     -H 'content-type: application/json' \
     -d '{"text":"ping","from":"master","press_enter":true}'

# worker -> master
curl -X POST http://localhost:<port>/send/master \
     -H 'content-type: application/json' \
     -d '{"text":"pong","from":"worker","press_enter":true}'
```

Each message must land in the *other* session's input, prefixed `--- from X ---`,
and appear in the dashboard group chat. Only once both directions are confirmed
should real work start. See `MASTER_WORKER_PROTOCOL.md` for the messaging rules
(the mandatory `from` field, loop avoidance, what `/send` does not authorize).
