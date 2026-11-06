import QtQuick

import org.kde.plasma.plasmoid
import org.kde.plasma.core as PlasmaCore
import org.kde.kirigami as Kirigami

import "logic/Status.js" as Status

PlasmoidItem {
    id: root

    readonly property bool inPanel: Plasmoid.formFactor === PlasmaCore.Types.Horizontal
                                    || Plasmoid.formFactor === PlasmaCore.Types.Vertical

    preferredRepresentation: inPanel ? compactRepresentation : fullRepresentation
    readonly property string desktopBackground: Plasmoid.configuration.desktopBackground
    Plasmoid.backgroundHints: desktopBackground === "translucent" ? PlasmaCore.Types.TranslucentBackground
        : desktopBackground === "none" ? PlasmaCore.Types.NoBackground
        : PlasmaCore.Types.DefaultBackground | PlasmaCore.Types.ConfigurableBackground
    switchWidth: Kirigami.Units.gridUnit * 10
    switchHeight: Kirigami.Units.gridUnit * 8

    // an error asks for attention; everything else is a normal, visible status
    Plasmoid.status: status.syncState === "error" ? PlasmaCore.Types.NeedsAttentionStatus : PlasmaCore.Types.ActiveStatus

    compactRepresentation: CompactRepresentation {
        plasmoidItem: root
        source: status
    }
    fullRepresentation: FullRepresentation {
        plasmoidItem: root
        source: status
    }

    toolTipMainText: Lang.i18n("Google Drive")
    toolTipSubText: Texts.summary(status.model, status.nowMs)

    Plasmoid.contextualActions: [
        PlasmaCore.Action {
            text: Lang.i18n("Sync now")
            icon.name: "view-refresh"
            enabled: status.model.serviceActive && status.syncState !== "syncing"
            onTriggered: status.act("now")
        },
        PlasmaCore.Action {
            text: status.model.serviceActive ? Lang.i18n("Pause syncing") : Lang.i18n("Resume syncing")
            icon.name: status.model.serviceActive ? "media-playback-pause" : "media-playback-start"
            enabled: status.syncState !== "missing"
            onTriggered: status.act(status.model.serviceActive ? "pause" : "resume")
        },
        PlasmaCore.Action {
            text: Lang.i18n("Open Google Drive in the browser")
            icon.name: "internet-web-browser"
            onTriggered: Qt.openUrlExternally("https://drive.google.com/")
        }
    ]

    // Language: one Lang object serves every widget in this Plasma session, so the widgets
    // share the setting. A widget that loads later adopts a language another one already set.
    function applyLanguage() {
        var mine = Plasmoid.configuration.language;
        if (!Lang.configured) {
            Lang.configured = true;
            Lang.code = mine;
        } else if (mine !== "" && Lang.code === "") {
            Lang.code = mine;
        } else if (mine !== Lang.code) {
            Plasmoid.configuration.language = Lang.code;
        }
    }
    readonly property string configuredLanguage: Plasmoid.configuration.language
    onConfiguredLanguageChanged: Lang.code = configuredLanguage
    Component.onCompleted: applyLanguage()
    Connections {
        target: Lang
        function onCodeChanged() {
            if (Plasmoid.configuration.language !== Lang.code) {
                Plasmoid.configuration.language = Lang.code;
            }
        }
    }

    StatusSource {
        id: status
        helper: Plasmoid.configuration.helperCommand
        // on the desktop the list is always visible, so poll as if the popup were open
        expanded: root.expanded || !root.inPanel
    }
}
