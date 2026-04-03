---
name: td-pops-builder
description: >
  Build audio-reactive, MIDI CC-controlled TouchDesigner POPs (Point Operators)
  networks from plain language descriptions. Translates natural language into
  touchdesigner_mcp commands that create live TD networks. Use this skill whenever
  the user asks to create particle systems, point clouds, audio-reactive visuals,
  POPs networks, MIDI-controlled TD patches, or any TouchDesigner network involving
  points, particles, forces, emitters, or audio-driven motion. Also triggers on
  'td-pops', 'build me a particle system', 'make points that react to audio',
  'MIDI-controlled particles', or any request combining TouchDesigner with
  particles/points/audio/MIDI.
---

# TD POPs Builder

Build TouchDesigner Point Operator networks from plain language via `touchdesigner_mcp`.

## Architecture

- **Executor**: Claude Code (you), using `touchdesigner_mcp` tools
- **Target**: Running TouchDesigner instance connected via MCP
- **Approach**: Code-driven only. Python scripting via `td_exec_python` for bulk operations; individual MCP tools for targeted edits. No manual node patching.
- **Operator focus**: POPs (Point Operators family). GPU-accelerated point/particle processing.

## Mandatory First Step: Discovery

POPs operator availability depends on the TD version running. Before building anything, run discovery to enumerate what's available:

```
td_exec_python:
  code: |
    import json
    # Get all POP operator types available in this TD build
    pop_types = []
    for t in sorted(op('/').opTypes):
        if 'pop' in t.lower() or 'POP' in t:
            pop_types.append(t)
    # Also check for particlesGpu and related
    for t in sorted(op('/').opTypes):
        if 'particle' in t.lower():
            pop_types.append(t)
    json.dumps(pop_types)
```

Store the result. All subsequent operator creation MUST use only confirmed-available type strings. If an operator type is not in the discovery result, do NOT attempt to create it — inform the user it's unavailable in their TD build.

Also discover CHOP types for audio/MIDI:

```
td_exec_python:
  code: |
    import json
    relevant = []
    keywords = ['audio', 'midi', 'analyze', 'spectrum', 'beat', 'fft']
    for t in sorted(op('/').opTypes):
        if any(k in t.lower() for k in keywords):
            relevant.append(t)
    json.dumps(relevant)
```

## Workflow

When the user describes a desired visual in plain language:

### 1. Parse Intent

Extract from the description:
- **Emitter geometry**: What shape/source emits points (sphere, grid, line, custom SOP, etc.)
- **Forces/behaviors**: Gravity, turbulence, attraction, curl noise, advection, spin, etc.
- **Kill conditions**: Lifespan, boundary, fade-out
- **Audio-reactive bindings**: Which visual parameters respond to which frequency bands
- **MIDI CC bindings**: Which parameters are exposed for real-time control
- **Post-processing**: Feedback, bloom, color grading, GLSL effects
- **Render method**: Point sprites, instanced geometry, trails, lines

If the description is ambiguous, ask ONE clarifying question. Do not over-ask — make reasonable defaults and state them.

### 2. Plan the Network

Before creating any operators, write out the full network plan as a list:
- Parent container path (default: `/project1/popnet1`)
- Every operator to create, with type string and name
- Every connection (from → to)
- Every parameter override
- Every expression binding (audio/MIDI reactivity)
- GLSL post-processing chain if applicable

Present this plan to the user. Wait for confirmation before executing.

### 3. Build

Use `td_exec_python` for bulk creation (faster, fewer round-trips). Use individual MCP tools (`td_create_op`, `td_connect`, `td_set_params`, `td_set_expression`) for targeted modifications or when debugging.

**Bulk creation pattern via td_exec_python:**

```python
# Example: Create a basic emitter + force + render chain
p = op('/project1')

# Create container
container = p.create(baseCOMP, 'popnet1')  # Adjust type per discovery

# Create operators inside container
# ... (use discovered type strings)
```

After building, always run `td_layout` on the parent container for visual clarity.

### 4. Wire Audio Reactivity

Read `references/CHOP_CHAINS.md` for standard audio analysis patterns.

Core chain: `audiodeviceInCHOP` → `audiospectCHOP` → `analyzeCHOP` (per band) → `mathCHOP` (normalize/smooth)

Bind to POPs parameters via `td_set_expression`:
```
op('audio_low')['chan1']       # bass energy → emission rate, point scale
op('audio_mid')['chan1']       # mid energy → turbulence force, color shift
op('audio_high')['chan1']      # treble energy → speed, brightness
op('audio_beat')['chan1']      # onset → burst trigger, reset
```

Smoothing is critical. Always apply exponential smoothing via `lagCHOP` or `filterCHOP` between analysis and parameter binding. Raw FFT data is unusable for visual control — it's noisy and frame-jittery.

### 5. Wire MIDI CC Control

Read `references/CC_MAP.md` for the full 4-bank mapping schema.

Core chain: `midiinCHOP` → `selectCHOP` (per CC) → `mathCHOP` (remap 0-127 to target range)

Bank switching: CC 35 selects active bank (0-3). CCs 36-99 are mapped per bank.

Create a `selectCHOP` per active CC, with channel name matching the MIDI CC number. Use `td_set_expression` to bind to POPs parameters.

### 6. GLSL Post-Processing

Read `references/GLSL_POST.md` for shader patterns.

Standard chain: POPs render → `feedbackTOP` → `glslTOP` (effects) → `compositeTOP` → `outTOP`

### 7. Verify

After building, query the network to confirm:
```
td_list_ops on the parent container
td_query_op on key operators to verify parameter values
```

Report the final network structure to the user.

## Defaults

When the user doesn't specify, use these defaults:
- Resolution: 1920×1080
- Point count: 10000
- Lifespan: 3.0 seconds
- Emission: continuous (not burst)
- Audio input: system default audio device
- MIDI input: first available MIDI device
- Smoothing: `lagCHOP` with lag 0.15s
- Render: point sprites with additive blending
- Background: black

## Naming Convention

All operators follow: `{function}_{family}` pattern
- `emit_pop`, `force_turb_pop`, `kill_life_pop`
- `audio_in_chop`, `audio_spec_chop`, `audio_low_chop`
- `midi_in_chop`, `midi_cc36_chop`
- `render_top`, `feedback_top`, `post_glsl_top`
- `out_top`

## Reference Files

- `references/CC_MAP.md` — Full MIDI CC 4-bank mapping schema (CC 35-99). Read when wiring MIDI control.
- `references/CHOP_CHAINS.md` — Standard audio analysis CHOP chains. Read when wiring audio reactivity.
- `references/GLSL_POST.md` — Post-processing GLSL shader patterns. Read when adding visual effects.
- `references/NETWORK_RECIPES.md` — Complete network recipes for common POPs configurations. Read for end-to-end build patterns.

## Critical Rules

1. NEVER guess operator type strings. Use only types confirmed by discovery.
2. NEVER create operators without presenting the plan first.
3. ALL audio-reactive bindings MUST go through smoothing. No raw FFT to parameters.
4. ALL MIDI CC values MUST be remapped from 0-127 to the target parameter range.
5. ALWAYS run `td_layout` after building.
6. ALWAYS verify the network after building.
7. If an MCP call fails, report the exact error. Do not retry silently.
8. Python scripting and GLSL TOPs only. No instruction to manually patch anything.
