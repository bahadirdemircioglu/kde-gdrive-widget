import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts

import org.kde.kirigami as Kirigami
import org.kde.kcmutils as KCM

// Settings → General: language, list length, desktop background, helper command.
KCM.SimpleKCM {
    id: page

    property string cfg_language
    property string cfg_languageDefault: ""
    property int cfg_recentCount
    property int cfg_recentCountDefault: 7
    property string cfg_desktopBackground
    property string cfg_desktopBackgroundDefault: "standard"
    property string cfg_helperCommand
    property string cfg_helperCommandDefault: '"$HOME/.local/bin/gdrive-status"'

    Kirigami.FormLayout {
        QQC2.ComboBox {
            Kirigami.FormData.label: Lang.i18n("Language:")
            textRole: "text"
            valueRole: "value"
            model: [{ value: "", text: Lang.i18n("System default") }].concat(
                ["en"].concat(Lang.available).map(function (code) {
                    var name = Qt.locale(code).nativeLanguageName || code;
                    return { value: code, text: name.charAt(0).toUpperCase() + name.slice(1) };
                }))
            Component.onCompleted: currentIndex = Math.max(0, indexOfValue(page.cfg_language))
            onActivated: page.cfg_language = currentValue
        }

        QQC2.SpinBox {
            Kirigami.FormData.label: Lang.i18n("Recent changes shown:")
            from: 3
            to: 30
            value: page.cfg_recentCount
            onValueModified: page.cfg_recentCount = value
        }

        QQC2.ComboBox {
            Kirigami.FormData.label: Lang.i18n("Desktop background:")
            textRole: "text"
            valueRole: "value"
            model: [
                { value: "standard", text: Lang.i18n("Standard") },
                { value: "translucent", text: Lang.i18n("Translucent") },
                { value: "none", text: Lang.i18n("None") }
            ]
            Component.onCompleted: currentIndex = Math.max(0, indexOfValue(page.cfg_desktopBackground))
            onActivated: page.cfg_desktopBackground = currentValue
        }

        Item {
            Kirigami.FormData.isSection: true
        }

        QQC2.TextField {
            Kirigami.FormData.label: Lang.i18n("Status command:")
            Layout.preferredWidth: Kirigami.Units.gridUnit * 20
            text: page.cfg_helperCommand
            onTextEdited: page.cfg_helperCommand = text
        }
        QQC2.Label {
            Layout.maximumWidth: Kirigami.Units.gridUnit * 24
            wrapMode: Text.Wrap
            font.pointSize: Kirigami.Theme.smallFont.pointSize
            opacity: 0.7
            text: Lang.i18n("Runs in a shell; the widget appends show, now, pause or resume. Plasma's PATH usually lacks ~/.local/bin, so keep the full path.")
        }
    }
}
