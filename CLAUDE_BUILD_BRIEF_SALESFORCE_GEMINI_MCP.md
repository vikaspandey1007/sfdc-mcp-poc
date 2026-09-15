# Claude Build Brief --- Salesforce Hosted MCP + Gemini Revenue Assistant Lab

## 1. Role and working mode

Act as a **principal Salesforce / Google Cloud / AI integration
engineer**. Your first responsibility is to **research and plan before
coding**.

I want to build a small, reproducible architecture lab that proves how
an external AI agent using a Gemini model can consume Salesforce
capabilities through **Salesforce Hosted MCP Servers**. The lab must be
technically credible enough to demonstrate during an enterprise
architecture/security discussion, but deliberately small enough to
build, understand, troubleshoot, and reproduce quickly.

Do **not** treat MCP as the intelligence layer. Maintain these
boundaries throughout the design:

-   **Gemini model** = language understanding and reasoning.
-   **Google ADK agent** = orchestration, instructions, tool selection,
    and control.
-   **MCP client/toolset** = standards-based mechanism used by the agent
    to discover/invoke exposed capabilities.
-   **Salesforce Hosted MCP Server** = governed MCP interface into
    Salesforce capabilities.
-   **Salesforce** = authoritative CRM/system of record and enforcement
    point for Salesforce permissions.
-   **External Client App (ECA)** = OAuth trust registration between the
    external MCP client and Salesforce.

Prefer current first-party documentation over assumptions. If current
Salesforce or Google functionality differs from this brief, **stop and
explicitly identify the discrepancy before implementing around it**.

------------------------------------------------------------------------

## 2. Why we are building this

The immediate objective is educational and architectural.

I need to be able to demonstrate, in approximately 15 minutes, the
answer to:

> "What actually connects to what when an LLM/agent uses MCP to interact
> with Salesforce?"

The longer-term client architecture is a **Revenue Intelligence Agent**
in a Gemini/GCP ecosystem that may eventually consume independently
governed MCP servers from:

1.  Demandbase --- intent/account intelligence.
2.  Salesforce --- CRM/account/opportunity context.
3.  Gong --- conversation intelligence.

This lab is **not** intended to integrate Demandbase or Gong now.

Salesforce is the first implementation because it gives us a
controllable system of record and allows us to demonstrate identity,
authorisation, MCP tool discovery, tool invocation, reasoning, and
governance.

The implementation should establish a pattern that could later be
extended to multiple MCP providers without pretending that approval of
one MCP server automatically approves another.

------------------------------------------------------------------------

## 3. Target business demonstration

Create a small **Revenue Prioritisation Assistant**.

Seed a disposable Salesforce Developer Edition / suitable Salesforce
test org with approximately:

-   5--10 Accounts.
-   8--15 Opportunities.
-   Deliberate variations in:
    -   Amount.
    -   Stage.
    -   Close Date.
    -   Account tier/strategic classification where practical.
    -   Last activity or another practical staleness indicator.
    -   Opportunity ownership if useful for demonstrating Salesforce
        sharing.

The principal user question is:

> "Which open opportunities over £250k should I focus on, and why?"

The desired behaviour is:

1.  User asks the question through the agent.
2.  Gemini understands that Salesforce information is required.
3.  The ADK agent discovers/selects an appropriate Salesforce MCP
    capability.
4.  The MCP client invokes Salesforce Hosted MCP.
5.  Salesforce authenticates/authorises the user and returns only
    permitted information.
6.  Gemini reasons over the returned information.
7.  The assistant produces a concise prioritised answer based only on
    retrieved CRM evidence.
8.  The response should make the evidence/source of its recommendation
    understandable.

A useful follow-up is:

> "Tell me more about Acme."

An intentional unhappy-path request is:

> "Move every opportunity over £250k to Closed Won."

For the initial implementation, the agent **must not be able to perform
this write**. It should explain that the required authorised capability
is unavailable.

This is intentional. The demo must establish:

> **The LLM's ability to reason about an action does not grant authority
> to execute the action.**

------------------------------------------------------------------------

## 4. Target architecture for MVP

Conceptually:

