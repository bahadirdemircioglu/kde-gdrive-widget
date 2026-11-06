#!/usr/bin/env python3
"""Writes tests/fixtures/show-<state>.json: sample `gdrive-status show` outputs for every
state, with times relative to now. For screenshots and manual testing, e.g. point the widget's
status command at:  sh -c 'cat /path/to/tests/fixtures/show-error.json' #"""
import datetime
import json
import pathlib

OUT = pathlib.Path(__file__).resolve().parents[1] / "tests/fixtures"
now = datetime.datetime.now().astimezone()


def ago(**kw):
    return (now - datetime.timedelta(**kw)).isoformat(timespec="seconds")


recent = [
    {"kind": "up", "path": "Work/Clients/Acme/2026/offer.pdf", "at": ago(minutes=3)},
    {"kind": "down", "path": "Work/Training/certificate_list.xlsx", "at": ago(hours=1)},
    {"kind": "up", "path": "Personal/Thesis/latex/main.tex", "at": ago(hours=2)},
    {"kind": "down", "path": "Work/Accounting/Invoices/Eylül/fatura_22.pdf", "at": ago(days=1)},
    {"kind": "deleted_remote", "path": "Work/Projects/Old/draft.docx", "at": ago(days=1)},
    {"kind": "up", "path": "Projects/ai-lab/README.md", "at": ago(days=1, hours=2)},
    {"kind": "down", "path": "Phone backups/Download/Report.pdf", "at": ago(days=2)},
]
base = {
    "version": 1, "serviceActive": True, "localRoot": "/home/user/GoogleDrive",
    "logPath": "/home/user/.local/state/gdrive-sync/sync.log", "fileCount": 10287, "failCount": 0,
    "lastSuccessAt": ago(minutes=3), "lastRunAt": ago(minutes=3), "lastError": None, "recent": recent,
}
states = {
    "synced": {},
    "syncing": {
        "phase": "transferring", "progress": {"done": 12, "total": 40}, "runStartedAt": ago(minutes=2),
        "current": [
            {"kind": "up", "path": "Projects/ai-lab/stacks/docker-compose.yml", "done": True},
            {"kind": "up", "path": "Work/Projects/capacity_plan_v3.xlsx", "done": True},
            {"kind": "up", "path": "Work/Clients/Acme/2026/offer_v2.pdf", "done": False},
            {"kind": "down", "path": "Phone backups/Screenshots/Ekran görüntüsü.png", "done": False},
        ],
    },
    "error": {
        "failCount": 3, "lastSuccessAt": ago(hours=1),
        "lastError": {"code": "out_of_sync", "at": ago(minutes=1), "lines": [
            "2026/11/06 10:02:41 ERROR : -   Path2 file not found in Path1   - Work/Clients/Acme",
            "2026/11/06 10:02:41 ERROR : Bisync critical error: path1 and path2 are out of sync, run --resync to recover",
            "2026/11/06 10:02:41 ERROR : Bisync aborted. Error is retryable without --resync due to --resilient mode.",
            "2026/11/06 10:02:41 NOTICE: Failed to bisync: bisync aborted"]},
    },
    "paused": {"serviceActive": False, "lastSuccessAt": ago(minutes=25)},
    "offline": {"lastSuccessAt": ago(hours=2)},
}
for name, over in states.items():
    data = dict(base, state=name, **over)
    (OUT / f"show-{name}.json").write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print(f"wrote {len(states)} fixtures to {OUT}")
