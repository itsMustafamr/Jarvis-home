# CLAUDE.md

How Claude works on the Jarvis-home project. Read this at the start of every session, then read `CONTEXT.md` for current state.

## The user

Rah. Solo developer. Code lives at `/Users/mohd7/Local/Jarvis-home` on his Mac (this folder, the local git clone) and at `/home/flash/jarvis` on his Jetson Orin Nano Super. Username on the Jetson is `flash`. Hostname is `flash-nano`.

## The deployment loop

Every change goes through this path:

1. Claude edits files in `/Users/mohd7/Local/Jarvis-home` on the Mac.
2. Rah commits and pushes to GitHub (`https://github.com/itsMustafamr/Jarvis-home`).
3. Rah SSHes to the Jetson, `cd ~/jarvis && git pull`.
4. Rah restarts whichever service was changed (`sudo systemctl restart jarvis-local` etc., or restarts the relevant tmux window).
5. Rah tests by pressing the Anker S3 call button and speaking.
6. Rah pastes logs back into the chat for Claude to verify.

Claude must always provide the git commit commands after a code change. Don't assume Rah remembers them.

## Testing rule — **always**

Whenever Claude makes a code change, before declaring it done, Claude must produce a **test plan** with:

1. **Concrete utterances** to speak into the Anker (or type into the browser). Not "try the feature" — actual sentences.
2. **Expected log output** — the specific lines Rah should see, including which `INTENT` tag identifies a fast-path vs LLM fallback.
3. **Where to fetch the logs from** — every test plan must include the exact command. Rah forgets which log lives where, so always remind him. **Always check whether he is running via systemd or manually in tmux before giving the command.**

   **If running via systemd** (after `systemd/install.sh` has been run):
   - `journalctl -u jarvis-local -f` — the Anker S3 button daemon (`local_input.py`). Memory, scheduler, time/timer/reminder, lights, weather, vision, LLM — all transit through here when the button is pressed.
   - `journalctl -u jarvis-server -f` — the WebSocket server (`server.py`), used only on the browser/phone path.
   - `journalctl -u llama-server -f` — the LLM. Look for `prompt eval time` / `eval time` to see token throughput, and `slot launch_slot_` to see when a request lands.

   **If running manually in tmux** (currently the default — `systemd/install.sh` has not been run):
   - The output prints to the tmux window. To also save it to a file, recommend Rah re-launch the script with `tee`:
     ```bash
     python3 local_input.py 2>&1 | tee /tmp/jarvis-local.log
     ```
     Then he can `cat /tmp/jarvis-local.log` after testing.
   - Alternative without restarting: inside tmux, `Ctrl-b :` → `pipe-pane -o "cat >> /tmp/jarvis-local.log"`. Same `Ctrl-b : pipe-pane` (no args) to stop.
   - **`journalctl -u jarvis-local` returns "No entries" in this mode — do not suggest it.**
4. **Pass/fail criteria** — what specifically tells Rah it worked or didn't.

Then Claude STOPS and waits for Rah to test and paste logs back. Don't move on to the next feature until Rah has confirmed.

## Reading the logs (cheat sheet)

In `local_input.py` logs:

- `CALL BUTTON: starting capture` — button was pressed
- `captured Ns -> /tmp/...wav (state=endpoint)` — VAD endpointed naturally; `state=timeout` means hit 15s cap; `state=no_speech` means nothing was heard
- `STT (Ns): '...'` — whisper transcript
- `INTENT memory: ...` / `INTENT time: ...` / `INTENT lights: ...` / `INTENT weather: ...` / `INTENT vision: ...` — fast-path took the request. If you see one of these, the LLM was bypassed.
- `LLM (Ns): '...'` — the request fell through to Gemma. **If you expected a fast path here, the regex missed.**
- `TTS (Ns): wrote ...` — Piper synthesised the reply
- `ANNOUNCE: '...'` — a scheduled timer/reminder fired

The single most important diagnostic is whether you see `INTENT xxx` or `LLM` — that tells you which path was taken.

## Code conventions

- File location for new code: top level of the repo. Module-per-file. Keep modules small enough that they read top-to-bottom.
- All Python paths in production reference `Path.home() / "jarvis" / ...` — avoid hard-coding `/home/flash/`.
- Persistent state goes in `~/jarvis/data/` (gitignored). SQLite for structured, JSON for flat.
- Intent matchers expose three things: `RX_*` patterns, `is_X_intent(text)` predicate, `handle(text) -> Optional[str]`. `handle()` returns the reply string if it handled the intent, `None` to fall through.
- New intents get plumbed in `pipeline._route_inner()`, ordered so more specific matchers run before more general ones.
- Anything that needs to speak from a background task uses `scheduler.get_scheduler().schedule_in(...)`. The Anker speaker is the only output sink in v1.
- systemd units live in `systemd/`. Each Python service uses `/home/flash/jarvis-venv/bin/python3` as `ExecStart` — never `/usr/bin/python3`, which lacks `ultralytics` / `torch` / `silero-vad`.

## What Claude does NOT do

- Don't ship code without a test plan attached.
- Don't claim a feature works just because the regex matched in a smoke test; always have Rah verify with real STT input through the Anker.
- Don't silently let LLM fallback fabricate confirmations. If the LLM might be asked to do something it can't actually do (set timers, control devices), the system prompt and few-shot examples must explicitly tell it to refuse.
- Don't fabricate technical facts. If unsure about a library, an API, a flag, or a version, say "I'm not sure" and search before answering.
- Don't keep using a stale `CONTEXT.md` — update it at the end of each change. If a session has produced more than ~3 features or bug fixes, append to CONTEXT.md before responding to the next message.

## Updating CONTEXT.md

After any of:

- A new feature is shipped and tested
- A bug is fixed
- A new file is added to the repo
- An architecture decision is made
- A future plan is added or removed
- Setup (paths, venv, devices, IPs) changes

…edit `CONTEXT.md` to reflect the new reality. Add a dated line under "Recent work" with a one-line description.

## Starting a fresh session

When Rah opens a new chat and asks Claude to continue:

1. Read `CLAUDE.md` (this file)
2. Read `CONTEXT.md` (current state, completed work, open bugs, plans)
3. Glance at the file list (`ls` the repo) to see if anything has been added that CONTEXT.md hasn't caught up to yet
4. Acknowledge what was last completed and what's next per `CONTEXT.md`, then ask Rah what he wants to tackle.
