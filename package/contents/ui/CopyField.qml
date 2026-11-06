import QtQuick
import QtQuick.Layouts

import org.kde.plasma.components as PlasmaComponents3

// A read-only command with a copy button (commands are shown, never run by the widget).
RowLayout {
    id: copyField

    property string text: ""

    PlasmaComponents3.TextField {
        id: field
        Layout.fillWidth: true
        readOnly: true
        text: copyField.text
        font.family: "monospace"
    }
    PlasmaComponents3.ToolButton {
        icon.name: "edit-copy"
        display: PlasmaComponents3.AbstractButton.IconOnly
        text: Lang.i18n("Copy")
        PlasmaComponents3.ToolTip.text: text
        PlasmaComponents3.ToolTip.visible: hovered
        onClicked: {
            field.selectAll();
            field.copy();
            field.deselect();
        }
    }
}
