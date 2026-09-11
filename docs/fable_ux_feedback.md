# TVRemoteWeb — UX review

Reviewed as a daily, one-handed, dim-room user driving a projector from the couch.
Sources: `module/files/remote.html`, `module/files/keystone.js`, `README.md`, `docs/screenshots/*`.
Read-only; no code changed.

## 1. Overall impression

This is a serious tool wearing a plain shirt. The engineering choices (real evdev pointer over WebSocket, staged apply + one-step restore everywhere, a PIN vault around kill) are better than most commercial remotes. The UI is honest and consistent in its *visual* language — one card style, one status-box style, one accent — and the Keystone Lab is genuinely novel.

But the page was laid out top-to-bottom like a document, not bottom-up like a thing you hold. The two controls used a hundred times a night (D-pad, volume) are the furthest from the thumb; the only acknowledgement that a keypress registered is a 10px grey string in the top-right of the header; and the tab bar spends 6 slots on things used once a month while the daily Pad/Remote split forces a tab switch to press Back. The second-tier features (Keystone, picture profiles) have grown dense prose and duplicated status boxes because the page explains itself instead of showing state. Fix reachability and feedback first; the rest is trimming.

## 2. Section-by-section

### Remote controls (`data-tab="remote"`, lines 300-358; `remote-controls.png`)

- **D-pad is at the top, thumb is at the bottom.** In `remote-controls.png` the UP key sits ~22% down a 2424px screen, directly under the sticky header; Vol −/+ are mid-screen; text input is nearest the thumb despite being the rarest action. Card order should invert: Navigation and volume last (just above `nav`), text input and HDMI first or collapsed.
- **No key-repeat.** Each `[data-k]` is `click` only (line 761); holding LEFT to scrub a row of 40 tiles means 40 discrete taps at ~80 ms shell-out each. `pointerdown` + repeat timer would match a physical remote.
- **Four dead cells in the 3×3 grid** (`.dpad .sp`, line 78). The corners are prime thumb real estate and could carry Back/Home or Vol −/+.
- **HDMI card (lines 332-342) squats between Media and Text Input** and fires `hdmiRequest('status')` on first show, then leaves a permanent green "HDMI 1, 2 and 3 are available." box. Rare action, permanent space.
- **Vol − / Mute / Vol +** ordering is right, but mute has no visible state (nothing tells you the projector is currently muted).
- The header keyboard button (`#global-keyboard`, line 292) is a good idea, well-executed.

### Latency / feedback (cross-cutting, `call()` lines 752-759)

- **The only ack for a keypress is `#s`** — a 10px, `--muted`, 42vw-wide, ellipsised span in the header (line 39). It's empty in every screenshot, so a first-time user doesn't even know it's a status. In a dim room, glancing from the projector to a grey `ok` in the phone's top-right corner is invisible. Errors render as `err: Failed to fetch` in the same grey.
- **No haptics on keys.** `navigator.vibrate` is used for touchpad tap/right-click (lines 926, 971) and pinning (1012) but never for the D-pad, media or volume keys — the exact place the finger wants confirmation without looking.
- `button:active { transform:scale(.95) }` (line 67) is the only visual press state, and it ends when the finger lifts, before the request round-trips. There's no in-flight or failed state on the button itself.

### Touchpad (`data-tab="pad"`, lines 361-389, JS 854-984)

- **Tap threshold is scaled by sensitivity — a real bug.** `moved` accumulates `dx/dy` *after* multiplying by `sens` (line 953-955) and tap-click requires `moved < 10` (line 971). At speed 5-6× a 2px jitter is 12 "units", so taps stop registering just when the user has cranked sensitivity. Compare with the long-press check `moved < 8` (line 926). Measure raw clientX/Y deltas for the gesture decisions.
- **The blue dot is not the cursor.** `#cursor` mirrors the finger's position inside the pad (lines 957-960), not the TV pointer. `Center` (line 981) only recentres this local dot and sends nothing to the projector — a false affordance that will be tapped hoping the TV cursor comes back to the middle.
- **Queued motion replays on reconnect.** `wsSend` buffers up to 100 messages while the socket is down (line 746) and `onopen` flushes them (line 737) — after a Wi-Fi blip the cursor lurches through stale deltas. Moves should be dropped, not queued; clicks can queue.
- **The red `.wsdot` is the only sign you're on the slow path.** Nothing explains why the cursor suddenly feels like syrup (CGI fallback, line 888).
- **Pad tab has no Back / Home / OK.** Mouse mode on Android TV is always "point, click, then Back" — that's a tab switch every time. A slim row of Back/Home under `.padrow` fixes the most common cross-section round-trip.
- Hint copy is duplicated: `.sec .note` (line 363) and `#padhint` (line 365) say the same thing.
- `.pad` sizing (`44vh`, 220-380px, line 96) and the `Hold` latch with `aria-pressed` + `pagehide` release (lines 897-914, 984) are well judged.

