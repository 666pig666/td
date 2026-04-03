# MIDI CC Mapping Schema

4-bank system. CC 35 = bank select. CCs 36-99 mapped per bank.

## Bank Select

| CC  | Function       | Values         |
|-----|----------------|----------------|
| 35  | Bank select    | 0-3 (4 banks)  |

## Bank 0: Emission & Geometry

| CC  | Function              | Default Range    | Notes                          |
|-----|-----------------------|------------------|--------------------------------|
| 36  | Emission rate         | 0-50000 pts/sec  | Log scale recommended          |
| 37  | Point lifespan        | 0.1-30.0 sec     |                                |
| 38  | Emission burst count  | 0-10000           | 0 = continuous mode            |
| 39  | Emitter geometry sel  | 0-7 (presets)     | sphere/cube/grid/line/ring/custom |
| 40  | Emitter scale X       | 0.01-10.0         |                                |
| 41  | Emitter scale Y       | 0.01-10.0         |                                |
| 42  | Emitter scale Z       | 0.01-10.0         |                                |
| 43  | Initial velocity      | 0.0-5.0           |                                |
| 44  | Velocity spread       | 0.0-1.0           | 0=directional, 1=omnidirectional |
| 45  | Point size            | 0.001-0.5         |                                |
| 46  | Point size variance   | 0.0-1.0           |                                |
| 47  | Color hue             | 0.0-1.0           |                                |
| 48  | Color saturation      | 0.0-1.0           |                                |
| 49  | Color brightness      | 0.0-1.0           |                                |
| 50  | Color alpha           | 0.0-1.0           |                                |

## Bank 1: Forces & Dynamics

| CC  | Function              | Default Range    | Notes                          |
|-----|-----------------------|------------------|--------------------------------|
| 36  | Gravity Y             | -10.0-10.0       | Bipolar: center=0              |
| 37  | Gravity X             | -10.0-10.0       | Bipolar                        |
| 38  | Gravity Z             | -10.0-10.0       | Bipolar                        |
| 39  | Turbulence amplitude  | 0.0-5.0          |                                |
| 40  | Turbulence frequency  | 0.01-10.0        |                                |
| 41  | Turbulence evolution  | 0.0-2.0          | Speed of noise field change    |
| 42  | Attractor strength    | -5.0-5.0         | Negative=repel                 |
| 43  | Attractor position X  | -5.0-5.0         |                                |
| 44  | Attractor position Y  | -5.0-5.0         |                                |
| 45  | Attractor position Z  | -5.0-5.0         |                                |
| 46  | Drag / friction       | 0.0-1.0          | 0=none, 1=full stop            |
| 47  | Spin rate             | 0.0-10.0         |                                |
| 48  | Spin axis X           | -1.0-1.0         |                                |
| 49  | Spin axis Y           | -1.0-1.0         |                                |
| 50  | Curl noise strength   | 0.0-3.0          |                                |

## Bank 2: Audio Reactivity Modifiers

These CCs modulate how audio analysis maps to visual parameters.

| CC  | Function                  | Default Range | Notes                           |
|-----|---------------------------|---------------|---------------------------------|
| 36  | Audio gain (master)       | 0.0-4.0       | Pre-analysis gain               |
| 37  | Bass → emission rate      | 0.0-1.0       | Modulation depth                |
| 38  | Bass → point scale        | 0.0-1.0       |                                 |
| 39  | Bass → force strength     | 0.0-1.0       |                                 |
| 40  | Mid → turbulence amp      | 0.0-1.0       |                                 |
| 41  | Mid → color hue shift     | 0.0-1.0       |                                 |
| 42  | Mid → spin rate           | 0.0-1.0       |                                 |
| 43  | High → brightness         | 0.0-1.0       |                                 |
| 44  | High → point size         | 0.0-1.0       |                                 |
| 45  | High → velocity           | 0.0-1.0       |                                 |
| 46  | Beat → burst trigger      | 0.0-1.0       | Threshold for beat-triggered burst |
| 47  | Beat → color flash        | 0.0-1.0       |                                 |
| 48  | Smoothing amount          | 0.01-1.0      | Global lag time for all audio   |
| 49  | Frequency crossover low   | 20-500 Hz     | Bass/mid boundary               |
| 50  | Frequency crossover high  | 500-8000 Hz   | Mid/treble boundary             |

## Bank 3: Post-Processing & Render

| CC  | Function                  | Default Range | Notes                           |
|-----|---------------------------|---------------|---------------------------------|
| 36  | Feedback amount           | 0.0-0.99      | 0=none, 0.99=heavy trails       |
| 37  | Feedback zoom             | 0.99-1.01     | <1 shrink, >1 grow              |
| 38  | Feedback rotation         | -0.05-0.05    | Radians per frame               |
| 39  | Feedback hue shift        | 0.0-1.0       |                                 |
| 40  | Bloom threshold           | 0.0-1.0       |                                 |
| 41  | Bloom intensity           | 0.0-3.0       |                                 |
| 42  | Bloom radius              | 1-50 px       |                                 |
| 43  | Color grade: contrast     | 0.5-2.0       |                                 |
| 44  | Color grade: gamma        | 0.5-2.0       |                                 |
| 45  | Color grade: saturation   | 0.0-2.0       |                                 |
| 46  | Background brightness     | 0.0-0.2       | 0=black                         |
| 47  | Render blend mode         | 0-4 (preset)  | add/alpha/multiply/screen/over  |
| 48  | Camera distance           | 0.5-20.0      |                                 |
| 49  | Camera orbit speed        | 0.0-2.0       |                                 |
| 50  | Master opacity            | 0.0-1.0       |                                 |

## Implementation Notes

- All CC values arrive as 0-127 integers. Remap to target range via `mathCHOP` (range map mode).
- Bank select (CC 35) should trigger a `switchCHOP` or Python callback that reassigns which `selectCHOP` feeds which parameters.
- For bipolar ranges (e.g., -10 to 10), remap 0-127 → -range to +range with 64 as center.
- Log scale remapping for emission rate: `pow(value/127.0, 3.0) * max_rate`
- CCs 51-99 are reserved for future assignment or user-custom mappings.
