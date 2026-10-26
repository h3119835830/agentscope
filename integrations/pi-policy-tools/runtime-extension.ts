import { Type } from "@earendil-works/pi-ai";
import { defineTool, type ExtensionAPI } from "@earendil-works/pi-coding-agent";

export default function (pi: ExtensionAPI) {
  pi.on("before_provider_request", async (event) => ({ ...(event.payload as Record<string, unknown>), thinking: { type: "disabled" } }));
  const managed = process.env.AGENTSCOPE_RUNTIME_JOB_PATH === "managed-jobs";
  const proposalParameters = managed ? Type.Object({
    decision: Type.Union(["restrict", "guidance_only", "no_change"].map(x => Type.Literal(x))),
    add_protected_paths: Type.Array(Type.String(), {maxItems:30, description:"Only new registered relative file paths or directory/** targets to protect. Existing policy is immutable; do not repeat existing targets."}),
    unresolved_requests: Type.Optional(Type.Array(Type.String(), {description: "IDs of necessary unassessed authenticated OS restrictions whose concrete registered targets remain ambiguous."})),
    identified_statements: Type.Array(Type.Object({statement: Type.String(), context_required: Type.Boolean(), context_reason: Type.String(), policy_type: Type.Union(["per_event","cross_event","content","semantic_only"].map(x => Type.Literal(x))), evidence_ids: Type.Array(Type.String())}), {maxItems:20}),
    evidence_ids: Type.Array(Type.String()),
    explanation: Type.String(),
  }) : Type.Object({
    decision: Type.Union(["task_grant", "restrict", "expand", "guidance_only", "no_change"].map(x => Type.Literal(x))),
    allowed_write_dirs: Type.Array(Type.String()),
    allow_output: Type.Boolean(),
    protected_paths: Type.Optional(Type.Array(Type.String())),
    evidence_ids: Type.Array(Type.String()),
    explanation: Type.String(),
  });
  const tools = {
    get_runtime_context: Type.Object({}),
    search_reviewed_history: Type.Object({}),
    submit_scope_proposal: proposalParameters,
  };
  const effectiveTools = process.env.AGENTSCOPE_RUNTIME_JOB_PATH === "managed-jobs"
    ? {...tools, read_runtime_source: Type.Object({id: Type.String()})} : tools;
  for (const [name, parameters] of Object.entries(effectiveTools)) {
    pi.registerTool(defineTool({
      name, label: name, description: name === "submit_scope_proposal" ? (managed ? "Submit only new restriction targets. The controller validates and automatically appends a restrict Delta; existing rules cannot be edited or removed. guidance_only/no_change append nothing." : "Submit a proposed policy snapshot for the non-managed workflow.") : name === "get_runtime_context" ? "Read the authenticated user request, effective policy snapshot, registered targets and additive-only contract." : "Read bound evidence for this policy job; this tool grants no authority.", parameters,
      async execute(_id, args, signal) {
        const response = await fetch(process.env.AGENTSCOPE_SCOPE_URL + "/api/generator/tasks/" + process.env.AGENTSCOPE_SCOPE_TASK +
          "/" + (process.env.AGENTSCOPE_RUNTIME_JOB_PATH || "scope-jobs") + "/" + process.env.AGENTSCOPE_SCOPE_JOB + "/tools/" + name, {
            method: "POST", signal, redirect: "error", headers: { "Content-Type": "application/json",
              Authorization: "Bearer " + process.env.AGENTSCOPE_SCOPE_TOKEN }, body: JSON.stringify({ args }),
          });
        return { content: [{ type: "text", text: await response.text() }], details: { status: response.status }, isError: !response.ok };
      },
    }));
  }
}
