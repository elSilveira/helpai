# Using ChatGPT/Codex OAuth in a Personal Local Tool

This guide explains how to let users who already signed in to Codex use your local CLI/app without asking them for an OpenAI API key.

The safest approach is to integrate with **Codex app-server**, not to read OAuth tokens directly or call hidden ChatGPT backend endpoints yourself.

---

## Main idea

```txt
Your local CLI/app
   ↓ JSON-RPC
codex app-server
   ↓ handled by Codex
ChatGPT OAuth / Codex subscription
```

This is useful for:

```txt
Personal CLI tools
Local desktop apps
Local coding agents
VS Code-like integrations
Trusted internal developer tooling
```

It is **not recommended** for:

```txt
Public SaaS backends
Multi-user cloud apps
Browser-only apps
Untrusted machines
Production systems that need stable API guarantees
```

For normal production apps, use the OpenAI API key and API billing.

---

## Why use Codex app-server?

OpenAI Codex supports two auth modes:

```txt
ChatGPT sign-in
→ subscription access through Codex

API key
→ OpenAI Platform usage-based billing
```

So if your user already signed in with:

```bash
codex login
```

your local tool can interact with Codex through `codex app-server`.

You should **not** manually read:

```bash
~/.codex/auth.json
```

That file contains sensitive account tokens. Treat it like a password.

---

## Step 1 — Require Codex locally

Ask users to install Codex:

```bash
npm install -g @openai/codex
```

Then they log in:

```bash
codex login
```

For terminal-only or headless environments:

```bash
codex login --device-auth
```

---

## Step 2 — Start `codex app-server` from your app

Example in Node.js:

```ts
import { spawn } from "node:child_process";
import readline from "node:readline";

const codex = spawn("codex", ["app-server"], {
  stdio: ["pipe", "pipe", "pipe"],
});

const rl = readline.createInterface({
  input: codex.stdout,
});

let nextId = 1;
const pending = new Map<number, (value: any) => void>();

rl.on("line", (line) => {
  if (!line.trim()) return;

  const msg = JSON.parse(line);

  if (msg.id && pending.has(msg.id)) {
    pending.get(msg.id)!(msg);
    pending.delete(msg.id);
    return;
  }

  // Notifications from Codex:
  // turn/started, item/agentMessage/delta, turn/completed, etc.
  console.log("event:", msg);
});

function rpc(method: string, params?: any): Promise<any> {
  const id = nextId++;

  const payload = {
    id,
    method,
    params,
  };

  codex.stdin.write(JSON.stringify(payload) + "\n");

  return new Promise((resolve) => {
    pending.set(id, resolve);
  });
}
```

---

## Step 3 — Initialize the app-server session

Before calling other methods, initialize the connection:

```ts
await rpc("initialize", {
  clientInfo: {
    name: "my_local_cli",
    title: "My Local CLI",
    version: "0.1.0",
  },
});

codex.stdin.write(
  JSON.stringify({
    method: "initialized",
    params: {},
  }) + "\n"
);
```

---

## Step 4 — Check if the user is logged in

```ts
const account = await rpc("account/read", {
  refreshToken: true,
});

console.log(account);
```

A logged-in ChatGPT/Codex account may look conceptually like this:

```json
{
  "id": 1,
  "result": {
    "account": {
      "type": "chatgpt",
      "email": "user@example.com",
      "planType": "pro"
    },
    "requiresOpenaiAuth": true
  }
}
```

Do not rely too hard on the exact shape until you generate types from the installed Codex version.

---

## Step 5 — Trigger login if needed

Browser flow:

```ts
const login = await rpc("account/login/start", {
  type: "chatgpt",
});

console.log("Open this URL:", login.result.authUrl);
```

Device-code flow:

```ts
const login = await rpc("account/login/start", {
  type: "chatgptDeviceCode",
});

console.log("Go to:", login.result.verificationUrl);
console.log("Code:", login.result.userCode);
```

---

## Step 6 — Start a Codex thread

