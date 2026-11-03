# translate Livekit's span records into our framework-neautral names

NAME_MAP = {
    "agent_session": "call",
    "agent_turn": "turn",
    "llm_request": "llm",
    "tts_request": "tts",
    "function_tool": "tool"
}

#LiveKit attribute -> our attribute
ATTR_MAP = {
    "lk.room_name": "call.room",
    "lk.user_input": "turn.user_text",
    "lk.response.text": "turn.agent_text",
    "lk.interrupted": "turn.interrupted",
    "lk.e2e_latency": "turn.e2e_latency",
    "gen_ai.request.model": "llm.model",
    "gen_ai.usage.input_tokens": "llm.input_tokens",
    "gen_ai.usage.output_tokens": "llm.output_tokens",
    "lk.input_text": "tts.text",
    "lk.user_transcript": "user.transcript",
    "lk.transcript_confidence": "user.confidence",
    "lk.function_tool.name": "tool.name",
    "lk.function_tool.arguments": "tool.arguments",
    "lk.function_tool.output": "tool.output",
    "lk.function_tool.is_error": "tool.is_error",
}

DROP_ATTRS = {"lk.chat_ctx"}

def normalize(span: dict) -> dict:
    span["name"] = NAME_MAP.get(span["name"], span["name"])
    new_attrs = {}
    for key, value in span["attributes"].items():
        if key in DROP_ATTRS:
            continue
        new_attrs[ATTR_MAP.get(key, key)] = value
    span["attributes"] = new_attrs
    return span

