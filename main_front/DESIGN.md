---
name: AI Construction Takeoff & Quantity Surveying
colors:
  surface: '#0d1322'
  surface-dim: '#0d1322'
  surface-bright: '#33394a'
  surface-container-lowest: '#080e1d'
  surface-container-low: '#151b2b'
  surface-container: '#191f2f'
  surface-container-high: '#242a3a'
  surface-container-highest: '#2f3445'
  on-surface: '#dde2f8'
  on-surface-variant: '#bcc9cd'
  inverse-surface: '#dde2f8'
  inverse-on-surface: '#2a3040'
  outline: '#869397'
  outline-variant: '#3d494c'
  surface-tint: '#4cd7f6'
  primary: '#4cd7f6'
  on-primary: '#003640'
  primary-container: '#06b6d4'
  on-primary-container: '#00424f'
  inverse-primary: '#00687a'
  secondary: '#b4c5ff'
  on-secondary: '#002a78'
  secondary-container: '#0053db'
  on-secondary-container: '#cdd7ff'
  tertiary: '#4fdbc8'
  on-tertiary: '#003731'
  tertiary-container: '#1abaa8'
  on-tertiary-container: '#00443c'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#acedff'
  primary-fixed-dim: '#4cd7f6'
  on-primary-fixed: '#001f26'
  on-primary-fixed-variant: '#004e5c'
  secondary-fixed: '#dbe1ff'
  secondary-fixed-dim: '#b4c5ff'
  on-secondary-fixed: '#00174b'
  on-secondary-fixed-variant: '#003ea8'
  tertiary-fixed: '#71f8e4'
  tertiary-fixed-dim: '#4fdbc8'
  on-tertiary-fixed: '#00201c'
  on-tertiary-fixed-variant: '#005048'
  background: '#0d1322'
  on-background: '#dde2f8'
  surface-variant: '#2f3445'
typography:
  headline-xl:
    fontFamily: JetBrains Mono
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
  headline-lg:
    fontFamily: JetBrains Mono
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 28px
  headline-md:
    fontFamily: JetBrains Mono
    fontSize: 16px
    fontWeight: '600'
    lineHeight: 24px
  headline-sm:
    fontFamily: JetBrains Mono
    fontSize: 14px
    fontWeight: '500'
    lineHeight: 20px
  body-lg:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  body-md:
    fontFamily: Inter
    fontSize: 13px
    fontWeight: '400'
    lineHeight: 18px
  body-sm:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
  label-lg:
    fontFamily: JetBrains Mono
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
  label-md:
    fontFamily: JetBrains Mono
    fontSize: 11px
    fontWeight: '500'
    lineHeight: 14px
  label-sm:
    fontFamily: JetBrains Mono
    fontSize: 10px
    fontWeight: '500'
    lineHeight: 12px
spacing:
  gutter: 0.5rem
  margin: 1rem
  space-xs: 0.125rem
  space-sm: 0.25rem
  space-md: 0.5rem
  space-lg: 1rem
  space-xl: 1.5rem
---

## Brand & Style

This design system establishes a high-performance, precision-engineered environment tailored for enterprise construction takeoff and quantity surveying professionals. The persona is technical, highly authoritative, and uncompromising on data clarity. The design style combines a refined **Minimalism** with dense, CAD-like spatial organization, utilizing low-contrast outlines and razor-sharp structural alignments to minimize visual fatigue during prolonged estimating sessions.

The interface evokes absolute confidence, dependability, and computational exactness. By treating data as a first-class citizen, the UI reduces cognitive friction, allowing quantity surveyors and estimators to process complex blueprints, manage material layers, and execute rapid financial calculations without distraction.

## Colors

The palette is anchored by deep, absorbing architectural dark tones paired with luminous engineering accents. 

- **Surfaces:** Deep Navy (`#0B1120`) serves as the core canvas, layered with Dark Workspace (`#080D18`), Panel Background (`#111A2C`), and Secondary Panel (`#172238`) to create immediate spatial hierarchy.
- **Accents:** Cyan (`#06B6D4`) drives primary interactive states and active measurement tools. Teal (`#14B8A6`) highlights secondary metrics and completion states. Blue (`#2563EB`) anchors structural links and system actions. 
- **Semantics:** Orange (`#F59E0B`) indicates warnings or review flags, Green (`#10B981`) signifies verified quantities and positive variances, and Red (`#EF4444`) denotes clashes, errors, or critical out-of-spec items.
- **Text:** Primary text uses `#F1F5F9` for maximum legibility against dark surfaces, secondary text relies on `#94A3B8`, and muted elements use `#64748B`.

## Typography

Typography is treated as a precision instrument. Monospaced typefaces (`JetBrains Mono`) are used for all numeric data, dimensions, coordinates, and codes to ensure vertical alignment across dense data tables. Sans-serif typefaces (`Inter`) handle general UI copy, descriptions, and descriptive metadata.

Maintain strict adherence to the type scale. Avoid scaling headings beyond 24px to preserve high information density across complex desktop viewports.

## Layout & Spacing

The application utilizes a fixed, high-density desktop grid system optimized for multi-monitor takeoff workstations. 

- **Grid:** A rigid multi-column structure with 8px gutters and 16px outer margins, ensuring alignment between CAD viewport coordinates and tabular data grids.
- **Adapting:** The layout is strictly optimized for desktop environments (1440px and above). Panels are dockable, resizable, and collapsible to maximize canvas real estate for blueprint rendering and AI vector tracing.

## Elevation & Depth

Depth is conveyed through **low-contrast outlines** and subtle surface-container tiering rather than heavy drop shadows. 

- **Borders:** Crisp, 1-px structural borders (`#172238` and `#2563EB` at low opacities) separate panels, toolbar groups, and table cells.
- **Layers:** Visual hierarchy relies strictly on background color stepping (moving from Deep Navy `#0B1120` to Secondary Panel `#172238`) to indicate active docking zones, floating measurement toolbars, and modal inspector overlays.

## Shapes

The design system enforces strict **Sharp (0px)** roundedness across all UI elements. Buttons, input fields, data tables, panels, and toolbars feature square corners to mirror the precision of architectural blueprints, CAD software, and technical drawing instruments. Avoid border radii entirely to maintain an uncompromising engineering aesthetic.

## Components

- **Buttons:** Compact, high-density action triggers with zero border radius. Primary buttons utilize Cyan (`#06B6D4`) with dark text, while secondary and ghost variants use crisp borders and muted hover states.
- **Data Tables:** The core of the system. Feature alternating row shading, sticky headers, fixed-width monospaced columns, vertical gridlines, and inline cell editing for rapid quantity adjustments.
- **Input Fields:** Flush text inputs with 1px borders, featuring integrated unit indicators (e.g., `m²`, `cu yd`, `USD`) pinned inside the container to maximize space.
- **Checkboxes & Radio Buttons:** Sharp 12px square and diamond geometry with high-contrast accent fills for multi-layer blueprint selection and material tagging.
- **Chips & Tags:** Compact status indicators for material categories, confidence scores, and verification states, using colored borders and solid dark fills.
- **Cards & Containers:** Flat structural containers with distinct header bars, collapsible sections, and embedded toolbar actions for property inspectors and layer managers.
- **CAD Viewport Toolbars:** Floating or docked toolbars housing snap-to-grid toggles, scale calibration tools, and AI polygon tracing controls.