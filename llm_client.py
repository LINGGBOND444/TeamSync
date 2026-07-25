"""LLM 客户端：调用 DeepSeek V4 API，提取 JSON，重试逻辑。"""

import json
import os
import re
from typing import Any

import openai
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

DEEPSEEK_BASE_URL = "https://api.deepseek.com"


def _extract_json(text: str) -> list[dict]:
    """从 LLM 返回文本中提取 JSON 数组。

    按优先级尝试：直接解析 → 提取 ```json 代码块 → 正则匹配 [...] 数组。
    """
    text = text.strip()

    # 1) 直接解析
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            if "tasks" in data:
                return data["tasks"]
    except json.JSONDecodeError:
        pass

    # 2) 提取 markdown 代码块
    code_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if code_match:
        try:
            data = json.loads(code_match.group(1))
            if isinstance(data, list):
                return data
            if isinstance(data, dict) and "tasks" in data:
                return data["tasks"]
        except json.JSONDecodeError:
            pass

    # 3) 正则匹配 JSON 数组
    array_match = re.search(r"\[[\s\S]*\]", text)
    if array_match:
        try:
            return json.loads(array_match.group(0))
        except json.JSONDecodeError:
            pass

    raise ValueError(f"无法从返回值中提取 JSON 数组，原始返回前 500 字符：\n{text[:500]}")


def generate_tasks(
    transcript: str,
    system_prompt: str,
    user_prompt_builder,
    model: str = "deepseek-v4-flash",
    max_retries: int = 2,
) -> tuple[list[dict], dict[str, Any]]:
    """调用 DeepSeek 生成任务，自动重试 JSON 解析失败。

    返回 (任务列表, 元数据字典)。
    """
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("未设置 DEEPSEEK_API_KEY 环境变量")

    client = OpenAI(api_key=api_key, base_url=DEEPSEEK_BASE_URL)

    last_error = None
    for attempt in range(max_retries + 1):
        retry_hint = ""
        if attempt > 0 and last_error:
            retry_hint = (
                f"【第 {attempt} 次重试 — 上次解析失败】"
                f"错误信息：{last_error}"
                f"请务必只输出 JSON 数组本身，开头是 [，结尾是 ]，"
                f"不要用 markdown 代码块包裹，不要加任何解释文字。"
            )

        user_message = user_prompt_builder(transcript, retry_hint)

        try:
            response = client.chat.completions.create(
                model=model,
                max_tokens=4096,
                temperature=0.1,
                extra_body={"thinking": {"type": "disabled"}},
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
            )
        except openai.AuthenticationError:
            raise RuntimeError("API Key 无效，请在侧边栏检查后重试")
        except openai.APIConnectionError:
            raise RuntimeError("网络连接失败，请检查网络后重试")
        except openai.APIError as e:
            raise RuntimeError(f"API 请求失败：{e}")

        raw_text = response.choices[0].message.content

        try:
            tasks = _extract_json(raw_text)
            metadata = {
                "model": response.model,
                "input_tokens": response.usage.prompt_tokens,
                "output_tokens": response.usage.completion_tokens,
                "attempts": attempt + 1,
            }
            return tasks, metadata
        except ValueError as e:
            last_error = str(e)

    raise ValueError(
        f"经过 {max_retries + 1} 次尝试后仍无法解析 JSON。"
        f"最后错误：{last_error}"
    )