``` text
Business User
     |
     v
Thin Revenue Assistant UI / ADK interaction surface
     |
     v
Google ADK Agent
     |
     +-- Gemini model
     |
     +-- MCP client / MCPToolset
              |
              | OAuth 2.0 / PKCE as supported/required
              v
       Salesforce Hosted MCP Server
              |
              v
       Salesforce Developer/Test Org
       - Account
       - Opportunity
       - Salesforce security model
```

There is an explicit trust boundary between the external Google/agent
runtime and Salesforce.

Do not collapse the ADK agent, Gemini model, MCP protocol, Salesforce
MCP server, and Salesforce APIs into one conceptual component.

------------------------------------------------------------------------

## 5. Salesforce authentication and access requirements

The plan must explicitly include the **Salesforce External Client App**.
Do not hide it as generic "OAuth configuration."

Validate all details against current Salesforce Hosted MCP
documentation.

At minimum investigate and plan for:

-   Salesforce Hosted MCP feature availability in the chosen org type.
-   Activation of only the Hosted MCP server(s) required for the use
    case.
-   Whether `sobject-reads`, `sobject-all`, a more constrained server,
    or a custom server/tool is the best choice.
-   External Client App creation/configuration.
-   OAuth callback URL requirements for:
    -   Postman diagnostic testing.
    -   The eventual custom Google ADK client.
-   Required OAuth scopes, including the current Salesforce MCP scope.
-   PKCE requirements.
-   JWT-shaped access-token requirements.
-   Named-user/per-user OAuth.
-   Permission Set / pre-authorisation approach.
-   CRUD.
-   FLS.
-   Sharing.
-   Refresh-token policy.
-   Consumer key/client ID handling.
-   Whether a client secret is appropriate for the selected client
    architecture.
-   Secret storage.
-   Logout/revocation.
-   Auditability.

**Do not use a legacy Salesforce Connected App if Salesforce Hosted MCP
currently requires an External Client App.**

No consumer secret, access token, refresh token, private key, password,
or other credential may be committed to Git.

Environment-specific identifiers and secrets must be externalised.

------------------------------------------------------------------------

## 6. Security principles

Treat security as part of the implementation, not documentation added
later.

Apply:

### Identity

Prefer per-user authentication so that the external agent acts as the
authenticated Salesforce user rather than a broad shared integration
identity, where supported by the selected architecture.

### Least privilege

The first version should expose **read-only capabilities needed for
Account/Opportunity analysis**.

Do not expose generic write/delete operations merely because Salesforce
can provide them.

### Salesforce enforcement

Validate and document how Salesforce:

-   Object permissions.
-   Field-level security.
-   Record sharing.
-   Permission Sets.
-   Hosted MCP tool/server configuration.

combine to determine effective access.

### Tool governance

Document exactly which MCP servers/tools are available to the agent.

The agent should not receive capabilities it does not need.

### Prompt/tool safety

Consider:

-   Prompt injection.
-   Malicious/untrusted Salesforce field content.
-   Tool-description manipulation where relevant.
-   Excessive tool permissions.
-   Data exfiltration.
-   Cross-tool data leakage in the later multi-MCP model.
-   Hallucination when Salesforce returns insufficient evidence.

### Data protection

Document:

-   Data crossing the Salesforce trust boundary.
-   What is sent to Gemini.
-   What is logged.
-   What should not be logged.
-   Retention considerations.
-   Any relevant GCP/Gemini configuration assumptions that require
    enterprise validation.

### Audit and observability

The implementation should make it possible to determine:

-   User.
-   Agent request.
-   Tool selected.
-   MCP invocation.
-   Salesforce result/failure.
-   Agent response.
-   Correlation/trace identifier where practical.

Avoid logging secrets or unnecessary Salesforce record data.

------------------------------------------------------------------------

## 7. Repository requirements

Propose the final structure during planning, but start from
approximately:

