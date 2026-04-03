# GLSL Post-Processing Patterns

Standard post-processing chain for POPs renders. All shaders are for `glslTOP` operators.

## Chain Order

```
POPs render output (renderTOP or similar)
  → feedbackTOP (trails/persistence)
  → glslTOP: bloom extraction
  → glslTOP: bloom blur + composite
  → glslTOP: color grade
  → glslTOP: chromatic aberration (optional)
  → outTOP
```

Each stage is a separate `glslTOP` for independent MIDI CC control. Do not collapse into a single mega-shader — modularity enables per-effect bypass and CC mapping.

## Feedback (Trails)

Not a GLSL shader — use native `feedbackTOP`:

```
feedbackTOP (name: feedback_top)
  - input: render output
  - target: the TOP feeding back into itself
  - parameters controlled by Bank 3 CCs:
    - feedback amount (CC 36): levelTOP opacity before feedback input
    - zoom (CC 37): transformTOP scale on feedback loop
    - rotation (CC 38): transformTOP rotate on feedback loop
    - hue shift (CC 39): hsvadjustTOP on feedback loop
```

Feedback implementation requires a loop: `renderTOP → compositeTOP(over feedback) → [effects] → outTOP`, with `feedbackTOP` tapping the composite output back to the composite's second input. Use `td_exec_python` to wire this since it requires careful connection ordering.

## Bloom

### Pass 1: Threshold Extraction

```glsl
// glslTOP: bloom_thresh_top
// Inputs: sTD2DInputs[0] = render output
uniform float uThreshold;  // CC 40, Bank 3

out vec4 fragColor;
void main() {
    vec4 c = texture(sTD2DInputs[0], vUV.st);
    float lum = dot(c.rgb, vec3(0.2126, 0.7152, 0.0722));
    fragColor = (lum > uThreshold) ? c : vec4(0.0);
}
```

### Pass 2: Blur + Composite

Use native `blurTOP` (name: `bloom_blur_top`) on threshold output, then `compositeTOP` (add mode) to merge bloom back with original. The blur radius maps to CC 42.

Alternative: multi-pass Gaussian in GLSL if finer control needed.

## Color Grade

```glsl
// glslTOP: colorgrade_top
// Inputs: sTD2DInputs[0] = composited image
uniform float uContrast;    // CC 43, Bank 3
uniform float uGamma;       // CC 44, Bank 3
uniform float uSaturation;  // CC 45, Bank 3

out vec4 fragColor;
void main() {
    vec4 c = texture(sTD2DInputs[0], vUV.st);

    // Contrast around midpoint
    c.rgb = (c.rgb - 0.5) * uContrast + 0.5;

    // Gamma
    c.rgb = pow(max(c.rgb, 0.0), vec3(1.0 / uGamma));

    // Saturation
    float lum = dot(c.rgb, vec3(0.2126, 0.7152, 0.0722));
    c.rgb = mix(vec3(lum), c.rgb, uSaturation);

    fragColor = vec4(clamp(c.rgb, 0.0, 1.0), c.a);
}
```

## Chromatic Aberration

```glsl
// glslTOP: chroma_ab_top
uniform float uAmount;  // 0.0-0.02, map to a CC if desired

out vec4 fragColor;
void main() {
    vec2 uv = vUV.st;
    vec2 dir = uv - 0.5;
    float d = length(dir);

    float r = texture(sTD2DInputs[0], uv + dir * uAmount * d).r;
    float g = texture(sTD2DInputs[0], uv).g;
    float b = texture(sTD2DInputs[0], uv - dir * uAmount * d).b;
    float a = texture(sTD2DInputs[0], uv).a;

    fragColor = vec4(r, g, b, a);
}
```

## Binding GLSL Uniforms to CHOPs

GLSL TOPs in TD read uniforms from input CHOPs. To bind a MIDI CC or audio signal to a GLSL uniform:

1. Create the CHOP chain that produces the value (see CHOP_CHAINS.md)
2. Connect that CHOP to the glslTOP's first CHOP input (not the TOP input)
3. In the GLSL shader, declare the uniform matching the CHOP channel name

Or use `td_set_expression` on the glslTOP's custom uniform parameters if the glslTOP exposes them as page parameters.

## Audio-Reactive Shader Modulation

For shaders that respond directly to audio (beyond parameter mapping), pass the full spectrum as a texture:

```
audiospectrumCHOP → choptoTOP (name: spectrum_tex_top)
  - creates a 1D texture where X = frequency, pixel value = amplitude

In GLSL:
  uniform sampler2D sSpectrum;  // or use sTD2DInputs[N]
  float bass = texture(sSpectrum, vec2(0.05, 0.5)).r;   // low freq
  float mid  = texture(sSpectrum, vec2(0.25, 0.5)).r;   // mid freq
  float high = texture(sSpectrum, vec2(0.7, 0.5)).r;    // high freq
```

This gives per-pixel frequency access inside the shader for complex audio-reactive effects like waveform displacement, spectrum-driven color palettes, or frequency-dependent distortion.

## Creation Pattern via MCP

```python
# Create a glslTOP with inline shader code
glsl = op('/project1').create(glslTOP, 'colorgrade_top')
# The GLSL code goes into the glslTOP's associated DAT
# TD auto-creates a DAT named 'colorgrade_top_pixel' (or similar)
# Write shader code to it:
shader_dat = op('/project1/colorgrade_top_pixel')  # verify name via td_query_op
shader_dat.text = '''...glsl code...'''
```

IMPORTANT: The exact mechanism for writing GLSL code to a glslTOP's shader DAT varies by TD version. After creating the glslTOP, use `td_query_op` to inspect its children/references and find the correct DAT to write to. If the DAT doesn't auto-create, create a `textDAT` and point the glslTOP's `dat` parameter to it.
