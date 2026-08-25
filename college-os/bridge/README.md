# Compass Bridge — the data plane

This is how Compass reads Google Workspace: a read-only Apps Script Web App you deploy in **your
own** Google account, which Compass calls with a shared token. Google charges nothing for it, and
no connector platform ever sees your data.

| | This bridge |
|---|---|
| Cost | free |
| Setup | one script, one deploy |
| Google Cloud project | the script's own auto-created one; you enable five APIs on it, once |
| Re-authorization | once, and it doesn't expire |
| Covers | Drive · Docs · Sheets · Slides · Calendar · Gmail (+ Tasks) |
| GitHub | a free read-only PAT |
| Google Meet | **no** — see below |

---

## Deploy it

**Do this in a NEW Apps Script project — not the one running `setup.gs`.** That separation is the
point: `setup.gs` needs write scopes to build the College OS, and this bridge must never have them.
Its manifest asks for `*.readonly` scopes only, so "Compass cannot change anything in my Google
account" is enforced by Google's OAuth layer rather than by trusting the code.

1. **script.google.com** → **New project**. Name it `Compass Bridge`.
2. Paste `api.gs` into `Code.gs`.
3. ⚙️ **Project Settings** → check *"Show appsscript.json manifest file"*, open the manifest, and
   replace it with `appsscript.json` from this folder. Set `timeZone` if you aren't on Eastern.
4. Run **`setUpBridge`**. Approve the OAuth prompt — it's your own script, so Google shows the
   "unverified app" warning (*Advanced* → *Go to project*). **Copy the token it prints.**
5. **Enable the five Google APIs this bridge calls.** Apps Script creates a Cloud project for your
   script automatically, but its APIs start switched off, so every read returns `google_api_403`
   until you turn them on. Run `testBridge` once — it prints the project number and a console link
   in the failure text — then enable, waiting a minute for each to propagate:

   Drive · Calendar · Gmail · Sheets · Tasks

   Only Drive, Calendar, Gmail and Tasks show up in the test output; **Sheets needs enabling too**,
   because the Sheets probe reads through Drive and only fails later, on a dashboard read.

   There is no cost — these APIs are free at any volume Compass generates. You never write code in
   the Cloud Console; you only flip five switches.
6. Run **`testBridge`** again. It exercises every scope and prints one line per connector, so you
   find a missing grant now rather than mid-session.
7. **Deploy** → **New deployment** → type **Web app**:
   - Execute as: **Me**
   - Who has access: **Anyone**

   Copy the `/exec` URL.
8. In Compass: **Settings → Connections** → paste the URL and token → *Connect bridge*. Compass
   verifies the deployment before saving anything.

Prefer configuring it once for every local profile? Put `COMPASS_BRIDGE_URL` and
`COMPASS_BRIDGE_TOKEN` in the workspace `.env` instead. Per-profile settings win over `.env`.

### GitHub

Not a Google service, so the bridge can't serve it. Create a
[fine-grained PAT](https://github.com/settings/tokens) with **read-only** access to the repos you
want tracked (Contents + Pull requests), and paste it into the same settings page. Free.

---

## About "Who has access: Anyone"

That setting is required for a program to call the deployment without a Google login. It does not
make your data public on its own:

- Every request must carry the token from `setUpBridge`. Without it the script returns
  `unauthorized` and does nothing.
- The token is compared in constant time, so a wrong guess leaks nothing by timing.
- The `/exec` URL itself is a long unguessable string.

**Treat the URL and token together as a password.** Anyone holding both can read what the scopes
allow. If either leaks, run **`rotateBridgeToken`** and re-paste the new token into Compass — the old
one stops working immediately.

---

## What it will not do

**Google Meet is unavailable.** The Meet REST API needs a Google Cloud project with the API enabled,
which is precisely the setup cost this path exists to avoid. Compass marks the Meet connector
`unsupported` and drops `meet_attended` from the evidence types it offers, rather than quietly
proposing evidence it can never observe.

**Nothing is written, ever.** The manifest has no write scopes to grant, and `HANDLERS` is an
allowlist — a capability name that isn't in it is rejected before anything runs.

**Message bodies are never read.** `gmail.get_message` requests `format=metadata`, so the script
receives headers and the snippet Gmail itself displays, and nothing else.

---

## Bonus: Google Tasks

Compass has never been able to see Google Tasks — which is why the COLLEGE DASHBOARD's `Tasks`
evidence rows degrade to manual confirmation. This bridge serves
`tasks.list_tasklists` and `tasks.list_tasks`, so that gap is now closeable. Compass does not consume
them yet; the endpoints are here and working, waiting on a `task_completed` evidence type.

---

## Troubleshooting

| Symptom in Compass | Cause |
|---|---|
| `bridge_not_public` — "returned a Google sign-in page" | Deployment access isn't **Anyone**. Redeploy. |
| `bridge_unauthorized` | Token mismatch. Re-run `setUpBridge` and copy the printed value. |
| `bridge_url_invalid` | Not the `/exec` deployment URL. The `/dev` URL won't work — it requires a login. |
| `bridge_not_set_up` | `setUpBridge` was never run in this project. |
| `google_api_403` on one connector | That scope wasn't approved. Re-run `testBridge`, then re-authorize. |

Changed `api.gs`? Apps Script serves the **deployed version**, not the editor's. Use
**Deploy → Manage deployments → edit → Version: New version**, or your edits won't take effect.