``` text
revenue-agent-mcp-demo/
|
|-- README.md
|-- .gitignore
|-- .env.example
|-- pyproject.toml / requirements.txt
|
|-- agent/
|   |-- __init__.py
|   |-- agent.py
|   |-- prompts.py
|   |-- mcp_config.py
|   `-- config.py
|
|-- app/
|   `-- app.py
|
|-- salesforce/
|   |-- setup.md
|   |-- external-client-app.md
|   |-- hosted-mcp.md
|   |-- permissions.md
|   |-- sample-data/
|   |   |-- accounts.csv
|   |   `-- opportunities.csv
|   `-- metadata/              # only where deployment is supported/useful
|
|-- scripts/
|   |-- verify_environment.*
|   `-- seed_data.*
|
|-- tests/
|   |-- test_agent.py
|   |-- test_mcp_connection.py
|   `-- test_guardrails.py
|
`-- docs/
    |-- architecture.md
    |-- dfd.md
    |-- security-model.md
    |-- threat-model.md
    |-- demo-script.md
    |-- troubleshooting.md
    `-- decisions/
        `-- ADR-001-*.md
```

Determine which Salesforce configuration can safely and reliably be
source-controlled/deployed and which must remain a documented
manual/bootstrap step.

Do not force declarative metadata deployment where Salesforce does not
support it cleanly.

------------------------------------------------------------------------

## 8. Build gates

The implementation must proceed through gates. **Do not jump directly to
a polished UI.**

### Gate 0 --- Research and feasibility

Before changing code:

1.  Verify current Salesforce Hosted MCP functionality.
2.  Verify suitable Salesforce org availability/requirements.
3.  Verify available Salesforce Hosted MCP servers/tools.
4.  Verify ECA/OAuth requirements.
5.  Verify whether Google ADK's current MCP client/tooling can
    authenticate directly against Salesforce's remote Hosted MCP
    endpoint using the required OAuth pattern.
6.  Identify any mismatch between Google ADK MCP authentication support
    and Salesforce Hosted MCP OAuth requirements.
7.  Determine whether an OAuth/token broker or other adapter would be
    required.
8.  Verify the recommended Gemini model/runtime for the lab.
9.  Verify local prerequisites.
10. Identify costs/quotas where relevant.

**Gate 0 deliverable:** feasibility report + recommended technical
path + unresolved questions.

Do not silently invent glue code if there is a protocol/authentication
incompatibility.

### Gate 1 --- Salesforce foundation

Establish:

-   Test/Developer org.
-   Sample Account/Opportunity data.
-   Test users if required.
-   Permission Set(s).
-   Restricted CRM permissions.
-   Salesforce Hosted MCP activation.
-   External Client App.
-   Correct OAuth settings.
-   Correct callback URL(s).
-   Correct MCP scopes.
-   PKCE/JWT settings.
-   Secure credential handling.

**Exit criterion:** Salesforce configuration is complete and documented.

### Gate 2 --- Prove MCP independently of Gemini

Use **Postman or another first-party-recommended diagnostic client** to
validate:

1.  OAuth.
2.  ECA.
3.  Salesforce Hosted MCP endpoint.
4.  Tool discovery.
5.  Read operation.
6.  Salesforce permissions.
7.  Failure behaviour.

Capture a sanitized example of:

-   tool/list or equivalent discovery;
-   successful read;
-   access-denied scenario if practical.

**Exit criterion:** Salesforce MCP works independently of any LLM.

This gate is mandatory.

### Gate 3 --- Google ADK + Gemini

Build one agent:

`RevenuePrioritisationAgent`

Initial behavioural contract:

``` text
You are a revenue intelligence assistant.

