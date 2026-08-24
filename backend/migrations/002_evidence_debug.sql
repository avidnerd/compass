-- 002: optional debug persistence of the exact content excerpt verification
-- read (user-requested; controlled by COMPASS_DEBUG_EVIDENCE).
ALTER TABLE evidence_items ADD COLUMN debug_excerpt TEXT;
