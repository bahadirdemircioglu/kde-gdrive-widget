import QtQuick

import org.kde.kirigami as Kirigami

import "logic/Status.js" as Status

// The cloud with a state badge in its lower-right corner (panel and popup header).
Item {
    id: cloud

    property string syncState: "missing"
    property bool active: false

    Kirigami.Icon {
        anchors.fill: parent
        source: Qt.resolvedUrl("../icons/cloud.svg")
        isMask: true
        color: Kirigami.Theme.textColor
        active: cloud.active
        opacity: cloud.syncState === "paused" || cloud.syncState === "offline" ? 0.55 : 1
    }

    Kirigami.Icon {
        id: badge
        width: Math.max(Kirigami.Units.iconSizes.small * 0.6, Math.round(Math.min(cloud.width, cloud.height) * 0.5))
        height: width
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.rightMargin: -Math.round(width * 0.1)
        source: Status.badgeIcon(cloud.syncState)

        RotationAnimation on rotation {
            running: cloud.syncState === "syncing"
            loops: Animation.Infinite
            from: 0
            to: 360
            duration: 1600
            onRunningChanged: {
                if (!running) {
                    badge.rotation = 0;
                }
            }
        }
    }
}