Use Salesforce tools when Salesforce evidence is required.
Never invent CRM information.
Only use information returned through authorised tools.
Explain the CRM evidence supporting recommendations.
Do not modify Salesforce data.
If the available tools cannot safely satisfy a request, say so.
```

Connect the ADK agent to Salesforce Hosted MCP using the technically
supported authentication approach identified in Gate 0.

**Exit criterion:**

The question:

> "Show me open opportunities worth more than £250k."

causes an observable sequence equivalent to:

`User -> Gemini/ADK -> MCP tool selection -> Salesforce MCP -> Salesforce -> MCP result -> Gemini -> answer`

### Gate 4 --- Thin user interface

Only after Gate 3 is stable.

Build the simplest reasonable browser interface.

Prefer a low-complexity Python solution unless another option is
strongly justified.

The UI should:

-   Accept a natural-language question.
-   Show the response.
-   Optionally show a small "evidence/tools used" section useful for
    demonstration.
-   Avoid exposing raw credentials/tokens.
-   Avoid becoming a separate frontend project.

### Gate 5 --- Security unhappy paths

Prove at least:

1.  Write request denied/unavailable.
2.  User cannot access records they do not have Salesforce access to, if
    practical.
3.  Agent does not fabricate CRM data when no record is returned.
4.  Invalid/expired authentication fails safely.
5.  Secrets are absent from logs/repository.

### Gate 6 --- Second MCP server

Only after Salesforce is stable, add a tiny **custom Policy MCP
Server**.

Expose a narrow tool such as:

`get_revenue_prioritisation_policy()`

Example business policy:

``` text
+3 Opportunity amount > £250k
+2 Close date within 30 days
+2 Strategic account
+2 No meaningful activity for >14 days
+1 Stage is Proposal or Negotiation
```

Then support:

> "Using our revenue prioritisation policy, which three Salesforce
> opportunities need attention and why?"

The agent should retrieve:

-   CRM facts from Salesforce MCP.
-   Business policy from Policy MCP.

The **agent**, not either MCP server, should orchestrate and reason
across the two results.

**Exit criterion:** multi-MCP tool selection and reasoning are
observable.

------------------------------------------------------------------------

## 9. Future-state architecture to preserve

Do not implement these integrations now, but ensure the design can
conceptually evolve from:

``` text
Revenue Agent
   |
   +-- Salesforce MCP
   `-- Policy MCP
```

to:

``` text
Revenue Intelligence Agent
   |
   +-- Demandbase MCP   -> intent / account intelligence
   +-- Salesforce MCP   -> CRM / opportunity context
   `-- Gong MCP         -> conversation intelligence
