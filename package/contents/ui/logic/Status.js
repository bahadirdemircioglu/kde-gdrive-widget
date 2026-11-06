.pragma library

// Pure view logic for the widget: turns `gdrive-status show` output into a safe model.
// No UI text here (QML translates); functions return codes.

var STATES = ["synced", "syncing", "error", "paused", "offline", "missing", "unconfigured"];
var PHASES = ["listing", "comparing", "transferring", "saving"];
var KINDS = ["up", "down", "deleted_remote", "deleted_local", "conflict"];
var ERROR_CODES = ["lock", "out_of_sync", "too_many_deletes", "permission", "auth", "not_initialized"];
var MODES = ["twoway", "upload", "download"];
var SETUP_STEPS = ["connect", "apply"];
var SETUP_STATES = ["running", "done", "failed", "cancelled"];

function _obj(v) {
    return v !== null && typeof v === "object" && !Array.isArray(v);
}

function _changes(list, withAt) {
    if (!Array.isArray(list)) {
        return [];
    }
    return list.filter(function (c) {
        return _obj(c) && KINDS.indexOf(c.kind) !== -1 && typeof c.path === "string";
    }).map(function (c) {
        return { kind: c.kind, path: c.path, at: typeof c.at === "string" ? c.at : "", done: c.done === true };
    });
}

function _str(v) {
    return typeof v === "string" ? v : "";
}

function _progress(p) {
    return _obj(p) && typeof p.done === "number" && typeof p.total === "number" ? { done: p.done, total: p.total } : null;
}

function _checks(c) {
    c = _obj(c) ? c : {};
    return {
        rclone: c.rclone === true,
        rcloneVersion: _str(c.rcloneVersion),
        rcloneOk: c.rcloneOk === true,
        systemd: c.systemd === true,
        inotify: c.inotify === true,
        pkgManager: _str(c.pkgManager),
        installCommand: _str(c.installCommand)
    };
}

// setup.json as reported by show; null when absent or unreadable
function _setup(s) {
    if (!_obj(s) || SETUP_STEPS.indexOf(s.step) === -1 || SETUP_STATES.indexOf(s.state) === -1) {
        return null;
    }
    var t = _obj(s.target) ? s.target : {};
    var url = _str(s.authUrl);
    return {
        step: s.step,
        state: s.state,
        // only rclone's own local login page is ever shown as a link
        authUrl: /^http:\/\/127\.0\.0\.1:\d+\/auth\?/.test(url) ? url : "",
        remote: _str(s.remote),
        createdRemote: s.createdRemote === true,
        phase: PHASES.indexOf(s.phase) !== -1 ? s.phase : null,
        progress: _progress(s.progress),
        setAside: _str(s.setAside),
        target: {
            remote: _str(t.remote),
            remotePath: _str(t.remotePath),
            local: _str(t.local),
            mode: MODES.indexOf(t.mode) !== -1 ? t.mode : "twoway",
            firstSync: _str(t.firstSync)
        },
        error: _obj(s.error) ? { code: _str(s.error.code), message: _str(s.error.message) } : null
    };
}

// stdout of `gdrive-status show` -> model; anything unreadable is state "missing"
function parseShow(text) {
    var d = null;
    try {
        d = JSON.parse(text);
    } catch (e) {
        d = null;
    }
    if (!_obj(d) || STATES.indexOf(d.state) === -1) {
        d = { state: "missing" };
    }
    var p = d.progress;
    return {
        state: d.state,
        phase: PHASES.indexOf(d.phase) !== -1 ? d.phase : null,
        progress: _progress(p),
        serviceActive: d.serviceActive === true,
        localRoot: typeof d.localRoot === "string" ? d.localRoot : "",
        logPath: typeof d.logPath === "string" ? d.logPath : "",
        fileCount: typeof d.fileCount === "number" ? d.fileCount : null,
        failCount: typeof d.failCount === "number" ? d.failCount : 0,
        lastSuccessAt: typeof d.lastSuccessAt === "string" ? d.lastSuccessAt : "",
        lastRunAt: typeof d.lastRunAt === "string" ? d.lastRunAt : "",
        runStartedAt: typeof d.runStartedAt === "string" ? d.runStartedAt : "",
        lastError: _obj(d.lastError) ? {
            code: errorCode(d.lastError),
            lines: Array.isArray(d.lastError.lines) ? d.lastError.lines.filter(function (l) { return typeof l === "string"; }) : [],
            at: typeof d.lastError.at === "string" ? d.lastError.at : ""
        } : null,
        recent: _changes(d.recent),
        current: _changes(d.current),
        mode: MODES.indexOf(d.mode) !== -1 ? d.mode : "twoway",
        backupDir: _str(d.backupDir),
        remotePath: _str(d.remotePath),
        createdRemote: d.createdRemote === true,
        duplicates: Array.isArray(d.duplicates) ? d.duplicates.filter(function (x) { return typeof x === "string"; }) : [],
        checks: _checks(d.checks),
        setup: _setup(d.setup)
    };
}

