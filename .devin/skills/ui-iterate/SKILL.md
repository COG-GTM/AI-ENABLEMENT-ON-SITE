---
name: ui-iterate
description: Iterate a local interface from a mockup and keep accessible before-and-after evidence.
argument-hint: "[mockup or local component]"
allowed-tools:
  - read
  - grep
  - glob
permissions:
  ask:
    - exec
    - Write(**)
triggers:
  - user
  - model
---

Run a local UI/UX iteration on `$ARGUMENTS`. Keep the change behavior-neutral unless the developer
explicitly approves a behavior change.

## Desktop loop

1. Edit the local static mockup or component and start the app's local development server.
2. Ask Devin Desktop to preview the local app. The [Desktop Previews guide](https://docs.devin.ai/desktop/previews)
   documents local previews, element selection, and sending captured errors to the agent.
3. Inspect the target flow; send selected elements and console errors back into the conversation.
   Capture a before/after screenshot pair using the capture controls available in your Desktop build;
   screenshot capture and preview availability in an offline or FedRAMP environment are confirm on
   your build.
4. Run the accessibility check (axe) and the existing behavior tests. Fix critical accessibility
   failures and retest the same flow.
5. Save the screenshots and the updated self-contained HTML or source files in the repository.
   Share a downloaded HTML file or screenshot through an approved collaboration channel; do not
   publish or share a live URL.

## CLI equivalent

Use the app's normal local server command, then run the repository's Playwright spec or screenshot
script against `http://127.0.0.1:<port>`. Save screenshots and console output to the fixture's evidence
folder, run the axe assertion, and keep a before/after pair. Stop the local server when finished.

Report what was actually tested, the screenshot paths, and any preview/browser feature that could not
be confirmed. A screenshot is evidence of appearance, not proof of functional parity.
