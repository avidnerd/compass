"""Canvas connector: ICS parsing, linking, and idempotent quest import.

Offline throughout — the feed is served by a stub, never fetched.
"""
import pytest

from app import ics
from app.errors import ApiError
from app.services import canvas as canvas_service
from tests.conftest import create_profile

FEED = """BEGIN:VCALENDAR\r
VERSION:2.0\r
PRODID:-//Instructure//Canvas//EN\r
BEGIN:VEVENT\r
UID:event-assignment-9931@instructure.com\r
DTSTART:20991018T235900Z\r
SUMMARY:Literature review draft [BIOL 240 Fall 2026]\r
DESCRIPTION:Three pages\\, APA style. Upload a PDF.\r
URL:https://canvas.example.edu/courses/12/assignments/9931\r
END:VEVENT\r
BEGIN:VEVENT\r
UID:event-calendar-event-55@instructure.com\r
DTSTART:20991015T140000Z\r
SUMMARY:Lecture 4 [BIOL 240 Fall 2026]\r
END:VEVENT\r
BEGIN:VEVENT\r
UID:event-assignment-9940@instructure.com\r
DTSTART;VALUE=DATE:20991102\r
SUMMARY:Problem set 3 [MATH 210]\r
END:VEVENT\r
BEGIN:VEVENT\r
UID:event-assignment-1@instructure.com\r
DTSTART:20200101T120000Z\r
SUMMARY:Long past assignment [HIST 101]\r
END:VEVENT\r
END:VCALENDAR\r
"""


# ------------------------------------------------------------------ parsing

def test_only_assignments_are_returned():
    """A feed also carries lectures; those are not work the student owes."""
    items = ics.assignments(FEED)
    uids = [a["uid"] for a in items]
    assert all("assignment" in u for u in uids)
    assert not any("calendar-event" in u for u in uids)


def test_course_is_split_out_of_the_summary():
    item = next(a for a in ics.assignments(FEED) if "9931" in a["uid"])
    assert item["title"] == "Literature review draft"
    assert item["course"] == "BIOL 240 Fall 2026"


def test_escaped_text_and_all_day_dates():
    items = {a["uid"]: a for a in ics.assignments(FEED)}
    assert items["event-assignment-9931@instructure.com"]["description"].startswith(
        "Three pages, APA style")
    all_day = items["event-assignment-9940@instructure.com"]
    assert all_day["all_day"] is True
    assert all_day["due_at"].startswith("2099-11-02")


def test_folded_lines_are_unfolded_per_rfc5545():
    folded = ("BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nUID:event-assignment-7@x\r\n"
              "DTSTART:20991201T120000Z\r\nSUMMARY:A very long assignment ti\r\n tle\r\n"
              "END:VEVENT\r\nEND:VCALENDAR\r\n")
    assert ics.assignments(folded)[0]["title"] == "A very long assignment title"


def test_upcoming_drops_past_deadlines():
    items = ics.assignments(FEED)
    ahead = ics.upcoming(items, days=365 * 100)
    assert not any("Long past" in a["title"] for a in ahead)
    assert any("Literature review" in a["title"] for a in ahead)


def test_a_feed_with_no_events_is_not_an_error():
    assert ics.assignments("BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n") == []


# ------------------------------------------------------------------- urls

def test_webcal_and_http_are_normalised_to_https():
    assert canvas_service.normalise_url(
        "webcal://canvas.example.edu/feeds/u.ics").startswith("https://")
    assert canvas_service.normalise_url(
        "http://canvas.example.edu/feeds/u.ics").startswith("https://")


def test_a_non_url_is_refused_with_instructions():
    with pytest.raises(ApiError) as exc:
        canvas_service.normalise_url("my canvas calendar")
    assert "Calendar Feed" in str(exc.value)


def test_the_feed_url_is_masked_because_it_is_a_bearer_secret():
    masked = canvas_service.mask("https://canvas.example.edu/feeds/users/SECRETTOKEN.ics")
    assert "SECRETTOKEN" not in masked
    assert "canvas.example.edu" in masked


