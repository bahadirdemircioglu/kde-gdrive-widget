#!/usr/bin/env bash
# Gelistirici kurulumu: komutlari (~/.local/bin) bu klasore baglar ve servisi bu klasorden calistirir.
# Son kullanici icin: "gdrive-setup" (terminal) ya da Plasma widget'indaki kurulum sihirbazi.
# Kullanim: ./install.sh (sudo ile degil, kendi kullanicinizla)
set -euo pipefail

die() { echo "Hata: $*" >&2; exit 1; }

[[ $EUID -ne 0 ]] || die "Kurulumu sudo olmadan, kendi kullanicinizla calistirin."
SCRIPT_DIR=$(dirname -- "$(readlink -f -- "${BASH_SOURCE[0]}")")
for script in gdrive-sync gdrive-syncd gdrive-lib.sh; do
  [[ -f "$SCRIPT_DIR/$script" ]] || die "$SCRIPT_DIR/$script bulunamadi."
  bash -n "$SCRIPT_DIR/$script"
done
for tool in systemctl flock python3; do
  command -v "$tool" >/dev/null || die "$tool gerekli. Bu kurulum systemd kullanan Linux icindir."
done
systemctl --user show-environment >/dev/null || die "systemd kullanici oturumuna erisilemiyor. Kendi oturumunuzda calistirin."

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
  # Calisan (0.1.0) kurulum: servis yazilir, ayar dosyasi mevcut degerlerden olusturulur. Senkron yok.
  "${SETUP[@]}" install-service --dev >/dev/null
  "${SETUP[@]}" migrate >/dev/null
  configured || die "Ayar dosyasi olusturulamadi."
  out=$("${SETUP[@]}" install-service --dev --start --json)
  case "$out" in *'"ok": false'*) die "Servis baslatilamadi: $out" ;; esac
  case "$out" in *'"skippedLinks": []'*) ;; *) echo "Uyari: ~/.local/bin altinda kendi dosyaniz var; dokunulmadi. ($out)" >&2 ;; esac
  echo "Kurulum tamamlandi. Servis bu klasorden calisiyor: $SCRIPT_DIR"
  echo "Durum: gdrive-status show   |   Gunluk: tail -f $STATE/sync.log"
else
  [[ -t 0 ]] || die "Henuz ayar yok. Terminalde calistirin: GDRIVE_DEV=1 python3 $SCRIPT_DIR/gdrive-setup"
  echo "Henuz ayar yok; kurulum sihirbazi aciliyor."
  GDRIVE_DEV=1 exec "${SETUP[@]}"
fi