### App launcher (`data-tab="apps"`, lines 392-437; `app-launcher.png`)

- **Long-press pin has a double-fire risk.** Android Chrome dispatches `contextmenu` on long-press (~500 ms) *and* the 550 ms `touchstart` timer is still armed (lines 1014-1017); `touchcancel` is not handled, so after `contextmenu` toggles the pin the timer can toggle it back. Worth verifying on-device; listen to `touchcancel` or drop one of the two paths.
- **Pinned apps look like primary CTAs.** Pinned = `.acc` blue (line 1003), the same colour as OK, Send, Play and Apply. With 3 pins the grid is a wall of blue.
- **Cast card first** (`#cast-card`, line 393) pushes the app grid down and fetches `pullCastStatus()` on every tab visit (line 712). Casting is a monthly action; put it below the grid.
- `.ctl` Rescan row (line 410) spends a full ~48px row on one small ghost button; fold it into the section header.
- "Open URL on SmartTube" is hard-coded (`org.smarttube.stable`, line 808); README line 66 promises "opens in the app you choose."
- Labels are raw package labels ("LtvL", "Htcsettings") with no icons; acceptable, but a `title` tooltip (line 1002) is useless on touch.

### Keystone Lab (`data-tab="align"`, lines 470-551, JS 1498-1909; `auto-align-*.png`)

The flow itself — calibrate, photograph, detect, drag-refine with a loupe, review, apply, restore — is the best part of the product. The issues are in framing and edge cases, not the algorithm.

- **"Start with camera" mutates the live projection with no confirm and no visible undo.** The label click (line 1626) immediately runs `calibrate 55%` + `view_open` in parallel with opening the camera. The manual presets confirm first (line 1896); auto doesn't. If the user cancels the camera sheet — very common — the projector is left at a 55% blue grid, `ksAutoMode` stays `true`, and the only ways out (`#ks-grid-close`, line 508; `#ks-restore`, line 548) are in a hidden manual card or the bottom of the page. Handle `change` with no file (or a focus-return) by closing the grid and offering restore.
- **Three status boxes say the same thing.** `ksSetStatus` writes to `#ks-auto-status`, `#ks-quick-status` and `#ks-status` (line 1527). `auto-align-start.png` shows the identical green sentence twice on one screen. One status, anchored where the user is looking (under the preview), is enough.
- **Step numbering starts at 2.** The visible auto card has no number; "1 · Photograph both rectangles" is `.ks-manual-only`, so the default view reads "2 Detected fit", "3 Review and apply" (`auto-align-start.png`). Either number the auto card 1 or drop the numerals.
- **Proposed values are firmware insets.** `LT 48,98 · RT 91,0 · RB 73,28 · LB 35,47` (`auto-align-apply.png`, line 1725) mean nothing to the person deciding whether to press Apply. Draw the proposed outline on the photo (a third, dashed colour) and demote the numbers to a `details`.
- **"Reviewed" means "dragged".** `updateKeystoneProposal` demands every corner of both quads be in `ksReviewed` (line 1716). When screen detection fails the user must nudge four green points that may already be right, or the Calculate button stays disabled with no explanation beyond a status string. A tap-to-confirm on a node should count.
- **Dragging works before "Edit detected points" is pressed** (`pointerdown` gates only on `ksAnnotation`, line 1751), yet the button label implies it unlocks editing; it actually only reveals the manual cards (line 1611). Rename to "Show manual controls" or gate dragging on it — one or the other.
- Native `confirm()` for apply/restore/zoom/reset/calibrate (lines 1847, 1859, 1874, 1884, 1896) is consistent within this tab but clashes with the in-page status pattern used everywhere else; fine for now, but the Apply confirm repeats the same inset string nobody can read.
- Detection is synchronous inside a `setTimeout(0)` (line 1801) — the "Detecting…" status renders, but the page freezes with no spinner for a second or two on a 12 MP photo. Acceptable, just unexplained.
- Copy is implementation-speak: "Prepares a centered 55% test image, then detects the blue projection…", "safely clips small edge-estimation overshoot" (lines 473, 515). The user needs: "Take one photo of the whole screen. We'll fit the picture to it."
- `keystone.js` error strings are actually good ("retake the photo more square-on", line 68) — the UI wraps them in "Adjust the points: …" (line 1730) even when the fix is retaking the photo.

### Picture / power / Bluetooth (`data-tab="tools"`, lines 555-624; `picture-controls.png`, `power-interface.png`)

