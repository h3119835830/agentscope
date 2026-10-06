import { Type } from "@earendil-works/pi-ai";
import { defineTool, type ExtensionAPI } from "@earendil-works/pi-coding-agent";

export default function (pi: ExtensionAPI) {
  pi.on("before_provider_request", async (event) => ({ ...(event.payload as Record<string, unknown>), thinking: { type: "disabled" } }));
  const schemas = {
    get_task_context: Type.Object({}),
    list_policy_sources: Type.Object({}),
    read_policy_source: Type.Object({ source_id: Type.String() }),
    search_historical_policies: Type.Object({ query: Type.String({ maxLength: 2000 }) }),
    get_enforcement_capabilities: Type.Object({}),
    validate_policy_draft: Type.Object({ draft: Type.Unknown() }),
    submit_task_policy_proposal: Type.Object({ proposal_hash: Type.String({ description: "Hash returned by a successful validate_policy_draft; server submits its immutable saved candidate" }) }),
  };
  for (const [name, parameters] of Object.entries(schemas)) {
    pi.registerTool(defineTool({
      name, label: name, description: `AgentScope controlled generator tool: ${name}. All scope is bound server-side to this job.`, parameters,
      async execute(_id, params, signal) {
        const url = `${process.env.AGENTSCOPE_GENERATOR_URL}/api/generator/tasks/${process.env.AGENTSCOPE_GENERATOR_TASK}/jobs/${process.env.AGENTSCOPE_GENERATOR_JOB}/tools/${name}`;
        const response = await fetch(url, { method: "POST", signal, headers: { "Content-Type": "application/json", Authorization: `Bearer ${process.env.AGENTSCOPE_GENERATOR_TOKEN}` }, body: JSON.stringify(params) });
        const text = await response.text();
        let rejected = false;
        try { rejected = JSON.parse(text).valid === false; } catch {}
        return { content: [{ type: "text", text }], details: { status: response.status }, isError: !response.ok || rejected };
      },
    }));
  }
}
