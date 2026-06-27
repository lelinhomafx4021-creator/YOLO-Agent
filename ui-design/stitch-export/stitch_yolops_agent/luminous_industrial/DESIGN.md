---
name: Luminous Industrial
colors:
  surface: '#fbf9f9'
  surface-dim: '#dbdad9'
  surface-bright: '#fbf9f9'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f5f3f3'
  surface-container: '#efeded'
  surface-container-high: '#e9e8e7'
  surface-container-highest: '#e3e2e2'
  on-surface: '#1b1c1c'
  on-surface-variant: '#5b4137'
  inverse-surface: '#303031'
  inverse-on-surface: '#f2f0f0'
  outline: '#8f7065'
  outline-variant: '#e4beb1'
  surface-tint: '#a73a00'
  primary: '#a73a00'
  on-primary: '#ffffff'
  primary-container: '#ff5c00'
  on-primary-container: '#521800'
  inverse-primary: '#ffb59a'
  secondary: '#5f5e5e'
  on-secondary: '#ffffff'
  secondary-container: '#e2dfde'
  on-secondary-container: '#636262'
  tertiary: '#0061a6'
  on-tertiary: '#ffffff'
  tertiary-container: '#0096fd'
  on-tertiary-container: '#002d51'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#ffdbce'
  primary-fixed-dim: '#ffb59a'
  on-primary-fixed: '#370e00'
  on-primary-fixed-variant: '#802a00'
  secondary-fixed: '#e5e2e1'
  secondary-fixed-dim: '#c8c6c5'
  on-secondary-fixed: '#1c1b1b'
  on-secondary-fixed-variant: '#474746'
  tertiary-fixed: '#d2e4ff'
  tertiary-fixed-dim: '#a0c9ff'
  on-tertiary-fixed: '#001c37'
  on-tertiary-fixed-variant: '#00497f'
  background: '#fbf9f9'
  on-background: '#1b1c1c'
  surface-variant: '#e3e2e2'
typography:
  headline-lg:
    fontFamily: Geist
    fontSize: 32px
    fontWeight: '600'
    lineHeight: 40px
    letterSpacing: -0.02em
  headline-lg-mobile:
    fontFamily: Geist
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.02em
  headline-md:
    fontFamily: Geist
    fontSize: 20px
    fontWeight: '500'
    lineHeight: 28px
    letterSpacing: -0.01em
  body-md:
    fontFamily: Geist
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
    letterSpacing: '0'
  body-sm:
    fontFamily: Geist
    fontSize: 13px
    fontWeight: '400'
    lineHeight: 18px
    letterSpacing: '0'
  label-md:
    fontFamily: JetBrains Mono
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
    letterSpacing: 0.02em
  label-sm:
    fontFamily: JetBrains Mono
    fontSize: 10px
    fontWeight: '500'
    lineHeight: 14px
    letterSpacing: 0.05em
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  base: 4px
  xs: 4px
  sm: 8px
  md: 16px
  lg: 24px
  xl: 40px
  gutter: 16px
  margin-mobile: 16px
  margin-desktop: 32px
---

## Brand & Style

This design system is built for high-performance productivity and professional precision. The personality is disciplined, efficient, and transparent, prioritizing content clarity over decorative elements. 

The aesthetic draws heavily from **Minimalism** and **Modern Corporate** styles, specifically emulating a "Linear-like" purity. It utilizes an expansive use of white space, razor-sharp alignment, and a strict information hierarchy. The emotional response should be one of focused calm and absolute reliability, stripping away visual noise to empower the user's workflow. Warm accents are used surgically, reserved only for critical path actions and high-priority states to ensure they command immediate attention against a clinical, neutral backdrop.

## Colors

The palette is centered on a "Pure White" philosophy. The primary background and main surface areas are strictly `#FFFFFF`. Depth is communicated through a curated scale of neutral greys rather than shadows. 

The **Primary Color** (Warm Orange) is a high-visibility tool. It must never be used for large backgrounds or decorative fills. Its application is restricted to:
1. Primary Call-to-Action buttons.
2. Active state indicators for critical navigation.
3. High-priority status badges.

The **Secondary** and **Neutral** colors provide the structural framework, using deep blacks for high-contrast typography and mid-tone greys for metadata and supporting UI elements.

## Typography

This design system utilizes **Geist** for its systematic, developer-friendly proportions and neutral tone. It provides the necessary clarity for complex data environments. For technical metadata and status labels, **JetBrains Mono** is employed to introduce a precise, industrial feel.

Typography should maintain high contrast against the white background. Use `FontWeight: 600` for primary headers to establish hierarchy without needing color. `Letter-spacing` is tightened slightly on larger headings to maintain a compact, "engineered" appearance.

## Layout & Spacing

The layout follows a **Fluid Grid** model with fixed maximum widths for content containers to ensure readability. A strict 4px base unit drives all spacing decisions.

- **Desktop:** 12-column grid, 16px gutters, 32px side margins.
- **Tablet:** 8-column grid, 16px gutters, 24px side margins.
- **Mobile:** 4-column grid, 12px gutters, 16px side margins.

Structure is defined by alignment rather than containment. Use whitespace (the `xl` unit) to separate major sections. Vertical rhythm should be tight within components (using `xs` and `sm`) and generous between logical groups (using `lg` and `xl`).

## Elevation & Depth

This design system moves away from traditional shadows in favor of **Tonal Layers** and **Low-Contrast Outlines**. 

- **Level 0 (Base):** Pure `#FFFFFF`.
- **Level 1 (Sub-navigation/Sidebar):** `#F9F9F9` with a `1px` border of `#E5E5E5`.
- **Level 2 (Modals/Overlays):** `#FFFFFF` with a very subtle, highly diffused neutral shadow (Alpha 0.05) and a `#D4D4D4` border to define the edge against the white background.

Depth is primarily signaled by hair-line borders (`1px`) in neutral greys. Active elements or focused inputs use a `1px` solid border in the primary color or a darker neutral shade to indicate interaction without adding physical "weight."

## Shapes

The shape language is **Soft** but leaning towards geometric. A standard radius of `4px` (`0.25rem`) is applied to buttons, inputs, and small containers. This subtle rounding maintains a professional, industrial character while preventing the UI from feeling sharp or aggressive. Larger cards or modals may use `8px` (`0.5rem`) to slightly soften their presence, but "Pill" shapes are strictly forbidden except for specific status tags.

## Components

- **Buttons:** 
  - **Primary:** Solid `#FF5C00` background with white text. High-impact.
  - **Secondary:** White background with `#D4D4D4` border. Text in `#1A1A1A`. 
  - **Tertiary:** Ghost style, no border or background until hover (`#F4F4F4`).
- **Input Fields:** 1px border using `border_subtle`. On focus, the border transitions to `secondary_color_hex` or a subtle primary glow. Background is always `#FFFFFF`.
- **Chips & Tags:** Small, monospaced text. Neutral status tags use `surface_container` background. Primary/Actionable tags use a very light tint of the primary color with primary-colored text.
- **Lists:** Clean rows separated by `1px` horizontal lines (`border_subtle`). Hover states should use `surface_container_low`.
- **Cards:** No shadows. Defined by a `1px` border of `#E5E5E5`. Headers within cards should be separated by a subtle divider.
- **Status Indicators:** Small 8px dots. Use the primary color only for "Urgent" or "Active" states. Use neutral greys for "Inactive" or "Draft" states.