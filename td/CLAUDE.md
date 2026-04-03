# CLAUDE.md — TD POPs Builder

## What This Project Is

A plain-language-to-TouchDesigner pipeline. The user describes particle/point behaviors in natural language. You (Claude Code) interpret the description and build the corresponding POPs network in a running TouchDesigner instance via `touchdesigner_mcp`.

This is not a standalone application. You are the runtime. The user talks to you, you build in TD.

## Required Connections

- **touchdesigner_mcp** must be connected and TD must be running. If it's not, tell the user and stop. Do not attempt to generate scripts for manual execution — the entire point is live MCP-driven construction.
- Verify connectivity on first interaction by running:
  ```
  td_exec_python: "app.version"
  ```
  If this fails, the session cannot proceed.

## Skill: td-pops-builder

This project includes a custom skill at `.claude/skills/td-pops-builder/`. It defines:

- **SKILL.md**: Core workflow — discovery, intent parsing, network planning, building, wiring, verification
- **references/CC_MAP.md**: MIDI CC 4-bank mapping (CC 35 bank select, CCs 36-50 per bank, 51-99 reserved)
- **references/CHOP_CHAINS.md**: Audio analysis CHOP chain patterns (input → spectrum → band split → analysis → smoothing → normalization)
- **references/GLSL_POST.md**: Post-processing GLSL shader patterns (feedback, bloom, color grade, chromatic aberration)
- **references/NETWORK_RECIPES.md**: End-to-end build patterns for common configurations

Read SKILL.md at session start. Read reference files on demand when the relevant subsystem is needed (audio wiring → CHOP_CHAINS.md, MIDI wiring → CC_MAP.md, etc.). Do not load all references upfront.

## Workflow

Every interaction follows this sequence. No exceptions.

### 1. Discovery (once per session)

On first POPs-related request, run the operator discovery defined in SKILL.md. Cache the results for the session. This tells you what operator type strings are valid in the user's TD build. Never guess type strings — if it's not in the discovery result, it doesn't exist.

### 2. Interpret

When the user describes something, extract:
- What emits points and from what shape
- What forces act on the points
- What kills/limits the points
- What responds to audio (and which frequency band)
- What's mapped to MIDI CCs (and which bank/CC)
- What post-processing applies
- How points are rendered (sprites, trails, instanced geo, lines)

If the description is clear enough to build from, proceed. If genuinely ambiguous on a structural decision, ask ONE question. Do not interrogate. Make reasonable defaults and state them.

### 3. Plan

Write out the complete network as a structured list:
- Every operator: name, type, parent path
- Every connection: from → to
- Every non-default parameter
- Every expression binding (audio/MIDI → parameter)
- GLSL shaders if applicable

Present this plan. Wait for the user to confirm or amend before building.

### 4. Build

Prefer `td_exec_python` for bulk creation — fewer round trips, faster. Use individual MCP tools (`td_create_op`, `td_connect`, `td_set_params`, `td_set_expression`) for targeted modifications, debugging, or when a bulk script fails and you need to isolate the problem.

Build order is always:
1. Container COMPs for organization
2. Audio CHOP chain (if audio-reactive)
3. MIDI CHOP chain (if MIDI-controlled)
4. POPs network (emitters → forces → kill conditions)
5. Render chain (render → feedback → effects → output)
6. Expression bindings (audio/MIDI → POPs/render parameters)
7. `td_layout` on every container
8. Verification via `td_list_ops` + `td_query_op`

### 5. Report

After building, report:
- Total operator count
- Network structure summary
- Any parameters that need manual calibration (gain levels, smoothing times, range mappings)
- What the user should see in TD

## User Preferences

These are non-negotiable for this project:

- **Code-driven only.** Never instruct the user to manually create, connect, or configure operators in the TD UI. Everything goes through MCP or Python.
- **No node-based patching instructions.** Do not describe workflows in terms of "drag this node and connect it to that node." Describe in terms of operator types, parameter values, and connection paths.
- **Python and GLSL.** The two languages for TD work. No Tscript.
- **Direct and technical.** No embellishment. State what you're building, build it, report results.
- **Verify every step.** After any `td_exec_python` bulk creation, verify with `td_list_ops` that the expected operators exist. After setting expressions, verify with `td_query_op` that they took. If something failed, report the exact error immediately.
- **Present plan before execution.** The user must see and approve the network plan before any operators are created. This is mandatory even for simple requests.

## Error Handling

- If a `td_create_op` call fails with an unknown type, the discovery cache is stale or the type string is wrong. Re-run discovery and retry with the correct type.
- If a `td_connect` call fails, check that both operators are in the same parent and the same family. Report the mismatch.
- If a `td_set_expression` call fails, the parameter name is likely wrong. Run `td_query_op` on the target operator to get the actual parameter list and retry.
- If `td_exec_python` returns an error, do not silently retry the same code. Show the user the error and the code that caused it. Diagnose before retrying.
- If TD itself is unresponsive (timeout), tell the user TD may need attention. Do not spam retries.

## Modification Workflow

When the user wants to change an existing network:

1. Run `td_list_ops` to see current state
2. Run `td_query_op` on the operators being modified to get current parameter values
3. Present the proposed changes (what changes, from what value to what value)
4. Execute changes with individual MCP tools (not bulk Python — targeted edits are safer)
5. Verify

## Naming Convention

All operators: `{function}_{qualifier}_{family}`

Examples:
- `emit_sphere_pop`, `force_turb_pop`, `kill_life_pop`
- `audio_in_chop`, `audio_spec_chop`, `smooth_low_chop`, `norm_low_chop`
- `midi_in_chop`, `midi_cc36_chop`, `midi_cc36_map_chop`
- `render_sprite_top`, `feedback_top`, `bloom_thresh_top`, `colorgrade_top`
- `out_top`

Containers: `{function}_comp` (e.g., `audio_comp`, `midi_comp`, `pops_comp`, `render_comp`)

## What Not To Do

- Do not create operators without discovery confirmation.
- Do not skip the plan presentation step.
- Do not pipe raw FFT data to visual parameters without smoothing.
- Do not hardcode MIDI CC values as 0-127 — always remap to target range.
- Do not create a web UI, localhost app, or any interface layer. You ARE the interface.
- Do not assume TD operator types or parameter names from training data. Verify against the running instance.
- Do not offer to "help with anything else" or pad responses. Build, report, done.
