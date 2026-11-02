# Architectural Glossary

This glossary explains every core agentic AI, MCP, and orchestration concept used in this project in plain language, explicitly linked to where it is implemented in your codebase.

---

### 1. Host (MCP Host)
* **Definition:** The application running the agent loop that initiates contact with tools and controls execution. The host manages security boundaries, passes user prompts, and invokes tools on remote or local servers.
* **In Your Code:** [`src/agents/career_checker.py`](file:///c:/Users/lasit/Documents/Job_Seek/src/agents/career_checker.py) and harvest adapters act as the client/host that consumes tools declared by the MCP server. In the raw JSON-RPC demo ([`tests/test_phase3_mcp.py`](file:///c:/Users/lasit/Documents/Job_Seek/tests/test_phase3_mcp.py)), `TestClient` is the explicit MCP host.

### 2. Client (MCP Client)
* **Definition:** The transport adapter inside the host application that translates high-level function calls into JSON-RPC 2.0 messages over streams (`stdio` pipes or HTTP/SSE).
* **In Your Code:** Used inside [`tests/test_phase3_mcp.py`](file:///c:/Users/lasit/Documents/Job_Seek/tests/test_phase3_mcp.py) where the Python parent process writes JSON-RPC requests to the subprocess's `stdin`.

### 3. Server (MCP Server)
* **Definition:** An independent, decoupled process that advertises and executes tools, prompts, or resources over the Model Context Protocol. It has zero knowledge of the LLM's conversation history; it simply receives function arguments and returns results.
* **In Your Code:** [`mcp_servers/career_page_reader/server.py`](file:///c:/Users/lasit/Documents/Job_Seek/mcp_servers/career_page_reader/server.py), built on `MCPServer("career_page_reader")`, running independently over `stdio`.

### 4. Tool (MCP Tool)
* **Definition:** An executable procedure exposed by an MCP server with an explicit JSON Schema defining its parameters. Tools cause side effects or perform compute (e.g. HTTP fetches, database writes).
* **In Your Code:** `@mcp.tool()` decorators in [`server.py`](file:///c:/Users/lasit/Documents/Job_Seek/mcp_servers/career_page_reader/server.py): `detect_ats(url)`, `list_jobs(careers_url)`, and `get_job_details(job_url)`.

### 5. Sampling (MCP Sampling)
* **Definition:** A feature in the MCP protocol allowing an MCP *server* to request LLM completions back from the *host* without needing its own API keys or LLM provider configurations.
* **In Your Code:** Used conceptually in [`src/agents/manager.py`](file:///c:/Users/lasit/Documents/Job_Seek/src/agents/manager.py), where the Manager audits rows by delegating LLM completion tasks.

### 6. Agent Card
* **Definition:** A machine-readable JSON metadata manifest (defined in the Agent-to-Agent / A2A specification) that describes an agent's public identity, capabilities, input/output schemas, SLA, and authentication endpoints.
* **In Your Code:** [`src/a2a/agent_card.json`](file:///c:/Users/lasit/Documents/Job_Seek/src/a2a/agent_card.json), served dynamically by [`src/a2a/service.py`](file:///c:/Users/lasit/Documents/Job_Seek/src/a2a/service.py) at `/.well-known/agent-card.json`.

### 7. Task Lifecycle & Durable Checkpointing
* **Definition:** Treating agent workflows as asynchronous state machines with explicit status transitions (`PENDING -> RUNNING -> COMPLETED -> VERIFIED / FAILED`). If a network connection drops or the process crashes, the orchestrator resumes exactly where it stopped with lease timeouts and atomic claims.
* **In Your Code:** Managed by SQLite in [`src/db.py`](file:///c:/Users/lasit/Documents/Job_Seek/src/db.py) (`tasks` table) and dispatched by [`src/agents/manager.py`](file:///c:/Users/lasit/Documents/Job_Seek/src/agents/manager.py).

### 8. Orchestrator-Workers Pattern
* **Definition:** A hierarchical architectural pattern where a single central "Manager" coordinates specialized "Workers". The Manager creates task queues, enforces rate limits, aggregates results, and validates evidence. Workers do not talk directly to each other or write directly to export files.
* **In Your Code:** [`src/agents/manager.py`](file:///c:/Users/lasit/Documents/Job_Seek/src/agents/manager.py) (Manager) coordinating harvest workers and the independent verification stage.

### 9. Prompt Injection & Structural Untrusted Framing
* **Definition:** An attack vector where external web data contains instructions attempting to hijack the agent's behavior. Defended in depth by:
  1. Enclosing external data in structural tags (e.g. `<UNTRUSTED_JOB_DATA>`) in data fetchers ([`mcp_servers/career_page_reader/server.py`](file:///c:/Users/lasit/Documents/Job_Seek/mcp_servers/career_page_reader/server.py)).
  2. Explicit system instructions directing the model to ignore instructions within untrusted tags ([`src/prompts/job_classifier.md`](file:///c:/Users/lasit/Documents/Job_Seek/src/prompts/job_classifier.md)).
  3. Stripping wrapper tags prior to sentence/evidence extraction.
  4. Code-level assertion checking that extracted evidence quotes exist verbatim as substrings of the fetched raw page text.
