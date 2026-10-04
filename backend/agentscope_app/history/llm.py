"""A tool-free DeepSeek JSON client. Credentials and reasoning are never returned."""
import hashlib
import json
import os
import time
import urllib.error
import urllib.request

class LLMError(RuntimeError):
    pass

class DeepSeekProvider:
    def __init__(self, *, api_key=None, model=None, base_url=None, timeout=120):
        self.api_key = api_key or os.getenv("AGENTSCOPE_HISTORY_LLM_KEY", "")
        self.model = model or os.getenv("AGENTSCOPE_HISTORY_LLM_MODEL", "deepseek-flash")
        self.base_url = (base_url or os.getenv("AGENTSCOPE_HISTORY_LLM_URL", "https://api.deepseek.com")).rstrip("/")
        self.timeout = timeout

    def generate(self, system, payload, prompt_version):
        if not self.api_key:
            raise LLMError("历史库 DeepSeek 服务凭据未配置")
        body = {"model": self.model, "messages": [
            {"role": "system", "content": system + "\nReturn only a JSON object."},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
            "response_format": {"type": "json_object"}, "max_tokens": 14000,
            "thinking": {"type": "disabled"}}
        encoded = json.dumps(body, ensure_ascii=False).encode()
        request = urllib.request.Request(self.base_url + "/chat/completions", encoded,
            {"Authorization": "Bearer " + self.api_key, "Content-Type": "application/json"})
        start = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                result = json.load(response)
        except urllib.error.HTTPError as e:
            # Provider response bodies may repeat credentials or request text.
            raise LLMError(f"DeepSeek HTTP {e.code}") from None
        except (TimeoutError, OSError, ValueError):
            raise LLMError("DeepSeek 请求超时、网络失败或响应无效") from None
        try:
            choice = result["choices"][0]
            if choice.get("finish_reason") == "length":
                raise LLMError("DeepSeek 输出被截断；请缩小文档分块")
            content = choice["message"]["content"]
            parsed = json.loads(content)
            if not isinstance(parsed, dict):
                raise ValueError()
        except json.JSONDecodeError as e:
            raise LLMError(f"DeepSeek JSON 无效（行 {e.lineno}，列 {e.colno}）") from None
        except (KeyError, IndexError, TypeError, ValueError) as e:
            raise LLMError("DeepSeek 未返回有效 JSON 对象（"+type(e).__name__+"）") from None
        metadata = {"provider": "deepseek", "model": self.model,
            "response_model": result.get("model", self.model), "prompt_version": prompt_version,
            "input_hash": hashlib.sha256(encoded).hexdigest(),
            "output_hash": hashlib.sha256(content.encode()).hexdigest(),
            "usage": result.get("usage", {}), "duration_ms": round((time.monotonic()-start)*1000)}
        # Only the final structured content is retained, never reasoning_content.
        return parsed, metadata
