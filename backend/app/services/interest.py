"""Bounded automatic interest scan.

Hard limits (from the plan): search ≤60 recent native Workspace files from the
last 90 days; sample ≤18 (≤8 Docs, ≤5 Sheets, ≤5 Slides); ≤4,000 normalized
chars per source; ≤32,000 chars total. Excerpts live in process memory only —
we persist fingerprints, short derived labels, and the editable profile.
"""
import json
import logging

from .. import db, events, jobs, llm, openrouter, telemetry
from ..errors import ApiError
from ..util import now_iso, sha256_hex

logger = logging.getLogger("compass.interest")

MAX_FILES_SEARCHED = 60
MAX_SAMPLED = 18
MAX_DOCS, MAX_SHEETS, MAX_SLIDES = 8, 5, 5
PER_SOURCE_CHARS = 4000
TOTAL_CHARS = 32000


async def start_interest_scan(profile: dict) -> dict:
    if not profile.get("scan_consented"):
        raise ApiError(409, "scan_not_consented",
                       "Please review the disclosure and consent before scanning.")
    return await jobs.enqueue("interest_scan", profile["id"], {})


async def get_interest_profile(profile_id: str) -> dict | None:
    cur = await db.get().execute("SELECT * FROM interest_profiles WHERE profile_id = ?", (profile_id,))
    row = await cur.fetchone()
    if row is None:
        return None
    return {
        "topics": json.loads(row["topics_json"]),
        "palette": row["palette"], "motif": row["motif"],
        "accessories": json.loads(row["accessories_json"]),
        "props": json.loads(row["props_json"]),
        "personality_presets": json.loads(row["personality_presets_json"]),
        "name_suggestions": json.loads(row["name_suggestions_json"]),
        "tone": row["tone"], "confidence": row["confidence"], "explanation": row["explanation"],
        "model_id": row["model_id"], "version": row["version"], "updated_at": row["updated_at"],
    }


async def patch_interest_profile(profile_id: str, patch: dict) -> dict:
    existing = await get_interest_profile(profile_id)
    if existing is None:
        raise ApiError(404, "not_found", "No interest profile yet — run a scan first.")
    fields: dict = {}
    if "topics" in patch and isinstance(patch["topics"], list):
        topics = [{"label": str(t.get("label", ""))[:60],
                   "confidence": float(t.get("confidence", 0.5))}
                  for t in patch["topics"] if isinstance(t, dict) and t.get("label")][:5]
        fields["topics_json"] = json.dumps(topics)
    if patch.get("palette") in llm.ALLOWED_PALETTES:
        fields["palette"] = patch["palette"]
    if patch.get("motif") in llm.ALLOWED_MOTIFS:
        fields["motif"] = patch["motif"]
    if patch.get("tone") in llm.ALLOWED_TONES:
        fields["tone"] = patch["tone"]
    if "accessories" in patch and isinstance(patch["accessories"], list):
        fields["accessories_json"] = json.dumps(
            [a for a in patch["accessories"] if a in llm.ALLOWED_ACCESSORIES][:3])
    if "props" in patch and isinstance(patch["props"], list):
        fields["props_json"] = json.dumps([p for p in patch["props"] if p in llm.ALLOWED_PROPS][:3])
    if fields:
        cols = ", ".join(f"{k} = ?" for k in fields)
        await db.get().execute(
            f"UPDATE interest_profiles SET {cols}, version = version + 1, updated_at = ? WHERE profile_id = ?",
            (*fields.values(), now_iso(), profile_id))
        await db.get().commit()
    return await get_interest_profile(profile_id)


def _fingerprint(files: list[dict]) -> str:
    material = "|".join(f"{f.get('id')}:{f.get('modified_time')}" for f in files)
    return sha256_hex(material)


async def _store_profile(profile_id: str, draft: llm.InterestProfileDraft, model_id: str | None,
                         fingerprint: str) -> None:
    await db.get().execute(
        """INSERT INTO interest_profiles (profile_id, topics_json, palette, motif, accessories_json,
             props_json, personality_presets_json, name_suggestions_json, tone, confidence,
             explanation, source_fingerprint, model_id, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(profile_id) DO UPDATE SET
             topics_json = excluded.topics_json, palette = excluded.palette, motif = excluded.motif,
             accessories_json = excluded.accessories_json, props_json = excluded.props_json,
             personality_presets_json = excluded.personality_presets_json,
             name_suggestions_json = excluded.name_suggestions_json, tone = excluded.tone,
             confidence = excluded.confidence, explanation = excluded.explanation,
             source_fingerprint = excluded.source_fingerprint, model_id = excluded.model_id,
             version = interest_profiles.version + 1, updated_at = excluded.updated_at""",
        (profile_id, json.dumps([t.model_dump() for t in draft.themes]), draft.palette, draft.motif,
         json.dumps(draft.accessories), json.dumps(draft.props),
         json.dumps(draft.personality_presets), json.dumps(draft.name_suggestions),
         draft.tone, draft.confidence, draft.explanation, fingerprint, model_id, now_iso()))
    await db.get().commit()


