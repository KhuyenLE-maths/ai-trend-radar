"""Tầng 1 bộ lọc AI-relevance: rule-based, chạy cho mọi repo, miễn phí (mục 3.3)."""
import re

# Topic GitHub nằm trong allowlist → cộng điểm mạnh
TOPIC_ALLOWLIST = {
    "ai", "llm", "llms", "agents", "ai-agents", "agentic-ai", "multi-agent",
    "mcp", "model-context-protocol", "rag", "retrieval-augmented-generation",
    "machine-learning", "deep-learning", "neural-network", "transformers",
    "mlops", "llmops", "computer-vision", "nlp", "natural-language-processing",
    "speech-recognition", "text-to-speech", "speech-to-text", "voice-ai",
    "vector-database", "embeddings", "knowledge-graph", "fine-tuning", "lora",
    "inference", "model-serving", "cuda", "gpu", "generative-ai", "genai",
    "diffusion-models", "stable-diffusion", "gpt", "chatgpt", "openai",
    "anthropic", "claude", "llama", "langchain", "prompt-engineering",
    "ai-coding", "copilot", "llm-evaluation", "synthetic-data", "data-science",
    "reinforcement-learning", "robotics", "ocr", "object-detection",
}

# (pattern, trọng số) — match trên name + description
KEYWORDS: list[tuple[str, float]] = [
    (r"\bllms?\b", 3), (r"\bagentic\b", 3), (r"\bai agents?\b", 3),
    (r"\bmulti[- ]agent\b", 3), (r"\bmcp\b", 2.5), (r"\bmodel context protocol\b", 3),
    (r"\brag\b", 2.5), (r"\bretrieval[- ]augmented\b", 3),
    (r"\bmachine learning\b", 2), (r"\bdeep learning\b", 2),
    (r"\bneural\b", 1.5), (r"\btransformers?\b", 1.5), (r"\bdiffusion\b", 1.5),
    (r"\bfine[- ]?tun", 2), (r"\binference\b", 1.5), (r"\bembeddings?\b", 2),
    (r"\bvector (database|db|store|search)\b", 3), (r"\bmlops\b", 3), (r"\bllmops\b", 3),
    (r"\bcomputer vision\b", 2), (r"\bnlp\b", 2), (r"\bspeech\b", 1.5),
    (r"\btext[- ]to[- ](speech|image|video)\b", 2.5), (r"\bvoice\b", 1),
    (r"\bgpt[- ]?\d?\b", 2), (r"\bchatbot\b", 1.5), (r"\bcopilot\b", 1.5),
    (r"\bprompt\b", 1.5), (r"\bgenerative ai\b", 2.5), (r"\bfoundation model\b", 3),
    (r"\bknowledge graph\b", 2), (r"\bcuda\b", 2), (r"\bgpu\b", 1),
    (r"\bsynthetic data\b", 2.5), (r"\bai[- ]powered\b", 1.5), (r"\bautonomous\b", 1),
    (r"\bopenai\b", 2), (r"\banthropic\b", 2), (r"\bclaude\b", 1.5),
    (r"\bllama\b", 2), (r"\bollama\b", 2), (r"\blangchain\b", 2),
    (r"\breinforcement learning\b", 2), (r"\bocr\b", 1.5),
]

# Tín hiệu KHÔNG liên quan → trừ điểm
NEGATIVE: list[tuple[str, float]] = [
    (r"\bcrypto(currency)?\b", -3), (r"\btrading bot\b", -3), (r"\bblockchain\b", -2),
    (r"\bminecraft\b", -3), (r"\bhomework\b", -3), (r"\bcourse (project|work)\b", -3),
    (r"\bassignments?\b", -2), (r"\btutorial\b", -1), (r"\bcheat\s?sheet\b", -1),
    (r"\binterview (prep|questions)\b", -2),
]

_COMPILED = [(re.compile(p, re.I), w) for p, w in KEYWORDS + NEGATIVE]


def relevance_score(name: str, description: str, topics: list[str]) -> float:
    """Điểm càng cao càng chắc chắn là project AI. Ngưỡng nhận: settings.ai_filter_threshold."""
    score = 0.0
    for t in topics:
        if t.lower() in TOPIC_ALLOWLIST:
            score += 3.0
    score = min(score, 9.0)  # trần điểm topic, tránh topic-spam
    text = f"{name} {description}"
    for rx, w in _COMPILED:
        if rx.search(text):
            score += w
    return round(score, 2)