# ------------------------------------------------------- link and import

@pytest.fixture
def feed(monkeypatch):
    calls = {"n": 0}

    async def fake_fetch(url: str) -> str:
        calls["n"] += 1
        return FEED
    monkeypatch.setattr(canvas_service, "fetch", fake_fetch)
    return calls


async def test_link_stores_the_feed_and_reports_what_it_found(env, feed):
    profile = await create_profile(env.client, "Student")
    pid = profile["profile"]["id"]
    result = await canvas_service.link(pid, "https://canvas.example.edu/feeds/u.ics")
    assert result["linked"] is True
    assert result["assignment_count"] == 3
    assert "u.ics" not in result["feed"]

    status = await canvas_service.public_link(pid)
    assert status["status"] == "linked"
    # The connector must never imply it can verify anything.
    assert status["evidence"] is False


async def test_assignments_require_a_linked_feed(env):
    profile = await create_profile(env.client, "Student")
    with pytest.raises(ApiError) as exc:
        await canvas_service.assignments({"id": profile["profile"]["id"]})
    assert exc.value.code == "canvas_not_linked"


async def test_importing_twice_does_not_create_two_quests(env, feed):
    profile = await create_profile(env.client, "Student")
    pid = profile["profile"]["id"]
    await canvas_service.link(pid, "https://canvas.example.edu/feeds/u.ics")

    uid = "event-assignment-9940@instructure.com"
    first = await canvas_service.import_assignments({"id": pid}, [uid], plan=False)
    assert len(first["created"]) == 1

    second = await canvas_service.import_assignments({"id": pid}, [uid], plan=False)
    assert second["created"] == []
    assert second["skipped"][0]["quest_id"] == first["created"][0]["quest_id"]


async def test_an_unknown_assignment_is_reported_not_invented(env, feed):
    profile = await create_profile(env.client, "Student")
    pid = profile["profile"]["id"]
    await canvas_service.link(pid, "https://canvas.example.edu/feeds/u.ics")
    result = await canvas_service.import_assignments({"id": pid}, ["event-assignment-nope@x"],
                                                    plan=False)
    assert result["created"] == []
    assert result["unknown"] == ["event-assignment-nope@x"]


async def test_quest_seed_carries_the_due_date_and_never_claims_evidence():
    seed = canvas_service.quest_seed({
        "uid": "event-assignment-1@x", "title": "Essay", "course": "ENG 101",
        "due_at": "2099-10-01T23:59:00+00:00", "description": None,
    })
    assert seed["target_date"] == "2099-10-01"
    assert "ENG 101" in seed["goal"]
    assert "evidence_specs" not in seed


def test_http_is_upgraded_for_remote_hosts_but_kept_on_loopback():
    """The feed URL is a bearer secret; loopback cannot leak it off the machine."""
    assert canvas_service.normalise_url(
        "http://canvas.example.edu/f.ics").startswith("https://")
    assert canvas_service.normalise_url(
        "http://127.0.0.1:8899/feed.ics").startswith("http://127.0.0.1")


# ------------------------------------------------- feeds beyond Canvas
# Canvas only carries deadlines an instructor put in Canvas. A course graded
# through Gradescope, Pearson or LabFlow can have deadlines that never reach it,
# so any tool publishing iCalendar can be added alongside.

OTHER_FEED = """BEGIN:VCALENDAR\r
VERSION:2.0\r
BEGIN:VEVENT\r
UID:gradescope-ps4@example\r
DTSTART:20991020T235900Z\r
SUMMARY:Problem Set 4\r
END:VEVENT\r
BEGIN:VEVENT\r
UID:gradescope-lab2@example\r
DTSTART:20991025T235900Z\r
SUMMARY:Lab 2 writeup\r
END:VEVENT\r
END:VCALENDAR\r
"""


