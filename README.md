# TeachDesk

A Windows desktop prototype for explicitly taught, visually verified workflows. It stores demonstrations locally, asks a configured vision model for a structured candidate workflow, and executes a reviewed workflow through the real Windows cursor and keyboard. The product contains no game-specific coordinates, game APIs, browser sessions, shell execution nodes, or hardcoded learned skills.

**Status:** version 0.2.0 adds a project-first interface: **New Project / Open Project → Teach → Review → Practice / Run**. Technical tools live in Settings → Project details. Existing data and the 0.1.3 HWND capture engine are preserved. Learning percentages still come from explicit checks; choosing a percentage cannot mark a task ready. **98 cloud tests pass; seven native Windows checks and real model learning remain pending.** User screenshots verify the first READY and final COMPLETE frames of a 0.1.3 recording, including a pause afterward; they do not establish native input or model competence.

**New here?** Start with the [beginner’s guide](docs/BEGINNERS_GUIDE.md) for a plain-English explanation and a step-by-step installation, teaching and testing walkthrough.

## Run on Windows

Requirements: Windows 10 2004+/11 (x64 graphics capture support), **64-bit Python 3.12**, an unlocked ordinary user session, one enabled monitor, and a standard, non-elevated application. Keep display scaling unchanged between teaching and practice. Start with the included lab, outside any sensitive application.

**Beginner launch:** after extracting the latest source ZIP, double-click **`Launch TeachDesk.cmd`** in the project folder. It creates/refreshes the local Python environment on its first use, installs the pinned dependencies, and launches the app. Later launches reuse the prepared environment. Keep its console open while TeachDesk runs. This launcher uses ordinary Python commands and does not change PowerShell execution policy. CMD startup was observed on Windows for earlier releases; the new graphics capture backend still needs Windows verification.

From this project directory in PowerShell:

```powershell
.\scripts\setup.ps1 -Test
.\scripts\launch.ps1
```

If local policy prevents running PowerShell scripts, the equivalent commands are:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip uninstall -y opencv-python-headless
.\.venv\Scripts\python.exe -m pip install -c constraints.txt -e . pytest==9.1.1
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m teachdesk.ui
```

There is no packaged Windows executable yet. Installation uses PyPI over verified TLS. Runtime/development dependency versions are pinned in `pyproject.toml` and `constraints.txt`; the build backend is setuptools. No external database or server is needed.

Capture uses the `windows-capture` 2.0.1 Windows x64 wheel, which wraps Microsoft Windows Graphics Capture. Each requested frame uses the exact selected HWND; there is no desktop-image fallback. Its native session stops after that frame (or an error/timeout). The default OS capture border remains enabled. Secondary windows retain Windows' default exclusion. The image size must match physical DWM visible bounds; mismatches pause capture instead of guessing scaling. `mss` is used only to enumerate display geometry. OpenCV uses its regular Windows distribution because the capture wrapper requires it; Linux retains the headless distribution. Setup removes the old headless package from an upgraded Windows environment to avoid competing `cv2` files.

This source adds no external service or paid API requirement. Windows capture requires compatible graphics support; protected/unsupported surfaces or driver failures may give no usable image. Per-frame session startup adds overhead: four frames per second is a best-effort sampling target, not a guaranteed rate. Do not use an older desktop-crop recording for learning; use a new task or remove older demonstrations through the UI and record again.

## First project: the controlled lab

1. Choose **New Project**, or select **Store Oak** and click **Open Project** to continue saved work. Describe the goal and allowed application, plus a visible finishing rule.
2. In **Teach**, use **Try the Practice App** or choose an open application. For the harmless Lab, enable text capture, reset it, and click **Start Teaching**.
3. Focus the Lab during the five-second countdown. Wait for **Recording**, then demonstrate Select Oak → type `oak` → Finish. Pause at each state. Leave COMPLETE visible for two seconds, return to TeachDesk and click **Stop**. Returning by clicking or Alt+Tab is supported.
4. **Review** opens automatically on the just-finished recording. Use **Beginning** and **End** to inspect it. Recording dates replace internal IDs in the picker. Detailed timeline/mistake/deletion tools remain under **Recording details**.
5. Configure AI later in **Settings → AI connection**. **Learn Project** uses compatible teaching examples, with explicit per-request transmission consent. Earlier incompatible captures stay local and are automatically skipped; no manual deletion is necessary when current evidence exists. No real model is substituted while credentials are absent.
6. Review the plain-language plan and its inferred rules, answer important questions, and save your review. Regenerate after blocking answers so the executable graph incorporates them.
7. In **Practice / Run**, teach a separate practice example after shuffling the Lab controls. Reset without another shuffle, then **Test Project**. It still requires actual action authorization and visible Windows interaction. There is one normal run confirmation plus any consequential-step confirmations; the normal duration limit is 120 seconds. Detailed mode can change the duration within the existing limits.
8. When all six real checks pass, **Run Project** uses the validated working version. Later candidates need explicit promotion using **Use This Validated Update**. Detailed versions, rollback, masks, branch/expected-stop examples, and run evidence remain in **Settings → Project details**.

The [short beginner guide](docs/BEGINNERS_GUIDE.md) covers these steps. No model/API setup is required just to open projects, teach, or inspect recordings.

Model-proposed boxes can be inaccurate. The candidate validator rejects missing, ambiguous, flat, out-of-bounds, or unsupported evidence crops. You can adjust a graph/box in **Workflow graph / edit**, using the full-resolution local screenshot linked in its timeline tooltip, and save a new candidate. A valid crop is not proof of a correct goal; review and held-out practice remain necessary. No stock “learned Oak task” is installed.

## Configure the runtime model and costs

The model helping build this source is **separate** from the model this application calls. A ChatGPT subscription does not supply application API access or API credit.

Use **Model configuration** to enter a Chat Completions API base (for example `https://api.openai.com/v1`) and an available **vision-capable model supporting JSON mode**. The identifier is configurable; choose one enabled for your provider/account, rather than assuming a particular model exists. Before launching, set `TEACHDESK_MODEL_KEY` using your Windows environment settings or a secret manager. Do not paste credentials into task descriptions, recordings, source, or configuration JSON. Restart the app to inherit environment changes. Local OpenAI-compatible vision endpoints are supported using a localhost URL and the no-key option if appropriate.

