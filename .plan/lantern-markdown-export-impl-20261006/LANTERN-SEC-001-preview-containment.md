# LANTERN-SEC-001 — Preview containment hardening

Status: OPEN
Priority: Security follow-up
Created: 2026-10-07
Source gate: M-A12 in specs/001-terminal-ime-markdown-export/spec.md

## Problem

The Markdown preview implementation uses a nonce-only CSP and escaped/sanitized Markdown output, but the broader Lantern preview surface still has residual same-origin containment risk:

1. the side-pane preview iframe is not sandboxed;
2. preview content is also reachable by same-tab navigation and window.open, so iframe sandboxing alone is not sufficient;
3. Lantern can serve uploaded .html and .svg content from the same origin.

If script execution is ever obtained through a future parser/browser/content-type defect, same-origin parent/opener capabilities could weaken the intended preview isolation.

## Required follow-up scope

### A. Preview iframe sandboxing
- define the minimum sandbox token set for the side-pane preview;
- preserve Markdown/Mermaid/PNG/PDF usability;
- verify Back/open-new-tab behavior;
- verify the sandbox does not silently re-enable same-origin script capability.

### B. Same-origin uploaded HTML/SVG serving
- inventory all routes that serve user-controlled .html/.svg;
- decide whether they should be forced to download, served from a distinct origin, assigned a restrictive content type/CSP, or otherwise isolated;
- cover same-tab and window.open paths, not only the side-pane iframe;
- add regression tests for script execution, opener access, navigation, and content-type handling.

## Acceptance

- threat model and chosen containment boundary documented;
- security owner reviews the design;
- tests prove untrusted uploaded HTML/SVG cannot gain unintended same-origin execution capability;
- side-pane sandbox behavior is covered;
- same-tab and new-window paths are covered;
- no regression to ordinary Markdown/Mermaid/PNG/PDF preview behavior.

## Non-goal

This follow-up does not block implementation correctness of the current Markdown/Mermaid renderer itself; it is the explicit residual-risk closure required by M-A12 before release.

## Tracking

Ticket ID: LANTERN-SEC-001
Owner: TBD — security owner
Release relationship: current Markdown lane remains gated on security-owner residual-risk sign-off; this ticket satisfies the required follow-up-ticket artifact, not the sign-off itself.
