-- Remove head-to-head battles, party boss encounters and the leaderboard they fed.
--
-- Why: competitive ranking is evidence-negative for the students Compass is for
-- (leaderboards motivate the top and demotivate everyone else, and they reduce
-- peer social engagement regardless of how competitive the student is), and both
-- features needed a live second player Compass has no user base to supply.
-- What survives is the mechanism with real support behind it: co-presence.
-- Parties become focus rooms — a shared timer and who else is working, never a
-- goal, a filename or a piece of evidence.
--
-- focus_sessions.battle_id is dropped: no writer sets it any more.

DROP INDEX IF EXISTS idx_boss_party;

DROP TABLE IF EXISTS boss_contributions;
DROP TABLE IF EXISTS boss_encounters;
DROP TABLE IF EXISTS battle_players;
DROP TABLE IF EXISTS battles;

ALTER TABLE focus_sessions DROP COLUMN battle_id;
