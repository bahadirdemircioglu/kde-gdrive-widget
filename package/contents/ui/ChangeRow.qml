import QtQuick
import QtQuick.Layouts

import org.kde.plasma.components as PlasmaComponents3
import org.kde.kirigami as Kirigami

import "logic/Status.js" as Status

// One changed file: direction icon, name, folder, time (or done/queued while syncing).
PlasmaComponents3.ItemDelegate {
    id: row

    property var change: ({ kind: "up", path: "", at: "", done: false })
    property bool live: false
    property double nowMs: Date.now()

    readonly property var parts: Status.splitPath(change.path)

    signal openRequested(var change)

    width: ListView.view ? ListView.view.width : implicitWidth
    onClicked: openRequested(change)

    Accessible.name: parts.name

    PlasmaComponents3.ToolTip.text: change.path
    PlasmaComponents3.ToolTip.visible: hovered
    PlasmaComponents3.ToolTip.delay: Kirigami.Units.toolTipDelay

    contentItem: RowLayout {
        spacing: Kirigami.Units.smallSpacing * 2

        Kirigami.Icon {
            Layout.preferredWidth: Kirigami.Units.iconSizes.smallMedium
            Layout.preferredHeight: Kirigami.Units.iconSizes.smallMedium
            source: Status.kindIcon(row.change.kind)
            opacity: row.live && !row.change.done ? 0.5 : 1
        }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 0
            PlasmaComponents3.Label {
                Layout.fillWidth: true
                text: row.parts.name
                textFormat: Text.PlainText
                elide: Text.ElideMiddle
                font.strikeout: row.change.kind === "deleted_local" || row.change.kind === "deleted_remote"
            }
            PlasmaComponents3.Label {
                Layout.fillWidth: true
                visible: text !== ""
                text: row.parts.dir
                textFormat: Text.PlainText
                elide: Text.ElideMiddle
                font: Kirigami.Theme.smallFont
                opacity: 0.7
            }
        }
        PlasmaComponents3.Label {
            text: row.live ? (row.change.done ? Lang.i18nc("file in a running sync", "done") : Lang.i18nc("file in a running sync", "queued"))
                           : Texts.when(row.change.at, row.nowMs)
            font: Kirigami.Theme.smallFont
            opacity: 0.7
        }
    }
}
