.pragma library

// Pure logic of the first-run wizard (SetupWizard.qml). No UI text here.

var MODES = ["twoway", "upload", "download"];

// pages shown for the current answers
function pages(checks, needsChoice, mode) {
    var out = [];
    if (!checks || !checks.rcloneOk || !checks.systemd) {
        out.push("requirements");
    }
    out.push("account", "driveFolder", "localFolder", "mode");
    if (mode === "twoway" && needsChoice) {
        out.push("preview");
    }
    out.push("progress", "done");
    return out;
}

// draft: {remote, remotePath, local, localCheck, mode, preview, firstSync}
function canNext(page, draft) {
    draft = draft || {};
    switch (page) {
    case "account":
        return typeof draft.remote === "string" && draft.remote !== "";
    case "driveFolder":
        return true;
    case "localFolder":
        return !!(draft.localCheck && draft.localCheck.ok);
    case "mode":
        return MODES.indexOf(draft.mode) !== -1;
    case "preview":
        return draft.firstSync === "another" || draft.firstSync === "match" || draft.firstSync === "merge";
    default:
        return false;
    }
}

// arguments of `gdrive-setup apply`
function applyArgs(draft) {
    var first = "none";
    var chk = draft.localCheck || {};
    if (draft.mode === "twoway") {
        if (chk.empty) {
            first = "empty";
        } else if (chk.ours) {
            first = "resume";
        } else if (draft.preview && draft.preview.needsChoice) {
            first = draft.firstSync;
        } else {
            first = "merge"; // nothing only here and nothing different: nothing to duplicate
        }
    }
    return [draft.remote, draft.remotePath || "", draft.local, draft.mode, first];
}

function childPath(path, name) {
    return path ? path + "/" + name : name;
}

function parentPath(path) {
    var i = (path || "").lastIndexOf("/");
    return i === -1 ? "" : path.slice(0, i);
}

// does the next step on the mode page compare the folder with Drive first?
function needsPreview(draft) {
    var chk = draft.localCheck || {};
    return draft.mode === "twoway" && !chk.empty && !chk.ours;
}

// stdout of a gdrive-setup step
function parseStep(text) {
    try {
        var d = JSON.parse(text);
        if (d !== null && typeof d === "object" && !Array.isArray(d)) {
            return d;
        }
    } catch (e) {
    }
    return { ok: false, error: "no_output" };
}
