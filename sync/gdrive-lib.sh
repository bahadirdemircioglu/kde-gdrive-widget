# gdrive-sync ve gdrive-syncd tarafindan "source" edilir: ayarlari okur.
# Ayarlar ~/.config/gdrive-sync/config dosyasinda (gdrive-setup yazar). Dosya calistirilmaz,
# sadece bilinen KEY=deger satirlari okunur. GDRIVE_* ortam degiskenleri onceliklidir.
# shellcheck shell=bash
CONF_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/gdrive-sync"

C_REMOTE="" C_PATH="" C_LOCAL="" C_MODE=""
if [ -f "$CONF_DIR/config" ]; then
  while IFS= read -r line || [ -n "$line" ]; do
    case "${line%%=*}" in
      REMOTE) C_REMOTE="${line#*=}" ;;
      REMOTE_PATH) C_PATH="${line#*=}" ;;
      LOCAL) C_LOCAL="${line#*=}" ;;
      MODE) C_MODE="${line#*=}" ;;
    esac
  done <"$CONF_DIR/config"
fi
REMOTE="${GDRIVE_REMOTE:-${C_REMOTE:-gdrive:}${C_PATH}}"   # rclone uzak adi + Drive klasoru
LOCAL="${GDRIVE_LOCAL:-${C_LOCAL:-$HOME/GoogleDrive}}"
MODE="${GDRIVE_MODE:-${C_MODE:-twoway}}"
