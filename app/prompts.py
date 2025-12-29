PROMPT_VERSION = "1.0.0"


def groq_description_messages(timestamp_local: str) -> list[dict]:
    system = (
        "You are a concise vision assistant. "
        "Describe only what is visible; no speculation. "
        "Use 2-3 sentences. "
        "Sentence 1: scene overview. "
        "Sentence 2: notable objects/people/actions. "
        "Sentence 3 (optional): lighting/weather/context. "
        "Avoid hedging words like 'seems' or 'appears'; if unclear, say 'unclear'. "
        "Use simple location cues (left/right/foreground/background) when helpful. "
        "Do not mention unseen devices or inferred items."
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
        "Each value is a lowercase array of short singular phrases. "
        "Deduplicate. Max 8 items per list. "
        "Avoid relational phrases like 'on right'. "
        "Do not repeat the same item across lists. "
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
        "Be direct and specific about changes. "
        "If no meaningful change, say: No significant change detected."
    )
    user = f"{label} comparison between {timestamp_a} and {timestamp_b}. What changed?"
    return system, user


def gemini_compare_sequence_prompt(
    window_label: str,
    label: str,
    timestamps: list[str],
) -> tuple[str, str]:
    system = (
        "Compare a sequence of images captured over time. "
        "Summarize notable changes and movement across the sequence. "
        "Be direct and specific. If no meaningful change, say: No significant change detected. "
        "Max 200 chars. 1-3 sentences only."
    )
    ts_lines = "\n".join(timestamps)
    user = (
        f"{label} sequence comparison.\n"
        f"Window: {window_label}\n"
        f"Timestamps:\n{ts_lines}\n"
        "What changed across the sequence?"
    )
    return system, user


def gemini_daily_prompt(date_label: str, tags_summary: str) -> tuple[str, str]:
    system = (
        "Summarize the hourly comparisons for the specified day. "
        "Return JSON only with keys: summary, highlights. "
        "Summary: 2-4 sentences, max 500 chars. "
        "Highlights: array of top 3 changes, short phrases. "
        "Incorporate the tag summary into highlights. "
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
        "If possible, reference the most relevant snapshot time(s) from the context. "
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


def gemini_range_summary_prompt(
    window_label: str,
    tags_summary: str,
    metadata: str,
    description_context: str,
    compare_context: str,
) -> tuple[str, str]:
    system = (
        "You summarize activity across a time range using only the provided context. "
        "Describe what happened (what, who, where, when) in detail. "
        "Include any comparison findings and metadata from the range. "
        "If multiple people appear, assign consistent labels like Person 1, Child 1, "
        "and keep them consistent across the range. Do not invent names. "
        "If details are unclear, say 'unclear'. "
        "Write a detailed narrative, up to 5000 characters."
    )
    user = (
        f"Time range: {window_label}\n"
        f"Tag summary: {tags_summary}\n"
        f"Metadata: {metadata}\n"
        "Descriptions:\n"
        f"{description_context}\n"
        "Comparisons:\n"
        f"{compare_context}"
    )
    return system, user


def gemini_story_arc_prompt(
    window_label: str,
    tags_summary: str,
    metadata: str,
    compare_context: str,
) -> tuple[str, str]:
    system = (
        "You generate a timeline story arc from hourly comparison notes. "
        "Return JSON only with key: bullets. "
        "Bullets: ordered timeline entries, 5-12 items, each <= 140 chars. "
        "Focus on what changed and when. Do not invent details."
    )
    user = (
        f"Time range: {window_label}\n"
        f"Tag summary: {tags_summary}\n"
        f"Metadata: {metadata}\n"
        "Hourly comparisons:\n"
        f"{compare_context}"
    )
    return system, user
