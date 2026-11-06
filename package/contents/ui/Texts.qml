pragma Singleton

import QtQuick

import "logic/Status.js" as Status

// Every user-visible sentence built from status codes, translated through Lang.
QtObject {
    function stateLabel(state) {
        switch (state) {
        case "synced":
            return Lang.i18n("Up to date");
        case "syncing":
            return Lang.i18n("Syncing");
        case "error":
            return Lang.i18n("Sync stopped");
        case "paused":
            return Lang.i18n("Paused");
        case "offline":
            return Lang.i18n("Offline");
        }
        return Lang.i18n("Sync helper not found");
    }

    function relText(rel) {
        if (!rel) {
            return Lang.i18n("never");
        }
        switch (rel.unit) {
        case "now":
            return Lang.i18n("just now");
        case "min":
            return Lang.i18np("%1 min ago", "%1 min ago", rel.n);
        case "hour":
            return Lang.i18np("%1 hour ago", "%1 hours ago", rel.n);
        case "yesterday":
            return Lang.i18n("yesterday");
        }
        return Lang.i18np("%1 day ago", "%1 days ago", rel.n);
    }

    function ago(iso, nowMs) {
        return relText(Status.relTime(iso, nowMs));
    }

    // short time for list rows: clock time today, "yesterday", else the date
    function when(iso, nowMs) {
        var rel = Status.relTime(iso, nowMs);
        if (!rel) {
            return "";
        }
        if (rel.unit === "now" || rel.unit === "min") {
            return relText(rel);
        }
        if (rel.unit === "hour") {
            return Lang.formatTime(new Date(iso));
        }
        if (rel.unit === "yesterday") {
            return Lang.i18n("yesterday");
        }
        return Lang.formatDate(new Date(iso), "d MMM");
    }

    function phaseLabel(phase) {
        switch (phase) {
        case "comparing":
            return Lang.i18nc("sync phase", "comparing");
        case "transferring":
            return Lang.i18nc("sync phase", "transferring files");
        case "saving":
            return Lang.i18nc("sync phase", "saving the state");
        }
        return Lang.i18nc("sync phase", "listing files");
    }

    // the coloured line under the title, also the tooltip
    function summary(m, nowMs) {
        switch (m.state) {
        case "synced":
            return Lang.i18n("Up to date · last sync %1", ago(m.lastSuccessAt, nowMs));
        case "syncing":
            if (m.phase === "transferring" && m.progress && m.progress.total > 0) {
                return Lang.i18n("Syncing · %1 of %2 files", m.progress.done, m.progress.total);
            }
            return Lang.i18n("Syncing · %1", phaseLabel(m.phase));
        case "error":
            return m.failCount > 1 ? Lang.i18np("Sync stopped · failed %1 time in a row", "Sync stopped · failed %1 times in a row", m.failCount)
                                   : Lang.i18n("Sync stopped · %1", errorTitle(Status.errorCode(m.lastError)));
        case "paused":
            return Lang.i18n("Paused · last sync %1", ago(m.lastSuccessAt, nowMs));
        case "offline":
            return Lang.i18n("Offline · last sync %1", ago(m.lastSuccessAt, nowMs));
        }
        return Lang.i18n("Sync helper not found");
    }

    function errorTitle(code) {
        switch (code) {
        case "lock":
            return Lang.i18n("A previous sync was interrupted");
        case "out_of_sync":
            return Lang.i18n("Your computer and Drive records don't match");
        case "too_many_deletes":
            return Lang.i18n("Too many deletions at once");
        case "permission":
            return Lang.i18n("No permission to change some files");
        case "auth":
            return Lang.i18n("The Google Drive sign-in has expired");
        }
        return Lang.i18n("rclone reported an error");
    }

    function errorBody(code) {
        switch (code) {
        case "lock":
            return Lang.i18n("rclone left a lock file behind. It expires on its own within 5 minutes and the next run continues.");
        case "out_of_sync":
            return Lang.i18n("After an interrupted sync rclone could not verify its saved file lists. Your files are safe; syncing is on hold.");
        case "too_many_deletes":
            return Lang.i18n("More than a quarter of the files would be deleted, so the sync stopped as a safety measure.");
        case "permission":
            return Lang.i18n("Google Drive refused a change (403), usually for files owned by someone else.");
        case "auth":
            return Lang.i18n("rclone's Google token is no longer valid, so it cannot reach your Drive.");
        }
        return Lang.i18n("The details below come from the sync log.");
    }

    function errorAdvice(code) {
        switch (code) {
        case "lock":
            return Lang.i18n("Usually nothing to do: it retries automatically.");
        case "out_of_sync":
            return Lang.i18n("Compare both sides; only if they are identical run the command below. Never resync while they differ.");
        case "too_many_deletes":
            return Lang.i18n("If the deletions are intended, run one sync with a higher --max-delete; otherwise restore the files.");
        case "permission":
            return Lang.i18n("Don't delete those files on this computer; remove them on drive.google.com or ask their owner.");
        case "auth":
            return Lang.i18n("Reconnect rclone to Google Drive with the command below.");
        }
        return Lang.i18n("Open the log for the full message.");
    }

    // a terminal command that goes with the advice (shown copyable, never run by the widget)
    function errorCommand(code) {
        switch (code) {
        case "out_of_sync":
            return "gdrive-sync --resync";
        case "auth":
            return "rclone config reconnect gdrive:";
        }
        return "";
    }
}
