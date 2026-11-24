#!/usr/bin/env bash
# One-time root setup for the NI GPIB-USB-HS on Ubuntu (kernel built without CONFIG_GPIB).
#   sudo bash setup_gpib.sh
# - installs linux-gpib userspace (libgpib, gpib_config, ibtest, python3-gpib)
# - builds/installs the mainline gpib_common + ni_usb_gpib kernel modules via DKMS
# - installs /etc/gpib.conf, creates the 'gpib' group, loads the driver, configures /dev/gpib0
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_USER="${SUDO_USER:?run this script with sudo from your normal user account}"
PKG=gpib-ni-usb
VER=7.0

[[ $EUID -eq 0 ]] || { echo "Run with sudo"; exit 1; }

echo "==> Installing userspace packages"
apt-get install -y gpib-user-tools libgpib0 libgpib-bin libgpib-dev python3-gpib dkms

echo "==> Installing kernel modules via DKMS"
if dkms status -m "$PKG" -v "$VER" 2>/dev/null | grep -q .; then
    dkms remove -m "$PKG" -v "$VER" --all || true
fi
rm -rf "/usr/src/$PKG-$VER"
mkdir -p "/usr/src/$PKG-$VER"
cp -r "$HERE/driver/common" "$HERE/driver/ni_usb" "$HERE/driver/include" \
      "$HERE/driver/Kbuild" "$HERE/driver/dkms.conf" "/usr/src/$PKG-$VER/"
dkms add -m "$PKG" -v "$VER"
for k in /lib/modules/*/build; do
    kver="$(basename "$(dirname "$k")")"
    echo "    building for $kver"
    dkms install -m "$PKG" -v "$VER" -k "$kver" || echo "    WARNING: build failed for $kver"
done

echo "==> Installing /etc/gpib.conf"
[[ -f /etc/gpib.conf && ! -f /etc/gpib.conf.orig ]] && cp /etc/gpib.conf /etc/gpib.conf.orig
install -m 0644 "$HERE/gpib.conf" /etc/gpib.conf

echo "==> Group 'gpib' for /dev/gpib* access"
getent group gpib >/dev/null || groupadd gpib
usermod -a -G gpib "$TARGET_USER"

echo "==> Load modules at boot"
echo "ni_usb_gpib" > /etc/modules-load.d/gpib.conf

echo "==> Loading driver"
udevadm control --reload-rules
modprobe ni_usb_gpib
sleep 3
udevadm settle || true

# udev normally runs gpib_config automatically; run it explicitly as well (harmless if already done)
if ! gpib_config --minor 0; then
    echo "    gpib_config failed; retrying once after 2s"
    sleep 2
    gpib_config --minor 0 || echo "    WARNING: gpib_config failed (it may already be configured by udev)"
fi

echo "==> Status"
lsmod | grep -E "gpib|ni_usb" || true
ls -l /dev/gpib0 || true
dmesg | grep -iE "gpib|ni_usb" | tail -15 || true
echo
echo "Done. '$TARGET_USER' was added to group 'gpib' (log out/in, or use 'sg gpib -c <cmd>' until then)."
