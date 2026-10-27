# TeachDesk: simple beginner guide

Version 0.2.0 opens with **New Project** and **Open Project**. A project has three steps: **Teach**, **Review**, and **Practice / Run**. The detailed tools are under Settings.

Your existing projects and recordings remain saved. Current window-capture recordings from 0.1.3 carry over; they do not need recording again just because the interface changed. Incompatible older recordings remain local reference and are automatically excluded from AI learning.

## Open the app

1. Close the previous TeachDesk and its Practice Lab.
2. Download the latest GitHub source ZIP. Right-click it and choose **Extract All**.
3. Open the extracted project folder and double-click **Launch TeachDesk.cmd**. Keep its console window open.
4. Confirm the title says **TeachDesk 0.2.0**.

Python 3.12, Windows 10 version 2004 or newer / Windows 11, and one enabled monitor are the starting configuration. Use a standard unlocked desktop. Installation does not need an AI key and does not make paid AI requests.

## New project or old project

- **New Project:** give it a name and describe what it should do, which application it may use, how you know it is finished, and anything it must not do.
- **Open Project:** select an existing project in the list, then click Open Project. Double-clicking also opens it.
- **Projects:** returns to the list when no session is active.

The percentage means **checks passed**, not recording time or a probability of success. You do not choose an arbitrary learning percentage. A narrower, clearly described goal needs fewer situations demonstrated than a broad goal; the same review and practice requirements still apply. Seeing 0% before there is a learned plan is expected.

## 1. Teach

1. Open the application you want to teach. Choose it under **Application** and use **Refresh** if needed.
2. For a safe first test, click **Try the Practice App**. TeachDesk opens its harmless Lab and selects it when available.
3. In the Lab, click **Reset**. Keep the Lab unmaximized and entirely on screen. Return to TeachDesk.
4. Enable **Include text I type** only for non-sensitive text. For this Lab, the text is `oak`. Ordinary typed keys are redacted when unchecked.
5. Click **Start Teaching**, then switch to the Lab within five seconds.
6. Wait until the status overlay says **Recording**. Leave **READY — choose an item** visible for another second.
7. Click **Select Oak**. Wait a second. Click the item-name field and type `oak`. Wait a second. Click **Finish task**.
8. Leave **COMPLETE — oak stored** visible for two seconds. Return to TeachDesk by clicking its window/taskbar icon or using Alt+Tab. Click **Stop**.

Teaching is explicit: opening a project does not start capture. The persistent status and separate overlay show Recording, Paused, or Stopped. Losing target focus pauses teaching capture automatically. Returning target focus normally resumes it. For a deliberate pause, use **Pause**, then **Resume** when ready; Resume gives another focus countdown.

The emergency stop is **Ctrl+Alt+F8**. It is handled independently of AI responses. Normal stopping saves the recording; an emergency or other interruption leaves it marked incomplete rather than presenting it as a successful example.

## 2. Review

Stopping automatically opens **Review** with the recording you just finished. The dropdown uses recording dates instead of internal IDs.

1. Click **Beginning** and check that the task starts in the expected state.
2. Click **End** and check the visible completion result. A recording marked Saved is not proof the task succeeded.
3. If something is wrong, use **Recording details** to inspect the timeline, label an irrelevant interval, or delete a mistaken recording after confirmation.
4. When an AI connection is configured, click **Learn Project**. It uses compatible saved teaching examples for this project; selecting a preview does not limit learning to that one recording. Practice examples and incompatible old captures are excluded.
5. Inspect the transmission confirmation before sending sampled screenshots, included actions, project notes and prior answers. You can cancel. The provider may charge.
6. Review the proposed goal, finishing rule, steps, branches, inferred rules, assumptions and allowed scope. Answer any important questions, check the review checkbox and click **Save Review**.

If a question blocks execution, saving an answer is not enough: use **Update Plan from My Answers**, review the regenerated plan, and save that review. The app cannot safely guess what an answer means for its executable graph.

You can postpone AI setup. Teaching, saved recordings, Beginning/End previews and Details remain usable. The app does not substitute a fake learned plan while AI is unavailable. Saving demonstrations does not train model weights.

## 3. Practice / Run

Do this after a plan has been learned and reviewed. Native input checks below should pass before automated execution.

1. Reset the Lab and click **Shuffle layout** until its controls visibly change position. Keep the same window size and scale.
2. In **Practice / Run**, click **Teach a Practice Example**. This records a separate example and does not send it to the AI. Perform the full task, then Stop as before.
3. Reset the Lab without shuffling again, so it matches that separate example's starting layout.
4. Return to **Practice / Run** and click **Test Project**. If several eligible examples exist, choose one by its recording date. Review and authorize the proposed visible actions; consequential actions still require their own explicit authorization.
5. Focus the selected app during the countdown. Let TeachDesk move/type/click visibly. Stop or intervene whenever necessary. The default run limit is two minutes, including pauses.

The checks include a valid task definition, important questions resolved, your review, verified practice on separate evidence, a relocated actionable target, and coverage of all declared branch outcomes. **Why this percentage?** shows the checklist. Failed, interrupted, unverified, or intervened practice does not qualify as a successful learning example.

At 100%, the first validated plan becomes the working version and **Run Project** becomes available. This means it passed the checks for its supported scope, not that it can handle every situation. Ready projects remain teachable. Later validated updates require **Use This Validated Update**; previous versions remain available in Details for rollback. Teaching extra examples does not silently replace the working version.

## Settings and Details

- **Settings → AI connection:** the connection form, provider consent, model identifier and API base URL. Your OpenAI API access/billing is separate from ChatGPT. Keep API keys out of screenshots, project notes, recordings and chat. The app reads `TEACHDESK_MODEL_KEY` from its launching environment.
- **Settings → Project details:** timeline, mistake labels, recording exclusions, expected-stop practice examples, workflow graph editing, prior versions, rollback, detailed run evidence and deletion controls. These use the same engine as the simple interface.
- **Settings → Edit project:** change its name or goal. Changing the goal invalidates prior review/practice readiness.
- **Settings → Archive / restore project:** keep a project without showing it in the normal list. Enable **Show archived projects** to find and restore it.

All actions still use your active Windows desktop. Locked/secure desktops, elevated windows, unsupported graphics/input, multiple monitors and unexpected visual states remain limitations. No anti-cheat, CAPTCHA or concealment bypass exists. Read-only capture uses the selected window; it does not execute hidden application commands.

## Test the Windows input plumbing

Close TeachDesk first to free its emergency hotkey. Open PowerShell in the extracted project folder and enter these commands one at a time:

```powershell
$env:TEACHDESK_WINDOWS_TESTS = '1'
.\.venv\Scripts\python.exe -m pytest tests/test_windows_native.py -q -s
Remove-Item Env:TEACHDESK_WINDOWS_TESTS
```

Seven opt-in tests open disposable Practice Labs and visibly test capture, covering/minimizing behavior, injected-event filtering, and emergency cancellation during movement, typing, held keys and held mouse buttons. Keep hands off during these automated checks. Save failures for diagnosis. Also verify your physical Ctrl+Alt+F8 combination; a synthetic hotkey test cannot prove every keyboard/driver combination.

The normal cloud/core suite uses test doubles for Windows and mocked model responses. It does not prove real AI learning or game competence. See [Windows acceptance](WINDOWS_ACCEPTANCE.md) and the [verification record](VERIFICATION.md) for actual evidence and remaining checks.

For dependency commands, model cost estimates and advanced constraints, see [README](../README.md). A different app, theme or scale needs its own supported examples and practice; the Lab does not establish universal desktop competence.
