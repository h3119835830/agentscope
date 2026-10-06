import { Type } from "@earendil-works/pi-ai";
import { defineTool, type ExtensionAPI } from "@earendil-works/pi-coding-agent";

export default function (pi: ExtensionAPI) {
  pi.on("before_provider_request", async (event) => ({ ...(event.payload as Record<string, unknown>), thinking: { type: "disabled" } }));
  const tools = {
    get_runtime_context: Type.Object({}),
    search_reviewed_history: Type.Object({}),
    submit_scope_proposal: Type.Object({
      decision: Type.Union((process.env.AGENTSCOPE_RUNTIME_JOB_PATH === "managed-jobs" ? ["restrict", "expand", "guidance_only", "no_change"] : ["task_grant", "restrict", "expand", "guidance_only", "no_change"]).map(x => Type.Literal(x))),
      allowed_write_dirs: Type.Array(Type.String()),
      ...(process.env.AGENTSCOPE_RUNTIME_JOB_PATH === "managed-jobs" ? {unresolved_requests: Type.Optional(Type.Array(Type.String(), {description: "IDs of necessary unassessed authenticated OS constraints that cannot be resolved to supported authorized targets. A nonempty list keeps tools paused pending clarification; no permission changes may accompany it."}))} : {}),
      allow_output: Type.Boolean(), protected_paths: Type.Optional(Type.Array(Type.String(), {description: "Blocks OS write/unlink on every matching target; /** blocks ALL descendants. Retain confirmed paths. New targets require context authorized_protection_targets and its authenticated request evidence; a project read receipt alone does not authorize protection."})), evidence_ids: Type.Array(Type.String()), explanation: Type.String(),
    }),
  };
  const effectiveTools = process.env.AGENTSCOPE_RUNTIME_JOB_PATH === "managed-jobs"
    ? {...tools, read_runtime_source: Type.Object({id: Type.String()})} : tools;
  for (const [name, parameters] of Object.entries(effectiveTools)) {
    pi.registerTool(defineTool({
      name, label: name, description: name === "submit_scope_proposal" ? "Submit a proposed policy snapshot only. restrict proposes tightening; expand records a pending confirmation candidate, never an approval or application; no_change/guidance_only retain the current snapshot. The controller separately applies verified restrictions and applies expansion only after authenticated human confirmation." : name === "get_runtime_context" ? "Read the frozen task, current policy, concrete path mapping, advertised expansion targets and candidate-only workflow contract." : "Read bound evidence for this policy job; this tool grants no authority.", parameters,
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
