# TeachDesk beginner’s guide

This guide takes you from downloading the project to teaching and testing one small task. Start with the included **Practice Lab**, which is a harmless local application. You do not need your game for these steps.

**Current status:** the original 49 core/UI tests also passed on the user's Windows PC. Version 0.1.2 also fixes selection of newly saved recordings and passes 68 core/regression tests on Linux; six native Windows tests remain pending. The changed capture path and a real model learning session still need verification on Windows. Your tests are part of validating this prototype, not just installing a finished product.

## 1. What we built, in plain English

TeachDesk has two main jobs: help turn your demonstration into a saved plan, and attempt that plan on your visible desktop.

```text
You demonstrate → Review a proposed workflow → Practice separately → Run the validated version
```

During teaching, it saves screenshots and timestamped mouse/keyboard events. It can connect a click to the screen before and after it. These recordings stay on your computer by default.

When you click **Generate / Regenerate with model**, a separately configured vision model receives selected teaching evidence, with your permission. It proposes a structured workflow: what the goal is, what visible conditions to look for, which actions to take, what their results should look like, and when to stop. Saving a demonstration does **not** train or change the model’s weights.

When executing, TeachDesk repeatedly looks at the selected window, chooses the next step from that workflow, visibly moves/types/clicks, and looks again to check the result. Its first recognition method compares small screenshot patterns. A button can move and still be recognized if its appearance stays sufficiently similar. A different theme, scale, animation, or ambiguous duplicate can prevent recognition.

The current runner follows the reviewed graph; it does not continually ask a model to invent new actions during a run. An unfamiliar situation can pause or stop it. It is not yet a general assistant that understands every desktop or game.

### Four words you will see

| Term | Meaning |
|---|---|
| Demonstration | A recording of you doing the task. |
| Candidate | A proposed workflow version that still needs review and testing. |
| Held-out example | A separate demonstration reserved for testing; it is not given to the learning model. |
| Postcondition | The visible result expected after a step, such as “ITEM SELECTED.” |

## 2. Get the files onto your Windows PC

