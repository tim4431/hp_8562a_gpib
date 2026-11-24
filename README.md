# hp_8562a_gpib

Control an **HP 8562A spectrum analyzer** from Linux through a **National Instruments GPIB-USB-HS** adapter,
using the open-source [linux-gpib](https://linux-gpib.sourceforge.io/) stack.

Developed on: Ubuntu 26.04, kernel 7.0.0-42-generic, NI GPIB-USB-HS (USB `3923:709b`).

## Why a driver build is needed

The linux-gpib drivers are part of the mainline kernel (`drivers/gpib` in v7.0),
but Ubuntu's kernel is built with `CONFIG_GPIB` unset. `driver/` contains the kernel v7.0
`gpib_common` core and `ni_usb_gpib` driver sources plus a Kbuild/DKMS wrapper, so they can be built
out-of-tree against the distro kernel headers. DKMS rebuilds them automatically on kernel upgrades.
Secure Boot must be disabled (or the modules signed with an enrolled MOK).

Ubuntu's packaged userspace (`libgpib0`, `gpib-user-tools`, `python3-gpib`, linux-gpib-user 4.3.7)
uses an ioctl ABI identical to the mainline kernel headers, so no userspace build is needed.

## Setup

```bash
sudo bash setup_gpib.sh
```

This installs the userspace packages, builds/installs the modules via DKMS for every installed kernel,
installs [`gpib.conf`](gpib.conf) to `/etc/gpib.conf`, creates the `gpib` group (and adds you to it),
autoloads `ni_usb_gpib` at boot, and configures `/dev/gpib0`.
Log out and back in for the group membership to take effect.

Notes:
- `ni_usb_gpib: unexpected data: buffer[6]=0x12 ...` warnings in `dmesg` during init are harmless
  for this adapter firmware; look for `attached to gpib0`.
- Rebuild manually (without DKMS): `make -C driver`.

## Usage

```bash
python3 hp8562a.py --scan            # list responding GPIB addresses
python3 hp8562a.py                   # ID, settings, peak marker (default address 18)
python3 hp8562a.py --trace a.csv     # single sweep, save trace A (601 points) to CSV
python3 hp8562a.py --cmd "CF 1GHZ;"  # raw command; queries ending in '?' print the reply
python3 hp8562a.py --pad 19 ...      # if the analyzer is not at address 18
```

From Python:

```python
from hp8562a import HP8562A

with HP8562A(board=0, pad=18) as sa:
    print(sa.idn())
    sa.center = 1e9
    sa.span = 10e6
    sa.single_sweep()
    freqs, levels = sa.trace("A")
    print(sa.peak())
```

The instrument's HP-IB address is shown on the analyzer under **CONFIG → HP-IB ADRS**.

## License

`driver/` is taken from the Linux kernel and is licensed GPL-2.0 (see the SPDX headers in each file).
