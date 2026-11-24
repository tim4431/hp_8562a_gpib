#!/usr/bin/env python3
"""HP 8562A spectrum analyzer over GPIB (linux-gpib + NI GPIB-USB-HS).

Usage:
    python3 hp8562a.py                 # identify + print current settings and peak marker
    python3 hp8562a.py --scan          # list all GPIB addresses that respond
    python3 hp8562a.py --trace a.csv   # single sweep, save trace A (freq_Hz, level) to CSV
    python3 hp8562a.py --cmd "CF?"     # send a raw command (queries ending in '?' print the reply)
"""
import argparse
import csv
import sys

import gpib

DEFAULT_PAD = 18  # HP 8562A factory default HP-IB address
TRACE_POINTS = 601


def _bytes(s):
    return s.encode("ascii") if isinstance(s, str) else s


def scan(board=0):
    """Return the list of primary addresses (1-30) with a listener present.

    The NI USB adapters report "no listeners" (ENOL) as an error instead of
    returning False, both for an empty address and when no device at all is
    handshaking on the bus; treat that as "not present".
    """
    found = []
    for pad in range(1, 31):
        try:
            if gpib.listener(board, pad):
                found.append(pad)
        except gpib.GpibError as e:
            if "no listeners" not in str(e):
                raise
    return found


class HP8562A:
    def __init__(self, board=0, pad=DEFAULT_PAD, timeout=gpib.T10s):
        self.h = gpib.dev(board, pad, 0, timeout, 1, 0)
        gpib.clear(self.h)  # selected device clear: resets the HP-IB parser

    def close(self):
        if self.h is not None:
            gpib.ibloc(self.h)  # return front panel to local
            gpib.close(self.h)
            self.h = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # --- raw I/O ---------------------------------------------------------
    def write(self, cmd):
        gpib.write(self.h, _bytes(cmd))

    def read_raw(self, n=1 << 16):
        return gpib.read(self.h, n)

    def read(self, n=1 << 16):
        return self.read_raw(n).decode("ascii", "replace").strip()

    def query(self, cmd, n=1 << 16):
        self.write(cmd)
        return self.read(n)

    def query_float(self, cmd):
        return float(self.query(cmd))

    # --- identification ---------------------------------------------------
    def idn(self):
        return self.query("ID?")

    def revision(self):
        return self.query("REV?")

    # --- frequency / amplitude settings (Hz, dBm) ---------------------------
    @property
    def center(self):
        return self.query_float("CF?")

    @center.setter
    def center(self, hz):
        self.write(f"CF {hz:.6f}HZ;")

    @property
    def span(self):
        return self.query_float("SP?")

    @span.setter
    def span(self, hz):
        self.write(f"SP {hz:.6f}HZ;")

    @property
    def start(self):
        return self.query_float("FA?")

    @start.setter
    def start(self, hz):
        self.write(f"FA {hz:.6f}HZ;")

    @property
    def stop(self):
        return self.query_float("FB?")

    @stop.setter
    def stop(self, hz):
        self.write(f"FB {hz:.6f}HZ;")

    @property
    def ref_level(self):
        return self.query_float("RL?")

    @ref_level.setter
    def ref_level(self, dbm):
        self.write(f"RL {dbm:.2f}DB;")

    @property
    def rbw(self):
        return self.query_float("RB?")

    @rbw.setter
    def rbw(self, hz):
        self.write(f"RB {hz:.0f}HZ;")

    @property
    def vbw(self):
        return self.query_float("VB?")

    @vbw.setter
    def vbw(self, hz):
        self.write(f"VB {hz:.0f}HZ;")

    @property
    def sweep_time(self):
        return self.query_float("ST?")

    @property
    def attenuation(self):
        return self.query_float("AT?")

    # --- sweeping / traces -------------------------------------------------
    def single_sweep(self):
        """Take one sweep and block until it has finished."""
        self.write("SNGLS;TS;")
        return self.query("DONE?")

    def continuous(self):
        self.write("CONTS;")

    def trace(self, which="A"):
        """Return (freqs_Hz, levels) for trace A or B, levels in reference-level units (dBm)."""
        self.write("TDF P;")
        raw = self.query(f"TR{which}?", n=TRACE_POINTS * 20)
        levels = [float(v) for v in raw.replace("\r", "").replace("\n", "").split(",") if v]
        fa, fb = self.start, self.stop
        n = len(levels)
        step = (fb - fa) / (n - 1) if n > 1 else 0.0
        freqs = [fa + i * step for i in range(n)]
        return freqs, levels

    def peak(self):
        """Place marker on the highest signal; return (freq_Hz, amplitude)."""
        self.write("MKPK HI;")
        return self.query_float("MKF?"), self.query_float("MKA?")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--board", type=int, default=0, help="GPIB board index (/dev/gpibN)")
    ap.add_argument("--pad", type=int, default=DEFAULT_PAD, help="instrument primary address")
    ap.add_argument("--scan", action="store_true", help="scan the bus for listeners and exit")
    ap.add_argument("--trace", metavar="CSV", help="take a single sweep and save trace A")
    ap.add_argument("--cmd", help="send a raw command string")
    args = ap.parse_args()

    if args.scan:
        found = scan(args.board)
        if found:
            print("Listeners at addresses:", found)
            return 0
        print("No listeners found. If every address fails, no device is handshaking on the bus:")
        print("check the instrument is powered on and the GPIB cable is seated at both ends.")
        return 1

    with HP8562A(args.board, args.pad) as sa:
        if args.cmd:
            if args.cmd.rstrip(";").endswith("?"):
                print(sa.query(args.cmd))
            else:
                sa.write(args.cmd)
            return 0

        print("ID        :", sa.idn())
        print("Revision  :", sa.revision())
        print(f"Center    : {sa.center / 1e6:.6f} MHz")
        print(f"Span      : {sa.span / 1e6:.6f} MHz")
        print(f"Start/Stop: {sa.start / 1e6:.6f} / {sa.stop / 1e6:.6f} MHz")
        print(f"Ref level : {sa.ref_level:.2f} dBm")
        print(f"RBW / VBW : {sa.rbw:g} / {sa.vbw:g} Hz")
        print(f"Sweep time: {sa.sweep_time:g} s")
        print(f"Atten     : {sa.attenuation:g} dB")

        if args.trace:
            sa.single_sweep()
            freqs, levels = sa.trace("A")
            with open(args.trace, "w", newline="") as f:
                w = csv.writer(f)
                w.writerow(["freq_Hz", "level"])
                w.writerows(zip(freqs, levels))
            print(f"Saved {len(levels)} points to {args.trace}")

        f, a = sa.peak()
        print(f"Peak      : {f / 1e6:.6f} MHz, {a:.2f} dBm")
        if args.trace:
            sa.continuous()
    return 0


if __name__ == "__main__":
    sys.exit(main())
