import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { loadQmlJs } from "./helpers/load-qml-js.mjs";

const S = loadQmlJs("Status.js");

test("parseShow: bad or empty input becomes 'missing' with safe defaults", () => {
  for (const input of ["", "not json", '{"state": "syn', "[]", "null", '{"state":"weird"}']) {
    const m = S.parseShow(input);
    assert.equal(m.state, "missing", input);
    assert.deepEqual(m.recent, []);
    assert.deepEqual(m.current, []);
    assert.equal(m.progress, null);
    assert.equal(m.failCount, 0);
    assert.equal(m.lastError, null);
  }
});

test("parseShow: keeps known fields and drops malformed list items", () => {
  const m = S.parseShow(JSON.stringify({
    state: "syncing", phase: "transferring", progress: { done: 1, total: 2 },
    serviceActive: true, localRoot: "/home/u/GoogleDrive", fileCount: 10287, failCount: 0,
    recent: [{ kind: "up", path: "a/b.pdf", at: "2026-11-06T10:00:00+03:00" }, { nope: 1 }, null],
    current: [{ kind: "down", path: "c.txt", done: true }],
  }));
  assert.equal(m.state, "syncing");
  assert.equal(m.phase, "transferring");
  assert.deepEqual(m.progress, { done: 1, total: 2 });
  assert.equal(m.fileCount, 10287);
  assert.equal(m.recent.length, 1);
  assert.equal(m.current[0].done, true);
});

test("relTime: now, minutes, hours today, yesterday, days", () => {
  const now = new Date(2026, 10, 6, 14, 0, 0).getTime();
  const at = (d, h, mi) => new Date(2026, 10, d, h, mi, 0).toISOString();
  assert.deepEqual(S.relTime(new Date(2026, 10, 6, 13, 59, 30).toISOString(), now), { unit: "now", n: 0 });
  assert.deepEqual(S.relTime(at(6, 13, 59), now), { unit: "min", n: 1 });
  assert.deepEqual(S.relTime(at(6, 13, 57), now), { unit: "min", n: 3 });
  assert.deepEqual(S.relTime(at(6, 10, 30), now), { unit: "hour", n: 3 });
  assert.deepEqual(S.relTime(at(5, 23, 50), now), { unit: "yesterday", n: 1 });
  assert.deepEqual(S.relTime(at(3, 9, 0), now), { unit: "day", n: 3 });
  assert.deepEqual(S.relTime(at(6, 15, 0), now), { unit: "now", n: 0 }, "future (clock skew) is 'now'");
  assert.equal(S.relTime("garbage", now), null);
  assert.equal(S.relTime(null, now), null);
});

test("todayCounts: only today's local date, deletes summed", () => {
  const now = new Date(2026, 10, 6, 14, 0, 0);
  const at = (d, h) => new Date(2026, 10, d, h, 0, 0).toISOString();
  const recent = [
    { kind: "up", at: at(6, 9) }, { kind: "up", at: at(6, 13) }, { kind: "down", at: at(6, 1) },
    { kind: "deleted_remote", at: at(6, 2) }, { kind: "deleted_local", at: at(6, 3) },
    { kind: "up", at: at(5, 23) },
  ];
  assert.deepEqual(S.todayCounts(recent, now), { up: 2, down: 1, deleted: 2 });
  assert.deepEqual(S.todayCounts([], now), { up: 0, down: 0, deleted: 0 });
});

test("badgeIcon and kindIcon", () => {
  assert.equal(S.badgeIcon("synced"), "state-ok");
  assert.equal(S.badgeIcon("syncing"), "state-sync");
  assert.equal(S.badgeIcon("error"), "state-error");
  assert.equal(S.badgeIcon("paused"), "state-pause");
  assert.equal(S.badgeIcon("offline"), "state-offline");
  assert.equal(S.badgeIcon("missing"), "state-warning");
  assert.equal(S.kindIcon("up"), "cloud-upload");
  assert.equal(S.kindIcon("down"), "cloud-download");
  assert.equal(S.kindIcon("deleted_remote"), "edit-delete");
  assert.equal(S.kindIcon("deleted_local"), "edit-delete");
});

test("splitPath", () => {
  assert.deepEqual(S.splitPath("Şirket/Muhasebe/fatura.pdf"), { name: "fatura.pdf", dir: "Şirket/Muhasebe" });
  assert.deepEqual(S.splitPath("kök.txt"), { name: "kök.txt", dir: "" });
});

test("phaseIndex and nextPollMs", () => {
  assert.equal(S.phaseIndex("listing"), 0);
  assert.equal(S.phaseIndex("saving"), 3);
  assert.equal(S.phaseIndex(undefined), 0);
  assert.equal(S.nextPollMs("syncing", false), 2000);
  assert.equal(S.nextPollMs("synced", true), 5000);
  assert.equal(S.nextPollMs("synced", false), 10000);
});

test("errorCode: known codes pass, anything else is unknown", () => {
  for (const c of ["lock", "out_of_sync", "too_many_deletes", "permission", "auth"]) {
    assert.equal(S.errorCode({ code: c }), c);
  }
  assert.equal(S.errorCode({ code: "rm -rf" }), "unknown");
  assert.equal(S.errorCode(null), "unknown");
});

test("shellQuote survives quotes, spaces, $() and newlines in a real shell", () => {
  const nasty = ["a b.pdf", "it's.pdf", "$(touch /tmp/pwned)", "x`id`y", 'q"uote', "new\nline", "Şirket/Teklif [Conflict].pdf"];
  for (const s of nasty) {
    const out = execFileSync("sh", ["-c", "printf %s " + S.shellQuote(s)], { encoding: "utf8" });
    assert.equal(out, s);
  }
});