@jobs.register("interest_scan")
async def run_interest_scan(job: dict) -> dict:
    from . import profiles as profile_service
    profile = await profile_service.get_profile(job["profile_id"])
    profile_id = profile["id"]

    files, _meta = await telemetry.search_recent_workspace_files(
        profile, limit=MAX_FILES_SEARCHED, days=90)
    await jobs.set_progress(job["id"], 0.2)

    docs = [f for f in files if f.get("mime_type") == telemetry.GOOGLE_DOC][:MAX_DOCS]
    sheets = [f for f in files if f.get("mime_type") == telemetry.GOOGLE_SHEET][:MAX_SHEETS]
    slides = [f for f in files if f.get("mime_type") == telemetry.GOOGLE_SLIDE][:MAX_SLIDES]
    sampled = (docs + sheets + slides)[:MAX_SAMPLED]
    fingerprint = _fingerprint(sampled)

    # Excerpts are process-memory only.
    samples: list[dict] = []
    total = 0
    for f in sampled:
        kind = {telemetry.GOOGLE_DOC: "doc", telemetry.GOOGLE_SHEET: "sheet",
                telemetry.GOOGLE_SLIDE: "slides"}[f["mime_type"]]
        if total >= TOTAL_CHARS:
            break
        if kind == "doc":
            excerpt = await telemetry.summarize_document(profile, f)
        elif kind == "sheet":
            excerpt = await telemetry.summarize_sheet(profile, f)
        else:
            excerpt = await telemetry.summarize_presentation(profile, f)
        if not excerpt:
            continue
        excerpt = excerpt[:PER_SOURCE_CHARS][: TOTAL_CHARS - total]
        total += len(excerpt)
        samples.append({"name": f.get("name") or "untitled", "kind": kind, "excerpt": excerpt})
    await jobs.set_progress(job["id"], 0.6)

    model_id: str | None = None
    if samples:
        try:
            draft, model_id = await llm.infer_interest_profile(profile_id, samples, fingerprint)
        except (openrouter.FreeModelUnavailable, openrouter.LLMOutputInvalid):
            draft = llm.fallback_interest_profile([f.get("name") or "" for f in sampled])
    else:
        # Distinct from a free-model outage: we had no readable content at all.
        draft = llm.fallback_interest_profile([f.get("name") or "" for f in files])
        draft.explanation = (
            "Compass couldn't read any file contents — connect Google Docs (and Sheets/Slides) "
            "in Settings → Connections, then rescan. These tags come from file names only.")

    # Persist per-file fingerprints + short derived labels (never bodies).
    labels = [t.label for t in draft.themes][:3]
    for f in sampled:
        await db.get().execute(
            """INSERT INTO source_summaries (profile_id, file_id, connector, fingerprint, labels_json,
                 modified_time, updated_at)
               VALUES (?, ?, 'google_drive', ?, ?, ?, ?)
               ON CONFLICT(profile_id, file_id) DO UPDATE SET
                 fingerprint = excluded.fingerprint, labels_json = excluded.labels_json,
                 modified_time = excluded.modified_time, updated_at = excluded.updated_at""",
            (profile_id, f["id"], f"{f['id']}:{f.get('modified_time')}", json.dumps(labels),
             f.get("modified_time"), now_iso()))
    await db.get().commit()

    await _store_profile(profile_id, draft, model_id, fingerprint)
    await db.get().execute(
        "UPDATE profiles SET onboarding_step = 'companion', updated_at = ? WHERE id = ? AND onboarding_step IN ('connect','scan')",
        (now_iso(), profile_id))
    await db.get().commit()
    await events.publish("profile", profile_id, "connection.updated", profile_id,
                         {"reason": "interest_scan_complete", "sampled": len(samples),
                          "free_model": model_id})
    return {"result_type": "interest_profile", "result_id": profile_id}
