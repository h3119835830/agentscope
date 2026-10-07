import { Type } from "@earendil-works/pi-ai";
import { defineTool, type ExtensionAPI } from "@earendil-works/pi-coding-agent";

export default function (pi: ExtensionAPI) {
  pi.on("before_provider_request", async (event) => ({ ...(event.payload as Record<string, unknown>), thinking: { type: "disabled" } }));
  const evidence = Type.Object({ source_id: Type.String(), relative_path: Type.String(), sha256: Type.String(), quote: Type.String({ minLength: 1, maxLength: 2000 }) }, { additionalProperties: false });
  const draft = Type.Object({
    name: Type.String({ minLength: 1, maxLength: 120 }), goal: Type.String({ maxLength: 8000 }),
    state: Type.Union([Type.Literal("ready"), Type.Literal("needs_clarification")]),
    constraints: Type.Array(Type.String({ minLength: 1, maxLength: 1000 }), { maxItems: 30 }),
    clarification: Type.String({ maxLength: 2000 }), evidence: Type.Array(evidence, { maxItems: 30 }),
  }, { additionalProperties: false });
  const schemas = {
    list_scene_sources: Type.Object({}, { additionalProperties: false }),
    read_scene_source: Type.Object({ source_id: Type.String(), offset: Type.Optional(Type.Integer({ minimum: 0 })), limit: Type.Optional(Type.Integer({ minimum: 1, maximum: 128000 })) }, { additionalProperties: false }),
    submit_scene_draft: Type.Object({ draft }, { additionalProperties: false }),
  };
  const descriptions: Record<string, string> = {
    list_scene_sources: "List the immutable sources for this read job. Metadata alone does not establish a task goal.",
    read_scene_source: "Read a byte range of a listed source. Cite exact returned text and its source_id/path/sha256 in your draft. Use end_offset for the next range.",
    submit_scene_draft: "Submit one public evidence-backed task draft, or ask for clarification. This creates no execution task and grants no authority.",
  };
  for (const [name, parameters] of Object.entries(schemas)) {
    pi.registerTool(defineTool({
      name, label: name, description: descriptions[name], parameters,
      async execute(_id, params, signal) {
        const url = `${process.env.AGENTSCOPE_SCENE_READ_URL}/api/scene-reader/jobs/${process.env.AGENTSCOPE_SCENE_READ_ID}/tools/${name}`;
        const response = await fetch(url, { method: "POST", signal, headers: { "Content-Type": "application/json", Authorization: `Bearer ${process.env.AGENTSCOPE_SCENE_READ_TOKEN}` }, body: JSON.stringify(params) });
        const text = await response.text();
        let rejected = false;
        try { rejected = JSON.parse(text).valid === false; } catch {}
        return { content: [{ type: "text", text }], details: { status: response.status }, isError: !response.ok || rejected };
      },
    }));
  }
}
