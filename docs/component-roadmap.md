# LLM Router component roadmap

This page is the source-owned roadmap for `llm-router`. The machine-readable component truth
is [`component.yaml`](../component.yaml). The public ecosystem order and cross-repository
phases belong to the
[Agentic Security Harness ecosystem roadmap](https://github.com/krivonosoff161/agentic-security-harness/blob/main/docs/ecosystem-roadmap.md).

## Current state

- Kind: `support_adapter`.
- Integration: `contract_only`; the repository owns invocation receipt V1, while Harness
  still does not discover or invoke this package as an extension.
- Package: `llm-router` v0.1.0, installed from a source checkout with `pip install -e .`.
- Python: `>=3.9`.
- Platforms: Linux and Windows are supported; the task CI matrix exercises both on Python
  3.9, 3.11, 3.12, and 3.13.
- Authority: `none`.

The package owns bounded provider routing, retries, usage/cost arithmetic, and the closed
`router-invocation-receipt-v1.0` source contract. It is not a
security control, policy gateway, secret broker, provider-attestation service, or invoice
oracle.

## Component-owned documents

- [`README.md`](../README.md): public front door, provider shapes, and configuration.
- [`project-map.md`](project-map.md): implementation and maintainer map.
- [`operating-model.md`](operating-model.md): role budgets, escalation, and residual risk.
- [`invocation-receipt.md`](invocation-receipt.md): canonical sanitized invocation evidence.
- [`use-cases.md`](use-cases.md): supported workflows and non-goals.

## Historical portfolio snapshots

The following digest-bound files are preserved as historical evidence. They describe an
earlier private-product portfolio projection and no longer own current ecosystem status:

- `docs/security-portfolio-roadmap.md`;
- `docs/security-portfolio-roadmap-public.yaml`;
- `docs/security-portfolio-roadmap-contract.json`.

They grant no operational authority. Current cross-repository status comes from the Harness
ecosystem roadmap; this repository owns only its support-adapter facts.

## Ordered next gates

1. Review and pin invocation receipt V1 from the Harness Extension SDK without moving
   credentials or provider calls into Harness Core.
2. Add an explicit package entry point and offline adapter conformance fixtures.
3. Pin supported Harness API and package compatibility ranges.
4. Promote integration beyond `contract_only` only after cross-repository suite verification.
