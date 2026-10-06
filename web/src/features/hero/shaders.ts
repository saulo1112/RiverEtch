// GLSL snippets shared by the hero's custom materials. All of them work in linear HDR color,
// before the tone mapping and color space chunks.

/**
 * `heroLuminance(rgb)` (Rec. 709) and `heroShoulder(rgb, knee, maxLuminance)`: a soft luminance
 * clamp that keeps surfaces below the bloom threshold without shifting their hue.
 */
export const SHOULDER_GLSL = /* glsl */ `
float heroLuminance(vec3 rgb) {
  return dot(rgb, vec3(0.2126, 0.7152, 0.0722));
}

vec3 heroShoulder(vec3 rgb, float knee, float maxLuminance) {
  float luminanceIn = heroLuminance(rgb);
  if (luminanceIn <= knee) {
    return rgb;
  }
  float range = maxLuminance - knee;
  float luminanceOut = knee + range * (1.0 - exp(-(luminanceIn - knee) / range));
  return rgb * (luminanceOut / luminanceIn);
}
`;

/**
 * `heroDither(rgb, fragCoord)`: adds triangular noise of about one 8-bit sRGB step, scaled for
 * linear color (the sRGB slope is approximated by 2.2 * linear^0.545), against gradient banding.
 */
export const DITHER_GLSL = /* glsl */ `
float heroHash(vec2 p) {
  vec3 p3 = fract(vec3(p.xyx) * 0.1031);
  p3 += dot(p3, p3.yzx + 33.33);
  return fract((p3.x + p3.y) * p3.z);
}

vec3 heroDither(vec3 rgb, vec2 fragCoord) {
  float noise = heroHash(fragCoord) + heroHash(fragCoord + 17.17) - 1.0;
  vec3 srgbStep = 2.2 * pow(max(rgb, vec3(1.0e-4)), vec3(0.545)) / 255.0;
  return max(rgb + noise * srgbStep, 0.0);
}
`;
