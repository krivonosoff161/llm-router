# LLM Router component roadmap

This page is the source-owned roadmap for `llm-router`. The machine-readable component truth
is [`component.yaml`](../component.yaml). The public ecosystem order and cross-repository
phases belong to the
[Agentic Security Harness ecosystem roadmap](https://github.com/krivonosoff161/agentic-security-harness/blob/main/docs/ecosystem-roadmap.md).

## Current state

- Kind: `support_adapter`.
- Integration: `standalone`; Harness does not discover or invoke this package as an extension.
- Package: `llm-router` v0.1.0, installed from a source checkout with `pip install -e .`.
- Python: `>=3.9`.
- Platforms: Linux and Windows are supported; the current CI test matrix records Linux only.
- Authority: `none`.

The package owns bounded provider routing, retries, and usage/cost arithmetic. It is not a
security control, policy gateway, secret broker, provider-attestation service, or invoice
oracle.

## Component-owned documents

- [`README.md`](../README.md): public front door, provider shapes, and configuration.
- [`project-map.md`](project-map.md): implementation and maintainer map.
- [`operating-model.md`](operating-model.md): role budgets, escalation, and residual risk.
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

1. Add Windows CI before describing Windows as a tested platform.
2. Define a provider/model adapter contract in the Harness Extension SDK without moving
   credentials or provider calls into Harness Core.
3. Add an explicit package entry point and offline adapter conformance fixtures.
4. Pin supported Harness API and package compatibility ranges.
5. Promote integration beyond `standalone` only after cross-repository suite verification.

