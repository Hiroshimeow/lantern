# M-A12 security-owner sign-off request

Status: PENDING AUTHORIZED SECURITY-OWNER DECISION
Scope: Markdown/Mermaid release lane only
Related gate: M-A12
Follow-up ticket: LANTERN-SEC-001

## Authority requirement still missing

Existing repository/workspace governance establishes an operator/spec-owner authority for specification and acceptance-contract decisions, including the recorded M-A11 operator decision. It does not establish that the current operator/release authority is also the security owner, nor does it delegate M-A12 residual-risk acceptance to the operator/spec-owner role.

An authorized signer must therefore provide evidence that they are the security owner for this release, or that repository/project governance delegates security residual-risk acceptance for M-A12 to their role.

## Minimal explicit decision required

The authorized security owner may satisfy M-A12 with one explicit decision containing all of the following:

> Acting as the authorized security owner for the Lantern Markdown/Mermaid release, I reviewed the residual preview-containment risk documented by M-A12 and LANTERN-SEC-001. I accept temporary release of the Markdown/Mermaid lane with that residual risk. LANTERN-SEC-001 remains OPEN and required follow-up work must cover both preview iframe sandboxing and containment of same-origin uploaded HTML/SVG serving.

The decision must identify the signer and the governance basis for their security-owner authority (for example, named security-owner assignment or an explicit delegation granting that role authority to accept this residual risk).

## Non-effects

This request does not change technical acceptance, product code, security requirements, or the OPEN status/scope of LANTERN-SEC-001.
