import QtQuick

import org.kde.plasma.plasma5support as P5Support

import "logic/Status.js" as Status

// Talks to the status helper (gdrive-status) through Plasma's executable engine and keeps
// the parsed model. The widget never runs rclone itself.
Item {
    id: source

    // shell command for the helper; the action is appended ("show", "now", "pause", "resume")
    property string helper: '"$HOME/.local/bin/gdrive-status"'
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
        exec(helper + " show", "show");
    }

    // action: "now" | "pause" | "resume"
    function act(action) {
        busyAction = action;
        exec(helper + " " + action, action);
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

        onNewData: function (sourceName, data) {
            var tag = tags[sourceName];
            delete tags[sourceName];
            disconnectSource(sourceName);
            if (tag === "show") {
                source.model = Status.parseShow(data["stdout"] || "");
                source.loaded = true;
                source.nowMs = Date.now();
                poll.interval = Status.nextPollMs(source.model.state, source.expanded);
                poll.restart();
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
