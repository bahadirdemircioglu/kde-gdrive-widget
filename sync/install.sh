#!/usr/bin/env bash
# Kullanım: ./install.sh (sudo ile değil, kendi kullanıcınızla çalıştırın)
set -euo pipefail

die() { echo "Hata: $*" >&2; exit 1; }
as_root() {
  command -v sudo >/dev/null || die "Bu adım için sudo gerekli: $*"
  sudo "$@"
}

[[ $EUID -ne 0 ]] || die "Kurulumu sudo olmadan, kendi kullanıcınızla çalıştırın."
SCRIPT_DIR=$(dirname -- "$(readlink -f -- "${BASH_SOURCE[0]}")")
for script in gdrive-sync gdrive-syncd; do
  [[ -f "$SCRIPT_DIR/$script" ]] || die "$SCRIPT_DIR/$script bulunamadı."
  bash -n "$SCRIPT_DIR/$script"
done
for tool in systemctl loginctl flock; do
  command -v "$tool" >/dev/null || die "$tool gerekli. Bu kurulum systemd kullanan Linux içindir."
done
systemctl --user show-environment >/dev/null || die "systemd kullanıcı oturumuna erişilemiyor. Kendi oturumunuzda çalıştırın."

packages=()
command -v rclone >/dev/null || packages+=(rclone)
command -v inotifywait >/dev/null || packages+=(inotify-tools)
if ((${#packages[@]})); then
  echo "Eksik paketler kuruluyor: ${packages[*]}"
  if command -v pacman >/dev/null; then
    as_root pacman -S --needed "${packages[@]}"
  elif command -v apt-get >/dev/null; then
    as_root apt-get update
    as_root apt-get install "${packages[@]}"
  elif command -v dnf >/dev/null; then
    as_root dnf install "${packages[@]}"
  elif command -v zypper >/dev/null; then
    as_root zypper install "${packages[@]}"
  else
    die "Paket yöneticisi tanınmadı. Şunları kurup tekrar çalıştırın: ${packages[*]}"
  fi
fi
for tool in rclone inotifywait; do
  command -v "$tool" >/dev/null || die "$tool kurulamadı."
done

has_remote() { rclone listremotes | grep -Fxq 'gdrive:'; }
if ! has_remote; then
  [[ -t 0 ]] || die "gdrive: bağlantısı yok. Terminalde 'rclone config' ile gdrive adlı Google Drive bağlantısını oluşturun."
  echo "Google Drive bağlantısı gerekiyor. Açılan menüde 'gdrive' adında Google Drive bağlantısı oluşturun."
  rclone config
  has_remote || die "gdrive: bağlantısı oluşturulmadı; servis kurulmadı."
fi

# Linger, kullanıcı oturum açmasa da servisin makine açılışında başlamasını sağlar.
user_name=$(id -un)
if [[ $(loginctl show-user "$user_name" -p Linger --value) != yes ]]; then
  echo "Oturum açılmadan çalışma etkinleştiriliyor..."
  loginctl enable-linger "$user_name" || as_root loginctl enable-linger "$user_name"
fi
[[ $(loginctl show-user "$user_name" -p Linger --value) == yes ]] || die "Linger etkinleştirilemedi."

chmod +x "$SCRIPT_DIR/gdrive-sync" "$SCRIPT_DIR/gdrive-syncd"
for extra in gdrive-status gdrive-nfc; do
  [[ -f "$SCRIPT_DIR/$extra" ]] && chmod +x "$SCRIPT_DIR/$extra"
done

# Komutlar ~/.local/bin altinda (widget gdrive-status'u oradan cagirir). Kullanicinin
# kendi dosyasi varsa ustune yazilmaz; sadece bizim (ya da kirik) sembolik baglar yenilenir.
bin_dir="$HOME/.local/bin"
mkdir -p "$bin_dir"
for cmd in gdrive-status gdrive-sync gdrive-nfc; do
  [[ -f "$SCRIPT_DIR/$cmd" ]] || continue
  link="$bin_dir/$cmd"
  if [[ -e "$link" && ! -L "$link" ]]; then
    echo "Uyari: $link zaten var ve sembolik bag degil; dokunulmadi." >&2
  else
    ln -sfn -- "$SCRIPT_DIR/$cmd" "$link"
  fi
done
mkdir -p "$HOME/GoogleDrive" "$HOME/.local/state/gdrive-sync"
unit_dir="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
mkdir -p "$unit_dir"
unit="$unit_dir/gdrive-sync.service"
temp_unit=$(mktemp "$unit_dir/.gdrive-sync.XXXXXX")
trap 'rm -f -- "$temp_unit"' EXIT

# systemd ExecStart, tırnak içinde bile % ve $ karakterlerini yorumlar.
exec_path="$SCRIPT_DIR/gdrive-syncd"
[[ $exec_path != *$'\n'* && $exec_path != *$'\r'* ]] || die "Klasör yolunda satır sonu olamaz."
exec_path=${exec_path//\\/\\\\}
exec_path=${exec_path//\"/\\\"}
exec_path=${exec_path//%/%%}
exec_path=${exec_path//\$/\$\$}
cat > "$temp_unit" <<EOF
[Unit]
Description=Google Drive surekli iki yonlu senkron (rclone bisync)
After=network-online.target

[Service]
Type=simple
ExecStart="$exec_path"
Restart=always
RestartSec=30
Nice=10
IOSchedulingClass=idle
TimeoutStopSec=120

[Install]
WantedBy=default.target
EOF

changed=0
if ! cmp -s "$temp_unit" "$unit"; then
  [[ ! -f "$unit" ]] || cp -p -- "$unit" "$unit.bak"
  install -m 644 "$temp_unit" "$unit"
  changed=1
fi
systemctl --user daemon-reload
# Değişmeyen kurulumu tekrar çalıştırmak devam eden senkronu kesmez.
if ((changed)) && systemctl --user is-active --quiet gdrive-sync.service; then
  systemctl --user restart gdrive-sync.service
fi
systemctl --user enable --now gdrive-sync.service
systemctl --user is-enabled --quiet gdrive-sync.service
systemctl --user is-active --quiet gdrive-sync.service

echo "Kurulum tamamlandı. Servis çalışıyor ve her açılışta otomatik başlayacak."
echo "Script klasörünü taşır veya yeniden adlandırırsanız install.sh dosyasını tekrar çalıştırın."
echo "Durum: systemctl --user status gdrive-sync.service"
echo "Senkron günlüğü: tail -f ~/.local/state/gdrive-sync/sync.log"
