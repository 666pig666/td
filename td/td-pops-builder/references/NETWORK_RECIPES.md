# Network Recipes

End-to-end patterns for common POPs configurations. All recipes assume discovery has been completed and operator types confirmed.

## Recipe 1: Basic Audio-Reactive Particle Fountain

**Description**: Points emit upward from a point, affected by gravity and turbulence. Bass drives emission rate, mid drives turbulence, treble drives brightness.

**Network plan**:

```
AUDIO CHAIN (CHOPs):
  audio_in_chop → audio_spec_chop
  audio_spec_chop → band_bass_chop → audio_low_chop → smooth_low_chop → norm_low_chop
  audio_spec_chop → band_mid_chop  → audio_mid_chop → smooth_mid_chop → norm_mid_chop
  audio_spec_chop → band_high_chop → audio_high_chop → smooth_high_chop → norm_high_chop

MIDI CHAIN (CHOPs):
  midi_in_chop → [selectCHOPs per active CC] → [mathCHOPs for remapping]

POPS NETWORK:
  emit_pop (source: sphere, rate: 5000)
    → force_grav_pop (gravity Y: -2.0)
    → force_turb_pop (turbulence amp: 0.5, freq: 1.0)
    → kill_life_pop (lifespan: 3.0)

RENDER:
  [POPs output] → render_top (point sprites, size: 0.01, additive blend)
    → feedback_top (amount: 0.85)
    → bloom_thresh_top → bloom_blur_top → bloom_comp_top
    → colorgrade_top
    → out_top

BINDINGS:
  norm_low_chop → emit_pop.rate (scaled)
  norm_mid_chop → force_turb_pop.amp (scaled)
  norm_high_chop → colorgrade_top.uBrightness
```

**Build sequence** (td_exec_python):

```python
import json

p = op('/project1')

# 1. Audio chain
# (Use discovered type strings — these are placeholders)
audio_in = p.create(audiodeviceinCHOP, 'audio_in_chop')
audio_spec = p.create(audiospectrumCHOP, 'audio_spec_chop')
audio_spec.inputConnectors[0].connect(audio_in)

# Band isolation + analysis + smoothing (bass)
band_bass = p.create(selectCHOP, 'band_bass_chop')
band_bass.inputConnectors[0].connect(audio_spec)
# ... set channel range params for bass

analyze_bass = p.create(analyzeCHOP, 'audio_low_chop')
analyze_bass.inputConnectors[0].connect(band_bass)

smooth_bass = p.create(lagCHOP, 'smooth_low_chop')
smooth_bass.inputConnectors[0].connect(analyze_bass)
smooth_bass.par.lag1 = 0.15

norm_bass = p.create(mathCHOP, 'norm_low_chop')
norm_bass.inputConnectors[0].connect(smooth_bass)
# ... set range mapping params

# Repeat for mid, high...

# 2. POPs network
# Create container (type depends on discovery)
# Create emitter, forces, kill inside container
# Wire them in sequence

# 3. Render chain
# Create renderTOP, feedback, bloom, colorgrade, out

# 4. Bind expressions
# Use op().par.<param>.expr = "..." for each binding
```

## Recipe 2: MIDI-Sculpted Curl Noise Field

**Description**: Dense point cloud advected through a 3D curl noise field. All noise parameters (frequency, amplitude, evolution speed, lacunarity) mapped to MIDI CCs in Bank 1. No audio reactivity.

**Network plan**:

```
MIDI CHAIN:
  midi_in_chop → select per CC → math remap per CC

POPS:
  emit_pop (source: volume/box, rate: 50000, continuous)
    → force_curl_pop (curl noise advection)
    → kill_life_pop (lifespan: 8.0)

RENDER:
  render_top (point sprites, tiny size: 0.002, additive)
    → colorgrade_top
    → out_top

MIDI BINDINGS (Bank 1):
  CC 39 → curl amplitude
  CC 40 → curl frequency
  CC 41 → curl evolution speed
  CC 46 → drag
  CC 47 → spin rate
```

## Recipe 3: Beat-Triggered Burst Swarm

**Description**: Points accumulate slowly, then burst outward on every detected beat. Between beats, points orbit an attractor. Bass energy scales burst force, treble scales attractor pull.

**Network plan**:

```
AUDIO CHAIN:
  Full band split + beat detection (see CHOP_CHAINS.md)

POPS:
  emit_pop (source: point, rate: 500, continuous between beats)
  emit_burst_pop (triggered by beat_chop, count: 2000)
    → force_attract_pop (strength: variable, position: origin)
    → force_burst_pop (radial outward, strength: variable, triggered)
    → kill_life_pop (lifespan: 5.0)
    → kill_boundary_pop (bounding sphere, radius: 10)

RENDER:
  render_top → feedback_top (high feedback: 0.92, with rotation)
    → bloom → colorgrade → out_top

BINDINGS:
  audio_beat_chop → emit_burst_pop trigger
  norm_low_chop → force_burst_pop.strength (scaled)
  norm_high_chop → force_attract_pop.strength (scaled)
```

Beat triggering implementation: use a `chopexecDAT` watching the beat channel. On value change above threshold, execute Python that sets the burst emitter's `emit` pulse parameter.

## Recipe 4: Spectrum Waterfall

**Description**: Points emitted in a line, X position = frequency, Y = time (scrolling down), color/brightness = amplitude. Creates a scrolling spectrogram-as-particles effect.

**Network plan**:

```
AUDIO:
  audio_in_chop → audio_spec_chop → choptoTOP (spectrum_tex_top)

POPS:
  emit_pop (source: line along X axis, rate = FFT bin count per frame)
    → custom position logic via Python/expressions:
      point X = frequency bin index (normalized)
      point Y = emission time (scrolls via constant velocity downward)
      point color = spectrum amplitude at that bin
    → kill_life_pop (lifespan = scroll duration)

RENDER:
  render_top (point sprites, size mapped to amplitude)
    → out_top
```

This recipe requires per-point attribute control that may exceed simple POP parameter binding. Implementation likely needs `td_exec_python` with a custom CHOP-to-SOP pipeline or instancing from the spectrum texture.

## General Build Pattern

For any recipe, the build sequence is always:

1. **Create containers** — parent COMPs for organization
2. **Build audio chain** — input → spectrum → bands → analysis → smoothing → normalization
3. **Build MIDI chain** — input → select per CC → remap
4. **Build POPs network** — emitter → forces → kill conditions
5. **Build render chain** — render → feedback → effects → out
6. **Wire expression bindings** — audio/MIDI outputs → POPs/render parameters
7. **Layout** — `td_layout` on each container
8. **Verify** — `td_list_ops` + `td_query_op` on key nodes

Never skip steps 7 and 8.
