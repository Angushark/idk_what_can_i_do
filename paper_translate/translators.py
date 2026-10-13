"""Translation backends: English -> Traditional Chinese (Taiwan)."""

from __future__ import annotations

import json
import os
from typing import Protocol

SYSTEM_PROMPT = """你是專業的學術論文翻譯者，負責把英文論文翻譯成台灣慣用的繁體中文。

規則：
- 使用台灣學術界慣用術語（例如：資料、演算法、網路、模型、訓練、品質、程式）。
- 譯文要通順、正式，符合中文論文寫作習慣，不要逐字硬翻。
- 數學式、變數名稱（如 x_i、θ、L_CE）、數字、單位、引用標記（如 [12]、(Smith et al., 2020)）、URL、程式碼、資料集與模型名稱（如 ImageNet、BERT、ResNet-50）保持原樣，不要翻譯。
- 重要專有名詞第一次出現時可在中文後加上英文原文，例如「注意力機制（attention mechanism）」，之後只用中文。
- 章節標題如 "1 Introduction" 翻成「1 緒論」，保留編號。
- 只輸出譯文本身，不要加入任何解釋。
- 每個段落獨立翻譯，id 必須與輸入一一對應。"""


class Translator(Protocol):
    name: str

    def translate_batch(self, texts: list[str], context: str = "") -> list[str]:
        ...


class ClaudeTranslator:
    """Uses the Claude API. Reads credentials from ANTHROPIC_API_KEY (or an `ant auth login` profile)."""

    name = "claude"

    def __init__(self, model: str | None = None, effort: str | None = None):
        import anthropic

        self.client = anthropic.Anthropic()
        self.model = model or os.environ.get("PAPER_TRANSLATE_MODEL", "claude-opus-5-5")
        self.effort = effort or os.environ.get("PAPER_TRANSLATE_EFFORT", "medium")

    def translate_batch(self, texts: list[str], context: str = "") -> list[str]:
        if not texts:
            return []
        payload = [{"id": i, "text": t} for i, t in enumerate(texts)]
        prompt = ""
        if context:
            prompt += f"<paper_context>\n{context}\n</paper_context>\n\n"
        prompt += (
            "請翻譯以下段落（JSON 陣列）。回傳 translations 陣列，每個元素包含相同的 id 與譯文 text。\n\n"
            + json.dumps(payload, ensure_ascii=False)
        )
        schema = {
            "type": "object",
            "properties": {
                "translations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"id": {"type": "integer"}, "text": {"type": "string"}},
                        "required": ["id", "text"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["translations"],
            "additionalProperties": False,
        }
        with self.client.beta.messages.stream(
            model=self.model,
            max_tokens=64000,
            system=SYSTEM_PROMPT,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            output_config={"effort": self.effort, "format": {"type": "json_schema", "schema": schema}},
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            response = stream.get_final_message()

        if response.stop_reason == "refusal":
            raise RuntimeError("Claude 拒絕翻譯這段內容")
        if response.stop_reason == "max_tokens":
            raise RuntimeError("輸出超過長度上限，請調小每批段落數")
        text = next(b.text for b in response.content if b.type == "text")
        data = json.loads(text)["translations"]
        by_id = {item["id"]: item["text"] for item in data}
        # Fall back to the source text for any id the model skipped.
        return [by_id.get(i, t) for i, t in enumerate(texts)]


class GoogleTranslator:
    """Free Google Translate via deep-translator. No API key, lower quality."""

    name = "google"

    def __init__(self):
        from deep_translator import GoogleTranslator as _G

        self._t = _G(source="en", target="zh-TW")

    def translate_batch(self, texts: list[str], context: str = "") -> list[str]:
        return [self._t.translate(t[:4900]) or t for t in texts]


class FakeTranslator:
    """Offline stand-in for tests: produces Chinese text of similar length."""

    name = "fake"

    def translate_batch(self, texts: list[str], context: str = "") -> list[str]:
        filler = "這是測試用的繁體中文譯文內容"
        return [(filler * (len(t) // (2 * len(filler)) + 1))[: max(2, len(t) // 2)] for t in texts]


def get_translator(name: str | None = None) -> Translator:
    name = name or os.environ.get("PAPER_TRANSLATE_BACKEND")
    if not name:
        name = "claude" if (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")) else "google"
    if name == "claude":
        return ClaudeTranslator()
    if name == "google":
        return GoogleTranslator()
    if name == "fake":
        return FakeTranslator()
    raise ValueError(f"未知的翻譯引擎：{name}（可用：claude、google、fake）")
