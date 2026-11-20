# Technical Design Document: Cross-Platform Python Desktop Application

**Status:** Draft
**Target Platforms:** Windows 10/11 and Linux distributions with the required Python and native webview dependencies. Bazzite/Atomic Fedora is the primary Linux validation target; other distributions should work where those prerequisites are available.
**Primary Runtime:** Python (managed via `uv`)

---

## 1. Overview & Goals

### 1.1 Purpose
Design a lightweight, maintainable, cross-platform desktop application written entirely in Python that behaves like a double-clickable desktop program without requiring heavy binary packaging steps (such as Electron or full PyInstaller builds) during development and distribution.

### 1.2 Core Goals
* **Cross-Platform Parity:** Single Python codebase running identically across Bazzite Linux and Windows.
* **Zero-Friction Launch:** Double-clickable execution via native OS shell scripts (`launch.sh` / `launch.bat`) with automatic dependency provisioning.
* **Immutable OS Compatibility:** Full isolation from system-level Python packages and read-only OS partitions (specifically targeting Bazzite Linux).
* **Modern Web-Based UI:** Leverage web rendering capabilities in a native desktop window without managing a separate JavaScript/TypeScript build pipeline.

### 1.3 Non-Goals
* Compiling standalone single-file `.exe` / `.app` binaries (deferred unless distribution to non-`uv` environments becomes required).
* Multi-user cloud hosting or public internet exposure (application binds strictly to `localhost`).
* Capturing input to create or edit bindings. A temporary joystick/gamepad capture may be used only to search existing profile bindings; it must not modify the profile.
* Treating a well-formed XML document as automatically compatible with Star Citizen. StarBinder must validate against documented/profile-observed constraints, but only Star Citizen itself can provide final compatibility confirmation.

---

## 2. System Architecture

The proposed application uses a **local client-server desktop architecture**: a local Python web server renders a web UI inside an OS-native webview window. Story 1 validated NiceGUI native mode on Windows 11 and Bazzite; proceed with NiceGUI for the application skeleton, while keeping the Linux webview dependency footprint under review.

```text
+-------------------------------------------------------------------+
|  OS Launcher (launch.sh / launch.bat)                             |
|   + Checks prerequisites, provisions approved dependencies        |
|   + Launches the isolated application environment                 |
+---------------------------------+---------------------------------+
                                  |
                                  v
+-------------------------------------------------------------------+
|  Isolated Python Environment (.venv managed by uv)                |
|  +-------------------------------------------------------------+  |
|  |  NiceGUI native mode                                      |  |
|  |   + Application State & Business Logic (Python)            |  |
|  |   + Local HTTP / WebSocket UI Sync                         |  |
|  +------------------------------+------------------------------+  |
|                                 | Local Loopback (WS/HTTP)        |
|                                 v                                 |
|  +-------------------------------------------------------------+  |
|  |  Native Webview Window (managed by NiceGUI)                 |  |
|  |   + Linux: Qt WebEngine (Bazzite spike configuration)      |  |
|  |   + Windows: Microsoft Edge WebView2                       |  |
|  +-------------------------------------------------------------+  |
+-------------------------------------------------------------------+
```

The Bazzite host lacked Python GTK bindings and GTK WebKit, so the spike used
pywebview's Qt backend. This added about 204 MB of downloaded Qt packages;
Chromium emitted a GBM warning and fell back to Vulkan rendering. Windows 11
worked with WebView2. Treat Linux native prerequisites and package size as a
deployment tradeoff to revisit, not as evidence that all Linux distributions
will provide the same working environment.

