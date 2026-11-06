#!/usr/bin/env bash
# Geliştirici kurulumu: komutları (~/.local/bin) bu klasöre bağlar ve servisi bu klasörden çalıştırır.
# Son kullanıcı için: "gdrive-setup" (terminal) ya da Plasma widget'ındaki kurulum sihirbazı.
# Kullanım: ./install.sh (sudo ile değil, kendi kullanıcınızla)
set -euo pipefail

die() { echo "Hata: $*" >&2; exit 1; }

[[ $EUID -ne 0 ]] || die "Kurulumu sudo olmadan, kendi kullanıcınızla çalıştırın."
SCRIPT_DIR=$(dirname -- "$(readlink -f -- "${BASH_SOURCE[0]}")")
for script in gdrive-sync gdrive-syncd gdrive-lib.sh; do
  [[ -f "$SCRIPT_DIR/$script" ]] || die "$SCRIPT_DIR/$script bulunamadı."
  bash -n "$SCRIPT_DIR/$script"
done
for tool in systemctl flock python3; do
  command -v "$tool" >/dev/null || die "$tool gerekli. Bu kurulum systemd kullanan Linux içindir."
done
systemctl --user show-environment >/dev/null || die "systemd kullanıcı oturumuna erişilemiyor. Kendi oturumunuzda çalıştırın."

SETUP=(python3 "$SCRIPT_DIR/gdrive-setup")
STATE="${GDRIVE_STATE:-$HOME/.local/state/gdrive-sync}"

configured() {
  python3 - "$SCRIPT_DIR" <<'EOF'
import sys
sys.path.insert(0, sys.argv[1])
import gdrive_common as g
sys.exit(0 if g.effective() else 1)
EOF
}

if configured || [[ -f "$STATE/initialized" ]]; then
  # Çalışan (0.1.0) kurulum: servis yazılır, ayar dosyası mevcut değerlerden oluşturulur. Senkron yok.
  "${SETUP[@]}" install-service --dev >/dev/null
  "${SETUP[@]}" migrate >/dev/null
  configured || die "Ayar dosyası oluşturulamadı."
  out=$("${SETUP[@]}" install-service --dev --start --json)
  case "$out" in *'"ok": false'*) die "Servis başlatılamadı: $out" ;; esac
  case "$out" in *'"skippedLinks": []'*) ;; *) echo "Uyarı: ~/.local/bin altında kendi dosyanız var; dokunulmadı. ($out)" >&2 ;; esac
  echo "Kurulum tamamlandı. Servis bu klasörden çalışıyor: $SCRIPT_DIR"
  echo "Durum: gdrive-status show   |   Günlük: tail -f $STATE/sync.log"
else
  [[ -t 0 ]] || die "Henüz ayar yok. Terminalde çalıştırın: GDRIVE_DEV=1 python3 $SCRIPT_DIR/gdrive-setup"
  echo "Henüz ayar yok; kurulum sihirbazı açılıyor."
  GDRIVE_DEV=1 exec "${SETUP[@]}"
fi