```

Each MCP server is an **independent security/data trust domain**.

Explicitly preserve this architectural rule:

> Approval of the Salesforce MCP implementation does not constitute
> approval of Demandbase, Gong, or any future MCP server. Each provider
> requires a delta assessment covering identity, tools, data, actions,
> retention, licensing, and cross-source aggregation risk.

------------------------------------------------------------------------

## 10. Non-functional requirements

Optimise for:

### Security

Least privilege, per-user access where supported, secure secret
handling, bounded tools, auditability.

### Maintainability

Small codebase, clear separation between agent, MCP configuration,
Salesforce bootstrap/configuration, and UI.

### Portability

The demo should run locally first and should not require an elaborate
cloud platform merely to prove the architecture.

### Scalability

Do not optimise for production scale, but avoid design decisions that
fundamentally prevent migration to a managed GCP runtime.

### Reliability

Failures should be explicit and diagnosable. Avoid broad exception
swallowing.

### Observability

Useful structured logs/traces without leaking secrets or excessive CRM
data.

### Agility

Adding a second MCP provider should be configuration/module work rather
than rewriting the application.

### Cost

Keep the lab inexpensive. Identify anything that could create material
Gemini/GCP/Salesforce cost.

------------------------------------------------------------------------

## 11. Design decisions to investigate

Before implementation, explicitly evaluate these decisions and recommend
one option with rationale:

### D1 --- Salesforce MCP server

Compare the narrowest read-oriented Salesforce Hosted MCP server against
broader `sobject-all`/Headless 360 capabilities.

Prefer the narrowest capability that proves the use case.

### D2 --- Authentication

Determine the exact OAuth architecture between the custom Google ADK
application and Salesforce Hosted MCP.

Do not assume that because Postman/Claude can authenticate, ADK
automatically handles the same flow.

### D3 --- Agent runtime

Compare:

-   local Google ADK runtime;
-   Vertex AI Agent Engine;
-   another justified GCP deployment target.

For the first lab, prefer local execution unless managed runtime
materially simplifies secure authentication.

### D4 --- UI

Compare:

-   ADK's development UI if sufficient;
-   Streamlit/simple Python UI;
-   custom web frontend.

Prefer minimum engineering.

### D5 --- Salesforce configuration-as-code

Determine what should be:

-   Salesforce metadata in Git;
-   scripted;
-   manual org bootstrap;
-   environment configuration;
-   secret-manager configuration.

### D6 --- Read capability

Determine whether generic Salesforce record-read MCP tools or a
purpose-specific Flow/Apex/Named Query MCP tool produces the best
balance of demo clarity and least privilege.

### D7 --- Second MCP

Choose a minimal MCP SDK/implementation for the Policy MCP Server
without introducing unnecessary infrastructure.

------------------------------------------------------------------------

## 12. Testing requirements

Create a small but meaningful test strategy.

Include:

### Unit tests

-   Prompt/agent guardrails where deterministic testing is possible.
-   Configuration validation.
-   Policy scoring logic if implemented locally.
-   Secret-redaction/logging helpers.

### Integration tests

-   Salesforce MCP connectivity.
-   Tool discovery.
-   Salesforce read.
-   Permission enforcement.
-   Authentication failure.
-   Gemini tool invocation.
-   Multi-MCP invocation.

### Demo acceptance tests

At minimum:

**AT-01** Given authorised Salesforce access, when the user asks for
open opportunities \> £250k, then only matching authorised records are
used.

**AT-02** When the user asks about a nonexistent opportunity, the agent
does not invent one.

**AT-03** When the user asks the agent to modify Salesforce, the initial
read-only agent refuses/cannot execute the write.

**AT-04** When Salesforce denies access, the agent does not bypass the
denial or expose hidden information.

**AT-05** When the Policy MCP is introduced, the agent combines policy
and CRM evidence and explains the resulting ranking.

**AT-06** No secret/token is committed to Git or displayed in
application logs.

------------------------------------------------------------------------

## 13. Documentation deliverables

The repository must leave enough information that another
architect/developer can reproduce the lab.

Produce:

1.  `README.md`
    -   Purpose.
    -   Architecture.
    -   Prerequisites.
    -   Quick start.
    -   Demo.
    -   Known limitations.
2.  `salesforce/setup.md`
    -   Org prerequisites.
    -   MCP activation.
    -   Sample data.
    -   Access model.
3.  `salesforce/external-client-app.md`
    -   Exact ECA settings.
    -   OAuth scopes.
    -   PKCE.
    -   JWT token setting.
    -   Callback handling.
    -   Permission-set/pre-authorisation approach.
    -   Secret guidance.
    -   Environment-specific values clearly identified.
4.  `docs/architecture.md`
    -   Component responsibilities.
    -   Trust boundaries.
    -   Sequence diagram.
    -   Why MCP is used.
5.  `docs/dfd.md`
    -   Data-flow diagram suitable for security review.
    -   Actors/processes/data stores/trust boundaries.
    -   Data classification notes.
6.  `docs/security-model.md`
    -   Authentication.
    -   Authorisation.
    -   Least privilege.
    -   Tool governance.
    -   Logging.
    -   Data handling.
    -   Revocation.
    -   Residual risks.
7.  `docs/threat-model.md`
    -   STRIDE-style or equivalent threat assessment.
    -   Prompt injection/tool misuse explicitly included.
8.  `docs/demo-script.md`
    -   15-minute happy-path script.
    -   Unhappy path.
    -   Architecture talking points.
    -   Likely audience questions.
9.  `docs/troubleshooting.md`
    -   OAuth callback mismatch.
    -   `invalid_client_id`.
    -   ECA propagation delay.
    -   invalid JWT/bearer-token errors.
    -   wrong Salesforce org during OAuth.
    -   MCP tool not visible.
    -   permission/FLS/sharing failures.
    -   ADK/MCP authentication failures.
10. ADRs for significant choices.

------------------------------------------------------------------------

## 14. Provenance requirements

Use **current first-party sources**.

Prioritise:

-   Salesforce Developer documentation for Hosted MCP Servers.
-   Salesforce documentation for External Client Apps.
-   Salesforce security/permissions documentation.
-   Google Agent Development Kit documentation.
-   Google Cloud / Vertex AI documentation.
-   Model Context Protocol official specification where protocol
    behaviour matters.

Do not base architectural decisions on random blogs, Medium posts,
copied examples, or stale pre-release implementations when primary
documentation exists.

For every material assumption in the implementation plan, provide the
primary-source URL.

Important Salesforce facts that must be independently verified during
planning include:

-   Hosted MCP clients require an External Client App.
-   Legacy Connected Apps are not the supported MCP authentication
    mechanism.
-   `mcp_api` and appropriate refresh/offline scope requirements.
-   PKCE.
-   JWT-shaped access tokens.
-   Per-user Salesforce permission enforcement.
-   Recommended use of Postman to isolate MCP/authentication before
    adding an LLM.

Do not blindly trust this brief; verify them against the current
documentation.

------------------------------------------------------------------------

## 15. Explicit non-goals

Do **not** initially:

-   Integrate Demandbase.
-   Integrate Gong.
-   Build production Revenue Intelligence.
-   Deploy Kubernetes.
-   Build a complex React frontend.
-   Create unrestricted Salesforce write access.
-   Create generic autonomous actions.
-   Add Data Cloud unless technically required.
-   Add MuleSoft merely because Salesforce is involved.
-   Add a vector database without a proven requirement.
-   Implement RAG when MCP tool retrieval already satisfies the use
    case.
-   Create custom Salesforce APIs if Hosted MCP already exposes the
    required capability.
-   Store Salesforce credentials in application source/config tracked by
    Git.
-   Build before Gate 0 establishes the supported authentication path.

------------------------------------------------------------------------

## 16. What I want from you FIRST

**Do not start implementation yet.**

Perform a planning/research pass and return a detailed implementation
plan in Markdown.

Your response must contain:

### A. Feasibility verdict

-   Can this architecture be implemented today with current Salesforce
    Hosted MCP + Google ADK/Gemini?
-   Confidence level.
-   Any blockers/caveats.

### B. Validated target architecture

Provide: - Component diagram. - Sequence diagram. - Authentication
flow. - Trust boundaries.

### C. Salesforce setup plan

Exact steps covering: - org; - MCP server; - ECA; - OAuth; - permission
sets; - sample data; - manual vs source-controlled configuration.

### D. Google/agent plan

Exact: - ADK components; - Gemini model choice; - MCP integration; -
OAuth/token handling; - local runtime; - optional GCP deployment.

### E. Repository plan

Final directory/file structure and responsibility of each file.

### F. Gate-by-gate implementation backlog

For every gate include: - tasks; - dependencies; - files changed; -
manual steps; - automated tests; - acceptance criteria; - estimated
effort; - likely failure modes.

### G. Security assessment

List: - threats; - controls; - residual risks; - items requiring
enterprise/client confirmation.

### H. Decision log

For each material architectural choice provide: - options; - pros; -
cons; - recommendation; - rationale; - confidence.

### I. Open questions

Only questions that genuinely block implementation. Do not ask questions
that can be answered from current primary documentation or by inspecting
the repository/environment.

### J. Implementation order

End with an exact recommended sequence of work.

------------------------------------------------------------------------

## 17. How to work after I approve the plan

After I review and approve the plan:

1.  Implement **one gate at a time**.
2.  Stop after each gate.
3.  Show:
    -   what changed;
    -   files created/modified;
    -   tests executed;
    -   results;
    -   manual action I need to perform;
    -   evidence that the gate acceptance criteria passed.
4.  Do not proceed to the next gate until I confirm.
5.  If reality differs from the plan, explain why and update the
    ADR/plan rather than silently working around it.
6.  Keep commits small and logically scoped.
7.  Never commit secrets.
8.  Prefer declarative/configuration approaches over custom code where
    practical.
9.  Do not introduce infrastructure or abstractions without a
    demonstrated requirement.

------------------------------------------------------------------------

## 18. Definition of done

The lab is complete when I can reliably demonstrate:

1.  Salesforce Hosted MCP is active and securely authenticated through
    an External Client App.
2.  A diagnostic client can discover and invoke the required Salesforce
    MCP tools independently of an LLM.
3.  A Google ADK/Gemini agent can use Salesforce through MCP.
4.  The agent answers the revenue-prioritisation question using actual
    Salesforce evidence.
5.  Salesforce permissions remain authoritative.
6.  The initial agent cannot perform unauthorised write operations.
7.  A second small Policy MCP server can be added.
8.  The same agent can reason across Salesforce CRM data and policy
    information obtained from two independent MCP servers.
9.  Logs/traces demonstrate the interaction without leaking secrets.
10. The repository contains a reproducible setup and a 15-minute
    architecture/security demonstration script.

The final architectural lesson should be obvious:

> **MCP standardises how the agent discovers and invokes external
> capabilities. Gemini provides reasoning. The ADK agent orchestrates.
> Salesforce remains authoritative for CRM data and access. Security
> approval applies to specific identities, tools, data flows, and
> actions --- not to "MCP" as a blanket technology.**
