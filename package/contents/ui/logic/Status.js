.pragma library

// Pure view logic for the widget: turns `gdrive-status show` output into a safe model.
// No UI text here (QML translates); functions return codes.

var STATES = ["synced", "syncing", "error", "paused", "offline", "missing"];
var PHASES = ["listing", "comparing", "transferring", "saving"];
var KINDS = ["up", "down", "deleted_remote", "deleted_local"];
var ERROR_CODES = ["lock", "out_of_sync", "too_many_deletes", "permission", "auth"];

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
        progress: _obj(p) && typeof p.done === "number" && typeof p.total === "number" ? { done: p.done, total: p.total } : null,
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
        current: _changes(d.current)
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
    return kind === "up" ? "cloud-upload" : kind === "down" ? "cloud-download" : "edit-delete";
}

function splitPath(path) {
    var i = path.lastIndexOf("/");
    return i === -1 ? { name: path, dir: "" } : { name: path.slice(i + 1), dir: path.slice(0, i) };
}

function phaseIndex(phase) {
    var i = PHASES.indexOf(phase);
    return i === -1 ? 0 : i;
}

function nextPollMs(state, expanded) {
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