function errorCode(err) {
    return _obj(err) && ERROR_CODES.indexOf(err.code) !== -1 ? err.code : "unknown";
}

function _midnight(ms) {
    var d = new Date(ms);
    return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
}

// -> {unit: "now"|"min"|"hour"|"yesterday"|"day", n} or null
function relTime(iso, nowMs) {
    if (typeof iso !== "string" || iso === "") {
        return null;
    }
    var t = Date.parse(iso);
    if (isNaN(t)) {
        return null;
    }
    var mins = Math.floor((nowMs - t) / 60000);
    if (mins < 1) {
        return { unit: "now", n: 0 };
    }
    if (mins < 60) {
        return { unit: "min", n: mins };
    }
    var days = Math.round((_midnight(nowMs) - _midnight(t)) / 86400000);
    if (days <= 0) {
        return { unit: "hour", n: Math.floor(mins / 60) };
    }
    if (days === 1) {
        return { unit: "yesterday", n: 1 };
    }
    return { unit: "day", n: days };
}

function todayCounts(recent, nowDate) {
    var out = { up: 0, down: 0, deleted: 0 };
    var today = _midnight(nowDate.getTime());
    (recent || []).forEach(function (c) {
        var t = Date.parse(c.at);
        if (isNaN(t) || _midnight(t) !== today) {
            return;
        }
        if (c.kind === "up") {
            out.up++;
        } else if (c.kind === "down") {
            out.down++;
        } else {
            out.deleted++;
        }
    });
    return out;
}

function badgeIcon(state) {
    return {
        synced: "state-ok",
        syncing: "state-sync",
        error: "state-error",
        paused: "state-pause",
        offline: "state-offline"
    }[state] || "state-warning";
}

function kindIcon(kind) {
    return kind === "up" ? "cloud-upload" : kind === "down" ? "cloud-download" : kind === "conflict" ? "vcs-conflicting" : "edit-delete";
}

function splitPath(path) {
    var i = path.lastIndexOf("/");
    return i === -1 ? { name: path, dir: "" } : { name: path.slice(i + 1), dir: path.slice(0, i) };
}

function phaseIndex(phase) {
    var i = PHASES.indexOf(phase);
    return i === -1 ? 0 : i;
}

function nextPollMs(state, expanded, setup) {
    if (setup && setup.state === "running") {
        return 1000;
    }
    if (state === "syncing") {
        return 2000;
    }
    return expanded ? 5000 : 10000;
}

// single-quote for sh: every character literal
function shellQuote(s) {
    return "'" + String(s).replace(/'/g, "'\\''") + "'";
}

// xdg-open command for a change row; deleted items open their folder. "" when unsafe.
function openCommand(localRoot, change) {
    if (!localRoot || !change || typeof change.path !== "string" || change.path === "") {
        return "";
    }
    var parts = change.path.split("/");
    if (change.path.charAt(0) === "/" || parts.indexOf("..") !== -1) {
        return "";
    }
    var rel = change.kind === "deleted_local" || change.kind === "deleted_remote" ? parts.slice(0, -1).join("/") : change.path;
    var target = localRoot.replace(/\/+$/, "") + (rel ? "/" + rel : "");
    return "xdg-open " + shellQuote(target);
}

// the status helper; if it is not installed yet, the copy bundled in the plasmoid
function helperCommand(installedCmd, bundled, action) {
    var cmd = installedCmd + " " + action;
    return bundled ? cmd + " 2>/dev/null || python3 " + shellQuote(bundled + "/gdrive-status") + " " + action : cmd;
}

// `gdrive-setup <args...> --json`, from the plasmoid (same version as this UI) when possible
function setupCommand(bundled, args) {
    var exe = bundled ? "python3 " + shellQuote(bundled + "/gdrive-setup") : '"$HOME/.local/bin/gdrive-setup"';
    return exe + " " + args.map(shellQuote).join(" ") + " --json";
}

// Qt.resolvedUrl("../code/sync") -> local path ("" when not a file URL)
function bundledDir(url) {
    url = String(url);
    if (url.indexOf("file://") !== 0) {
        return "";
    }
    try {
        return decodeURIComponent(url.slice(7)).replace(/\/+$/, "");
    } catch (e) {
        return "";
    }
}
