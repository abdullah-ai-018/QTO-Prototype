"""
TypeSafe Jev AI classifier for drywall wall types.
Queries the TypeSafe Jev LLM using structured Noul criteria with >=0.85 threshold,
JSON caching in drywall_registry.json, and automatic fallback to MockClassifier.
"""

from __future__ import annotations
import json
import os
from typing import Any, Dict, List
from dotenv import load_dotenv

from qto.classify.mock import evaluate_with_mock

PROBABILITY_THRESHOLD = 0.85
REVIEW_THRESHOLD = 0.50
DEFAULT_CACHE_FILE = "drywall_registry.json"


def load_environment_credentials(env_path: str | None = None) -> str | None:
    """
    Robustly loads environment credentials from 'env' or '.env' files.
    Returns the Jev API key or None if not located.
    """
    if env_path and os.path.exists(env_path):
        load_dotenv(env_path)
    elif os.path.exists("env"):
        load_dotenv("env")
    elif os.path.exists(".env"):
        load_dotenv(".env")
    else:
        load_dotenv()

    api_key = os.getenv("Jev_Key") or os.getenv("JEV_KEY")
    return api_key


def evaluate_with_jev(
    wall_tag: str,
    materials: str,
    api_key: str | None = None,
    client: Any | None = None,
    timeout_sec: float = 10.0,
) -> float:
    """
    Queries the Jev LLM for the probability that a wall tag represents a drywall assembly.
    Falls back gracefully to MockClassifier if API key is missing or network call fails.
    """
    if not api_key:
        api_key = load_environment_credentials()

    if not api_key:
        # Fallback to mock classifier
        return evaluate_with_mock(wall_tag, materials)

    try:
        from typesafe_sdk import Noul, NoulCriteria, TypeSafeClient

        state = {
            "wall_tag": wall_tag,
            "materials": materials,
            "context": "GWB = Gypsum Wall Board (Drywall). GYP. BD. = Gypsum Board (Drywall). GL = Glass. PW = Privacy Wall.",
        }

        questions = {
            "is_drywall": Noul(
                instructions=(
                    f"Read the materials for wall tag `{wall_tag}`. Is this a drywall partition "
                    f"(constructed using Gypsum Wall Board / GWB / Gypsum Board)?"
                ),
                criteria=NoulCriteria(
                    true="Specifies Gypsum Wall Board (GWB), Gypsum Board, or drywall on metal studs, C-H studs, or furring.",
                    false="Specifies glass officefront system (GL1/GL2), demountable furniture privacy wall (PW), or masonry without gypsum.",
                ),
            )
        }

        if client is not None:
            response = client.system_one(state=state, questions=questions)
            prob = round(float(response.answers["is_drywall"].noul), 4)
            return prob

        with TypeSafeClient(api_key=api_key, model="jev-latest") as cl:
            response = cl.system_one(state=state, questions=questions)
            prob = round(float(response.answers["is_drywall"].noul), 4)
            return prob

    except Exception as e:
        # Log notice and fall back to deterministic mock evaluation
        print(f"[JEV NOTICE] Jev query unavailable or timed out ({e}). Using deterministic mock.")
        return evaluate_with_mock(wall_tag, materials)


def get_wall_registry(
    tags: List[str],
    materials_map: Dict[str, str],
    cache_file: str = DEFAULT_CACHE_FILE,
    force_refresh: bool = False,
    api_key: str | None = None,
) -> Dict[str, Dict[str, Any]]:
    """
    Builds the drywall classification registry for discovered tags.
    Loads from cache if available; otherwise queries Jev (or mock fallback) and persists cache.
    """
    registry: Dict[str, Dict[str, Any]] = {}

    # Load from cache if valid and requested
    if os.path.exists(cache_file) and not force_refresh:
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                cached = json.load(f)
            # Check if all tags are present in cache
            if all(t in cached for t in tags):
                return {t: cached[t] for t in tags if t in cached}
            # Otherwise use cached entries where available
            registry.update(cached)
        except Exception:
            registry = {}

    if not api_key:
        api_key = load_environment_credentials()

    client = None
    if api_key:
        try:
            from typesafe_sdk import TypeSafeClient
            client = TypeSafeClient(api_key=api_key, model="jev-latest")
        except Exception:
            client = None

    try:
        for tag in tags:
            if tag in registry and not force_refresh:
                continue

            materials = materials_map.get(tag, "")
            prob = evaluate_with_jev(tag, materials, api_key=api_key, client=client)

            if prob >= PROBABILITY_THRESHOLD:
                decision = "DRYWALL"
            elif prob >= REVIEW_THRESHOLD:
                decision = "CLASS_REVIEW"
            else:
                decision = "NOT_DRYWALL"

            registry[tag] = {
                "wall_tag": tag,
                "probability": prob,
                "is_drywall": prob >= PROBABILITY_THRESHOLD,
                "decision": decision,
                "materials": materials,
                "materials_excerpt": materials[:160] + ("..." if len(materials) > 160 else ""),
            }

        # Save registry to cache
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(registry, f, indent=2)
        except Exception as e:
            print(f"[CACHE WARNING] Could not write cache to '{cache_file}': {e}")

    finally:
        if client is not None and hasattr(client, "close"):
            try:
                client.close()
            except Exception:
                pass

    return {t: registry[t] for t in tags if t in registry}
