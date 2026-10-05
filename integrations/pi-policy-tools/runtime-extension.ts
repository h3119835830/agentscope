import { Type } from "@earendil-works/pi-ai";
import { defineTool, type ExtensionAPI } from "@earendil-works/pi-coding-agent";

export default function (pi: ExtensionAPI) {
  pi.on("before_provider_request", async (event) => ({ ...(event.payload as Record<string, unknown>), thinking: { type: "disabled" } }));
  const tools = {
    get_runtime_context: Type.Object({}),
    search_reviewed_history: Type.Object({}),
    submit_scope_proposal: Type.Object({
      decision: Type.Union(["task_grant", "restrict", "expand", "guidance_only", "no_change"].map(x => Type.Literal(x))),
      allowed_write_dirs: Type.Array(Type.Union([Type.Literal("backend"), Type.Literal("frontend")])),
      allow_output: Type.Boolean(), evidence_ids: Type.Array(Type.String()), explanation: Type.String(),
    }),
  };
  for (const [name, parameters] of Object.entries(tools)) {
    pi.registerTool(defineTool({
      name, label: name, description: "ScopeManager candidate-only tool; task and job are bound server-side.", parameters,
      async execute(_id, args, signal) {
        const response = await fetch(process.env.AGENTSCOPE_SCOPE_URL + "/api/generator/tasks/" + process.env.AGENTSCOPE_SCOPE_TASK +
          "/scope-jobs/" + process.env.AGENTSCOPE_SCOPE_JOB + "/tools/" + name, {
            method: "POST", signal, redirect: "error", headers: { "Content-Type": "application/json",
              Authorization: "Bearer " + process.env.AGENTSCOPE_SCOPE_TOKEN }, body: JSON.stringify({ args }),
          });
        return { content: [{ type: "text", text: await response.text() }], details: { status: response.status }, isError: !response.ok };
      },
    }));
  }
}