Explicit configuration consent and confirmation for each generation are required. A call sends up to **24 original-resolution sampled screenshots** from up to eight training demonstrations, their included non-movement action events, typed explanations, the task description, and prior review answers. Movement samples remain local for style measurement. Held-out examples and execution screenshots are not transmitted. No live streaming or model call occurs during execution.

Budget approximately 5k–40k input tokens and up to 9k output tokens per generation for modest screenshots; actual image usage depends on resolution/model and can exceed this estimate. At an **illustrative** $2 per million input tokens and $8 per million output tokens, this is roughly $0.08–$0.15 per call. This is not a provider price quote. Check the selected provider’s current image pricing, retention, and terms first; regeneration costs another call. Local models require adequate local compute but no paid API by the app. Unsupported image/JSON modes, authorization errors, truncated responses, or invalid graphs produce explicit errors, never synthetic learning. The client does not automatically retry billable requests.

On a restricted network allow the exact chosen model hostname (e.g. `api.openai.com`) plus PyPI installation hosts `pypi.org` and `files.pythonhosted.org`. Configuring a URL does not change firewall settings. HTTP is allowed only for localhost; redirects and TLS-verification bypasses are disabled. Requests have a 180-second timeout. Provider error bodies are withheld because they may echo private request content.

## Controls, privacy and limits

- **Emergency stop: Ctrl+Alt+F8.** A dedicated Windows `RegisterHotKey` thread sets cancellation and releases held synthetic inputs independently of Qt and model responses. If registration fails, teaching/execution is blocked. Input is sent one native event at a time behind a cancellation gate; unissued input is discarded. Release failures are recorded and prevent a verified outcome. This is cooperative OS-level stopping, not a real-time guarantee on a frozen/secure Windows desktop.
- The persistent state banner and small non-activating overlay show Recording, Running, Paused or Stopped. Only explicitly enabled teaching/running sessions capture screenshots or inputs. The window list refresh reads titles/process names without screenshots. No webcam/microphone recording is implemented; typed timestamped explanations are supported.
- Scope is one selected foreground HWND/PID/executable/title. Recording ignores input when it is out of focus; execution pauses on scope/focus/geometry changes. The runner rechecks identity, foreground, desktop, display and action target on resume. A partially issued action is **not replayed**: correct it manually, resume, and its visual postcondition must be present before continuation. An intervention run is never readiness evidence. A new correction demonstration can produce a separate candidate version.
- A frame is checked both before and after acquisition for visibility, minimized state, identity, focus and placement. The center must belong to the selected window. In-flight frames affected by minimizing, covering, moving or switching away are discarded; teaching capture pauses and retains its last valid frame, then resumes when the window is available. This is a sampled boundary check, not a proof that no pixels can change between checks. Review actual previews before transmitting evidence. No start/stop recording hotkey was added.
- Physical mouse/keyboard input pauses execution by default. You can disable that setting; focus, display and scope checks remain mandatory. Already held physical modifiers can interfere with automation: release them before a run. Do not use the emergency combination as a workflow key binding.
- Defaults: 120 seconds per run (operator may choose 10–300), 80 total nodes, eight visits per node, no action retries, visual waits bounded to 20 seconds, key holds to five seconds, scrolls to ten notches. Demonstrations stop after ten minutes, 50,000 events, or approximately 512 MiB of image files. Limit stops produce interrupted demonstrations, not valid examples.
- Exclusions are window-relative normalized rectangles, e.g. `[[0.7,0,1,0.2]]`. They are blacked out **before saving or transmitting frames**, and reused during execution. Any exclusion disables ordinary key recording for the whole demonstration. Consistent exclusions are required across training examples. Password-field detection and automatic secret scrubbing are **not implemented**; pause before credentials and keep sensitive windows/notifications out of the captured rectangle. A foreground window can still have an overlapping notification; scope is not a pixel-level privacy sandbox.
- Data defaults to `%LOCALAPPDATA%\TeachDesk` (`TEACHDESK_HOME` overrides it). This is ordinary local storage, not encrypted storage. The app enforces a single instance per store. Delete demonstrations, run history or an entire task in the UI; deleting source evidence invalidates derived versions, and deleting practice removes readiness evidence. To remove everything, close the app and delete the data folder. Deletion is ordinary filesystem/SQLite deletion, not forensic secure erasure; SQLite WAL/free pages and provider-retained content may remain. Protect your Windows user account and use disk encryption for sensitive data.
- Before each run, review/authorize the listed goal, scope, targets, typed text and key combinations. Model-labeled consequential nodes require additional explicit per-node authorization. The model can misclassify effects; the final human review is part of the boundary. Initial acceptance is for the harmless lab. Do not run a graph against purchases, messages, deletion, terminals or other consequential surfaces without inspecting and specifically authorizing those effects. Authorization is never inferred from a recording or saved across runs.
- Screen text is untrusted task data. The model has no tools and cannot execute source code; the schema accepts only bounded visual desktop actions. This does not prove immunity to deceptive screenshots or incorrect semantic plans. There are no anti-cheat/CAPTCHA bypasses, drivers, concealment mechanisms or claims of undetectability.