```ts
const threadRes = await rpc("thread/start", {
  cwd: process.cwd(),
});

const threadId = threadRes.result.thread.id;
```

Codex uses this rough structure:

```txt
Thread
→ conversation/session

Turn
→ one user request and one assistant execution

Item
→ messages, tool calls, deltas, logs, etc.
```

---

## Step 7 — Send a request to Codex

The exact request shape can change by Codex version, so generate types from the installed CLI:

```bash
codex app-server generate-ts --out ./codex-schema
```

Conceptually, your turn request will look like this:

```ts
await rpc("turn/start", {
  threadId,
  input: [
    {
      type: "text",
      text: "Analyze this repository and explain the architecture.",
    },
  ],
});
```

Then listen to notifications from stdout:

```ts
rl.on("line", (line) => {
  const msg = JSON.parse(line);

  switch (msg.method) {
    case "turn/started":
      console.log("Codex started working");
      break;

    case "item/agentMessage/delta":
      process.stdout.write(msg.params.delta);
      break;

    case "turn/completed":
      console.log("\nDone");
      break;

    default:
      console.log("event:", msg);
  }
});
```

Again, use generated types to confirm exact event names and payload shapes for your version.

---

## Step 8 — Package your CLI

Your CLI flow could be:

```txt
1. Check if `codex` exists
2. Start `codex app-server`
3. Initialize JSON-RPC session
4. Read account
5. If no account, start ChatGPT login
6. Start thread
7. Start turn
8. Stream events back to the user
```

Example check:

```ts
import { execSync } from "node:child_process";

function ensureCodexInstalled() {
  try {
    execSync("codex --version", { stdio: "ignore" });
  } catch {
    throw new Error(
      "Codex CLI is required. Install it with: npm install -g @openai/codex"
    );
  }
}
```

---

## Important security rules

Do **not** do this:

```txt
Read ~/.codex/auth.json
Extract access_token
Call hidden ChatGPT/Codex endpoints directly
Expose the token to your app frontend
Send the token to your backend
Commit the token
Log the token
```

Prefer this:

```txt
Let Codex own login
Let Codex own token refresh
Let Codex own model/backend calls
Talk to Codex through app-server
```

---

## What about an OpenAI-compatible local proxy?

Some projects expose something like:

```txt
http://127.0.0.1:10531/v1
```

and make it look similar to the OpenAI API.

Usually they do this by:

```txt
Reading local Codex OAuth tokens
Calling ChatGPT/Codex backend endpoints
Mapping those responses into OpenAI-compatible JSON
```

That can work for personal experiments, but it is fragile because:

```txt
It depends on internal endpoints
It may break when OpenAI changes Codex internals
It may violate intended auth boundaries
It makes token handling riskier
It is not suitable for public SaaS
```

Use that only as a local experiment, not as a production architecture.

---

## Recommended architecture

For a **personal local developer tool**:

```txt
User machine
  ├─ Your CLI
  └─ codex app-server
        └─ ChatGPT/Codex OAuth
```

For a **production app**:

```txt
Frontend
  ↓
Your backend
  ↓
OpenAI API key
  ↓
OpenAI API
```

For a **public SaaS**:

```txt
Your users log in to your app
Your backend owns OpenAI API billing
You manage quotas, plans, abuse prevention, and costs
```

---

## Final recommendation

If your goal is:

```txt
"Let users who already use Codex run my local agent without pasting an API key"
```

Use:

```txt
codex app-server
```

If your goal is:

```txt
"Let users use my cloud app without me paying API costs"
```

Do not use Codex OAuth for that. Use your own API billing model, user-provided API keys, or charge users inside your product.

---

## References

- OpenAI Codex authentication docs: https://developers.openai.com/codex/auth
- OpenAI Codex app-server README: https://github.com/openai/codex/blob/main/codex-rs/app-server/README.md
- OpenAI Codex CI/CD auth notes: https://developers.openai.com/codex/auth/ci-cd-auth
