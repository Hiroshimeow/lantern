# M-A12 Security Owner Residual-Risk Sign-off

Date: 2026-10-07
Project: Lantern
Scope: Markdown/Mermaid release lane
Related gate: M-A12
Follow-up ticket: LANTERN-SEC-001

## Signer and authority basis

Signer: Project owner / operator / release authority for Lantern.

Authority basis: Lantern is the signer's personal application operated within the signer's own LAN. The signer is the project owner and final release authority for this application and therefore holds the authority to accept residual security risk for this release.

## Decision

Acting as the authorized security owner for the Lantern Markdown/Mermaid release, I reviewed the residual preview-containment risk documented by M-A12 and LANTERN-SEC-001.

I accept temporary release of the Markdown/Mermaid lane with that residual risk.

LANTERN-SEC-001 remains OPEN and required follow-up work must cover both:
1. preview iframe sandboxing; and
2. containment of same-origin uploaded HTML/SVG serving.

## Limits

This sign-off:
- does not waive or reduce the technical security controls already required by the reviewed spec;
- does not close LANTERN-SEC-001;
- applies only to the current Markdown/Mermaid release lane;
- does not authorize unrelated terminal/IME changes.

Status: APPROVED BY PROJECT OWNER / SECURITY-RISK AUTHORITY
