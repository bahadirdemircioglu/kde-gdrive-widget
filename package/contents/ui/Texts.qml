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
        case "unconfigured":
            return Lang.i18n("Not set up yet");
        }
        return Lang.i18n("Sync helper not found");
    }

    function modeLabel(mode) {
        switch (mode) {
        case "upload":
            return Lang.i18n("Upload only");
        case "download":
            return Lang.i18n("Download only");
        }
        return Lang.i18n("Two-way");
    }

    function modeDescription(mode) {
        switch (mode) {
        case "upload":
            return Lang.i18n("This computer is copied to Drive. Nothing is ever deleted on Drive, so it works like a backup.");
        case "download":
            return Lang.i18n("Drive is copied to this computer. Nothing is ever deleted here, so it works like a backup.");
        }
        return Lang.i18n("Changes on either side reach the other, deletions included. The folder always looks like your Drive.");
    }

    // a failed setup step (codes from gdrive-setup)
    function setupError(error) {
        var code = error ? error.code : "";
        switch (code) {
        case "offline":
            return Lang.i18n("Google Drive could not be reached. Check the internet connection and try again.");
        case "auth":
            return Lang.i18n("The Google sign-in did not finish. Try again and allow access in the browser.");
        case "name_taken":
            return Lang.i18n("An rclone connection with this name already exists.");
        case "needs_choice":
            return Lang.i18n("This folder already has files; choose what to do with them first.");
        case "interrupted":
            return Lang.i18n("The setup was interrupted (for example by a restart). Files already copied are kept; start it again to continue.");
        case "systemd":
            return Lang.i18n("The background service could not be started.");
        case "rclone_missing":
            return Lang.i18n("rclone is not installed.");
        case "no_output":
            return Lang.i18n("The setup helper did not answer.");
        case "sync":
            return Lang.i18n("The first sync failed. Files already copied are kept; open the log for details or try again.");
        }
        return error && error.message ? error.message : Lang.i18n("Something went wrong.");
    }

    function localFolderProblem(reason) {
        switch (reason) {
        case "root":
            return Lang.i18n("The root folder cannot be synced.");
        case "home":
            return Lang.i18n("Choose a folder inside your home folder, not the home folder itself.");
        case "file":
            return Lang.i18n("This is a file, not a folder.");
        case "nested":
            return Lang.i18n("This folder overlaps the folder that is already in sync.");
        case "state":
            return Lang.i18n("This folder holds the sync service's own data.");
        }
        return "";
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
        case "unconfigured":
            return m.setup && m.setup.state === "running" ? Lang.i18n("Setting up…") : Lang.i18n("Not set up yet");
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
        case "not_initialized":
            return Lang.i18n("The setup was not finished");
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
        case "not_initialized":
            return Lang.i18n("Two-way sync needs a first sync that records both sides. It never starts one on its own, because merging two different sides creates duplicates.");
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
        case "not_initialized":
            return Lang.i18n("Run the setup again; it checks the folder before the first sync.");
        }
        return Lang.i18n("Open the log for the full message.");
    }

    // a terminal command that goes with the advice (shown copyable, never run by the widget)
    function errorCommand(code, remote) {
        switch (code) {
        case "out_of_sync":
            return "gdrive-sync --resync";
        case "auth":
            return "rclone config reconnect " + Status.shellQuote(remote || "gdrive:");
        }
        return "";
    }
}