- **Thirteen disabled controls fill the first two screens.** Default state is `locked` (line 1142), so every slider/select renders at 0.58 opacity and does nothing until a custom slot is chosen via a collapsed `details` (line 565). `picture-controls.png` is a page of inert sliders. Hide the `.setting-list` until editable, or show only the three used-by-profiles values.
- **Shared status box lives in the wrong card.** `#settings-status` is inside the Picture card (line 599), but Power & interface `Apply selected` writes into it (line 1276) — the confirmation appears above the fold you just scrolled past. Give Power its own status or move the box below both.
- Profile grid: "Current values · Read-only · discard edits" is a *destructive* action styled like a profile (line 563). Separate it as a ghost "Discard edits" button.
- Text sizes: `.sec` 10px, `.advanced-note` 10.5px, `.pq-profile small` 9.5px (lines 54, 191, 196). Readable at desk brightness, not from a dim couch. Nothing on the Tools tab should be under 12px.
- Rotation 90°/270° on a projector (line 608) can leave the user with a sideways UI and no warning; it deserves the same `confirm()` that Bluetooth-off gets (line 1313).
- Bluetooth "on"/"off" as two buttons where the "on" one turns `.acc` when enabled (line 1288) reads as a pressed-toggle, which is fine — but then "Bluetooth off" ghost + confirm feels like a different pattern from every other on/off pair (Live: on/off is a single toggle, line 1451).

### Process monitor / maintenance (lines 626-675, JS 1340-1496; `process-monitor.png`, `maintenance-tools.png`)

- **Kill buttons are ~30px tall** (`.proc button` padding 7px/6px, 10px font, line 145) inside 11px rows — the most dangerous control on the page has the smallest target. 44px minimum, or move kill behind a row tap.
- Kill is offered on kernel threads (`[sugov:0]`, `[kworker/...]`, `[kbase_event]` in `process-monitor.png`) and on `busybox httpd` itself. Killing the server that serves the page yields `err: Failed to fetch` in the header (line 1446) and a dead remote. Filter bracketed names and mark self-hosting PIDs.
- Kill feedback also goes to header `#s` (line 1438) rather than the vault's own `#proc-ts`/`.empty` area, unlike every other Tools card which uses a local `.settings-status`.
- PIN vault (`#proc-vault`, lines 652-675) locking on `details` close and on 403 is correct and clearly explained. Note the screenshot (`process-monitor.png`) predates the vault; docs are drifting.
- Maintenance confirm text leaks identifiers: `'Run: restart_httpd ?'` (line 1483). "↻ httpd" will drop the page's own server with no "reconnecting…" state.
- The Tools tab is one 6-card scroll: Picture (13 controls), Power, Bluetooth, Maintenance, System, Processes. "Reboot Projector" is a ghost button buried at the fifth card. Tools should be a short list of collapsed `details` (the vault pattern already exists, line 148) with the picture editor and process list closed by default.

### Navigation and hierarchy (nav lines 262-283, 680-687)

- Six tabs at 10px labels. Stats gets a top-level tab; Align gets one; but D-pad and Pad — the two things alternated *within a single interaction* — are separate tabs. Merge Stats into Tools, and consider a Pad card at the bottom of Remote (or Back/Home on Pad).
- Four emoji icons plus one SVG (`Align`) render with different weight and colour (`remote-controls.png`); one icon system.
- `showTab` remembers the last tab (line 705, 1920), so a user who ended in Align reopens the page in Align. Default to Remote unless the last tab was Remote/Pad.

## 3. Top 5 fixes, ranked by impact-to-effort

1. **Acknowledge every keypress where the thumb is.** Add `navigator.vibrate(10)` and a ~150 ms `.sent` flash to `[data-k]`/`[data-sys]` handlers, and surface `call()` errors as a bottom toast instead of the header `#s`. *Rationale:* today the user cannot tell a slow projector from a dropped tap. `remote.html` lines 752-765, 761; `.status` line 39.
2. **Invert the Remote tab so Navigation + volume sit above the nav bar,** with text input and HDMI on top (or HDMI collapsed). One `flex-direction: column-reverse` on the pane, or reorder the cards. *Rationale:* the primary control is currently in the least reachable zone. Lines 300-358; `remote-controls.png`.
3. **Make auto-align safe on cancel and de-duplicate its status.** Confirm before `prepareAutoAlignment`, close the grid and restore if no photo arrives, and write status to one box under the preview. *Rationale:* the happiest path leaves the projector showing a blue grid whenever the camera sheet is dismissed. Lines 1626-1636, 1527, 508.
4. **Fix the touchpad's sensitivity-scaled tap threshold and drop (don't replay) queued moves.** Measure `moved` from raw client deltas; skip `M` messages in `wsSend` when `!wsReady`. Retire or wire up `Center`. *Rationale:* two small bugs that make the flagship feature feel flaky at exactly the settings power users pick. Lines 953-955, 971, 744-748, 981.
5. **Collapse the Tools tab:** hide the 13 locked picture controls until a custom slot is active, give Power its own status box, and grow Kill to 44px while hiding kernel threads. *Rationale:* Tools is the second-most-visited tab and currently opens on two screens of disabled sliders. Lines 580-599, 1142, 1276, 145, 1340-1352.
