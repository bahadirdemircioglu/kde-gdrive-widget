import QtQuick
import QtQuick.Layouts

import org.kde.plasma.components as PlasmaComponents3
import org.kde.kirigami as Kirigami

import "logic/Status.js" as Status

// What went wrong, in plain words, what to do, and the raw log lines (copyable).
Rectangle {
    id: card

    property var lastError: null
    property string lastSuccessAt: ""
    property string remote: ""
    property double nowMs: Date.now()

    readonly property string code: Status.errorCode(lastError)
    readonly property var lines: lastError ? lastError.lines : []

    signal setupRequested()

    implicitHeight: body.implicitHeight + Kirigami.Units.largeSpacing * 2
    radius: Kirigami.Units.cornerRadius
    color: Qt.alpha(Kirigami.Theme.negativeBackgroundColor, 0.6)
    border.color: Qt.alpha(Kirigami.Theme.negativeTextColor, 0.4)

    ColumnLayout {
        id: body
        anchors.fill: parent
        anchors.margins: Kirigami.Units.largeSpacing
        spacing: Kirigami.Units.smallSpacing

        PlasmaComponents3.Label {
            Layout.fillWidth: true
            text: Texts.errorTitle(card.code)
            font.weight: Font.DemiBold
            color: Kirigami.Theme.negativeTextColor
            wrapMode: Text.Wrap
        }
        PlasmaComponents3.Label {
            Layout.fillWidth: true
            text: Texts.errorBody(card.code)
            wrapMode: Text.Wrap
        }
        PlasmaComponents3.Label {
            Layout.fillWidth: true
            text: Lang.i18n("What to do: %1", Texts.errorAdvice(card.code))
            wrapMode: Text.Wrap
        }
        PlasmaComponents3.Button {
            visible: card.code === "not_initialized"
            icon.name: "configure"
            text: Lang.i18n("Set up again…")
            onClicked: card.setupRequested()
        }
        RowLayout {
            Layout.fillWidth: true
            visible: Texts.errorCommand(card.code, card.remote) !== ""
            PlasmaComponents3.TextField {
                id: commandField
                Layout.fillWidth: true
                readOnly: true
                text: Texts.errorCommand(card.code, card.remote)
                font.family: "monospace"
            }
            PlasmaComponents3.ToolButton {
                icon.name: "edit-copy"
                display: PlasmaComponents3.AbstractButton.IconOnly
                text: Lang.i18n("Copy")
                PlasmaComponents3.ToolTip.text: text
                PlasmaComponents3.ToolTip.visible: hovered
                onClicked: {
                    commandField.selectAll();
                    commandField.copy();
                    commandField.deselect();
                }
            }
        }
        PlasmaComponents3.Label {
            Layout.fillWidth: true
            text: Lang.i18n("Last successful sync: %1", Texts.ago(card.lastSuccessAt, card.nowMs))
            font: Kirigami.Theme.smallFont
            opacity: 0.75
            wrapMode: Text.Wrap
        }

        RowLayout {
            Layout.fillWidth: true
            visible: card.lines.length > 0
            PlasmaComponents3.ToolButton {
                id: detailsButton
                checkable: true
                icon.name: checked ? "go-down" : "go-next"
                text: Lang.i18n("Details")
            }
            Item {
                Layout.fillWidth: true
            }
            PlasmaComponents3.ToolButton {
                visible: detailsButton.checked
                icon.name: "edit-copy"
                text: Lang.i18n("Copy")
                onClicked: {
                    clip.text = card.lines.join("\n");
                    clip.selectAll();
                    clip.copy();
                }
            }
        }
        PlasmaComponents3.Label {
            Layout.fillWidth: true
            visible: detailsButton.checked
            text: card.lines.join("\n")
            textFormat: Text.PlainText
            font.family: "monospace"
            font.pointSize: Kirigami.Theme.smallFont.pointSize
            wrapMode: Text.WrapAnywhere
        }
    }

    // clipboard access without extra modules
    TextEdit {
        id: clip
        visible: false
    }
}
