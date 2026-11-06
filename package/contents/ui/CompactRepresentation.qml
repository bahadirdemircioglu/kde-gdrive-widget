import QtQuick

import org.kde.plasma.plasmoid

// Panel: cloud + state badge; click toggles the popup.
MouseArea {
    id: compactRoot

    property PlasmoidItem plasmoidItem
    property var source
    property bool wasExpanded: false

    hoverEnabled: true
    acceptedButtons: Qt.LeftButton
    onPressed: wasExpanded = plasmoidItem.expanded
    onClicked: plasmoidItem.expanded = !wasExpanded

    Accessible.name: plasmoidItem ? plasmoidItem.toolTipMainText : ""
    Accessible.description: plasmoidItem ? plasmoidItem.toolTipSubText : ""
    Accessible.role: Accessible.Button

    CloudIcon {
        anchors.fill: parent
        syncState: compactRoot.source ? compactRoot.source.syncState : "missing"
        active: compactRoot.containsMouse
    }
}
