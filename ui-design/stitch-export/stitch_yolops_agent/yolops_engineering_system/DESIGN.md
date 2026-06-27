---
name: YOLOps Engineering System
colors:
  surface: '#fff8f5'
  surface-dim: '#e0d8d5'
  surface-bright: '#fff8f5'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#faf2ee'
  surface-container: '#f4ece8'
  surface-container-high: '#eee7e3'
  surface-container-highest: '#e9e1dd'
  on-surface: '#1e1b19'
  on-surface-variant: '#584237'
  inverse-surface: '#33302d'
  inverse-on-surface: '#f7efeb'
  outline: '#8c7164'
  outline-variant: '#e0c0b1'
  surface-tint: '#9d4300'
  primary: '#9d4300'
  on-primary: '#ffffff'
  primary-container: '#f97316'
  on-primary-container: '#582200'
  inverse-primary: '#ffb690'
  secondary: '#665f3d'
  on-secondary: '#ffffff'
  secondary-container: '#eae0b5'
  on-secondary-container: '#6a6341'
  tertiary: '#486554'
  on-tertiary: '#ffffff'
  tertiary-container: '#83a18f'
  on-tertiary-container: '#1c372a'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#ffdbca'
  primary-fixed-dim: '#ffb690'
  on-primary-fixed: '#341100'
  on-primary-fixed-variant: '#783200'
  secondary-fixed: '#ede3b8'
  secondary-fixed-dim: '#d1c79d'
  on-secondary-fixed: '#201c02'
  on-secondary-fixed-variant: '#4d4727'
  tertiary-fixed: '#caead6'
  tertiary-fixed-dim: '#afceba'
  on-tertiary-fixed: '#042014'
  on-tertiary-fixed-variant: '#314d3e'
  background: '#fff8f5'
  on-background: '#1e1b19'
  surface-variant: '#e9e1dd'
typography:
  display-lg:
    fontFamily: Inter
    fontSize: 32px
    fontWeight: '600'
    lineHeight: 40px
    letterSpacing: -0.02em
  headline-md:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.01em
  title-sm:
    fontFamily: Inter
    fontSize: 18px
    fontWeight: '500'
    lineHeight: 28px
  body-base:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 22px
  body-sm:
    fontFamily: Inter
    fontSize: 13px
    fontWeight: '400'
    lineHeight: 20px
  label-caps:
    fontFamily: Geist
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
    letterSpacing: 0.05em
  mono-data:
    fontFamily: Geist
    fontSize: 13px
    fontWeight: '400'
    lineHeight: 20px
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  unit: 4px
  container-max: 1440px
  gutter: 24px
  margin-page: 32px
  stack-sm: 8px
  stack-md: 16px
  stack-lg: 24px
---

## Brand & Style

The design system is engineered for industrial-grade object detection workflows. It balances the high-density information requirements of an MLOps platform with a warm, professional aesthetic that reduces cognitive fatigue.

The style is **Corporate / Modern**, drawing inspiration from high-productivity tools like Linear and Vercel. It prioritizes clarity, structural integrity, and functional elegance. By using a warm neutral base instead of cold blues or stark whites, the system feels approachable yet rigorous. Every element is aligned to a strict grid to evoke a sense of precision—essential for data labeling and model training environments.

## Colors

The palette is anchored by a high-energy **Primary Orange (#F97316)**, used sparingly for action items and progress indicators. The foundation is built on **Stone neutrals**, moving from a soft background (#FAFAF9) to deep grey text (#1C1917) to maintain high contrast without the harshness of pure black.

- **Primary:** Actionable items, focus states, and primary buttons.
- **Accents:** Light Gold (Warning/Pending), Soft Green (Success/Healthy), and Low-saturation Blue (Info/Processing) are used for status chips and data visualization.
- **Surface:** Pure White (#FFFFFF) is reserved for interactive cards and modals to create a distinct layer above the grey background.
- **Borders:** A consistent Warm Grey (#E7E5E4) defines the structure without creating visual noise.

## Typography

This design system utilizes **Inter** as the primary typeface for its exceptional legibility in data-heavy interfaces. For technical strings, coordinates, and developer-facing metrics, **Geist** is employed to provide a precise, monospaced feel.

For Chinese rendering, the system falls back to **PingFang SC**, ensuring weight consistency with Inter. 

- **Hierarchy:** Headlines use tighter letter spacing and semi-bold weights to appear "engineered." 
- **Body Text:** Set at 14px for standard density, with a 13px variant for sidebars and secondary meta-data.
- **Labels:** Small caps or Geist Mono are used for table headers and technical parameters (e.g., Confidence Scores, IoU Thresholds).

## Layout & Spacing

The layout follows a **Fluid Grid** model with fixed constraints for maximum readability. The dashboard uses a sidebar-and-stage architecture.

- **Grid:** A 12-column grid is used for the main content area.
- **Rhythm:** An 8px linear scale (using 4px as a half-step base) governs all padding and margins. 
- **Adaptation:** On Desktop, the main stage has a 32px margin. On Tablet, it reduces to 24px. On Mobile, the layout collapses to a single column with 16px margins, and secondary actions are moved to a bottom sheet or overflow menu.
- **Density:** High-density views (like dataset annotation grids) use 8px spacing, while analytical dashboards use 24px to provide breathing room.

## Elevation & Depth

This design system uses **Tonal Layers** combined with **Ambient Shadows** to create a sophisticated, flat-but-layered feel. 

- **Level 0 (Background):** #FAFAF9. The canvas.
- **Level 1 (Cards/Surfaces):** Pure White with a 1px border (#E7E5E4). No shadow.
- **Level 2 (Hover/Active):** Pure White with a soft, diffused shadow: `0 4px 12px rgba(28, 25, 23, 0.05)`.
- **Level 3 (Modals/Popovers):** Pure White with a more pronounced shadow: `0 12px 32px rgba(28, 25, 23, 0.1)`.

This approach avoids heavy skeuomorphism while ensuring that interactive elements are clearly prioritized.

## Shapes

The shape language is "Soft-Industrial." By using a **Rounded (8px/0.5rem)** base, the UI feels modern and accessible, avoiding the aggressive sharpness of legacy industrial software.

- **Buttons & Inputs:** 8px (standard).
- **Cards & Modals:** 12px (rounded-lg).
- **Status Chips:** Full pill-shaped (rounded-full) to distinguish them from interactive buttons.
- **Selection Frames:** Inside the image annotator, detection boxes use a 2px radius or sharp corners to denote mathematical precision.

## Components

### Buttons
- **Primary:** Solid Orange (#F97316) with white text.
- **Secondary:** White background, 1px border (#E7E5E4), deep grey text.
- **Ghost:** No border or background unless hovered. Used for utility actions in the toolbar.

### Inputs
- **Field:** White background, 8px radius, 1px border. Focus state: 1px Orange border with a 2px soft orange glow (10% opacity).
- **Labels:** Placed above the field in `body-sm` weight 500.

### Chips (Status)
- Small, uppercase, using the accent palette. 
- *Example:* "训练中" (Training) uses Blue accent; "已完成" (Completed) uses Green accent.

### Cards
- Always use white background and 12px roundedness.
- Headers within cards should have a subtle bottom border (#E7E5E4) to separate titles from content.

### Data Visualization
- Line charts for "mAP" or "Loss" should use the Primary Orange for the main metric and Deep Grey for comparison baselines.
- Grid lines should be light warm grey, matching the system borders.