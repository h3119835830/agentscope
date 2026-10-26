// Presentation only. The immutable model result and evidence remain unchanged.
export const publicAuditText=value=>String(value||'').replace(/\binstance-[a-f0-9]{16}\b/g,'当前 Agent').replace(/\bsession-[a-f0-9-]{36}\b/g,'当前会话').replace(/\b[a-f0-9]{32,64}\b/g,'（证据摘要）').replace(/\b(?:tool|kernel):\d+\b/g,'关联证据');