## Supported scope and readiness

This first prototype supports **stable visual controls that move in a window at the same scale/theme**, observable state transitions, bounded explicit branches/loops, text entry, shortcuts/holds, dragging, and scrolling. Every action needs a unique visual target and a postcondition that is absent before that action and visible afterwards. Completion must be absent initially and observed in two successive captures at the end. Animated world scenes, visually identical items, hidden state, arbitrary inventory semantics, generic OCR, camera rotation, target scale changes, dynamic window titles, or postconditions that cannot be recognized from a template are unsupported. The game was not supplied or tested.

Single-monitor coordinates use physical pixels with per-monitor DPI awareness enabled before Qt starts. Positions are searched visually, not replayed. A moved/resized window is supported **between** runs if the visual targets retain their size and all other checks pass; movement/resize during an action pauses. Scaling/display changes require new demonstration/practice. Maximized windows whose extended border falls outside monitor bounds may be rejected; start with an unmaximized lab entirely on screen. Elevated windows (UIPI), UAC/secure desktop, locked/disconnected sessions, other sessions, raw-input games that reject injection, nonstandard keyboard behavior, and fullscreen protected surfaces are unsupported. Do not elevate TeachDesk to work around them.

Capture, window/monitor geometry and mouse-position queries use explicit physical coordinates, including a scoped per-thread DPI context restored after calls. This avoids depending solely on an earlier process-level DPI request succeeding. Demonstrations predating capture validation v3 (HWND-bound capture) are kept locally and labeled **re-record after update**. They are blocked from model transmission, practice and readiness; record fresh evidence if none is compatible. Incompatible older recordings are retained as reference and automatically excluded from model requests. The update never deletes prior data automatically.

Readiness percentage is the rounded fraction of **six explicit checks**, never a model success probability:

1. Valid structured goal/inputs/start/completion/graph.
2. No unresolved material clarifications (answers must be applied through a new graph).
3. User review of supported scope, assumptions and authorization boundary.
4. An unintervened, visually verified supervised completion using a separate held-out recorded example, including its starting layout and completion evidence.
5. At least one such practice with an actionable visual target relocated at least 20 window pixels from its source crop.
6. Both outcomes of every declared branch witnessed in qualifying held-out practice. An explicitly labeled held-out **expected-stop example** may validate a deliberate stop branch without being counted as a completed task.

Only the demonstrated, reviewed scope is assessed. Unshown branches should be explicitly excluded, not fabricated. Unexpected states stop or pause; there is no autonomous general recovery/replanning. Additional demonstrations and answers produce candidate workflows; the active version remains unchanged until the candidate passes checks and is promoted. Prior versions and rollback remain available if their evidence still exists and their checks still pass.

Run performance is separate: verified completions, failures, interventions, stops/expected stops, interrupted sessions and evaluated-run count. A successful exit/PID/open port is not a verified completion. Style is also separate: recorded timing and a representative normalized cursor path guide movement/acceleration and typing pace, with smooth defaults when samples are insufficient. Reported executed speed uses measured wall time. Style fidelity is not statistically validated; independent path/acceleration comparisons and richer drag/scroll profiles remain future work. No errors are intentionally inserted.

## Development and verification

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -c constraints.txt -e . pytest==9.1.1
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q
```

Linux supports core tests and an offscreen Qt UI/lab; capture/input are explicitly unavailable. `pynput` is a Windows-only dependency in this project. See [Windows acceptance](docs/WINDOWS_ACCEPTANCE.md), [architecture and staged work](docs/ARCHITECTURE.md), and [verification evidence](docs/VERIFICATION.md). The CI definition runs core/offscreen tests on Linux and Windows; creating that definition is not evidence that CI or native tests have executed.
