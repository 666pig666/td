# Audio Analysis CHOP Chains

Standard patterns for extracting usable visual-control signals from audio.

## Core Chain: Audio Input → Band Split → Analysis → Smoothing

### Step 1: Audio Input

```
audiodeviceInCHOP (name: audio_in_chop)
  - driver: system default (or specify device index)
  - channels: 2 (stereo)
  - sample rate: 44100 or 48000
```

### Step 2: Spectrum Analysis

```
audiospectrumCHOP (name: audio_spec_chop)
  - input: audio_in_chop
  - output: frequency-domain representation
  - FFT size: 2048 (good balance of frequency/time resolution)
  - window: Hanning
```

### Step 3: Band Isolation

Create three `selectCHOP` + `analyzeCHOP` pairs for bass/mid/high:

**Bass (20-250 Hz):**
```
selectCHOP (name: band_bass_chop)
  - input: audio_spec_chop
  - channel select by index range corresponding to 20-250 Hz
analyzeCHOP (name: audio_low_chop)
  - input: band_bass_chop
  - function: average (RMS of band energy)
```

**Mid (250-4000 Hz):**
```
selectCHOP (name: band_mid_chop)
  - input: audio_spec_chop
  - channel select by index range corresponding to 250-4000 Hz
analyzeCHOP (name: audio_mid_chop)
  - input: band_mid_chop
  - function: average
```

**High (4000-20000 Hz):**
```
selectCHOP (name: band_high_chop)
  - input: audio_spec_chop
  - channel select by index range corresponding to 4000-20000 Hz
analyzeCHOP (name: audio_high_chop)
  - input: band_high_chop
  - function: average
```

### Step 4: Beat Detection

```
audiobandCHOP or custom onset detection:
  - Compare current bass energy to short-term average
  - Threshold crossing = beat onset
  - Output: single channel, 0 or 1

Implementation via td_exec_python if no native beat CHOP:
  Use a chopexecDAT watching audio_low_chop
  Trigger when value exceeds threshold * rolling_average
  Output pulse to a constantCHOP (name: audio_beat_chop)
```

### Step 5: Smoothing (CRITICAL)

Every analysis output MUST pass through smoothing before binding to visual parameters.

```
lagCHOP (name: smooth_low_chop)
  - input: audio_low_chop
  - lag: 0.15 sec (attack), 0.3 sec (release)
  - reason: raw FFT → visual = seizure-inducing jitter

lagCHOP (name: smooth_mid_chop)
  - input: audio_mid_chop
  - lag: 0.1 sec (attack), 0.25 sec (release)

lagCHOP (name: smooth_high_chop)
  - input: audio_high_chop
  - lag: 0.05 sec (attack), 0.15 sec (release)
  - note: treble needs faster response than bass
```

Attack/release asymmetry is essential: fast attack follows transients, slow release prevents flicker.

### Step 6: Normalization

```
mathCHOP (name: norm_low_chop)
  - input: smooth_low_chop
  - range: map input [measured_min, measured_max] → [0, 1]
  - note: measured range depends on source material; start with [0, 0.5] → [0, 1]
    and adjust per session
```

## Bulk Creation via td_exec_python

For speed, create the entire audio chain in one Python call:

```python
p = op('/project1')

# Audio in
ain = p.create(audiodeviceinCHOP, 'audio_in_chop')

# Spectrum
spec = p.create(audiospectrumCHOP, 'audio_spec_chop')
spec.inputConnectors[0].connect(ain)

# Per-band analysis (bass example)
sel_bass = p.create(selectCHOP, 'band_bass_chop')
sel_bass.inputConnectors[0].connect(spec)
# Set channel selection params for bass range

ana_bass = p.create(analyzeCHOP, 'audio_low_chop')
ana_bass.inputConnectors[0].connect(sel_bass)
ana_bass.par.function = 4  # RMS or average — check via td_query_op

lag_bass = p.create(lagCHOP, 'smooth_low_chop')
lag_bass.inputConnectors[0].connect(ana_bass)
lag_bass.par.lag1 = 0.15
lag_bass.par.lag2 = 0.3

# Repeat for mid, high...
```

IMPORTANT: The exact parameter names (`par.function`, `par.lag1`, etc.) depend on the TD version. After creating each operator, use `td_query_op` to verify available parameter names if uncertain.

## MIDI Input Chain

```
midiinCHOP (name: midi_in_chop)
  - device: first available (or specify by name)
  - type: Control Change

selectCHOP (name: midi_cc36_chop)  # one per active CC
  - input: midi_in_chop
  - channel: cc36 (or however TD names the channel)

mathCHOP (name: midi_cc36_map_chop)
  - input: midi_cc36_chop
  - from range: 0-127
  - to range: [target parameter range from CC_MAP.md]
```

## Expression Binding Examples

After building the audio/MIDI chains, bind to POPs parameters:

```python
# Audio-reactive emission rate
td_set_expression(
  op_path='/project1/popnet1/emit_pop',
  param_name='rate',    # verify actual param name via td_query_op
  expression="op('/project1/norm_low_chop')['chan1'] * 50000"
)

# MIDI CC-controlled turbulence
td_set_expression(
  op_path='/project1/popnet1/force_turb_pop',
  param_name='amp',
  expression="op('/project1/midi_cc39_map_chop')['chan1']"
)

# Combined: audio modulated by MIDI depth control
td_set_expression(
  op_path='/project1/popnet1/force_turb_pop',
  param_name='amp',
  expression="op('/project1/norm_mid_chop')['chan1'] * op('/project1/midi_cc40_map_chop')['chan1']"
)
```

The modulation depth pattern (`audio_signal * midi_depth_cc`) is how Bank 2 CCs work: the CC scales how much audio affects the target parameter.
