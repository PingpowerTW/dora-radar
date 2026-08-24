<!-- SEED: re-run /impeccable document once there's code to capture the actual tokens and components. -->

---
name: Dora GitHub Trending Dashboard
description: Automated GitHub trending project monitoring dashboard
colors:
  bg-primary: "#0d1117"
  bg-secondary: "#161b22"
  bg-tertiary: "#21262d"
  border-color: "#30363d"
  text-primary: "#e6edf3"
  text-secondary: "#8b949e"
  accent-blue: "#58a6ff"
  accent-green: "#3fb950"
  accent-purple: "#bc8cff"
  accent-orange: "#d29922"
  accent-red: "#f85149"
typography:
  body:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, sans-serif"
    fontSize: "14px"
    lineHeight: "1.6"
  mono:
    fontFamily: "'JetBrains Mono', monospace"
rounded:
  sm: "4px"
  md: "8px"
  lg: "12px"
  xl: "16px"
spacing:
  sm: "8px"
  md: "16px"
  lg: "24px"
  xl: "32px"
---

# Design System: Dora GitHub Trending Dashboard

## 1. Overview

**Creative North Star: "The Analyst's Cockpit"**

Dora GitHub Trending Dashboard is a data-intensive monitoring tool designed for extended viewing sessions. The interface is a command center — every pixel serves the data. The dark theme is not an afterthought; it's the native state, matching GitHub's own aesthetic while reducing eye strain during prolonged analysis.

This system explicitly rejects generic SaaS landing page clichés, hero metric templates, and decorative glassmorphism. The dashboard is built for one purpose: clarity of insight. Charts, tables, and trend data take precedence over everything else.

**Key Characteristics:**
- Dark mode native with GitHub-inspired color palette
- Data-dense layouts optimized for quick scanning
- Clear visual hierarchy: Daily → Weekly → Monthly trends
- Subtle gradients used only for visual separation, never decoration

## 2. Colors

### Background
- **GitHub Dark** (#0d1117): Primary background. The foundation of the entire interface.
- **Surface** (#161b22): Card and panel backgrounds. Slightly lighter to create depth through tone.
- **Elevated** (#21262d): Interactive elements, hover states, active tabs.

### Text
- **Primary** (#e6edf3): Headings, key data points, active content.
- **Secondary** (#8b949e): Labels, descriptions, muted content.

### Accent
- **Blue** (#58a6ff): Primary interactive elements, active states, links.
- **Green** (#3fb950): Positive signals, growth indicators, success states.
- **Purple** (#bc8cff): Special categories, premium content indicators.

### Status
- **Orange** (#d29922): Warning states, medium priority alerts.
- **Red** (#f85149): Critical alerts, high priority, negative signals.

### Gradients
- Subtle gradients used only for section dividers and visual interest in empty states. Never for data representation.

### Named Rules
**The Data-First Rule.** Colors exist to differentiate data, not to decorate. Every color on screen must have a functional purpose.

## 3. Typography

**Body Font:** System font stack (-apple-system, BlinkMacSystemFont, Segoe UI, Roboto)
**Monospace Font:** JetBrains Mono (for code snippets, star counts, technical data)

**Character:** Clean, readable system fonts prioritize information density over personality. Monospace is reserved exclusively for technical data where character width matters.

### Hierarchy
- **Heading** (600, 1.5rem): Section titles — "今日熱門", "本週趨勢"
- **Subheading** (500, 1.125rem): Card titles, chart labels
- **Body** (400, 0.875rem): Descriptions, metadata, secondary text
- **Label** (500, 0.75rem, uppercase): Tab labels, filter labels
- **Mono** (400, 0.875rem): Star counts, technical metrics, timestamps

## 4. Elevation

This system uses **tonal layering** exclusively. No shadows, no glassmorphism. Depth is conveyed through background color variations:
- Base: #0d1117 (darkest)
- Surface: #161b22 (one level up)
- Elevated: #21262d (interactive state)

## 5. Components

### Cards
- **Shape:** Medium radius (8px)
- **Background:** Surface color (#161b22)
- **Border:** 1px solid border-color (#30363d)
- **Padding:** 16px internal
- **States:** Default, hover (elevated background)

### Tabs
- **Shape:** Full width, bottom border indicator
- **Active:** Blue accent bottom border
- **Inactive:** Text-secondary color
- **Typography:** Label weight, uppercase

### Tables
- **Header:** Tertiary background, bold text
- **Rows:** Alternating subtle background variation
- **Borders:** Bottom border only, 1px
- **Padding:** 12px vertical, 16px horizontal

### Status Badges
- **Shape:** Small radius (4px)
- **Colors:** Green (positive), Orange (warning), Red (critical)
- **Size:** Compact, inline with text

### Buttons
- **Primary:** Blue background, white text
- **Secondary:** Transparent with blue border
- **Danger:** Red background, white text
- **Radius:** Medium (8px)
- **Padding:** 10px 20px

## 6. Do's and Don'ts

### Do:
- **Do** maintain the dark theme as the default and only mode. This is a data tool, not a marketing page.
- **Do** use the GitHub-inspired color palette consistently. It's familiar to developers and reduces cognitive load.
- **Do** prioritize information density. Users scan dozens of projects; compact layouts with clear hierarchy are essential.
- **Do** use tonal layering for depth — never shadows or glassmorphism.
- **Do** reserve accent colors for functional purposes: status indicators, interactive elements, data differentiation.

### Don't:
- **Don't** use light mode as a default or toggle. The dashboard is designed for dark environments.
- **Don't** use glassmorphism, blur effects, or frosted glass. They reduce readability and add no information.
- **Don't** use decorative gradients on data elements. Gradients are only for visual separators.
- **Don't** use side-stripe borders on cards or table rows.
- **Don't** use numbered section markers (01 / 02 / 03) as default scaffolding.
- **Don't** use tiny uppercase tracked eyebrows above every section.
- **Don't** use inconsistent component vocabulary — cards, tables, and buttons must look the same everywhere.
- **Don't** use heavy color or full-saturation accents on inactive states.
- **Don't** use display fonts in UI labels or data tables.
