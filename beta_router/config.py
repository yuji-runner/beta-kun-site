import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")


# Ollama
OLLAMA_HOST = os.getenv(
    "OLLAMA_HOST",
    "http://10.3.90.50:11434",
)
OLLAMA_MODEL = os.getenv(
    "OLLAMA_MODEL",
    "qwen2.5:7b",
)


# Groq
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_BASE_URL = os.getenv(
    "GROQ_BASE_URL",
    "https://api.groq.com/openai/v1",
)
GROQ_MODEL = os.getenv(
    "GROQ_MODEL",
    "llama-3.1-8b-instant",
)
SYSTEM_PROMPT = """
あなたはβRouterから呼び出されるAIアシスタントです。

βRouterはネットワーク機器ではありません。
Ollama、Groq、NVIDIA NIM、Codexなど複数のAIを、
仕事内容・速度・費用・機密性に応じて使い分けるAIルーターです。

現在の役割:
- Ollama: ローカル処理、分類、整形、短い要約
- Groq: 高速な文章生成、長めの要約、レビュー
- NVIDIA NIM: 将来追加予定の別モデル検証
- Codex: 将来追加予定のリポジトリ編集、テスト、実装

回答は原則として日本語で行ってください。
分からないことは推測で断定しないでください。

分類・整形・要約・変換を依頼された場合は、
挨拶、感想、確認、補足提案を付けず、原則として処理結果だけを返してください。

依頼文に含まれていない個人情報、過去の会話、内部メモ、
健康情報、予定、天気などを勝手に補ってはいけません。

機密情報を扱う場合も、機密保持を宣言する文章ではなく、
依頼された処理結果だけを簡潔に返してください。
"""


# NVIDIA NIM
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
NVIDIA_BASE_URL = os.getenv(
    "NVIDIA_BASE_URL",
    "https://integrate.api.nvidia.com/v1",
)
NVIDIA_MODEL = os.getenv(
    "NVIDIA_MODEL",
    "deepseek-ai/deepseek-v4-flash",
)
