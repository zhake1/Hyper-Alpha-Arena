"""
Hyper AI Memory Service - User insights and memory management

This module provides:
1. Memory storage and retrieval
2. Mem0-style LLM-based deduplication (ADD/UPDATE/DELETE/NONE)
3. Memory categories for organized storage
4. Importance scoring for retrieval prioritization

Memory Categories:
- preference: User trading preferences and style
- decision: Important trading decisions made
- lesson: Lessons learned from trades
- insight: Market insights and observations
- context: General context about user's situation

Architecture:
- Memory is extracted during context compression
- Deduplication prevents redundant entries
- Retrieval is via tools, not automatic injection
"""
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests
from sqlalchemy.orm import Session

from database.models import HyperAiMemory

logger = logging.getLogger(__name__)

# Memory categories
MEMORY_CATEGORIES = [
    "preference",  # Trading preferences
    "decision",    # Important decisions
    "lesson",      # Lessons learned
    "insight",     # Market insights
    "context",     # General context
]


def get_memories(
    db: Session,
    category: Optional[str] = None,
    limit: int = 20,
    active_only: bool = True
) -> List[Dict[str, Any]]:
    """
    Retrieve memories, optionally filtered by category.

    Args:
        db: Database session
        category: Filter by category (None for all)
        limit: Maximum number of memories to return
        active_only: Only return active memories

    Returns:
        List of memory dictionaries
    """
    query = db.query(HyperAiMemory)

    if active_only:
        query = query.filter(HyperAiMemory.is_active == True)

    if category:
        query = query.filter(HyperAiMemory.category == category)

    # Order by importance and recency
    memories = query.order_by(
        HyperAiMemory.importance.desc(),
        HyperAiMemory.created_at.desc()
    ).limit(limit).all()

    return [
        {
            "id": m.id,
            "category": m.category,
            "content": m.content,
            "source": m.source,
            "importance": m.importance,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in memories
    ]


def add_memory(
    db: Session,
    category: str,
    content: str,
    source: str = "conversation",
    importance: float = 0.5
) -> HyperAiMemory:
    """
    Add a new memory entry.

    Args:
        db: Database session
        category: Memory category
        content: Memory content
        source: Source of the memory (conversation, compression, manual)
        importance: Importance score (0.0 to 1.0)

    Returns:
        Created memory object
    """
    memory = HyperAiMemory(
        category=category,
        content=content,
        source=source,
        importance=importance,
        is_active=True
    )
    db.add(memory)
    db.commit()
    db.refresh(memory)
    return memory


def update_memory(
    db: Session,
    memory_id: int,
    content: Optional[str] = None,
    importance: Optional[float] = None,
    is_active: Optional[bool] = None
) -> Optional[HyperAiMemory]:
    """Update an existing memory."""
    memory = db.query(HyperAiMemory).filter(HyperAiMemory.id == memory_id).first()
    if not memory:
        return None

    if content is not None:
        memory.content = content
    if importance is not None:
        memory.importance = importance
    if is_active is not None:
        memory.is_active = is_active

    memory.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(memory)
    return memory


def delete_memory(db: Session, memory_id: int) -> bool:
    """Soft delete a memory by marking it inactive."""
    memory = db.query(HyperAiMemory).filter(HyperAiMemory.id == memory_id).first()
    if not memory:
        return False

    memory.is_active = False
    memory.updated_at = datetime.utcnow()
    db.commit()
    return True


# Mem0-style deduplication prompt
DEDUP_PROMPT = """You are a memory deduplication assistant. Given an existing memory and a new memory, decide what action to take.

Existing memory:
Category: {existing_category}
Content: {existing_content}

New memory:
Category: {new_category}
Content: {new_content}

Decide ONE action:
- ADD: New memory is different and valuable, keep both
- UPDATE: New memory is an update/refinement of existing, merge them
- DELETE: Existing memory is outdated/contradicted by new, remove existing
- NONE: New memory is redundant/duplicate, discard it

Respond with ONLY the action word (ADD, UPDATE, DELETE, or NONE) and a brief merged content if UPDATE.

Format:
ACTION: <action>
MERGED: <merged content if UPDATE, otherwise empty>"""


def check_deduplication(
    existing: Dict[str, Any],
    new_content: str,
    new_category: str,
    api_config: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Use LLM to decide deduplication action (Mem0-style).

    Returns:
        {"action": "ADD|UPDATE|DELETE|NONE", "merged": "..."}
    """
    prompt = DEDUP_PROMPT.format(
        existing_category=existing.get("category", ""),
        existing_content=existing.get("content", ""),
        new_category=new_category,
        new_content=new_content
    )

    base_url = api_config.get("base_url", "")
    api_key = api_config.get("api_key", "")
    model = api_config.get("model", "")
    api_format = api_config.get("api_format", "openai")

    if not all([base_url, api_key, model]):
        return {"action": "ADD", "merged": ""}

    try:
        from services.ai_decision_service import build_chat_completion_endpoints, build_llm_payload, build_llm_headers

        if api_format == "anthropic":
            endpoint = f"{base_url.rstrip('/')}/messages"
        else:
            endpoints = build_chat_completion_endpoints(base_url, model)
            endpoint = endpoints[0] if endpoints else f"{base_url}/chat/completions"

        # Use unified headers/payload builders (see build_llm_payload in ai_decision_service)
        headers = build_llm_headers(api_format, api_key)
        body = build_llm_payload(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            api_format=api_format,
            max_tokens=200,
            temperature=None,
        )

        response = requests.post(endpoint, headers=headers, json=body, timeout=30)

        if response.status_code != 200:
            return {"action": "ADD", "merged": ""}

        data = response.json()

        # Extract response
        if api_format == "anthropic":
            content = data.get("content", [])
            text = content[0].get("text", "") if content else ""
        else:
            choices = data.get("choices", [])
            text = choices[0].get("message", {}).get("content", "") if choices else ""

        # Parse response
        action = "ADD"
        merged = ""

        for line in text.strip().split("\n"):
            if line.startswith("ACTION:"):
                action_str = line.replace("ACTION:", "").strip().upper()
                if action_str in ["ADD", "UPDATE", "DELETE", "NONE"]:
                    action = action_str
            elif line.startswith("MERGED:"):
                merged = line.replace("MERGED:", "").strip()

        return {"action": action, "merged": merged}

    except Exception as e:
        logger.error(f"Deduplication check failed: {e}")
        return {"action": "ADD", "merged": ""}


def add_memory_with_dedup(
    db: Session,
    category: str,
    content: str,
    api_config: Dict[str, Any],
    source: str = "conversation",
    importance: float = 0.5
) -> Optional[HyperAiMemory]:
    """
    Add memory with Mem0-style deduplication.

    Checks existing memories in the same category and decides:
    - ADD: Create new memory
    - UPDATE: Merge with existing memory
    - DELETE: Remove outdated existing memory, add new
    - NONE: Discard new memory (duplicate)

    Returns:
        Created/updated memory or None if discarded
    """
    # Get existing memories in same category
    existing_memories = get_memories(db, category=category, limit=10)

    if not existing_memories:
        # No existing memories, just add
        return add_memory(db, category, content, source, importance)

    # Check against each existing memory
    for existing in existing_memories:
        result = check_deduplication(existing, content, category, api_config)
        action = result.get("action", "ADD")

        if action == "NONE":
            # Duplicate, discard new memory
            logger.info(f"Memory discarded as duplicate of #{existing['id']}")
            return None

        elif action == "UPDATE":
            # Merge with existing
            merged_content = result.get("merged") or content
            updated = update_memory(
                db, existing["id"],
                content=merged_content,
                importance=max(importance, existing.get("importance", 0.5))
            )
            logger.info(f"Memory #{existing['id']} updated with merged content")
            return updated

        elif action == "DELETE":
            # Delete existing, will add new below
            delete_memory(db, existing["id"])
            logger.info(f"Memory #{existing['id']} deleted, replaced by new")
            break

    # ADD action or after DELETE
    return add_memory(db, category, content, source, importance)


# Memory extraction prompt for compression
EXTRACT_MEMORIES_PROMPT = """Analyze this conversation and extract important user insights to remember.

Conversation:
{conversation}

Extract memories in these categories:
- preference: User's trading preferences and style
- decision: Important trading decisions made
- lesson: Lessons learned from trades
- insight: Market insights and observations

For each memory, provide:
- category: One of the above categories
- content: The insight to remember (1-2 sentences)
- importance: Score from 0.0 to 1.0

Respond in JSON format:
{{"memories": [
  {{"category": "preference", "content": "...", "importance": 0.8}},
  ...
]}}

Only extract truly important insights. If nothing significant, return empty list."""


def extract_memories_from_conversation(
    conversation_text: str,
    api_config: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """
    Extract memories from conversation using LLM.

    Returns:
        List of {"category", "content", "importance"} dicts
    """
    prompt = EXTRACT_MEMORIES_PROMPT.format(
        conversation=conversation_text[:6000]
    )

    base_url = api_config.get("base_url", "")
    api_key = api_config.get("api_key", "")
    model = api_config.get("model", "")
    api_format = api_config.get("api_format", "openai")

    if not all([base_url, api_key, model]):
        return []

    try:
        from services.ai_decision_service import build_chat_completion_endpoints, build_llm_payload, build_llm_headers

        if api_format == "anthropic":
            endpoint = f"{base_url.rstrip('/')}/messages"
        else:
            endpoints = build_chat_completion_endpoints(base_url, model)
            endpoint = endpoints[0] if endpoints else f"{base_url}/chat/completions"

        # Use unified headers/payload builders (see build_llm_payload in ai_decision_service)
        headers = build_llm_headers(api_format, api_key)
        body = build_llm_payload(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            api_format=api_format,
            max_tokens=500,
            temperature=None,
        )

        response = requests.post(endpoint, headers=headers, json=body, timeout=60)

        if response.status_code != 200:
            return []

        data = response.json()

        # Extract response text
        if api_format == "anthropic":
            content = data.get("content", [])
            text = content[0].get("text", "") if content else ""
        else:
            choices = data.get("choices", [])
            text = choices[0].get("message", {}).get("content", "") if choices else ""

        # Parse JSON response
        import re
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
            return result.get("memories", [])

    except Exception as e:
        logger.error(f"Memory extraction failed: {e}")

    return []


def process_compression_memories(
    db: Session,
    conversation_text: str,
    api_config: Dict[str, Any]
) -> int:
    """
    Extract and store memories during context compression.

    Returns:
        Number of memories added/updated
    """
    # DEBUG: Log when compression memory extraction is triggered
    print(f"[DEBUG] process_compression_memories TRIGGERED", flush=True)
    print(f"[DEBUG] conversation_text length: {len(conversation_text)}", flush=True)
    print(f"[DEBUG] api_config model: {api_config.get('model', 'unknown')}", flush=True)

    memories = extract_memories_from_conversation(conversation_text, api_config)

    # DEBUG: Log extracted memories
    print(f"[DEBUG] Extracted {len(memories)} memories from LLM", flush=True)
    for i, mem in enumerate(memories):
        print(f"[DEBUG] Memory {i}: category={mem.get('category')}, content={mem.get('content', '')[:100]}...", flush=True)

    count = 0

    for mem in memories:
        category = mem.get("category", "context")
        content = mem.get("content", "")
        importance = mem.get("importance", 0.5)

        if not content or category not in MEMORY_CATEGORIES:
            print(f"[DEBUG] Skipping memory: category={category}, content_empty={not content}", flush=True)
            continue

        result = add_memory_with_dedup(
            db, category, content, api_config,
            source="compression",
            importance=importance
        )
        if result:
            count += 1
            print(f"[DEBUG] Memory saved: id={result.get('id')}, action={result.get('action')}", flush=True)
        else:
            print(f"[DEBUG] Memory not saved (dedup or error)", flush=True)

    print(f"[DEBUG] process_compression_memories COMPLETED: {count} memories saved", flush=True)
    logger.info(f"Processed {count} memories from compression")
    return count
