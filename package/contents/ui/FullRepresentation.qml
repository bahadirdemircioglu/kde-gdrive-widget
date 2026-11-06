import QtQuick
import QtQuick.Layouts

import org.kde.plasma.plasmoid
import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.components as PlasmaComponents3
import org.kde.plasma.extras as PlasmaExtras
import org.kde.kirigami as Kirigami

import "logic/Status.js" as Status

// Popup (panel) or the widget itself (desktop): status, recent changes, actions.
PlasmaExtras.Representation {
    id: full

    property PlasmoidItem plasmoidItem
    property var source

    readonly property var m: source ? source.model : Status.parseShow("")
    readonly property string syncState: m.state
    readonly property double nowMs: source ? source.nowMs : Date.now()
    readonly property bool syncing: syncState === "syncing"
    readonly property var today: Status.todayCounts(m.recent, new Date(nowMs))
    readonly property var rows: syncing ? m.current : m.recent.slice(0, Plasmoid.configuration.recentCount)
    readonly property bool inPopup: plasmoidItem ? plasmoidItem.inPanel : false

    Layout.preferredWidth: Kirigami.Units.gridUnit * 22
    Layout.preferredHeight: Kirigami.Units.gridUnit * 28
    Layout.minimumWidth: Kirigami.Units.gridUnit * 14
    Layout.minimumHeight: Kirigami.Units.gridUnit * 12

    function stateColor(state) {
        switch (state) {
        case "synced":
            return Kirigami.Theme.positiveTextColor;
        case "syncing":
            return Kirigami.Theme.linkColor;
        case "error":
        case "missing":
            return Kirigami.Theme.negativeTextColor;
        }
        return Kirigami.Theme.disabledTextColor;
    }

    header: PlasmaExtras.PlasmoidHeading {
        contentItem: RowLayout {
            spacing: Kirigami.Units.largeSpacing

            CloudIcon {
                Layout.preferredWidth: Kirigami.Units.iconSizes.medium
                Layout.preferredHeight: Kirigami.Units.iconSizes.medium
                syncState: full.syncState
            }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 0
                Kirigami.Heading {
                    Layout.fillWidth: true
                    level: 3
                    text: Lang.i18n("Google Drive")
                    elide: Text.ElideRight
                }
                PlasmaComponents3.Label {
                    Layout.fillWidth: true
                    text: Texts.summary(full.m, full.nowMs)
                    color: full.stateColor(full.syncState)
                    font.weight: Font.DemiBold
                    elide: Text.ElideRight
                }
            }
            PlasmaComponents3.ToolButton {
                icon.name: "configure"
                display: PlasmaComponents3.AbstractButton.IconOnly
                text: Lang.i18n("Configure…")
                PlasmaComponents3.ToolTip.text: text
                PlasmaComponents3.ToolTip.visible: hovered
                onClicked: Plasmoid.internalAction("configure").trigger()
            }
        }
    }

    contentItem: Item {
      ColumnLayout {
        anchors.fill: parent
        anchors.topMargin: Kirigami.Units.largeSpacing
        anchors.leftMargin: Kirigami.Units.largeSpacing
        anchors.rightMargin: Kirigami.Units.largeSpacing
        spacing: Kirigami.Units.largeSpacing

        // ---- not installed / no status yet ----
        Kirigami.PlaceholderMessage {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: full.syncState === "missing"
            icon.name: "state-warning"
            text: Lang.i18n("Sync helper not found")
            explanation: Lang.i18n("The widget reads its status with this command:\n%1 show\n\nInstall the sync service with sync/install.sh from the widget's project, or change the command in the settings.",
                                   Plasmoid.configuration.helperCommand)
        }

        // ---- counters ----
        RowLayout {
            Layout.fillWidth: true
            visible: full.syncState !== "missing" && !full.syncing
            spacing: Kirigami.Units.smallSpacing

            Repeater {
                model: [
                    { label: Lang.i18n("Files"), value: full.m.fileCount === null ? "–" : Number(full.m.fileCount).toLocaleString(Lang.locale, "f", 0) },
                    { label: Lang.i18n("Uploaded today"), value: String(full.today.up) },
                    { label: Lang.i18n("Downloaded today"), value: String(full.today.down) }
                ]
                delegate: Rectangle {
                    required property var modelData
                    Layout.fillWidth: true
                    Layout.preferredWidth: 1
                    implicitHeight: tile.implicitHeight + Kirigami.Units.smallSpacing * 2
                    radius: Kirigami.Units.cornerRadius
                    color: Qt.alpha(Kirigami.Theme.textColor, 0.06)
                    ColumnLayout {
                        id: tile
                        anchors.fill: parent
                        anchors.margins: Kirigami.Units.smallSpacing
                        anchors.leftMargin: Kirigami.Units.largeSpacing
                        spacing: 0
                        PlasmaComponents3.Label {
                            Layout.fillWidth: true
                            text: modelData.label
                            font: Kirigami.Theme.smallFont
                            opacity: 0.75
                            elide: Text.ElideRight
                        }
                        PlasmaComponents3.Label {
                            text: modelData.value
                            font.weight: Font.Bold
                            font.pointSize: Kirigami.Theme.defaultFont.pointSize * 1.15
                        }
                    }
                }
            }
        }

        PhaseStrip {
            Layout.fillWidth: true
            visible: full.syncing
            phase: full.m.phase || "listing"
            progress: full.m.progress
        }

        ErrorCard {
            Layout.fillWidth: true
            visible: full.syncState === "error"
            lastError: full.m.lastError
            lastSuccessAt: full.m.lastSuccessAt
            nowMs: full.nowMs
        }

        // ---- list ----
        PlasmaComponents3.Label {
            Layout.fillWidth: true
            visible: full.syncState !== "missing"
            text: full.syncing ? Lang.i18n("Now") : Lang.i18n("Recent changes")
            font.weight: Font.DemiBold
            opacity: 0.75
        }
        PlasmaComponents3.ScrollView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: full.syncState !== "missing"

            ListView {
                id: list
                clip: true
                model: full.rows
                delegate: ChangeRow {
                    required property var modelData
                    change: modelData
                    live: full.syncing
                    nowMs: full.nowMs
                    onOpenRequested: c => full.source.open(Status.openCommand(full.m.localRoot, c))
                }
                PlasmaExtras.PlaceholderMessage {
                    anchors.centerIn: parent
                    width: parent.width - Kirigami.Units.gridUnit * 2
                    visible: list.count === 0
                    iconName: full.syncing ? "state-sync" : "state-ok"
                    text: full.syncing ? Lang.i18n("Looking for changes…") : Lang.i18n("No changes yet")
                }
            }
        }
      }
    }

    footer: PlasmaExtras.PlasmoidHeading {
        position: PlasmaComponents3.ToolBar.Footer
        visible: full.syncState !== "missing"
        contentItem: Flow {
            spacing: Kirigami.Units.smallSpacing

            PlasmaComponents3.Button {
                icon.name: "view-refresh"
                text: full.syncing ? Lang.i18n("Syncing…")
                    : full.syncState === "error" ? Lang.i18n("Try again") : Lang.i18n("Sync now")
                enabled: full.m.serviceActive && !full.syncing && full.source.busyAction === ""
                onClicked: full.source.act("now")
            }
            PlasmaComponents3.Button {
                icon.name: full.m.serviceActive ? "media-playback-pause" : "media-playback-start"
                text: full.m.serviceActive ? Lang.i18n("Pause") : Lang.i18n("Resume")
                enabled: full.source.busyAction === ""
                onClicked: full.source.act(full.m.serviceActive ? "pause" : "resume")
            }
            PlasmaComponents3.ToolButton {
                icon.name: "folder-open"
                text: Lang.i18n("Open folder")
                enabled: full.m.localRoot !== ""
                onClicked: full.source.open("xdg-open " + Status.shellQuote(full.m.localRoot))
            }
            PlasmaComponents3.ToolButton {
                icon.name: "internet-web-browser"
                text: Lang.i18n("Drive")
                PlasmaComponents3.ToolTip.text: Lang.i18n("Open Google Drive in the browser")
                PlasmaComponents3.ToolTip.visible: hovered
                onClicked: Qt.openUrlExternally("https://drive.google.com/")
            }
            PlasmaComponents3.ToolButton {
                icon.name: "text-x-log"
                text: Lang.i18n("Log")
                PlasmaComponents3.ToolTip.text: Lang.i18n("Open the sync log")
                PlasmaComponents3.ToolTip.visible: hovered
                enabled: full.m.logPath !== ""
                onClicked: full.source.open("xdg-open " + Status.shellQuote(full.m.logPath))
            }
        }
    }
}