def test_a_non_canvas_feed_keeps_every_dated_event():
    """Only Canvas uses the assignment-UID convention; other feeds have no such
    marker, and a student who adds one has already chosen what it holds."""
    assert ics.assignments(OTHER_FEED, canvas_only=True) == []
    assert len(ics.assignments(OTHER_FEED, canvas_only=False)) == 2


async def test_a_second_feed_adds_its_deadlines(env, monkeypatch):
    profile = await create_profile(env.client, "Student")
    pid = profile["profile"]["id"]

    async def fake_fetch(url: str) -> str:
        return OTHER_FEED if "gradescope" in url else FEED
    monkeypatch.setattr(canvas_service, "fetch", fake_fetch)

    await canvas_service.link(pid, "https://canvas.example.edu/f.ics")
    await canvas_service.link(pid, "https://cal.example.com/gradescope.ics",
                              label="Gradescope", kind="generic")

    stored = await canvas_service.feeds(pid)
    assert [f["kind"] for f in stored] == ["canvas", "generic"]

    items, _ = await canvas_service._all_assignments(pid)
    titles = {a["title"] for a in items}
    assert "Literature review draft" in titles   # Canvas
    assert "Problem Set 4" in titles             # the other tool
    assert {a["feed_label"] for a in items} == {"Canvas", "Gradescope"}


async def test_one_dead_feed_does_not_blank_out_the_others(env, monkeypatch):
    profile = await create_profile(env.client, "Student")
    pid = profile["profile"]["id"]

    async def fake_fetch(url: str) -> str:
        if "broken" in url:
            raise canvas_service.CanvasError("canvas_not_found", "gone")
        return FEED
    monkeypatch.setattr(canvas_service, "fetch", fake_fetch)

    await canvas_service.link(pid, "https://canvas.example.edu/f.ics")
    await canvas_service._save_feeds(pid, (await canvas_service.feeds(pid)) + [
        {"id": "x", "url": "https://broken.example.com/f.ics", "label": "Dead", "kind": "generic"}])

    items, meta = await canvas_service._all_assignments(pid, force=True)
    assert items, "a dead feed must not blank out a working one"
    assert meta["feed_errors"][0]["code"] == "canvas_not_found"


async def test_the_same_deadline_through_two_feeds_counts_once(env, monkeypatch):
    profile = await create_profile(env.client, "Student")
    pid = profile["profile"]["id"]

    async def _same(url: str) -> str:
        return FEED
    monkeypatch.setattr(canvas_service, "fetch", _same)

    await canvas_service.link(pid, "https://canvas.example.edu/a.ics")
    await canvas_service.link(pid, "https://canvas.example.edu/b.ics", label="Copy")
    items, _ = await canvas_service._all_assignments(pid, force=True)
    assert len(items) == len({a["uid"] for a in items})


async def test_removing_one_feed_keeps_the_rest(env, monkeypatch):
    profile = await create_profile(env.client, "Student")
    pid = profile["profile"]["id"]

    async def fake_fetch(url: str) -> str:
        return OTHER_FEED if "other" in url else FEED
    monkeypatch.setattr(canvas_service, "fetch", fake_fetch)

    await canvas_service.link(pid, "https://canvas.example.edu/f.ics")
    await canvas_service.link(pid, "https://other.example.com/f.ics", kind="generic")
    other = next(f for f in await canvas_service.feeds(pid) if f["kind"] == "generic")

    result = await canvas_service.unlink_feed(pid, other["id"])
    assert result["feed_count"] == 1
    assert [f["kind"] for f in await canvas_service.feeds(pid)] == ["canvas"]


async def test_a_credential_written_before_multi_feed_still_reads(env):
    """Older profiles stored a single feed_url; that must keep working."""
    from app import providers as provider_service
    profile = await create_profile(env.client, "Student")
    pid = profile["profile"]["id"]
    await provider_service.save_credentials(
        pid, "canvas", {"feed_url": "https://canvas.example.edu/legacy.ics"})
    stored = await canvas_service.feeds(pid)
    assert len(stored) == 1 and stored[0]["kind"] == "canvas"
