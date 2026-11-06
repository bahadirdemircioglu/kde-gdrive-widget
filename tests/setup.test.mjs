import { test } from "node:test";
import assert from "node:assert/strict";
import { loadQmlJs } from "./helpers/load-qml-js.mjs";

const W = loadQmlJs("Setup.js");
const ok = { rcloneOk: true, systemd: true, inotify: true };

test("pages: requirements only when something required is missing, preview only when needed", () => {
  assert.deepEqual(W.pages(ok, false, "twoway"), ["account", "driveFolder", "localFolder", "mode", "progress", "done"]);
  assert.deepEqual(W.pages({ ...ok, inotify: false }, false, "twoway")[0], "account");
  assert.deepEqual(W.pages({ ...ok, rcloneOk: false }, false, "twoway")[0], "requirements");
  assert.deepEqual(W.pages({ ...ok, systemd: false }, false, "twoway")[0], "requirements");
  assert.deepEqual(W.pages(ok, true, "twoway"), ["account", "driveFolder", "localFolder", "mode", "preview", "progress", "done"]);
  assert.ok(!W.pages(ok, true, "download").includes("preview"));
});

test("canNext per page", () => {
  assert.equal(W.canNext("requirements", {}), false);
  assert.equal(W.canNext("account", { remote: "" }), false);
  assert.equal(W.canNext("account", { remote: "gdrive:" }), true);
  assert.equal(W.canNext("driveFolder", {}), true);
  assert.equal(W.canNext("localFolder", { localCheck: { ok: false } }), false);
  assert.equal(W.canNext("localFolder", { localCheck: { ok: true } }), true);
  assert.equal(W.canNext("mode", { mode: "upload" }), true);
  assert.equal(W.canNext("mode", { mode: "x" }), false);
  assert.equal(W.canNext("preview", { firstSync: "" }), false);
  assert.equal(W.canNext("preview", { firstSync: "match" }), true);
  assert.equal(W.canNext("preview", { firstSync: "merge" }), true);
});

test("applyArgs: the first-sync rule", () => {
  const base = { remote: "gdrive:", remotePath: "Belgeler", local: "/home/u/GD" };
  assert.deepEqual(W.applyArgs({ ...base, mode: "upload", localCheck: { empty: false } }),
    ["gdrive:", "Belgeler", "/home/u/GD", "upload", "none"]);
  assert.deepEqual(W.applyArgs({ ...base, mode: "twoway", localCheck: { empty: true } })[4], "empty");
  assert.deepEqual(W.applyArgs({ ...base, mode: "twoway", localCheck: { empty: false, ours: true } })[4], "resume");
  assert.deepEqual(W.applyArgs({ ...base, mode: "twoway", localCheck: { empty: false }, preview: { needsChoice: true }, firstSync: "match" })[4], "match");
  assert.deepEqual(W.applyArgs({ ...base, mode: "twoway", localCheck: { empty: false }, preview: { needsChoice: false } })[4], "merge");
});

test("parentPath and childPath for Drive folder browsing", () => {
  assert.equal(W.childPath("", "Şirket"), "Şirket");
  assert.equal(W.childPath("Şirket", "Belgeler 2026"), "Şirket/Belgeler 2026");
  assert.equal(W.parentPath("Şirket/Belgeler 2026"), "Şirket");
  assert.equal(W.parentPath("Şirket"), "");
  assert.equal(W.parentPath(""), "");
});

test("parseStep: JSON from a gdrive-setup step, errors become {ok:false}", () => {
  assert.deepEqual(W.parseStep('{"folders":["a"]}'), { folders: ["a"] });
  assert.deepEqual(W.parseStep(""), { ok: false, error: "no_output" });
  assert.deepEqual(W.parseStep("Traceback..."), { ok: false, error: "no_output" });
});
