import QtQuick
import QtQuick.Layouts

import org.kde.plasma.components as PlasmaComponents3
import org.kde.kirigami as Kirigami

import "logic/Status.js" as Status

// Four steps of a bisync run; the current one fills with the file progress while transferring.
ColumnLayout {
    id: strip

    property string phase: "listing"
    property var progress: null

    readonly property int current: Status.phaseIndex(phase)
    readonly property real fraction: progress && progress.total > 0 ? progress.done / progress.total : 0.3

    spacing: Kirigami.Units.smallSpacing

    RowLayout {
        Layout.fillWidth: true
        spacing: Kirigami.Units.smallSpacing

        Repeater {
            model: [
                Lang.i18nc("sync step", "Listing"),
                Lang.i18nc("sync step", "Comparing"),
                Lang.i18nc("sync step", "Transfer"),
                Lang.i18nc("sync step", "Saving")
            ]
            delegate: ColumnLayout {
                required property int index
                required property string modelData
                Layout.fillWidth: true
                Layout.preferredWidth: 1
                spacing: Kirigami.Units.smallSpacing

                Rectangle {
                    Layout.fillWidth: true
                    implicitHeight: 4
                    radius: 2
                    color: Qt.alpha(Kirigami.Theme.textColor, 0.15)

                    Rectangle {
                        anchors.left: parent.left
                        anchors.top: parent.top
                        anchors.bottom: parent.bottom
                        radius: 2
                        color: Kirigami.Theme.highlightColor
                        width: index < strip.current ? parent.width
                             : index > strip.current ? 0
                             : parent.width * (strip.current === 2 ? strip.fraction : 0.5)
                        Behavior on width {
                            NumberAnimation { duration: Kirigami.Units.longDuration }
                        }
                    }
                }
                PlasmaComponents3.Label {
                    Layout.fillWidth: true
                    text: modelData
                    elide: Text.ElideRight
                    font.pointSize: Kirigami.Theme.smallFont.pointSize
                    opacity: index === strip.current ? 1 : 0.7
                    font.weight: index === strip.current ? Font.DemiBold : Font.Normal
                }
            }
        }
    }

    PlasmaComponents3.Label {
        visible: strip.current === 2 && !!strip.progress && strip.progress.total > 0
        text: strip.progress ? Lang.i18np("%2 of %1 file transferred", "%2 of %1 files transferred",
                                          strip.progress.total, strip.progress.done) : ""
    }
}
