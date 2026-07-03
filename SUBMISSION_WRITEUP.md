# Visual Triage — Submission Write-Up

## Project Overview

**Visual Triage** is a multi-agent medical triage system built on Google ADK 2.0. It combines
graph-based workflow orchestration, real-time provider matchmaking via MCP tools, and
enterprise-grade security guardrails into a single conversational experience.

The system guides users from symptom description through severity classification, HIPAA consent
collection, and finally delivers ranked hospital/clinic recommendations with live wait times
and patient reviews.

---

## Key Design Decisions

### 1. Graph-Based Workflow Over Sequential Agents

Rather than using a simple `SequentialAgent`, the project uses ADK 2.0's `Workflow` class with
**conditional routing**. This enables:

- **Branching on security status**: Clean inputs proceed to symptom analysis; injected inputs
  are routed to a security alert node
- **Branching on consent**: Approved users get provider matching; denied/emergency users get
  appropriate responses without unnecessary LLM calls
- **No wasted compute**: Emergency (RED) cases short-circuit the entire pipeline with a 911
  alert, skipping the provider search entirely

### 2. Security-First Architecture

The `security_checkpoint` node sits at the graph entry point — every user message must pass
through it before reaching any LLM agent. This is a deliberate architectural choice:

- PII is scrubbed **before** it reaches Gemini, preventing sensitive data from entering
  model context
- Prompt injections are caught at the gate, before any agent processes the input
- Every decision is logged as structured JSON for audit compliance

### 3. Human-in-the-Loop (HITL) Consent Gate

Medical data sharing requires explicit user consent. The `hitl_consent_gate` node:

- Uses ADK's `RequestInput` to pause execution and collect user consent
- Validates both HIPAA consent language and a valid 5-digit ZIP code
- Supports session resumption via `rerun_on_resume=True`
- Handles edge cases: missing consent, missing ZIP, emergency override

### 4. MCP-Based Tool Server

Provider data is served through a **Model Context Protocol** (MCP) stdio server rather than
hardcoded functions. This design:

- Keeps the agent code decoupled from data sources
- Allows the MCP server to be replaced with a real healthcare API without changing agent logic
- Provides three specialized tools that the LLM agents can call autonomously

### 5. Pydantic-Enforced Data Flow

All inter-node data uses Pydantic `BaseModel` schemas:

- `SymptomReport`: specialty, severity (RED/YELLOW/GREEN), educational notes
- `ProviderInfo` / `HospitalRecommendations`: structured provider data with reviews

This ensures type safety across the entire pipeline and prevents malformed data from
propagating between agents.

---

## Advanced Features Not Found in Typical Projects

| Feature | Why It's Advanced |
|---------|-------------------|
| Conditional graph routing with dict-based routing maps | Goes beyond simple agent chaining |
| PII regex scrubbing before LLM context | Prevents data leakage at the architecture level |
| Prompt injection keyword detection | Proactive security, not reactive |
| Emergency severity short-circuit | Domain-specific safety logic integrated into the graph |
| HITL with RequestInput + resume | Full pause/resume cycle with consent validation |
| MCP stdio tool server | Decoupled, protocol-based tool architecture |
| Structured JSON audit logging | Every security decision is traceable |
| Resumable sessions | Conversations survive process restarts |

---

## Challenges & Learnings

1. **ADK 2.0 Edge Syntax**: The Workflow API uses dict-based routing maps
   `(node, {"route": target})` rather than 3-element tuples. This required inspecting the
   installed package source to discover the correct API surface.

2. **Node Auto-Wrapping**: Functions, LlmAgents, and tools placed directly in edges are
   auto-wrapped into `FunctionNode`, `_LlmAgentWrapper`, etc. No manual wrapping needed.

3. **Windows + MCP**: The MCP stdio server must use `sys.executable` to resolve the correct
   Python binary within the virtual environment.

4. **Content vs Output**: `Event.output` drives downstream data flow, but `Event.content`
   is what renders in the ADK web UI. Both must be set for user-facing nodes.

---

## What I Would Add Next

- **Real healthcare API integration** (replacing simulated data)
- **Image upload support** for visual symptom analysis (rashes, wounds)
- **Insurance verification** via additional MCP tools
- **Multi-language support** for non-English speakers
- **Eval suite** with edge cases (ambiguous symptoms, consent refusal, injection variants)
