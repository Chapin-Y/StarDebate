"""共享容错 JSON 解析模块。
处理 AI 返回 JSON 常见的格式错误（截断、多余 ``` 标记、括号不匹配等）。
供 ai_expand、framework、speech_writer 等 AI 功能模块共用。
"""
import json as _json
from typing import Callable, Optional


def _try_complete_json(json_text: str, cut_pos: int) -> Optional[str]:
    """尝试在 cut_pos 处截断并补全缺失的括号，返回补全后的合法 JSON 字符串或 None。"""
    truncated = json_text[:cut_pos + 1]
    depth_brace = 0
    depth_bracket = 0
    in_string = False
    escape_next = False
    for ch in truncated:
        if escape_next:
            escape_next = False
            continue
        if ch == '\\':
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == '{':
            depth_brace += 1
        elif ch == '}':
            depth_brace -= 1
        elif ch == '[':
            depth_bracket += 1
        elif ch == ']':
            depth_bracket -= 1

    if in_string:
        return None

    suffix = ']' * depth_bracket + '}' * depth_brace
    if not suffix:
        return None
    completed = truncated + suffix
    try:
        _json.loads(completed)
        return completed
    except _json.JSONDecodeError:
        return None


def robust_json_parse(
    json_text: str,
    fallback_extractor: Optional[Callable[[str], Optional[list]]] = None,
) -> tuple:
    """容错 JSON 解析：处理 AI 常见的 JSON 格式错误。

    Args:
        json_text: 待解析的 JSON 文本（可能被截断或格式错误）
        fallback_extractor: 可选的回退提取器，用于最后一步尝试按括号
            计数提取特定结构（如 ai_expand 的 schemes 数组）。
            不提供时跳过第 4 步。

    Returns:
        (dict | None, error_msg | None): 成功时返回 (parsed_dict, None)，
        失败时返回 (None, error_reason)。
    """
    # 1. 标准解析
    try:
        return _json.loads(json_text), None
    except _json.JSONDecodeError:
        pass

    # 2. 截断到最后一个完整结构
    trunc_bounds = [json_text.rfind("}"), json_text.rfind("]")]
    last_pos = max(trunc_bounds)
    if last_pos >= 0:
        completed = _try_complete_json(json_text, last_pos)
        if completed:
            try:
                return _json.loads(completed), None
            except _json.JSONDecodeError:
                pass

        all_positions = sorted(
            [i for i, ch in enumerate(json_text) if ch in ('}', ']')],
            reverse=True,
        )
        for pos in all_positions[:20]:
            if pos == last_pos:
                continue
            completed = _try_complete_json(json_text, pos)
            if completed:
                try:
                    return _json.loads(completed), None
                except _json.JSONDecodeError:
                    pass

    # 3. 逐字符回退（最多回退 2000 字符）
    for i in range(len(json_text) - 1, max(0, len(json_text) - 2000), -1):
        if json_text[i] in ('"', '}', ']', '\n'):
            try:
                return _json.loads(json_text[:i + 1]), None
            except _json.JSONDecodeError:
                continue

    # 4. 回退提取器（如 ai_expand 的 schemes 数组提取）
    if fallback_extractor is not None:
        result = fallback_extractor(json_text)
        if result is not None:
            return {"schemes": result}, None

    return None, "无法解析 AI 返回的 JSON 格式"
