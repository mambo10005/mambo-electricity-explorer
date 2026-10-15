# 0008 — Theme colors and a focus-only CSS override

- **Status:** Accepted
- **Date:** 2026-10-11
- **Streamlit:** 1.65.0 (measurements are tied to this version)

## Context

- Stage 8 measured white primary-button text at 3.30:1 with Streamlit's default primary
  (#FF4B4B).
- Stage 9 fixed button text through supported configuration:
  - `primaryColor = "#2563EB"` under `[theme.light]` and `[theme.dark]`, which keeps the
    user's System/Light/Dark choice;
  - white text at 5.17:1 (default) and 8.54:1 (hover/focus).
- Keyboard focus stayed weak: Streamlit draws its own ring as the primary color at 50%
  alpha, 2.14:1 (light) and 1.77:1 (dark) against the page.

Project target: a clearly visible keyboard focus indicator at **≥ 3:1 against the adjacent
colors**.

## Options

1. **Supported configuration only.** Streamlit 1.65 has no focus option. The ring is
   derived from `primaryColor`, and no single primary works:
   - In dark mode, the white button text needs the primary's luminance ≤ 0.18 (for 4.5:1).
   - A ring of that color at 50% alpha over #0E1117 stays below 3:1.

   Raising the primary would break button-text contrast. **Rejected: cannot reach the
   target.**
2. **JavaScript or DOM changes.** Out of scope; not allowed.
3. **A minimal, centralized, focus-only stylesheet.** **Chosen.**

## Decision

`src/mambo_explorer/focus.css`, injected once by `app.py` through
`focus_style.inject_focus_style()` (`st.html` with a `<style>` element only; no script).

- Applies only to `:focus-visible` (keyboard focus), inside `[data-testid="stApp"]`.
- Selectors use only stable hooks: element names, ARIA roles, input types, and
  `data-testid` / `data-baseweb` / `data-rac` attributes. No generated class names.
- Changes only `outline` and `outline-offset`. It never removes Streamlit's native outline
  or its ring; it adds a 3 px solid outline, 2 px outside the control.
- One color for both themes, **#3B82F6**, chosen to be at least 3:1 against every
  background a ring can sit on:
  - light page #FFFFFF: 3.68
  - light sidebar and inputs #F0F2F6: 3.28
  - dark page #0E1117: 5.14
  - dark sidebar and inputs #262730: 4.03
  - dark toolbar #131720: 4.88

  CSS cannot detect the user's in-app theme choice, so a per-theme color is not possible
  without JavaScript.
- Multiselect chip remove buttons sit on the chip, which is filled with the primary
  #2563EB. They get a 2 px **white** ring inset 2 px (5.17:1 against the chip).

## Version dependence and fallback

The hooks were read from the rendered DOM of Streamlit 1.65.0:
- radios and checkboxes: a visually hidden input inside a `label`;
- select boxes: a React Aria `role="group"` wrapper around `input[role="combobox"]`;
- multiselects: `stMultiSelectTagsContainer`;
- sliders: a hidden `input[type="range"]` inside the `data-rac` thumb.

If an upgrade changes a hook, that control falls back to Streamlit's own (weaker) focus
styling. Nothing breaks visually, and the layout is untouched.

Two guards catch this:
- `tests/test_theme_contrast.py` fails on any Streamlit version change, prompting a
  re-measure.
- `tests/test_focus_css.py` checks selector coverage and safety.

## Consequences

- Rendered measurements and the exact states covered are in `docs/accessibility.md`.
- This is a contrast and visibility measure, not a WCAG conformance claim. No
  screen-reader test has been run (BL-6).
- `.streamlit/config.toml` and `focus.css` are the only theme customizations. Any new CSS
  needs an ADR.
