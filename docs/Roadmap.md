# Delivery roadmap

## Current build

The local document workspace is implemented: ingestion and OCR, hybrid retrieval, local model integration, checked citations, a browser interface, run history, recovery, cancellation, deletion, and local traces. Verification results and outstanding release gates are recorded in [Results.md](Results.md).

The local release is complete only when its required checks pass, including the full browser journey and the frozen 30-question real-model evaluation. A passing smoke test or mocked model suite cannot replace those gates.

## Next steps

1. Resolve the remaining browser/runtime and evaluation failures without weakening assertions or timeouts.
2. Complete the full frozen evaluation and retain all attempts, model digests, source hashes, timings, and failed cases.
3. Review the answers against their passages and record the limits of this small synthetic corpus.
4. Rehearse backup/restore and review the local data-handling and dependency-license constraints before wider use.

## Later milestones

| Milestone | Work | Evidence needed |
|---|---|---|
| Cloud integration | AWS Bedrock, Azure Foundry, and Gemini Enterprise Agent Platform adapters | Current official contracts, approved accounts/data regions, live boundary tests, cost limits, and provider-specific quality reports. |
| Development tools | Compare GitHub Copilot Enterprise, Claude Code, Managed Agents, OpenAI Codex, and Cursor | Fixed tasks, isolated repository copies, correctness review, time/review effort, and permitted data handling. Resolve which product “Managed Agents” means. |
| Retrieval breadth | Embedding-service comparisons, reranking, taxonomies, and knowledge graphs | Held-out ablations against the existing hybrid baseline; provenance and freshness checks. |
| ML lifecycle | scikit-learn experiments, model tracking/versioning, drift, and retraining | Leakage-resistant splits, artifact lineage, drift tests, human promotion, and rollback. |
| GPU infrastructure | NVIDIA/CUDA serving, telemetry, scheduling, scaling, and bin-packing | Separate simulation and hardware results, quota checks, resource limits, and FIFO comparison. |
| Physical AI | ROS/ROS2 simulation, distributed edge behavior, and hybrid workload optimization | Disconnection/staleness tests, site isolation, independent stop, and placement comparisons. No physical actuation. |

These milestones require their own scope, owner, access, and budget decisions. They are not part of the first local release. The complete competency list remains in [Skills.md](Skills.md).