For NiceGUI UI patterns and implementation examples, use the [official
documentation](https://nicegui.io/documentation/) and [examples
gallery](https://nicegui.io/examples/). Check examples against the project's
pinned NiceGUI version and native-mode behavior before adopting them.

### 2.1 Launcher Bootstrap

The launcher must not assume Python or `uv` is already installed. Before launching the app, guide the user through this sequence:

1. Detect a supported Python installation (`py -3` on Windows; `python3` and then `python` on Linux). Verify the minimum supported version.
2. If Python is missing or unsupported, explain the requirement and offer official installation instructions. Only perform an installation when explicitly offered and approved; otherwise exit cleanly without modifying the system.
3. After Python is available, check for `uv`.
4. If `uv` is missing, explain what it is used for and ask whether StarBinder may install it. Provide manual installation instructions if declined. Do not silently install tools.
5. Use `uv` to create or repair the project-local virtual environment, verify/install the pinned application dependencies from `pyproject.toml` and the checked-in `uv.lock`, and launch the app only when setup succeeds.
6. If setup or dependency installation fails, show the actionable error and logs; do not continue with a partially provisioned environment.

The launcher should be idempotent and safe to rerun. It must not require administrator privileges for normal setup, alter a system Python installation, or install dependencies globally. Keep the environment and cache in user-writable locations; make their paths configurable for immutable or restricted systems.

Python packages cannot satisfy every native webview prerequisite. Detect and explain missing platform components separately (for example, Linux GTK/WebKit libraries or the Windows WebView2 Runtime). Never attempt privileged OS package installation without explicit consent; provide platform-specific recovery instructions.

Story 2 selects Python 3.11 as the minimum support version and `uv` with a
checked-in lockfile for dependency management. The launcher flow for installing
or locating `uv` remains for Story 10. The Linux native backend currently uses
Qt WebEngine on Bazzite; validate prerequisites and package size on other
supported distributions before release.
Because these prompts run before the Python app exists, the launcher must provide a visible, accessible bootstrap interaction of its own. Decide whether launch scripts require a terminal or use native OS dialogs, and test double-click behavior in file managers; never silently fail or leave the user with no explanation.

---

## 3. Keybind Import Requirements

### 3.1 Supported Input

The initial feature imports, displays, and saves Star Citizen exported action-map XML files.

* Parse the XML document from a user-selected file.
* Read profile metadata from the root and `CustomisationUIHeader` elements.
* Preserve every `actionmap`, `action`, and `rebind` entry.
* Keep action and input identifiers in their original form for stable round-tripping and future export support.
* Support multiple rebinding entries for the same action.
* Display no bindings for actions that have no `rebind` element.
* Treat malformed XML, missing maps, and unknown devices or input tokens as recoverable import errors or warnings, not crashes.
* Parse unknown future Star Citizen action names without requiring a code change.
* Prefer the action-map and action names as stable identifiers; do not rely on display text supplied by XML.

### 3.2 File Operations, Conflict Detection, and Save Safety

Support a standard three-operation file workflow:

* **Open:** Select an XML binding file, validate it, and replace the current profile after confirmation if the current profile has unsaved edits.
* **Save:** Write the current bindings and profile metadata back to the currently opened file.
* **Save As:** Choose a destination XML file and then use that file as the current save target.

Open and Save As file selection should allow a user to enter or paste a full path directly, rather than requiring directory-by-directory navigation. If a platform's native picker does not make this practical, provide a clear path-entry alternative.

The first save of an unsaved or newly imported profile should behave as Save As and request a destination. The current file path and profile name should be visible in the app chrome.

Opening and saving must remain compatible with Star Citizen's action-map XML format:

* Read the original root metadata and action-map structure.
* Preserve unrecognized elements and attributes when the parser/library can safely round-trip them; the exact preservation contract is provisional pending in-game experiments (see §12.2).
* Update only existing `action` and `rebind` nodes for binding edits.
* Change only the selected existing binding assignment, without rewriting unrelated entries.
* Do not create action nodes or new rebinds. Clear or edit only an existing assignment.
* The supplied profiles include whitespace-valued assignments such as `<rebind input="kb1_ "/>` and `<rebind input="js2_ "/>`. Preserve them exactly as source data and do not confuse them with a concrete binding such as `kb1_ralt+m`. Whether and how clearing should emit such an unbind token must be confirmed by importing saved files into Star Citizen.
* Update `profileName` and `CustomisationUIHeader label` consistently for a renamed profile.
* Save as UTF-8 XML. Whether changed files may be reformatted, compressed, have comments added/removed, or have elements reordered remains an open compatibility question, not a guarantee.

#### External Modification Detection

The app must detect when the currently open profile changes outside StarBinder (for example, when Star Citizen or another editor saves it):

* Record the opened file's content fingerprint and filesystem metadata after a successful load or save.
* Recheck on window focus, before Save/Save As overwrite, and immediately before atomic replacement. Metadata such as size and modification time may be a quick signal; compare content hashes to confirm a change.
* If external changes are found, visibly mark the open profile as externally changed and identify the path/time. Do not silently overwrite it.
* Offer to reload the external version, compare/review differences, or save the in-memory version to a different file. Keep the current in-memory edits until the user chooses.
* Recheck just before replacement to reduce the race window. If the file changes again, abort the write and ask the user to resolve the conflict.
* Never automatically merge XML changes in the first implementation.
* Apply the same preflight/final-recheck protection to an existing Save As destination; replacing a different existing file requires explicit confirmation and a verified backup.

Before committing a save:

1. Serialize to a temporary file in the destination directory.
2. Flush and close it, then validate the exact serialized file.
3. If replacing an existing target, create a backup and verify that backup succeeded.
4. Atomically replace the target with the validated temporary file; do not truncate the original in place.
5. Rotate old backups only after a successful replacement.

Use the platform's atomic replace operation on the same filesystem and flush file/directory metadata where supported. A failed stage must leave the original target untouched, retain the in-memory edits, and report the failing path and cause.

Keep timestamped sibling backups and retain the five most recent successful pre-save versions by default. Make the retention count configurable, with a clear way to disable or manually clean backups. Never delete the only known-good version to satisfy rotation.

### 3.3 Undo and Unsaved State

Track a dirty/unsaved state separately for:

* Binding assignments
* Catalog presentation overrides
* Profile metadata

Provide Undo and Redo for user edits within the current open profile or catalog draft. Keep profile/XML edits and catalog/localization edits in separate histories so an Undo cannot unexpectedly change a different document. Opening a different file starts a new profile history after unsaved changes are resolved. Each edit should be one undoable operation; clearing a binding must be a single operation that restores the exact original representation and order when undone. Undo/Redo must update dirty state correctly, including returning to clean when the current state exactly matches the last saved state.

The UI should mark the window or file control with an unsaved indicator and prevent accidental loss by prompting before:

* Opening another file
* Creating or importing a new profile
* Closing the app
* Exiting developer editing with an unsaved draft

Save should preserve the original file until serialization succeeds. On write failure, retain the in-memory changes and report the target path and error.

### 3.4 Compatibility Validation

Validation has separate levels and must not claim more certainty than the available evidence provides:

* **XML well-formedness:** The serialized file parses as XML.
* **StarBinder structural validation:** Expected root/profile structure and required attributes are present; action maps, action names, rebind shape, device references, and values conform to observed supported forms.
* **Compatibility warnings:** Unknown elements, attributes, action maps, device types, tokens, or version combinations are preserved and surfaced for review, not silently deleted.
* **In-game verification:** The strongest compatibility check is opening/importing the profile in the corresponding Star Citizen build. Automated validation cannot replace this check without an authoritative game schema or validator.

No authoritative Star Citizen action-map XSD was found in the public references checked for this design. A file named [`DS_ActionMaps.xsd`](https://github.com/SCToolsfactory/SCJMapper-V2/blob/42f61bfaceae4e5baf4b9c1aadcc99e43608da99/Table/DS_ActionMaps.xsd) exists in the community SCJMapper-V2 repository, but it describes a .NET DataSet (`DS_ActionMaps` / `T_ActionMap` / `T_Action`) in a `tempuri.org` namespace, not Star Citizen's exported `<ActionMaps>` profile XML. It must not be used to validate profiles. The same repository's [AC_Examples.txt](https://github.com/SCToolsfactory/SCJMapper-V2/blob/42f61bfaceae4e5baf4b9c1aadcc99e43608da99/AC_Examples.txt) documents examples and notes dated 2015; it is useful historical community evidence, not a current authoritative specification.

Use game-exported profiles from each supported game version as compatibility fixtures, and keep the structural validator permissive for unknown content. Require manual import testing in Star Citizen before declaring a generated profile release-verified.

### 3.5 Initial Parsing Scope

The sample `StarBinder_StarBind_480.xml` demonstrates the expected baseline:

* Root metadata: `profileName`, `optionsVersion`, and `rebindVersion`
* 23 action maps
* 210 actions
* Keyboard, mouse, gamepad, and joystick inputs
* Multiple bindings, for example `v_operator_mode_cycle_forward`
* No bindings, for example `nextweapon`
* Axes and hold-axis placeholders, such as `js1_rotz` and `js1_ `
* Reused action names across maps
* Existing concrete assignments such as `v_set_mining_mode` -> `kb1_ralt+m`, which must display as `Right Alt + M`
* Whitespace-valued unbind/placeholder entries such as `kb1_ ` and `js2_ `, whose precise save semantics still require in-game verification

```text
actionmap: spaceship_movement
action: v_ifcs_toggle_esp
bindings:
  - device: keyboard
    modifiers: [Left Alt]
    key: E
human label: Toggle Enhanced Stick Precision
category: Flight - Movement
```

For this feature, the display label should be descriptive but need not be an exact copy of Star Citizen's in-game labels. A curated label is preferred whenever the semantic meaning is known.

---

## 4. Binding Domain Model

Use typed Python models rather than passing XML elements through the UI:

```text
BindingProfile
  profileName
  optionsVersion
  rebindVersion
  actionMaps[]

ActionMap
  name
  actions[]

Action
  mapName
  name
  labelKey
  descriptionKey
  bindings[]

Binding
  rawInput
  device
  chords[]
  modifierTokens[]
  kind

InputChord
  deviceInstance
  inputKind
  inputName
```

Classify input kinds as `keyboard`, `mouse`, `gamepad`, `joystick`, `axis`, `hat`, or `unknown`. Keep `rawInput` intact for diagnostics and for a future XML export path.

The action owns its name and description; a binding row presents the binding text with its parent action's name and description. Do not duplicate localization text on each physical binding.

Input parsing must be split from input formatting. This allows the app to support an internal model such as `KB1 + Left Alt + E` while rendering platform-appropriate labels such as `Left Alt + E`.

---

## 5. Human-Readable Mapping

Description lookup should use a layered localization strategy:

1. **Curated action metadata**
   - Match on stable `actionMap.name + action.name`.
   - Optionally add patch/version aliases when the action identifier changes.
   - Map identifiers to localization keys rather than English text.
   - Provide both a short name and a description for every curated action.
   - Store the mapping data outside application code in a maintained JSON or YAML catalog.

2. **Localized presentation**
   - Store each locale in a separate bundle, for example `locales/en-US.yaml`, `locales/de-DE.yaml`, or standard gettext `.po` files.
   - Resolve a short label and explanatory description through stable keys.
   - Resolve action-map category names through the same localization mechanism.
   - Use locale fallback in this order: exact locale, language fallback, then English.
   - Treat an unknown action name as a catalog miss, not a localization failure.
   - Include locale coverage data so untranslated or newly introduced actions can be identified.

3. **Neutral name derivation**
   - Strip a leading vehicle prefix when useful, such as `v_`.
   - Split underscores into words.
   - Convert small, explicit acronym and modifier tables:
     - `ifcs` -> `IFCS`
     - `qdrive` -> `Quantum Drive`
     - `mfd` -> `MFD`
     - `esp` -> `ESP`
   - Convert common direction and operation words:
     - `toggle` -> `Toggle`
     - `cycle` -> `Cycle`
     - `increase` / `decrease` -> `Increase` / `Decrease`
     - `back` / `forward` / `left` / `right` -> `Backward` / `Forward` / `Left` / `Right`

4. **Safe fallback**
   - If no curated metadata exists, show the humanized action name.
   - Always preserve the raw action identifier in a secondary or expandable field.
   - Never present internal tokens as the primary description.

Action-map names also require curated display names. For example:

* `spaceship_movement` -> `Flight - Movement`
* `spaceship_targeting_advanced` -> `Flight - Advanced Targeting`
* `spaceship_mining` -> `Flight - Mining`
* `player_emotes` -> `General - Emotes`

The catalog is intentionally authoritative only for descriptions and presentation. It must not replace the XML as the source of assignments, devices, or binding counts.

---

## 6. Input Rendering

Raw input strings should be converted through a token dictionary:

| Raw token | Display |
| --- | --- |
| `kb1_lctrl` | Left Ctrl |
| `kb1_ralt` | Right Alt |
| `kb1_lshift` | Left Shift |
| `kb1_rctrl` | Right Ctrl |
| `kb1_mouse5` | Mouse 5 |
| `kb1_np_3` | Numpad 3 |
| `kb1_num1` | Number 1 |
| `kb1_rbracket` | `]` |
| `js1_button11` | Joystick 1 - Button 11 |
| `js1_hat1_up` | Joystick 1 - Hat 1 Up |
| `js1_rotz` | Joystick 1 - Twist/Rudder Axis |
| `js2_slider1` | Joystick 2 - Slider 1 |
| `gp1_shoulderr` | Gamepad - Right Shoulder |

Rules:

* Split `+` into ordered modifier and key/axis components.
* Normalize aliases with unknown aliases retained as humanized fallbacks.
* Render modifier combinations consistently, with modifiers first.
* Label joystick axes by their intended function in context when the action provides it; for example, a `y` axis on `v_strafe_vertical` is a vertical strafe axis rather than merely `Axis Y`.
* Represent a blank or whitespace-only input as an unbound placeholder.
* Mark axis-based assignments as axis bindings, not as one-time presses.
* Display missing and placeholder bindings distinctly: `(No binding)` means absent, while `(Axis)` or `(Hat)` describes an assigned control.

---

## 7. Keybind Browser

The initial UI should be sufficient for the app's primary read-and-understand goal:

* Provide a conventional application menu or an equally discoverable in-window menu. At minimum, **File** contains Open, Save, Save As, and Exit; **Edit** contains Undo and Redo. If native menus are unavailable or inconsistent across supported platforms, use an in-window menu with the same commands and behavior.
* Provide standard shortcuts: `Ctrl+O` for Open, `Ctrl+S` for Save, `Ctrl+Shift+S` for Save As, `Ctrl+Z` for Undo, and `Ctrl+Y` for Redo on Windows/Linux.
* Open an existing Star Citizen bindings XML file through a native or in-app file picker.
* Save changes back to the current bindings file.
* Save As copies the current profile to a user-selected XML file.
* Profile name and source metadata.
* A visible status when the source file has changed externally, with an action to review or resolve the conflict.
* Action maps in an accordion/concertina hierarchy that can be expanded and collapsed independently.
* Expanded sections display a responsive grid of bindings and their human-readable names.
* Human-readable action labels with raw names available in search or an expandable detail view.
* Current bindings shown as device-aware chord badges.
* Each binding row uses the concise `binding — name` presentation.
* The description appears in a mouse-hover tooltip, for example:
  - `Spacebar — Jump`
  - Tooltip: `Makes your character jump upward.`
* The detail panel should also include the description for keyboard navigation and non-pointer access.
* Search across display label, description, raw action name, action-map name, and input text.
* Filter by action map, device type, and whether an action is bound.
* A clear indication of unknown or unreviewed descriptions.
* A detail panel showing the raw XML identifiers and every assigned rebind.
* Focused binding controls support Backspace or Delete to clear the selected binding.

Do not highlight every string containing a key. Bindings must remain associated with their action and action map.

### 7.1 Accordion Layout

Use two or three accordion levels:

```text
General
  Ship Systems
    [binding badge] — [human-readable name]
    [binding badge] — [human-readable name]
Flight
  Movement
    [binding badge] — [human-readable name]
```

Keep the expanded/collapsed state for each section during the current session. When filters are active, expand matching sections automatically and collapse or dim empty sections.

### 7.2 Dual Filtering

Provide two purpose-specific filters:

* **Binding filter:** Find actions assigned to an exact or partial control.
  - Keyboard: `Space`, `Ctrl+K`, `Numpad 3`
  - Joystick: `Joystick 2 - Button 3`
  - Mouse: `Mouse 5`
  - Match normalized display text, raw input tokens, and device aliases.
  - Example: entering `Space` should find actions bound to the Spacebar.

* **Name filter:** Find actions by name or description.
  - Match display name, description, raw action name, and action-map name.
  - Filter down only the matching actions while leaving section structure visible.
  - Example: entering `walk forward` should find the matching movement action and its binding.

The filters should be independent. The binding filter answers `what does this button do?`; the name filter answers `what button performs this action?`. When both are populated, apply them together as an intersection.

Include a clear/reset control and show a match count for the filtered grid.

---

## 8. Binding Subsections

Bindings should be grouped by gameplay context, while the `actionmap` remains the stable XML identifier.
The proposed initial hierarchy follows the Star Citizen control guides:

| Subsection | Display section | XML action maps |
| --- | --- | --- |
| General | Operator Modes and Seats | `seat_general` |
| General | Ship Systems | `spaceship_general`, `lights_controller` |
| General | Emotes | `player_emotes` |
| General | Optical Tracking | `player_input_optical_tracking` |
| General | Spectator | `spectator` |
| Flight | View | `spaceship_view` |
| Flight | Movement | `spaceship_movement`, `spaceship_quantum`, `vehicle_driver` |
| Flight | Targeting | `spaceship_targeting`, `spaceship_targeting_advanced`, `spaceship_radar` |
| Flight | Weapons | `spaceship_weapons`, `spaceship_missiles` |
| Flight | Defensive Systems | `spaceship_defensive` |
| Flight | Power and Engineering | `spaceship_power` |
| Flight | Scanning | `spaceship_scanning` |
| Flight | Mining | `spaceship_mining` |
| Flight | Salvage | `spaceship_salvage` |
| Flight | Tractor Beam | `tractor_beam` |
| On Foot | Player | `player` |
| On Foot | Interaction and Choice | `player_choice` |

The hierarchy is presentation metadata, not part of the XML parser:

* Map a known `actionmap.name` to a top-level section and subsection in the action catalog.
* Preserve the action-map name internally and include it in search and detail views.
* Allow future action maps to appear under an `Other` section instead of being hidden.
* Keep axis assignments beside their related controls rather than splitting them into a separate device-only view.
* Add specialized subsections as needed for distinct Star Citizen control contexts, such as EVA, vehicles, turrets, or ship repair.

The UI should use expandable top-level sections in this order:

```text
General
  - Operator Modes and Seats
  - Ship Systems
  - Emotes
  - Optical Tracking
  - Spectator
Flight
  - View
  - Movement
  - Targeting
  - Weapons
  - Defensive Systems
  - Power and Engineering
  - Scanning
  - Mining
  - Salvage
  - Tractor Beam
On Foot
  - Player
  - Interaction and Choice
Other
```

This taxonomy can later include a context-specific `Turret` section; the sample profile currently places its turret actions in `seat_general` and `spaceship_*` maps, so those should be recategorized by action where action data is more specific.

---

## 9. Theme and Settings

The app should support at least light and dark themes, with dark grey as the initial dark theme background rather than pure black.

### 9.1 Initial Dark Palette

| Role | Hex |
| --- | --- |
| Background | `#24282B` |
| Primary text / primary accent | `#DDF0F4` |
| Primary highlight | `#6CB8C7` |
| Secondary accent | `#49BEBC` |
| Secondary highlight | `#49BEBC` |
| Action | `#D1FDE1` |
| Action highlight | `#19D961` |
| Warning | `#FFAAB6` |
| Warning highlight | `#DB193B` |

The exact surface, border, and text colors derived from this palette are implementation details and must maintain readable contrast. Do not use pure black for the default dark background.

Recommended semantic usage:

* `Primary` for main text and primary controls
* `Primary Highlight` for focus, selected navigation, and links
* `Secondary` for supporting controls and visual separation
* `Action` for normal confirmations and success states
* `Action Highlight` for active success actions or selected state
* `Warning` for caution surfaces and lower-severity alerts
* `Warning Highlight` for destructive or high-severity actions

### 9.2 Configurable Theme Model

Represent the theme as typed semantic colors rather than hard-coded component colors:

```text
Theme
  mode: dark | light | custom
  fontFamily
  fontSize
  fontWeight
  fontStyle
  background
  surface
  surfaceElevated
  text
  textMuted
  border
  primary
  primaryHighlight
  secondary
  secondaryHighlight
  action
  actionHighlight
  warning
  warningHighlight
```

Derived colors for hover, pressed, disabled, and focus states should come from the semantic palette or be calculated consistently. Persist only user-authored values and the selected mode; do not require a full generated theme to be stored.

### 9.3 Typography

Typography should be configurable independently of the color theme:

```text
Typography
  fontFamily
  baseFontSize
  weight
  style
```

Recommended settings:

* **Font family:** A platform-safe font selector with defaults such as `System UI`, `Inter`, `Segoe UI`, `Noto Sans`, or a custom installed font.
* **Base size:** A numeric value in points or pixels, within an accessible range such as 12–24.
* **Weight:** Normal or semibold, with medium/bold options if supported by the selected font.
* **Style:** Normal, with optional italic support for secondary or descriptive text.

Use a derived type scale rather than a separate size for every control:

* Small labels
* Base text
* Section headings
* Page/profile headings

Respect the platform text-scaling preference. Configured size should act as a multiplier or preferred base size, never as a fixed size that overrides accessibility settings.

Persist typography separately from palette values so switching themes preserves font choices. If a selected font is unavailable, fall back to `System UI` and indicate the missing font in Settings.

### 9.4 Settings Dialog

The Settings dialog should include:

* Light, dark, and custom mode selection
* Native or web color-selector controls for each semantic palette role
* Text displays for `#RRGGBB` values
* Font-family selection
* Base-font-size control
* Weight and style controls
* Live preview of buttons, badges, accordion headers, grids, warnings, tooltips, and text sizes
* A **Developer mode** checkbox
* A contrast warning when a text/background pair is likely unreadable
* Reset to default and reset to application defaults actions
* Apply and cancel behavior with no theme mutation until Apply

The initial dark palette can be shipped as a preset. A future system-theme option may follow the same model.

Theme settings belong in local application configuration, remain independent of imported profile XML, and should not affect binding names or descriptions.

---

## 10. Developer Mode

Developer mode is an optional local UI mode for maintaining the action catalog and identifying incomplete presentation metadata.

Enable it with the Developer mode checkbox in Settings. It should persist for the local user and may be disabled or hidden through application configuration in packaged builds.

### 10.1 Developer Status

When Developer mode is enabled, display build metadata in the lower-right corner:

* Application version
* Build timestamp
* Optional build channel or Git revision

The footer should remain non-interfering and should not cover the binding grid or dialogs.

### 10.2 Unresolved Metadata Highlighting

Highlight fields that do not have a meaningful curated name or description:

* Neutral-name fallback labels
* Missing locale translations
* Missing descriptions
* Unknown input tokens
* Unknown or unmapped action-map names

Use the warning palette for highlight color and expose the reason in a tooltip or detail panel. For example:

```text
v_ifcs_toggle_esp  [warning highlight]
  Name: Toggle IFCS ESP
  Description: Missing curated description
  Resolution: Add localization keys and a description
```

Highlighting must not alter XML or binding semantics. Raw identifiers should remain visible when developer metadata is incomplete.

### 10.3 Editing Behavior

Normal mode should allow targeted editing of existing binding assignments:

* Double-click an existing binding field to edit that existing XML binding manually.
* Do not capture physical input; edit the binding string or its component fields as text.
* Editing changes only the selected existing `<rebind>`; it does not add another rebind or create an action.
* Confirm edits with Enter or an explicit save control.
* Cancel edits with Escape or cancel.
* Focus a selected binding field and press Backspace or Delete to clear it.
* Provide an explicit clear control or context action as an accessible alternative to the Backspace/Delete shortcut.
* Show a binding as `(No binding)` immediately after clearing and mark the change as unsaved.
* Require confirmation before clearing if more than one binding or profile assignment would be affected.
* Keep display/catalog edits separate from the raw XML binding. Do not provide input capture or a UI operation to assign a new physical key or button.

Developer mode should allow all presentation and existing-assignment fields to be editable:

* Localized action display name (not the raw Star Citizen action identifier)
* Localized action description
* Action-map/subsection names
* Localization key
* Existing raw binding string or its input-token components
* Input-token aliases
* Section and subsection assignment

Raw action-map and action identifiers are stable source identifiers and should remain read-only. Catalog/localization edits are stored separately from profile edits; existing binding-string edits affect the binding XML. Neither mode creates new action nodes or adds new rebinds.

### 10.4 Edit Persistence and Safety

Use a catalog edit review path so accidental changes are not silently written:

* Keep an in-memory draft until Save is chosen.
* Mark changed fields and changed locale bundles.
* Warn before discarding unsaved changes.
* Record intentional clears separately from actions that were originally unbound, retaining the exact XML representation needed for reliable undo and serialization.
* Write catalog/localization edits to the user's writable metadata-override directory without mutating the original XML profile or shipped source data.
* Treat Save and Save As as profile binding operations; keep them separate from Save Changes in the developer catalog editor.
* Saving a catalog edit should not silently rewrite the currently opened binding XML.
* Preserve raw values in the detail panel and in exported diagnostics.
* Reject duplicate localization keys and invalid theme or catalog structures.

### 10.5 Search and Diagnostics

Developer mode should support filters for:

* Missing names
* Missing descriptions
* Missing translations
* Unknown input tokens
* Unknown action maps
* Edited but unsaved fields

This mode provides enough metadata coverage to maintain the local catalog while keeping the normal browser compact and read-only where appropriate.

---

## 11. Catalog Maintenance

The action catalog and locale text are application metadata, stored separately from every imported or saved Star Citizen XML profile. Saving a binding profile must never write labels, descriptions, or translations into that XML.

```yaml
# action_catalog.yaml
action_maps:
  spaceship_movement:
    label_key: action_map.spaceship_movement

actions:
  spaceship_movement:
    v_toggle_salvage_mode:
      label_key: action.spaceship_movement.v_toggle_salvage_mode-name
      description_key: action.spaceship_movement.v_toggle_salvage_mode-description
```

```yaml
# locales/en-US.yaml (equivalent bundles exist for other locales)
action_map:
  spaceship_movement: Flight - Movement

action:
  spaceship_movement:
    v_toggle_salvage_mode-name: Toggle Salvage Mode
    v_toggle_salvage_mode-description: Switch the ship's salvage system into or out of salvage mode.
```

The catalog key is scoped by action-map and raw action name because raw action names may be reused in different maps. Labels and descriptions use separate localization keys and live in locale bundles such as `locales/en-US.yaml` and `locales/de-DE.yaml`. Input-token translations may use shared keys in those bundles.

A missing localized label or description should fall back to English or the neutral name derivation. The UI should mark curated versus fallback text.

Developer edits modify catalog/localization files or user overrides, never raw action identifiers in the XML. Keep shipped catalog data read-only; save user-authored overrides in the user's writable application-data directory so edits survive app updates and installations in read-only locations. Provide a deliberate export/review workflow before contributing overrides back to shipped data.

---

## 12. Testing Strategy

Testing is a first-class requirement because an XML profile can look correct in the UI yet be changed or serialized in a way Star Citizen cannot load. During implementation, run the relevant automated and manual checks locally; do not make testing on every supported OS a per-story requirement. Defer broader cross-platform release qualification to the release gate. Automated tests should not require Star Citizen, a joystick, or network access.

### 12.1 Test Layers

* **Unit tests:** XML parsing, binding-token parsing/formatting, catalog and locale lookup, fallback behavior, filtering, theme validation, and dirty-state transitions.
* **Integration tests:** Open a profile, apply supported edits, undo/redo them, save or Save As, reopen the result, and verify both the visible model and XML contents.
* **UI tests:** File dialogs, accordion expansion, both independent filters and their intersection, tooltips and keyboard-accessible descriptions, editing, clearing, unsaved prompts, and settings persistence.
* **Launcher tests:** Simulate Python missing/present/unsupported, `uv` missing/present, user consent/decline, dependency installation success/failure, and native webview prerequisites without modifying the host or requiring network access.
* **Local smoke tests:** Launch and exercise the changed behavior on the developer's local OS and supported Python version. Cross-platform smoke testing is a release check, not a per-story blocker.

Use the test framework and UI automation supported by the selected application stack; keep core parsing and serialization tests independent of the GUI toolkit.

### 12.2 XML Fixture and Compatibility Tests

Treat the XML profiles in `Documentation/mappings/` as a fixture corpus, including the older GameGlass profiles and the StarBinder/layout profiles from multiple game versions.

Tests should verify:

* All fixtures parse without losing action maps, actions, repeated rebinds, or metadata.
* Known inventory totals are checked per fixture as regression baselines, not as assumptions applied to every future Star Citizen profile.
* Identical action names in different action maps remain distinct.
* Multiple rebinds for one action remain separate and ordered.
* Unbound actions, whitespace-only inputs, axes, hats, and unknown tokens remain distinguishable.
* Unknown XML elements and attributes survive a semantic round-trip.
* A newly introduced action map, action, device, or token is retained and reported as unknown rather than discarded.
* Parsing malformed or truncated XML reports a useful error and leaves the currently open profile unchanged.
* Compatibility validation reports well-formedness and StarBinder structural errors separately from uncertain in-game compatibility.

Keep representative fixtures small and focused for unit tests; retain the supplied full profiles for compatibility and regression tests.

#### XML Preservation Experiments (Required Before Promising Format Preservation)

The initial contract is semantic preservation of supported and unknown XML data, not byte-for-byte formatting preservation. Do not claim that comments, whitespace, element ordering, or formatting survive edits until tested.

When implementation reaches real-file save testing:

1. Make controlled variants of real exported profiles: reorder elements, compact/pretty-print whitespace, add comments, and modify only one binding.
2. Compare no-op saves and edited saves for preserved XML meaning, comments, unknown attributes/elements, ordering, and formatting.
3. Import each variant into the matching Star Citizen build and record which transformations are accepted or rejected.
4. Choose and document the safest serialization behavior based on those results. If a no-op save is requested, prefer leaving the original bytes untouched.

Until that experiment is complete, preserve unknown nodes/attributes where the XML library permits, but do not promise comments or formatting will round-trip or that reordered/compressed XML is game-compatible.

### 12.3 Save and Edit Tests

* Saving without edits does not change binding meaning or remove unrelated XML content.
* Clearing a binding changes only the selected assignment using a verified Star Citizen unbind representation; it distinguishes intentional clears from actions originally unbound.
* Undo restores the exact prior binding representation and ordering; Redo reapplies the clear. Undo and Redo histories do not cross between profile and catalog edits.
* Save As leaves the source file unchanged and makes the chosen destination the active save target.
* Reopening a saved file reproduces the intended profile and binding state.
* A changed source file is detected by fingerprint; saving aborts without overwriting it and presents reload/review/Save As choices.
* A source changed between preflight and atomic replacement is detected at the final recheck; StarBinder does not silently overwrite it.
* Saving creates a backup of an existing target, rotates only after a successful atomic replacement, and preserves the configured number of recent backups.
* Failures during serialization, validation, backup, or replacement leave the original file intact and the in-memory model dirty.
* The staged serialized file is re-parsed and structurally validated before replacement; tests do not misrepresent this as proof of Star Citizen acceptance.
* Canceling an unsaved-changes prompt does not replace or discard the current profile.
* Catalog/localization edits never modify the binding XML and persist in separate locale/catalog data or user overrides.

### 12.4 Presentation and Filtering Tests

* Exact and partial binding searches match both normalized display labels and raw input tokens (for example `Space` and `js2_button3`).
* Name searches match localized labels, descriptions, and raw action identifiers.
* Populating both filters returns only entries matching both criteria.
* Unknown action names, translations, and input tokens show safe fallbacks and developer-mode diagnostics.
* Tooltip descriptions are also accessible without a mouse.
* Theme and typography settings survive restart; invalid or unavailable values fall back without making the UI unusable.

### 12.5 Release Checks

Before a release, run the automated suite locally and complete cross-platform smoke checks on Windows and the supported Linux distribution(s). Maintain a manual checklist for first-run Python/`uv` detection and consent flow, native prerequisites, file picker behavior, app launch, Save/Save As, undo/redo, external-edit conflict resolution, and opening saved profiles in Star Citizen. Do not treat a successful XML parse or structural validation by StarBinder as proof that Star Citizen accepts a generated file.

---

## 13. Implementation Stories

Stories are ordered by dependency and risk. The first is a time-boxed technical spike; it validates the proposed UI stack before substantial application code is built. Run the spike in developer-prepared environments so it does not depend on the end-user bootstrap story.

### Story 1 — Validate NiceGUI Native Mode on Windows and Bazzite

**As a developer,** I want a minimal NiceGUI native-mode proof of concept on Windows and Bazzite, **so that** we can confirm the proposed desktop UI stack and its system requirements before committing to it.

**Acceptance criteria**

* A small test app opens a native window and displays a basic control on both platforms.
* A native file picker opens, returns a selected XML path, and the app displays the selected filename without parsing or changing the file.
* The app presents File and Edit menus (native or in-window); File → Open invokes the picker. Save and Undo/Redo may be labeled placeholders in this spike.
* Closing the window shuts down the local server and process cleanly.
* Record the tested OS versions, Python version, NiceGUI version, webview engine, installation steps, and any native prerequisites.
* If either platform fails or requires unacceptable setup, document the failure and choose an alternative before proceeding to Story 2.

**Outcome:** The acceptance checks passed on Bazzite and Windows 11. Both
launched the native window, selected an XML file using File → Open, displayed
the selection without parsing or changing it, and shut down cleanly. The
in-window File/Edit menus worked on both; their spike layout is only a
functional probe and should not be carried into the product UI as-is. NiceGUI
3.19.0 was used on both. Bazzite used Python 3.13.18 and pywebview 6.2.1 with
Qt 6.12.0. Windows used uv-managed Python 3.13 and WebView2; its exact Python
patch and WebView2 version, and the Windows build number, were not recorded.
The Bazzite OS was 45.20261117.1 (Kinoite). Setup used `uv run --python 3.13
main.py` (or the Windows helper batch file) with internet access for any
uncached Python and packages.

The spike did not test pasting a full path into the native picker; direct path
entry remains a product requirement from §3.2 and is not a Story 1 blocker.

### Story 2 — Establish the Application Skeleton and Runtime Decision

**As a developer,** I want a minimal, reproducible Python project with the chosen desktop runtime, **so that** features can be developed and tested consistently.

**Acceptance criteria**

* The successful outcome of Story 1 is recorded as the UI/runtime decision, or an alternative is chosen with rationale.
* A minimal app starts from the repository using the documented development command.
* Dependencies are declared and pinned according to the selected dependency-management approach.
* Automated tests run on the chosen Python support floor and the initial CI target (Linux).

**Outcome:** NiceGUI native mode is the selected runtime. The app skeleton is
packaged from `src/`, launched with `uv run --locked python -m starbinder`,
and binds its native-mode server to loopback. Python 3.11 is the support floor;
the exact dependency graph is committed in `uv.lock`, generated from pinned
NiceGUI/native-webview dependencies in `pyproject.toml`. Local unit tests cover
the app's runtime selection and native launch configuration. Initial CI targets
Ubuntu Linux on Python 3.11; cross-platform checks remain for release
qualification. The local native window was visually confirmed by the user.

### Story 3 — Parse Star Citizen Profiles Safely

**As a user,** I want to open a Star Citizen action-map XML profile and see its contents represented accurately, **so that** I can understand what the profile contains without changing it.

**Acceptance criteria**

* Parse profile metadata, action maps, actions, and ordered rebind entries from the supplied fixture corpus.
* Preserve concrete assignments such as `kb1_ralt+m`, multiple rebinds, and action names repeated in different maps.
* Keep missing rebind elements distinct from whitespace-valued inputs such as `kb1_ `.
* Unknown XML content and input tokens remain available to the model and are reported without failing the import.
* Malformed input reports an actionable error and does not replace the currently open profile.
* Parser and model tests run without the UI.

### Story 4 — Resolve Action Names, Descriptions, and Categories

**As a user,** I want action identifiers presented with understandable names and descriptions, **so that** I can interpret bindings without knowing internal game identifiers.

**Acceptance criteria**

* Action-map/action identifiers resolve through a curated catalog to localized name and description keys.
* Text is kept in separate locale bundles and never written into the profile XML.
* Locale fallback and neutral-name fallback work when metadata is missing.
* The UI/model can identify whether text is curated, translated, or a fallback.

### Story 5 — Browse and Search Bindings

**As a user,** I want bindings grouped into expandable subsections and searchable by either control or action, **so that** I can answer both “what does this control do?” and “what control performs this action?”

**Acceptance criteria**

* Display the profile in the agreed accordion hierarchy and responsive binding grid.
* Show each input with its action name; show the description on hover and through keyboard-accessible details.
* Binding and name filters work independently and together as an intersection.
* Search matches normalized input display, raw input tokens, localized text, and raw action identifiers.
* Unknown maps/actions remain visible under `Other` or an equivalent fallback section.
* Optional joystick/gamepad capture detects a pressed button or moved axis and uses it to search existing assignments only; it never creates or edits bindings.

### Story 6 — Add Theme, Typography, and User Settings

**As a user,** I want to customize the appearance and persist my preferences, **so that** the app is comfortable to use across sessions.

**Acceptance criteria**

* Light and dark themes work, with the specified dark palette as the initial default.
* Font family, size, weight, and style settings work with safe fallback when a font is unavailable.
* Settings preview, apply, cancel, and reset behave as specified.
* Settings persist in a user-writable application-data location, separate from profile XML and shipped catalog data.

### Story 7 — Edit Existing Bindings with Undo and Redo

**As a user,** I want to edit or clear an existing binding and undo mistakes, **so that** I can maintain assignments already present in a profile.

**Acceptance criteria**

* Double-click edits only the selected existing binding; the UI does not capture physical input or create actions/rebinds.
* Backspace/Delete and an explicit clear action clear the selected assignment.
* The exact Star Citizen-compatible representation for an intentional clear is verified by in-game tests before enabling profile-saving clears.
* Undo restores the prior raw value and order exactly; Redo reapplies the operation.
* The UI distinguishes an edited empty/cleared assignment from a profile entry that was originally absent.
* Profile and catalog Undo/Redo histories are isolated.

### Story 8 — Save, Save As, Backups, and Conflict Resolution

**As a user,** I want to save profile edits safely without losing external changes, **so that** I can use the resulting profile in Star Citizen with recoverable history.

**Acceptance criteria**

* Save and Save As follow the documented path and unsaved-change behavior.
* The exact serialized temporary file is parsed and structurally validated before replacement.
* Replacing a file uses an atomic operation and creates a verified backup before replacement; backup rotation occurs only after success.
* External modification is detected and highlighted; Save aborts on conflict and offers reload, review, or Save As without automatic merge.
* Failures preserve the original file and leave in-memory changes dirty.
* In-game compatibility and XML format-preservation experiments are completed and recorded before claiming compatibility for edited/saved output.

### Story 9 — Maintain Catalog Metadata in Developer Mode

**As a catalog maintainer,** I want to find and edit unresolved labels, descriptions, translations, and input aliases, **so that** the human-readable catalog can evolve independently of user profiles.

**Acceptance criteria**

* Developer mode shows build metadata and highlights unresolved catalog/localization fields.
* Presentation fields and existing binding assignments have distinct edit paths.
* Catalog edits save to user-writable overrides, are undoable, and do not modify binding XML.
* Duplicate keys, invalid structures, and unsaved drafts are reported safely.

### Story 10 — Deliver the First-Run Launcher

**As a user,** I want the launcher to check prerequisites and ask before installing tools, **so that** I can start the app without manually configuring a global Python environment.

**Acceptance criteria**

* Python and `uv` are detected independently, with supported versions verified.
* Missing Python, `uv`, or native webview prerequisites produce clear setup instructions and explicit consent before any installation.
* Dependencies install only into an isolated user-writable environment; no global or administrator install is required.
* Failure is visible and actionable, and the launcher never starts with a partially provisioned environment.
* First-run behavior is tested by simulated prerequisite states and by double-clicking on each supported OS.

Stories may be split into smaller implementation tasks, but their acceptance criteria and dependencies should remain intact.