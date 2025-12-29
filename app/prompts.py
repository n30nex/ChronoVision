PROMPT_VERSION = "1.0.0"


def groq_description_messages(timestamp_local: str) -> list[dict]:
    system = (
        "You are a concise vision assistant. "
        "Describe the snapshot in 2-3 sentences. "
        "Focus on notable objects, people, and actions."
    )
    user = f"Snapshot time: {timestamp_local}. Describe this image."
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def groq_tag_messages(description_text: str) -> list[dict]:
    system = (
        "You extract tags from snapshot descriptions. "
        "Return JSON only with keys: people, vehicles, objects. "
        "Each value is an array of lowercase short phrases. "
        "No extra text."
    )
    user = f"Description: {description_text}"
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def gemini_compare_prompt(timestamp_a: str, timestamp_b: str, label: str) -> tuple[str, str]:
    system = (
        "Compare the two images. Max 200 chars. 1-3 sentences only. "
        "Be direct and specific about changes."
    )
    user = f"{label} comparison between {timestamp_a} and {timestamp_b}. What changed?"
    return system, user


def gemini_daily_prompt(date_label: str, tags_summary: str) -> tuple[str, str]:
    system = (
        "Summarize the last 24 hours of hourly comparisons. "
        "Return JSON only with keys: summary, highlights. "
        "Summary: 2-4 sentences, max 500 chars. "
        "Highlights: array of top 3 changes, short phrases. "
        "No extra text."
    )
    user = (
        f"Daily report for {date_label}.\n"
        f"Tag summary: {tags_summary}\n"
        "Summarize key changes and pick top 3 highlights."
    )
    return system, user


def gemini_ask_prompt(query: str, window_label: str, tags_summary: str, context: str) -> tuple[str, str]:
    system = (
        "You answer questions about recent camera snapshots using only the provided context. "
        "If the answer is not in the context, say you do not have enough information. "
        "Keep the response concise, 1-3 sentences."
    )
    user = (
        f"Question: {query}\n"
        f"Window: {window_label}\n"
        f"Tag summary: {tags_summary}\n"
        "Context:\n"
        f"{context}"
    )
    return system, user