test("openCommand: file inside the sync root, folder for deleted items", () => {
  assert.equal(S.openCommand("/home/u/GoogleDrive", { kind: "up", path: "a/it's.pdf" }),
    "xdg-open '/home/u/GoogleDrive/a/it'\\''s.pdf'");
  assert.equal(S.openCommand("/home/u/GoogleDrive", { kind: "deleted_local", path: "a/b.pdf" }),
    "xdg-open '/home/u/GoogleDrive/a'");
  assert.equal(S.openCommand("/home/u/GoogleDrive", { kind: "up", path: "../../etc/passwd" }), "");
  assert.equal(S.openCommand("", { kind: "up", path: "a" }), "");
});

test("parseShow: unconfigured keeps checks and setup progress", () => {
  const m = S.parseShow(JSON.stringify({
    state: "unconfigured",
    checks: { rclone: true, rcloneVersion: "1.75.2", rcloneOk: true, python: true, systemd: true, inotify: false,
      pkgManager: "pacman", installCommand: "sudo pacman -S --needed inotify-tools" },
    setup: { step: "apply", state: "running", phase: "transferring", progress: { done: 3, total: 9 },
      target: { remote: "gdrive:", remotePath: "", local: "/home/u/GD", mode: "twoway", firstSync: "empty" },
      authUrl: "http://127.0.0.1:53682/auth?state=x", error: null },
  }));
  assert.equal(m.state, "unconfigured");
  assert.equal(m.checks.rcloneOk, true);
  assert.equal(m.checks.inotify, false);
  assert.equal(m.checks.installCommand, "sudo pacman -S --needed inotify-tools");
  assert.equal(m.setup.state, "running");
  assert.deepEqual(m.setup.progress, { done: 3, total: 9 });
  assert.equal(m.setup.target.local, "/home/u/GD");
  assert.equal(m.setup.authUrl, "http://127.0.0.1:53682/auth?state=x");
});

test("parseShow: setup garbage is null, unknown setup states dropped, auth url must be local", () => {
  assert.equal(S.parseShow(JSON.stringify({ state: "unconfigured", setup: "x" })).setup, null);
  assert.equal(S.parseShow(JSON.stringify({ state: "unconfigured", setup: { step: "apply", state: "weird" } })).setup, null);
  const m = S.parseShow(JSON.stringify({ state: "unconfigured", setup: { step: "connect", state: "running", authUrl: "https://evil.example/" } }));
  assert.equal(m.setup.authUrl, "");
  assert.deepEqual(S.parseShow(JSON.stringify({ state: "unconfigured" })).checks.rcloneOk, false);
});

test("parseShow: mode, conflicts, duplicates, backupDir, not_initialized", () => {
  const m = S.parseShow(JSON.stringify({
    state: "error", mode: "download", backupDir: "/home/u/.local/share/gdrive-sync/backup",
    duplicates: ["Rapor.pdf", 5], createdRemote: true,
    lastError: { code: "not_initialized", lines: [] },
    recent: [{ kind: "conflict", path: "a.txt", at: "2026-11-06T10:00:00+03:00" }],
  }));
  assert.equal(m.mode, "download");
  assert.deepEqual(m.duplicates, ["Rapor.pdf"]);
  assert.equal(m.backupDir, "/home/u/.local/share/gdrive-sync/backup");
  assert.equal(m.createdRemote, true);
  assert.equal(m.lastError.code, "not_initialized");
  assert.equal(m.recent[0].kind, "conflict");
  assert.equal(S.parseShow(JSON.stringify({ state: "synced", mode: "sideways" })).mode, "twoway");
  assert.equal(S.kindIcon("conflict"), "vcs-conflicting");
});

test("nextPollMs: a running setup polls every second", () => {
  assert.equal(S.nextPollMs("unconfigured", false, { state: "running" }), 1000);
  assert.equal(S.nextPollMs("unconfigured", true, { state: "done" }), 5000);
  assert.equal(S.badgeIcon("unconfigured"), "state-warning");
});

test("helperCommand and setupCommand quote everything and fall back to the bundled copy", () => {
  const bundled = "/home/u/.local/share/plasma/plasmoids/x/contents/code/sync";
  assert.equal(S.helperCommand('"$HOME/.local/bin/gdrive-status"', bundled, "show"),
    `"$HOME/.local/bin/gdrive-status" show 2>/dev/null || python3 '${bundled}/gdrive-status' show`);
  assert.equal(S.helperCommand('"$HOME/.local/bin/gdrive-status"', "", "now"), '"$HOME/.local/bin/gdrive-status" now');
  const nasty = "/tmp/it's $(id) dir";
  const cmd = S.setupCommand(nasty, ["check-local", "/home/u/Google Sürücü's"]);
  assert.equal(cmd, `python3 '/tmp/it'\\''s $(id) dir/gdrive-setup' 'check-local' '/home/u/Google Sürücü'\\''s' --json`);
  const out = execFileSync("sh", ["-c", cmd.replace(/^python3 /, "printf '%s|' ")], { encoding: "utf8" });
  assert.equal(out, `${nasty}/gdrive-setup|check-local|/home/u/Google Sürücü's|--json|`);
  assert.equal(S.setupCommand("", ["check"]), `"$HOME/.local/bin/gdrive-setup" 'check' --json`);
});

test("bundledDir: file URL of the plasmoid code folder to a path", () => {
  assert.equal(S.bundledDir("file:///home/u/.local/share/plasma/plasmoids/x/contents/code/sync"),
    "/home/u/.local/share/plasma/plasmoids/x/contents/code/sync");
  assert.equal(S.bundledDir("file:///home/u/G%C3%BCzel%20dir/code/sync"), "/home/u/Güzel dir/code/sync");
  assert.equal(S.bundledDir("qrc:/x"), "");
});