1. Download the latest TeachDesk source ZIP from the GitHub `teachdesk-prototype` branch linked in the conversation. Version 0.1.2 contains `Launch TeachDesk.cmd`.
2. Right-click it and choose **Extract All**. Do not launch from inside the ZIP.
3. Open the extracted project folder (GitHub names it `GPTBot-teachdesk-prototype`). You should see `README.md`, `pyproject.toml`, `Launch TeachDesk.cmd`, and the `scripts` and `teachdesk` folders. That is your **project folder**.
4. Install **64-bit Python 3.12** from [python.org](https://www.python.org/downloads/windows/), including the Python launcher if offered. Other Python versions are not the documented starting configuration.
5. Open PowerShell in the project folder: in File Explorer, click the address bar, type `powershell`, and press Enter.
6. Check Python:

   ```powershell
   py -3.12 --version
   ```

   Expect `Python 3.12.x`. If Windows cannot find `py`, finish installing Python/the launcher and open a new PowerShell window.

For the first test, use Windows 10/11 with **one enabled monitor**, leave scaling unchanged, and keep the screen unlocked. Use ordinary windows rather than running TeachDesk or the lab as administrator.

## 3. Install and open TeachDesk

For the simplest route, **double-click `Launch TeachDesk.cmd`** in your extracted project folder. It prepares the environment on first use and opens the app. No PowerShell commands or activation scripts are needed for this route. Keep the console open. If it reports an error, preserve the output. Check that the app title says **TeachDesk 0.1.2**.

When updating, first close both TeachDesk and its Lab. Extract the new download and open its launcher. Task data lives outside the program folder, so the same Windows account normally sees its existing library. Old recordings are labeled **re-record after update** and cannot be sent to the model. Delete the affected demonstration through the UI, or create a new task and record a clean example. Your previous data is not deleted automatically.

The manual setup and test commands below remain available for troubleshooting and validation.

In that PowerShell window, run:

```powershell
.\scripts\setup.ps1 -Test
```

This creates an isolated Python environment inside `.venv`, installs dependencies, checks them, and runs the core tests. It needs Internet access to download packages. The installation does not need a model key and does not make paid model calls.

**Expected result:** tests pass, with the six interactive Windows tests skipped unless you explicitly enabled them. A skipped native test has not passed; the next section explains how to run those checks.

If PowerShell says script execution is disabled, use these equivalent commands instead of changing your machine’s security policy:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -c constraints.txt -e . pytest==9.1.1
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest -q
```

If installation or tests fail, stop here and keep the error output. Do not treat a failed setup as ready.

Open the application:

```powershell
.\scripts\launch.ps1
```

Or, if scripts are disabled:

```powershell
.\.venv\Scripts\python.exe -m teachdesk.ui
```

Keep PowerShell open while using the app. You should see **Learning**, **Ready to Run**, the task controls, and a **Stopped** indicator. A missing-model notice is expected before configuration. No recording should be active just because the app is open.

## 4. First, check Windows input and emergency stopping

The emergency combination is **Ctrl + Alt + F8**. It is handled by a separate Windows hotkey thread, so stopping does not wait for a model response.

Before learning anything, run the supplied native diagnostics:

1. Close the main TeachDesk window so it releases that hotkey.
2. In PowerShell, run:

   ```powershell
   $env:TEACHDESK_WINDOWS_TESTS = '1'
   .\.venv\Scripts\python.exe -m pytest tests/test_windows_native.py -q -s
   Remove-Item Env:TEACHDESK_WINDOWS_TESTS
   ```

3. The tests open disposable lab windows and send **visible** mouse/keyboard input. Keep your hands off during the test. If Windows refuses to focus a lab, click it during the focus window and retry.
4. Expect **six passing tests**: capture/filtering with a check for the Lab's visible colors, rejection of minimized-window capture, and emergency cancellation during movement, typing, a held key, and a held mouse button. These tests trigger the registered hotkey using native input; you should additionally check your physical keyboard combination later.

If a check fails, save the complete output and identify which test failed. Do not proceed to automated game control. A successful diagnostic checks Windows plumbing, not model learning or game competence.

Reopen TeachDesk using the launch command when finished.

## 5. Teach your first task — no model needed yet

Click **Launch Practice Lab**. It opens a separate window with a status bar, **Select Oak**, an item-name field, **Finish task**, **Reset**, and **Shuffle layout**.

The task you will teach is: select Oak, type `oak`, then finish.

### Create the task

1. In TeachDesk, click **Create Task**.
2. Name it `Practice Lab — Store Oak`.
3. Use this goal:

   > In TeachDesk Practice Lab, click Select Oak, enter oak in the item-name field, and click Finish task. The task is finished only when COMPLETE — oak stored appears. Only this lab window is authorized. Stop if the expected controls or states are missing.

4. Click **Refresh Windows** and select **TeachDesk Practice Lab** under **Exact target window**. Select the lab, not PowerShell or TeachDesk itself.
5. Choose **Training demonstration** in the recording-type dropdown.
6. For this harmless text, check **Record ordinary typed keys (may include secrets)**. This lets the model see `oak`. Leave it unchecked for sensitive work; redacted text may require a later clarification.
7. Leave exclusions as `[]` for this clean lab example. Keep **Pause on physical input** enabled; that setting applies during automated execution.

### Record a clean demonstration

1. Keep the lab unmaximized, completely on screen, and away from the small top-left status overlay. Click **Reset** in the lab.
2. In TeachDesk, click **Start Recording / Teach More**.
3. TeachDesk minimizes. You have **five seconds** to click and focus the lab.
4. Wait until the five-second countdown ends and the status overlay says **Recording**. Then wait one more second with `READY — choose an item` visible. Actions during the countdown are not recorded.
5. Click **Select Oak**. Wait about one second on `ITEM SELECTED — enter oak`.
6. Click the item-name field and type `oak`. Wait about one second on `TEXT ACCEPTED — finish task`.
7. Click **Finish task**. Wait about one second on `COMPLETE — oak stored`.
8. Return to TeachDesk and click **Stop**.

The pauses help the prototype’s sampled screenshots capture each result. It samples around four frames per second rather than saving continuous video.

Switching away or minimizing the Lab should pause teaching capture and discard a frame affected by the transition, retaining the previous valid frame. Returning the Lab to the foreground should resume capture. You can use the existing **Pause** button before switching, and **Stop** to finish. A `complete` recording label means the session was saved normally; inspect its previews to verify the task's starting and completion states were actually captured.

### Check what was recorded

After a recording finishes, TeachDesk automatically opens **Demonstrations & timeline**, selects that recording and previews its first captured frame. This also applies to interrupted recordings; check their status before using them. Use the dropdown to browse older recordings and select rows. You should see timestamped input events and corresponding screenshots. The ordinary letters should appear only if you opted into recording them. Key/button releases can include held durations.

If you made a mistake, either use **Label mistake / irrelevant interval** or delete that demonstration and record a clean one. An interval looks like `2.5,5.0,accidental click`: start seconds, end seconds, explanation. Do this before generating a candidate; changing evidence later invalidates earlier review/practice eligibility.

**You have now tested recording and storage, not learning.** You can close/reopen the app here to confirm the task and recording remain without configuring a model.

## 6. Connect a model when you are ready to test learning

The app needs its own model service. Your ChatGPT subscription does not automatically provide an application API key or API credit.

The easiest documented route is a vision-capable model exposed through a compatible Chat Completions API with JSON mode. The model identifier depends on your provider/account; the app does not choose one for you.

### Cost and privacy before you configure it

Generation can send up to **24 sampled screenshots**, included action logs, task explanations, and earlier review answers. The app requests your consent and confirms each transmission. Held-out testing recordings are not sent. Execution itself does not make model calls.

An illustrative generation estimate is approximately **$0.08–$0.15** at $2 per million input tokens and $8 per million output tokens. That is an example, **not current provider pricing or a spending cap**. Actual screenshot sizes, model pricing, and retries can change the cost. Check your provider’s prices and set a suitable account budget before use.

### Configure the key and endpoint

1. Obtain an API key through your chosen provider’s official account settings. Do not paste the key into this chat, task notes, recordings, or project files.
2. On Windows, search Start for **Edit environment variables for your account**.
3. Under **User variables**, add a variable named `TEACHDESK_MODEL_KEY`, with your key as its value. This is an ordinary user environment variable, not an encrypted vault; a secret manager is preferable if you already use one.
4. Close TeachDesk and the old PowerShell window. Open a **new** PowerShell window in the project folder and relaunch so the app inherits the new variable.
5. Click **Model configuration**. Set the API base URL, for example `https://api.openai.com/v1`, and your provider’s supported vision model identifier.
6. Leave **Localhost model requires no API key** unchecked for a hosted provider. That option is for a separately installed local compatible model.
7. Read the transmission notice, choose whether to consent, and save. Configuration alone does not send a demonstration.

Without this configuration, recording, timeline review, storage, and Windows diagnostics can still be tested. Generating and executing a learned candidate cannot be completed through the normal teaching flow. There is no substitute pretend-learning mode.

## 7. Generate and review a workflow

1. Select your Oak task and open **Review & questions**.
2. Click **Generate / Regenerate with model**. Read the screenshot count/destination and authorize transmission only if the recording is appropriate.
3. Wait for the result. This can take a few minutes. A rejected response or inaccurate image crop is a failed generation attempt, not a learned task.
4. Check the summary: correct goal, lab-only scope, correct input text, sensible steps, and a distinct completion condition.
5. Read assumptions and exception behavior. The proposed workflow should stop when its required state cannot be recognized.
6. If an important question appears, answer it and click **Save answers and review**. Then **regenerate** so that the answer can change the actual workflow. Saving an answer alone does not remove the execution blocker.
7. When you understand the final candidate, check the review checkbox and click **Save answers and review**.

Zero questions is valid for a clear demonstration. You do not need to explain every click.

A progress bar below 100% is expected at this point: the candidate has not yet passed separate practice. Beginners can leave **Workflow graph / edit** alone. If the model repeatedly proposes bad crops or an unsuitable plan, keep the exact error and relevant screenshot/timestamp for diagnosis rather than approving an incorrect version.

## 8. Test learning with a different layout

This is the key test that goes beyond repeating your recorded click positions.

### Record a separate testing example

1. In the lab, click **Shuffle layout**. Confirm at least one actionable control moved compared with your teaching recording. Shuffle again if the layout happened to stay the same.
2. Do not change display scaling, theme, or window size for this first test.
3. In TeachDesk, choose **Held-out completion example**.
4. Record yourself completing the same Oak task in the new layout, using the same one-second waits. Stop normally.

This example stays out of the model’s learning input. You do not need to regenerate after recording it.

### Let TeachDesk attempt it

1. Click **Reset** in the lab. **Do not click Shuffle layout again**: practice should start in the held-out layout you just recorded.
2. In TeachDesk, select your candidate workflow version and click **Supervised Practice**.
3. Choose the held-out recording. If asked for a declared input, supply the intended value, such as `oak`.
4. Read the actual action/text/key plan. Authorize only the lab interactions you intend. Keep the default 120-second limit for this short task.
5. During the countdown, focus the lab. Release mouse buttons and keys, then keep hands off. Physical intervention normally pauses execution.
6. Watch for the real cursor selecting the relocated control, visible typing, and the final completion state.
7. Open **Runs & evidence** afterwards. Look for a `verified` outcome and the readiness evidence, not just a finished-looking screen.

Full readiness requires six checks: valid workflow, resolved important questions, your review, a verified separate practice completion, a relocated actionable target, and coverage of both outcomes of any declared branches. A task with no declared branches has no branch outcomes to test; that does not establish support for unshown situations.

At 100%, the **first** validated version becomes active and moves to **Ready to Run**. Later improvements require explicit promotion. **100% means the checklist passed for this supported scope, not a 100% success guarantee.**

If a run needed your help, it should be classified as an intervention and cannot qualify for readiness, even when you disabled automatic pausing.

## 9. Use Run and perform simple acceptance tests

For ordinary use, select the **active** Ready version, reset the lab, click **Run**, review its authorization, and focus the lab during the countdown.

Complete these checks before considering a game task:

| Test | What you do | What should happen |
|---|---|---|
| Physical emergency stop | During a sufficiently long harmless run, press Ctrl+Alt+F8. | New input stops and held synthetic inputs are released. History must not count it as a verified completion. A short Oak run may finish too quickly; use the native diagnostics for the automated held-input checks. |
| Manual intervention | Move the real mouse during practice. | With the default setting, it pauses. A resumed assisted run must not grant readiness. |
| Already complete | Try running while the lab still says COMPLETE. | It refuses before acting; reset before a valid run. |
| Unexpected state | Check **Unexpected state** in the lab, then attempt the normal Oak workflow. | It cannot validate the normal starting state and should stop without performing the normal task. Uncheck it and reset afterwards. |
| Persistence | Close/reopen TeachDesk. | Task, recordings, answers, versions, readiness evidence, and history remain. No task automatically resumes. |

If anything continues issuing input after an emergency stop, stop testing and preserve the failure details. A passing core test suite cannot override a failing test on your actual desktop.

For the full physical-key, held-input, scope, privacy and rollback protocol, follow [Windows acceptance](WINDOWS_ACCEPTANCE.md).

## 10. Improve a task without losing its working version

Use **Start Recording / Teach More** with **Training demonstration** for additional conditions or a recovery example, then generate a new candidate. New evidence alone does not modify the existing active workflow.

Review and practice the new candidate separately. When all checks pass, use **Promote / Restore Version** to make it active. To roll back, select a previous version with valid retained evidence and use that same button. Deleting its supporting evidence can make a version unavailable or ineligible for restoration.

While paused during an action, complete/correct that step manually, then click **Resume after correction** and refocus during the countdown. TeachDesk checks the expected result; it does not blindly reissue a partly typed string or a partly completed click. If the required result is still missing, the run should stop. For your first attempts, stopping and restarting from Reset is often easier to diagnose than resuming halfway.

## 11. Common problems

| Problem | What to check |
|---|---|
| `py` is not recognized | Install Python 3.12 with its launcher; open a new PowerShell window. |
| Script execution is disabled | Use the direct Python commands in section 3. |
| Model is unavailable | Verify the variable name, open a new terminal, relaunch, and check endpoint/model/consent. Never share the key to troubleshoot. |
| Model HTTP 401 or 403 | Check the selected provider’s authentication and model permissions. |
| Model HTTP 429 | Check account quota, credit, and rate limits. A retry may incur another charge. |
| Model rejects images/JSON or produces invalid crops | Confirm model capabilities; review the exact error and source screenshots. This prototype can need a clearer demonstration or candidate repair. |
| No frames or missing actions | Confirm the lab was selected and foreground during recording, and that the demonstration completed normally. Ordinary text is redacted unless opted in. |
| A preview shows desktop wallpaper or TeachDesk rather than the Lab | Do not send that evidence to a model. Use version 0.1.2, record a fresh demonstration, and inspect both the first and final frames. If it recurs, retain the error/geometry details and report it; native capture is still under validation. |
| A demonstration says re-record after update | It predates capture validation v2. Delete that demonstration or use a new task, then record again. |
| Target lost foreground focus | Focus the selected lab during the countdown; do not click TeachDesk during a run unless intentionally intervening. |
| Target is missing or ambiguous | Reset to the expected state; keep the same scale/theme; remove duplicate-looking targets. Do not reduce verification just to get a pass. |
| Practice says the layout is wrong | Reset without shuffling after the held-out recording, or record a new held-out example of the current layout. |
| Readiness is below 100% | Read the unchecked items. Saving a recording or answering a question alone is insufficient. |
| Run refuses a candidate | Use Supervised Practice first; ordinary Run requires the active validated version. |
| Emergency hotkey is unavailable | Close another TeachDesk instance or the app registering Ctrl+Alt+F8. Do not proceed without a working stop control. |
| Display/window is unsupported | Use one enabled monitor and a fully visible, unmaximized, non-elevated lab at unchanged scaling. |

When reporting a problem, include the step, exact error, Windows version/display scaling, and relevant run outcome. Share only reviewed, non-sensitive screenshot crops if needed. Never include API keys or an unreviewed data folder.

## 12. Your data and the next step

Tasks and evidence normally live at `%LOCALAPPDATA%\TeachDesk`. Paste that path into File Explorer’s address bar to find them. They are ordinary local files, not encrypted recordings. The UI provides deletion of demonstrations, run history, and entire tasks; deletion can invalidate readiness. Close TeachDesk before copying the whole folder as a backup. The model key is supplied separately and is not stored in that folder by the app.

For future non-lab work, keep key capture off unless needed, pause before sensitive content, and use recording exclusions. Automatic password detection is not implemented. For this first clean lab task, using no exclusions avoids extra configuration.

Your first milestone is **a verified, model-generated Oak task completing at a changed layout, plus confirmed emergency stopping and persistence on your own Windows PC**. Only then move to one small, clearly bounded action in your game. The game remains untested; animated scenes, camera changes, indistinguishable items, and applications rejecting simulated input can exceed the prototype’s current capabilities.
