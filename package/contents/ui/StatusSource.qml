import QtQuick

import org.kde.plasma.plasma5support as P5Support

import "logic/Status.js" as Status
import "logic/Setup.js" as Setup

// Talks to the status helper (gdrive-status) through Plasma's executable engine and keeps
// the parsed model. The widget never runs rclone itself.
Item {
    id: source

    // shell command for the helper; the action is appended ("show", "now", "pause", "resume")
    property string helper: '"$HOME/.local/bin/gdrive-status"'
    // the sync scripts bundled in the plasmoid: used for setup, and while nothing is installed
    readonly property string bundled: Status.bundledDir(Qt.resolvedUrl("../code/sync"))
    // the popup is open: refresh more often
    property bool expanded: false

    property var model: Status.parseShow("")
    property bool loaded: false
    // ticks every 30 s so relative times ("3 min ago") stay current
    property double nowMs: Date.now()
    readonly property string syncState: model.state
    // an action is running (buttons show it and do not double-fire)
    property string busyAction: ""

    function refresh() {
        exec(Status.helperCommand(helper, bundled, "show"), "show");
    }

    // action: "now" | "pause" | "resume"
    function act(action) {
        busyAction = action;
        exec(Status.helperCommand(helper, bundled, action), action);
    }

    // one `gdrive-setup <args...> --json` step; callback(result object)
    function setupStep(args, callback) {
        var cmd = Status.setupCommand(bundled, args);
        engine.callbacks[cmd] = callback;
        exec(cmd, "setup");
    }

    // shellCommand is already quoted (Status.openCommand / Status.shellQuote)
    function open(shellCommand) {
        if (shellCommand) {
            exec(shellCommand, "open");
        }
    }

    function exec(cmd, tag) {
        if (engine.connectedSources.indexOf(cmd) !== -1) {
            return; // the same command is still running
        }
        engine.tags[cmd] = tag;
        engine.connectSource(cmd);
    }

    onExpandedChanged: {
        if (expanded) {
            refresh();
        }
    }
    onHelperChanged: refresh()
    Component.onCompleted: refresh()

    P5Support.DataSource {
        id: engine
        engine: "executable"
        connectedSources: []
        property var tags: ({})
        property var callbacks: ({})

        onNewData: function (sourceName, data) {
            var tag = tags[sourceName];
            delete tags[sourceName];
            disconnectSource(sourceName);
            if (tag === "show") {
                source.model = Status.parseShow(data["stdout"] || "");
                source.loaded = true;
                source.nowMs = Date.now();
                poll.interval = Status.nextPollMs(source.model.state, source.expanded, source.model.setup);
                poll.restart();
            } else if (tag === "setup") {
                var cb = callbacks[sourceName];
                delete callbacks[sourceName];
                if (cb) {
                    cb(Setup.parseStep(data["stdout"] || ""));
                }
                soon.interval = 300;
                soon.restart();
            } else if (tag === "now" || tag === "pause" || tag === "resume") {
                source.busyAction = "";
                // "now" only wakes the daemon; give it a moment to start the run
                soon.interval = tag === "now" ? 1500 : 300;
                soon.restart();
            }
        }
    }

    Timer {
        id: poll
        interval: 10000
        running: true
        onTriggered: source.refresh()
    }
    Timer {
        id: soon
        onTriggered: source.refresh()
    }
    Timer {
        interval: 30000
        running: true
        repeat: true
        onTriggered: source.nowMs = Date.now()
    }
}
