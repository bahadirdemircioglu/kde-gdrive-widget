import QtCore
import QtQuick
import QtQuick.Dialogs
import QtQuick.Layouts

import org.kde.plasma.components as PlasmaComponents3
import org.kde.kirigami as Kirigami

import "logic/Status.js" as Status
import "logic/Setup.js" as Setup

// First-run setup (and "Change setup…"): requirements → account → Drive folder → local folder
// → mode → preview (only when the folder already has files) → progress. Every step runs
// `gdrive-setup <step> --json`; the long ones (login, first sync) run detached and report
// through `gdrive-status show` (m.setup), so closing the popup or restarting Plasma is fine.
Item {
    id: wiz

    property var source
    readonly property var m: source ? source.model : Status.parseShow("")
    readonly property var setup: m.setup
    // opened from a working setup ("Change setup…"): can be closed
    property bool closable: false
    signal closeRequested()

    readonly property string homeDir: Status.bundledDir(StandardPaths.writableLocation(StandardPaths.HomeLocation))
    readonly property var allPages: ["requirements", "account", "driveFolder", "localFolder", "mode", "preview", "progress"]
    readonly property var pageList: Setup.pages(m.checks, !!(draft.preview && draft.preview.needsChoice), draft.mode)
    readonly property var stepPages: pageList.filter(p => p !== "progress" && p !== "done" && p !== "requirements")

    property string page: ""
    // the answers so far: {remote, remotePath, local, localCheck, mode, preview, firstSync}
    property var draft: ({ remote: "", remotePath: "", local: "", localCheck: null, mode: "twoway", preview: null, firstSync: "" })
    property var remotes: []
    property string suggestName: "gdrive:"
    property bool newAccount: false
    property bool wholeDrive: true
    property var folders: []
    property string busy: ""        // a short step is running: "remotes", "folders", "check", "preview", "start"
    property string errorText: ""

    function setDraft(changes) {
        var d = Object.assign({}, draft);
        for (var k in changes) {
            d[k] = changes[k];
        }
        draft = d;
    }

    function go(p) {
        errorText = "";
        page = p;
        if (p === "account") {
            loadRemotes();
        } else if (p === "driveFolder" && !wholeDrive) {
            loadFolders();
        } else if (p === "localFolder") {
            if (draft.local === "") {
                setDraft({ local: homeDir + "/GoogleDrive" });
            }
            checkLocal();
        }
    }

    function step(name, args, callback) {
        busy = name;
        errorText = "";
        source.setupStep(args, function (r) {
            busy = "";
            if (r.ok === false) {
                errorText = Texts.setupError({ code: r.error, message: r.message });
                return;
            }
            callback(r);
        });
    }

    function loadRemotes() {
        step("remotes", ["remotes"], function (r) {
            remotes = (r.remotes || []).map(x => x.name);
            suggestName = r.suggestName || "gdrive:";
            if (draft.remote === "" && remotes.length > 0) {
                setDraft({ remote: remotes[0] });
            }
            newAccount = remotes.length === 0;
        });
    }

    function loadFolders() {
        folders = [];
        step("folders", ["drive-folders", draft.remote, draft.remotePath], function (r) {
            folders = r.folders || [];
        });
    }

    function checkLocal() {
        setDraft({ localCheck: null, preview: null, firstSync: "" });
        if (draft.local === "") {
            return;
        }
        var asked = draft.local;
        step("check", ["check-local", asked], function (r) {
            if (draft.local === asked) {
                setDraft({ localCheck: r });
            }
        });
    }

    function next() {
        var i = pageList.indexOf(page);
        switch (page) {
        case "account":
            if (newAccount) {
                step("start", ["connect", suggestName], function () {});
                return;
            }
            break;
        case "mode":
            if (Setup.needsPreview(draft)) {
                step("preview", ["preview", draft.remote, draft.remotePath, draft.local], function (r) {
                    setDraft({ preview: r, firstSync: "" });
                    if (r.needsChoice) {
                        go("preview");
                    } else {
                        start();
                    }
                });
                return;
            }
            start();
            return;
        case "preview":
            if (draft.firstSync === "another") {
                setDraft({ local: "" });
                go("localFolder");
                return;
            }
            start();
            return;
        }
        go(pageList[i + 1]);
    }

    function back() {
        var i = stepPages.indexOf(page);
        if (i > 0) {
            go(stepPages[i - 1]);
        }
    }

    function start() {
        step("start", ["apply"].concat(Setup.applyArgs(draft)), function () {
            page = "progress";
        });
    }

    function retry() {
        // the folder is "ours" now: the first sync continues where it stopped
        var t = setup ? setup.target : null;
        if (!t || t.local === "") {
            go("localFolder");
            return;
        }
        setDraft({ remote: t.remote, remotePath: t.remotePath, local: t.local, mode: t.mode });
        step("check", ["check-local", t.local], function (r) {
            setDraft({ localCheck: r });
            start();
        });
    }

    // follow the detached steps
    onSetupChanged: {
        if (!setup) {
            return;
        }
        if (setup.step === "connect" && setup.state === "done" && page === "account" && newAccount) {
            newAccount = false;
            setDraft({ remote: setup.remote });
            loadRemotes();
            go("driveFolder");
        } else if (setup.step === "connect" && setup.state === "failed" && page === "account") {
            errorText = Texts.setupError(setup.error);
        } else if (setup.step === "apply" && setup.state === "running") {
            page = "progress";
        } else if (setup.step === "apply" && setup.state === "done" && closable && page === "progress") {
            closeRequested();
        }
    }
    onPageListChanged: {
        if (page === "requirements" && pageList[0] !== "requirements") {
            go(pageList[0]);
        }
    }
    Component.onCompleted: {
        if (setup && setup.state === "running" && setup.step === "apply") {
            page = "progress";
        } else if (setup && setup.step === "apply" && (setup.state === "failed" || setup.state === "cancelled") && !closable) {
            page = "progress";
        } else {
            go(pageList[0]);
        }
    }

    readonly property bool connecting: !!(setup && setup.step === "connect" && setup.state === "running")
    readonly property bool applying: !!(setup && setup.step === "apply" && setup.state === "running")
    readonly property bool startsSync: (page === "mode" && !Setup.needsPreview(draft))
                                       || (page === "preview" && draft.firstSync !== "another")
    readonly property bool canGoNext: busy === "" && !connecting && (page === "account" && newAccount ? true : Setup.canNext(page, draft))

    ColumnLayout {
        anchors.fill: parent
        spacing: Kirigami.Units.largeSpacing

        // ---- title ----
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 0
            Kirigami.Heading {
                Layout.fillWidth: true
                level: 3
                wrapMode: Text.Wrap
                text: {
                    switch (wiz.page) {
                    case "requirements":
                        return Lang.i18n("A few programs are missing");
                    case "account":
                        return Lang.i18n("Google account");
                    case "driveFolder":
                        return Lang.i18n("What to sync from Drive");
                    case "localFolder":
                        return Lang.i18n("Folder on this computer");
                    case "mode":
                        return Lang.i18n("How to sync");
                    case "preview":
                        return Lang.i18n("This folder already has files");
                    }
                    return Lang.i18n("Setting up Google Drive");
                }
            }
            PlasmaComponents3.Label {
                visible: wiz.stepPages.indexOf(wiz.page) !== -1
                text: Lang.i18n("Step %1 of %2", wiz.stepPages.indexOf(wiz.page) + 1, wiz.stepPages.length)
                opacity: 0.7
                font: Kirigami.Theme.smallFont
            }
        }

        // ---- pages ----
        StackLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            currentIndex: Math.max(0, wiz.allPages.indexOf(wiz.page))

            // requirements
            ColumnLayout {
                spacing: Kirigami.Units.smallSpacing
                Repeater {
                    model: [
                        { label: Lang.i18n("rclone 1.66 or newer"), ok: wiz.m.checks.rcloneOk,
                          note: wiz.m.checks.rclone && !wiz.m.checks.rcloneOk ? Lang.i18n("version %1 is too old", wiz.m.checks.rcloneVersion) : "" },
                        { label: Lang.i18n("systemd user session"), ok: wiz.m.checks.systemd, note: "" },
                        { label: Lang.i18n("inotify-tools (optional: uploads start right away)"), ok: wiz.m.checks.inotify, note: "" }
                    ]
                    delegate: RowLayout {
                        required property var modelData
                        Layout.fillWidth: true
                        Kirigami.Icon {
                            Layout.preferredWidth: Kirigami.Units.iconSizes.small
                            Layout.preferredHeight: Kirigami.Units.iconSizes.small
                            source: modelData.ok ? "checkmark" : "dialog-cancel"
                            color: modelData.ok ? Kirigami.Theme.positiveTextColor : Kirigami.Theme.negativeTextColor
                        }
                        PlasmaComponents3.Label {
                            Layout.fillWidth: true
                            text: modelData.note ? modelData.label + " · " + modelData.note : modelData.label
                            wrapMode: Text.Wrap
                        }
                    }
                }
                PlasmaComponents3.Label {
                    Layout.fillWidth: true
                    Layout.topMargin: Kirigami.Units.largeSpacing
                    visible: wiz.m.checks.installCommand !== ""
                    text: Lang.i18n("Install them by running this in a terminal (it asks for your password):")
                    wrapMode: Text.Wrap
                }
                CopyField {
                    Layout.fillWidth: true
                    visible: wiz.m.checks.installCommand !== ""
                    text: wiz.m.checks.installCommand
                }
                PlasmaComponents3.Button {
                    Layout.topMargin: Kirigami.Units.smallSpacing
                    icon.name: "view-refresh"
                    text: Lang.i18n("Check again")
                    onClicked: wiz.source.refresh()
                }
                Item { Layout.fillHeight: true }
            }

            // account
            ColumnLayout {
                spacing: Kirigami.Units.smallSpacing
                PlasmaComponents3.Label {
                    Layout.fillWidth: true
                    text: Lang.i18n("Which Google account should be synced?")
                    wrapMode: Text.Wrap
                }
                Repeater {
                    model: wiz.remotes
                    delegate: PlasmaComponents3.RadioButton {
                        required property string modelData
                        text: Lang.i18n("%1 (already connected)", modelData.replace(/:$/, ""))
                        checked: !wiz.newAccount && wiz.draft.remote === modelData
                        enabled: !wiz.connecting
                        onToggled: if (checked) {
                            wiz.newAccount = false;
                            wiz.setDraft({ remote: modelData, remotePath: "" });
                        }
                    }
                }
                PlasmaComponents3.RadioButton {
                    text: Lang.i18n("Connect a Google account")
                    checked: wiz.newAccount
                    enabled: !wiz.connecting
                    onToggled: if (checked) wiz.newAccount = true
                }
                PlasmaComponents3.Label {
                    Layout.fillWidth: true
                    Layout.leftMargin: Kirigami.Units.gridUnit * 1.5
                    visible: wiz.newAccount && !wiz.connecting
                    text: Lang.i18n("Your browser opens Google's sign-in page. rclone keeps the access key on this computer only.")
                    wrapMode: Text.Wrap
                    opacity: 0.75
                    font: Kirigami.Theme.smallFont
                }
                RowLayout {
                    Layout.fillWidth: true
                    Layout.topMargin: Kirigami.Units.largeSpacing
                    visible: wiz.connecting
                    PlasmaComponents3.BusyIndicator {
                        Layout.preferredWidth: Kirigami.Units.iconSizes.medium
                        Layout.preferredHeight: Kirigami.Units.iconSizes.medium
                        running: wiz.connecting
                    }
                    ColumnLayout {
                        Layout.fillWidth: true
                        PlasmaComponents3.Label {
                            Layout.fillWidth: true
                            text: Lang.i18n("Sign in to Google in the browser and allow access…")
                            wrapMode: Text.Wrap
                        }
                        PlasmaComponents3.Label {
                            Layout.fillWidth: true
                            visible: wiz.setup && wiz.setup.authUrl !== ""
                            text: "<a href=\"" + (wiz.setup ? wiz.setup.authUrl : "") + "\">" + Lang.i18n("No browser opened? Open the sign-in page") + "</a>"
                            textFormat: Text.StyledText
                            wrapMode: Text.Wrap
                            font: Kirigami.Theme.smallFont
                            onLinkActivated: link => Qt.openUrlExternally(link)
                        }
                    }
                }
                PlasmaComponents3.BusyIndicator {
                    visible: wiz.busy === "remotes"
                    running: visible
                }
                Item { Layout.fillHeight: true }
            }

            // Drive folder
            ColumnLayout {
                spacing: Kirigami.Units.smallSpacing
                PlasmaComponents3.RadioButton {
                    text: Lang.i18n("Everything in My Drive")
                    checked: wiz.wholeDrive
                    onToggled: if (checked) {
                        wiz.wholeDrive = true;
                        wiz.setDraft({ remotePath: "" });
                    }
                }
                PlasmaComponents3.RadioButton {
                    text: Lang.i18n("Only one folder")
                    checked: !wiz.wholeDrive
                    onToggled: if (checked) {
                        wiz.wholeDrive = false;
                        wiz.loadFolders();
                    }
                }
                RowLayout {
                    Layout.fillWidth: true
                    visible: !wiz.wholeDrive
                    PlasmaComponents3.ToolButton {
                        icon.name: "go-up"
                        enabled: wiz.draft.remotePath !== "" && wiz.busy === ""
                        display: PlasmaComponents3.AbstractButton.IconOnly
                        text: Lang.i18n("Up")
                        PlasmaComponents3.ToolTip.text: text
                        PlasmaComponents3.ToolTip.visible: hovered
                        onClicked: {
                            wiz.setDraft({ remotePath: Setup.parentPath(wiz.draft.remotePath) });
                            wiz.loadFolders();
                        }
                    }
                    PlasmaComponents3.Label {
                        Layout.fillWidth: true
                        text: [Lang.i18n("My Drive")].concat(wiz.draft.remotePath ? wiz.draft.remotePath.split("/") : []).join(" › ")
                        font.weight: Font.DemiBold
                        elide: Text.ElideMiddle
                    }
                }
                PlasmaComponents3.ScrollView {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    visible: !wiz.wholeDrive
                    ListView {
                        id: folderList
                        clip: true
                        model: wiz.folders
                        delegate: PlasmaComponents3.ItemDelegate {
                            required property string modelData
                            width: ListView.view.width
                            icon.name: "folder"
                            text: modelData
                            onClicked: {
                                wiz.setDraft({ remotePath: Setup.childPath(wiz.draft.remotePath, modelData) });
                                wiz.loadFolders();
                            }
                        }
                        PlasmaComponents3.BusyIndicator {
                            anchors.centerIn: parent
                            visible: wiz.busy === "folders"
                            running: visible
                        }
                        PlasmaComponents3.Label {
                            anchors.centerIn: parent
                            visible: wiz.busy === "" && folderList.count === 0
                            text: Lang.i18n("No sub-folders")
                            opacity: 0.6
                        }
                    }
                }
                PlasmaComponents3.Label {
                    Layout.fillWidth: true
                    visible: !wiz.wholeDrive
                    text: Lang.i18n("Click a folder to open it; the folder shown above is synced.")
                    wrapMode: Text.Wrap
                    opacity: 0.7
                    font: Kirigami.Theme.smallFont
                }
                Item {
                    Layout.fillHeight: true
                    visible: wiz.wholeDrive
                }
            }

            // local folder
            ColumnLayout {
                spacing: Kirigami.Units.smallSpacing
                PlasmaComponents3.Label {
                    Layout.fillWidth: true
                    text: Lang.i18n("Where should the files appear on this computer?")
                    wrapMode: Text.Wrap
                }
                RowLayout {
                    Layout.fillWidth: true
                    PlasmaComponents3.TextField {
                        id: localField
                        Layout.fillWidth: true
                        text: wiz.draft.local
                        onTextEdited: {
                            wiz.setDraft({ local: text, localCheck: null });
                            checkTimer.restart();
                        }
                    }
                    PlasmaComponents3.Button {
                        icon.name: "document-open-folder"
                        text: Lang.i18n("Choose…")
                        onClicked: folderDialog.open()
                    }
                }
                PlasmaComponents3.Label {
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                    readonly property var c: wiz.draft.localCheck
                    color: c && !c.ok ? Kirigami.Theme.negativeTextColor : Kirigami.Theme.textColor
                    opacity: c && !c.ok ? 1 : 0.75
                    text: {
                        if (!c) {
                            return wiz.busy === "check" ? Lang.i18n("Checking…") : "";
                        }
                        if (!c.ok) {
                            return Texts.localFolderProblem(c.reason);
                        }
                        if (c.ours) {
                            return Lang.i18n("The earlier setup of this folder continues where it stopped.");
                        }
                        if (!c.exists) {
                            return Lang.i18n("The folder will be created.");
                        }
                        if (c.empty) {
                            return Lang.i18n("The folder is empty.");
                        }
                        return Lang.i18n("The folder already has files. Before anything is copied you will see what differs from Drive.");
                    }
                }
                Item { Layout.fillHeight: true }
                Timer {
                    id: checkTimer
                    interval: 400
                    onTriggered: wiz.checkLocal()
                }
                FolderDialog {
                    id: folderDialog
                    currentFolder: "file://" + (wiz.draft.local || wiz.homeDir)
                    onAccepted: {
                        wiz.setDraft({ local: Status.bundledDir(selectedFolder) });
                        wiz.checkLocal();
                    }
                }
            }

            // mode
            ColumnLayout {
                spacing: Kirigami.Units.largeSpacing
                Repeater {
                    model: ["twoway", "upload", "download"]
                    delegate: ColumnLayout {
                        required property string modelData
                        Layout.fillWidth: true
                        spacing: 0
                        PlasmaComponents3.RadioButton {
                            text: Texts.modeLabel(modelData) + (modelData === "twoway" ? " " + Lang.i18n("(recommended)") : "")
                            checked: wiz.draft.mode === modelData
                            font.weight: Font.DemiBold
                            onToggled: if (checked) wiz.setDraft({ mode: modelData })
                        }
                        PlasmaComponents3.Label {
                            Layout.fillWidth: true
                            Layout.leftMargin: Kirigami.Units.gridUnit * 1.5
                            text: Texts.modeDescription(modelData)
                            wrapMode: Text.Wrap
                            opacity: 0.75
                        }
                    }
                }
                Item { Layout.fillHeight: true }
            }

            // preview
            ColumnLayout {
                id: previewPage
                spacing: Kirigami.Units.smallSpacing
                readonly property var pv: wiz.draft.preview || { onlyDrive: 0, onlyLocal: 0, different: 0, same: 0 }
                PlasmaComponents3.Label {
                    Layout.fillWidth: true
                    text: Lang.i18n("Compared with Drive:")
                    wrapMode: Text.Wrap
                }
                GridLayout {
                    columns: 2
                    columnSpacing: Kirigami.Units.largeSpacing
                    rowSpacing: 0
                    PlasmaComponents3.Label { text: Lang.i18n("Only on Drive") }
                    PlasmaComponents3.Label { text: String(previewPage.pv.onlyDrive); font.weight: Font.Bold }
                    PlasmaComponents3.Label { text: Lang.i18n("Only in this folder") }
                    PlasmaComponents3.Label { text: String(previewPage.pv.onlyLocal); font.weight: Font.Bold }
                    PlasmaComponents3.Label { text: Lang.i18n("Different") }
                    PlasmaComponents3.Label { text: String(previewPage.pv.different); font.weight: Font.Bold }
                    PlasmaComponents3.Label { text: Lang.i18n("Same") }
                    PlasmaComponents3.Label { text: String(previewPage.pv.same); font.weight: Font.Bold }
                }
                Repeater {
                    model: [
                        { value: "another", label: Lang.i18n("Use another, empty folder (recommended)"),
                          note: Lang.i18n("Drive then appears exactly as it is, with no extra files.") },
                        { value: "match", label: Lang.i18n("Make this folder match Drive"),
                          note: Lang.i18n("Files that are only here are moved to %1, not deleted.", "~/.local/share/gdrive-sync/set-aside-…") },
                        { value: "merge", label: Lang.i18n("Merge both"),
                          note: Lang.i18n("Files only here are uploaded to Drive; for different files the newer one wins and the older is kept aside.") }
                    ]
                    delegate: ColumnLayout {
                        required property var modelData
                        Layout.fillWidth: true
                        Layout.topMargin: Kirigami.Units.smallSpacing
                        spacing: 0
                        PlasmaComponents3.RadioButton {
                            text: modelData.label
                            checked: wiz.draft.firstSync === modelData.value
                            onToggled: if (checked) wiz.setDraft({ firstSync: modelData.value })
                        }
                        PlasmaComponents3.Label {
                            Layout.fillWidth: true
                            Layout.leftMargin: Kirigami.Units.gridUnit * 1.5
                            text: modelData.note
                            wrapMode: Text.Wrap
                            opacity: 0.75
                            font: Kirigami.Theme.smallFont
                        }
                    }
                }
                Item { Layout.fillHeight: true }
            }

            // progress
            ColumnLayout {
                spacing: Kirigami.Units.smallSpacing
                readonly property var t: wiz.setup ? wiz.setup.target : null
                readonly property var pr: wiz.setup ? wiz.setup.progress : null
                PlasmaComponents3.Label {
                    Layout.fillWidth: true
                    visible: parent.t !== null
                    text: parent.t ? (parent.t.remote + parent.t.remotePath) + "  ⇄  " + parent.t.local + "\n" + Texts.modeLabel(parent.t.mode) : ""
                    wrapMode: Text.WrapAnywhere
                    opacity: 0.8
                }
                PlasmaComponents3.Label {
                    Layout.fillWidth: true
                    Layout.topMargin: Kirigami.Units.largeSpacing
                    visible: wiz.applying
                    text: parent.pr && parent.pr.total > 0
                          ? Lang.i18n("First sync · %1 of %2 files", parent.pr.done, parent.pr.total)
                          : Lang.i18n("First sync · %1", Texts.phaseLabel(wiz.setup ? wiz.setup.phase : null))
                    wrapMode: Text.Wrap
                }
                PlasmaComponents3.ProgressBar {
                    Layout.fillWidth: true
                    visible: wiz.applying
                    indeterminate: !(parent.pr && parent.pr.total > 0)
                    from: 0
                    to: parent.pr && parent.pr.total > 0 ? parent.pr.total : 1
                    value: parent.pr ? parent.pr.done : 0
                }
                PlasmaComponents3.Label {
                    Layout.fillWidth: true
                    visible: wiz.applying
                    text: Lang.i18n("You can close this; the setup keeps running in the background.")
                    wrapMode: Text.Wrap
                    opacity: 0.7
                    font: Kirigami.Theme.smallFont
                }
                Kirigami.InlineMessage {
                    Layout.fillWidth: true
                    visible: !!(wiz.setup && wiz.setup.step === "apply" && (wiz.setup.state === "failed" || wiz.setup.state === "cancelled"))
                    type: wiz.setup && wiz.setup.state === "cancelled" ? Kirigami.MessageType.Information : Kirigami.MessageType.Error
                    text: wiz.setup && wiz.setup.state === "cancelled"
                          ? Lang.i18n("Stopped. Files already copied are kept; start again to continue.")
                          : Texts.setupError(wiz.setup ? wiz.setup.error : null)
                }
                Item { Layout.fillHeight: true }
            }
        }

        Kirigami.InlineMessage {
            Layout.fillWidth: true
            visible: wiz.errorText !== ""
            type: Kirigami.MessageType.Error
            text: wiz.errorText
        }

        // ---- buttons ----
        RowLayout {
            Layout.fillWidth: true
            PlasmaComponents3.Button {
                visible: wiz.stepPages.indexOf(wiz.page) > 0
                enabled: wiz.busy === "" && !wiz.connecting
                icon.name: "go-previous"
                text: Lang.i18n("Back")
                onClicked: wiz.back()
            }
            PlasmaComponents3.Button {
                visible: wiz.page === "progress" && !wiz.applying
                icon.name: "go-previous"
                text: Lang.i18n("Change answers")
                onClicked: wiz.go("localFolder")
            }
            Item { Layout.fillWidth: true }
            PlasmaComponents3.BusyIndicator {
                Layout.preferredWidth: Kirigami.Units.iconSizes.smallMedium
                Layout.preferredHeight: Kirigami.Units.iconSizes.smallMedium
                visible: wiz.busy === "preview" || wiz.busy === "start"
                running: visible
            }
            PlasmaComponents3.Button {
                visible: wiz.connecting || wiz.applying
                icon.name: "dialog-cancel"
                text: Lang.i18n("Cancel")
                onClicked: wiz.source.setupStep(["cancel"], function () {})
            }
            PlasmaComponents3.Button {
                visible: wiz.closable && !wiz.applying && !wiz.connecting
                text: Lang.i18n("Close")
                onClicked: wiz.closeRequested()
            }
            PlasmaComponents3.Button {
                visible: wiz.page === "progress" && !wiz.applying
                icon.name: "view-refresh"
                text: Lang.i18n("Try again")
                onClicked: wiz.retry()
            }
            PlasmaComponents3.Button {
                visible: wiz.stepPages.indexOf(wiz.page) !== -1
                enabled: wiz.canGoNext
                icon.name: wiz.startsSync ? "media-playback-start" : "go-next"
                text: wiz.startsSync ? Lang.i18n("Start syncing")
                      : wiz.page === "account" && wiz.newAccount ? Lang.i18n("Sign in…") : Lang.i18n("Next")
                onClicked: wiz.next()
            }
        }
    }
}
