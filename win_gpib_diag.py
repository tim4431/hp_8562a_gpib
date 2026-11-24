#!/usr/bin/env python3
"""Find out what makes the HP 8562A restart on GPIB commands (Windows, NI-488.2).

Calls NI's ni4882.dll directly, so no linux-gpib code is involved. Only the
standard library is needed.

    python win_gpib_diag.py                 # bus lines + listener scan, sends no data
    python win_gpib_diag.py --list          # list the trigger tests
    python win_gpib_diag.py --test id_eoi   # run one trigger test
    python win_gpib_diag.py --all           # run every test, stopping to let it recover

A test counts as a crash when the analyzer stops acknowledging its address
afterwards. Watch the screen too: a fast restart could fall between two polls.
"""
import argparse
import ctypes
import sys
import time

# ni4882.h
ERR, TIMO = 0x8000, 0x4000
T1s, T3s = 11, 12
IbcREADDR, IbcAUTOPOLL, IbcSRE, IbcTIMING = 0x06, 0x07, 0x0B, 0x11
LINES = ["EOI", "ATN", "SRQ", "REN", "IFC", "NRFD", "NDAC", "DAV"]  # bit 15..8, valid bits 7..0
IBERR = ["EDVR", "ECIC", "ENOL", "EADR", "EARG", "ESAC", "EABO", "ENEB", "EDMA", "", "EOIP",
         "ECAP", "EFSO", "", "EBUS", "ESTB", "ESRQ", "", "", "", "ETAB", "ELCK"]

# name: (bytes to send or None, assert EOI, remote enable, device clear first, T1 timing, read reply)
# T1 timing: 1 = 2 us (slowest), 2 = 500 ns, 3 = 350 ns
TESTS = {
    "addr_only":   (None,        True,  True,  False, 1, False),  # REN + addressing, no data
    "clear_only":  (None,        True,  True,  True,  1, False),  # selected device clear, no data
    "partial":     (b"I",        False, True,  False, 1, False),  # incomplete word, unterminated
    "semicolon":   (b";",        True,  True,  False, 1, False),  # terminator, no command word
    "crlf":        (b"\r\n",     True,  True,  False, 1, False),
    "unknown":     (b"ZQX;",     True,  True,  False, 1, False),  # word in no command table
    "id_eoi":      (b"ID?",      True,  True,  False, 1, True),
    "id_semi":     (b"ID?;",     True,  True,  False, 1, True),
    "id_crlf":     (b"ID?\r\n",  False, True,  False, 1, True),
    "id_noread":   (b"ID?;",     True,  True,  False, 1, False),  # parse but never address to talk
    "id_fast":     (b"ID?;",     True,  True,  False, 2, True),
    "id_clear":    (b"ID?;",     True,  True,  True,  1, True),   # what hp8562a.py does
    "set_cf":      (b"CF 1GHZ;", True,  True,  False, 1, False),  # a set command, no reply
    "id_local":    (b"ID?;",     True,  False, False, 1, True),   # REN off
}


class Gpib:
    def __init__(self, board=0, dll=None):
        self.d = dll or ctypes.WinDLL("ni4882.dll")
        self.board = board

    def status(self):
        return int(self.d.Ibsta()) & 0xFFFF, int(self.d.Iberr()), int(self.d.Ibcnt())

    def check(self, what):
        sta, err, cnt = self.status()
        if sta & ERR:
            name = IBERR[err] if 0 <= err < len(IBERR) else str(err)
            raise RuntimeError(f"{what}: {name} (ibsta=0x{sta:04x}, sent/received {cnt})")
        return cnt

    def config(self, ud, opt, val):
        self.d.ibconfig(ud, opt, val)
        self.check(f"ibconfig 0x{opt:02x}")

    def lines(self):
        v = ctypes.c_short()
        self.d.iblines(self.board, ctypes.byref(v))
        self.check("iblines")
        bits = v.value & 0xFFFF
        return {n: bool(bits & (0x8000 >> i)) for i, n in enumerate(LINES) if bits & (0x80 >> i)}

    def listener(self, pad):
        """True/False; an empty bus reports ENOL instead of False."""
        v = ctypes.c_short()
        self.d.ibln(self.board, pad, 0, ctypes.byref(v))
        sta, err, _ = self.status()
        if sta & ERR:
            if err in (2, 14):  # ENOL, EBUS: nobody handshaking
                return False
            self.check(f"ibln {pad}")
        return bool(v.value)

    def open(self, pad, eot):
        ud = self.d.ibdev(self.board, pad, 0, T3s, int(eot), 0)
        self.check("ibdev")
        return ud

    def reset_bus(self):
        self.d.ibsic(self.board)
        self.check("ibsic")


def wait_recover(g, pad, limit):
    t0 = time.time()
    while time.time() - t0 < limit:
        if g.listener(pad):
            return time.time() - t0
        time.sleep(0.5)
    return None


def run_test(g, pad, name, watch=12.0):
    data, eot, ren, clear, timing, read = TESTS[name]
    print(f"\n[{name}] send={data!r} EOI={eot} REN={ren} SDC={clear} T1={timing}")
    if not g.listener(pad):
        print("  analyzer does not answer at this address before the test; skipped")
        return "skipped"
    note, reply = [], None
    ud = None
    try:
        g.reset_bus()
        g.config(g.board, IbcAUTOPOLL, 0)
        g.config(g.board, IbcTIMING, timing)
        g.config(g.board, IbcSRE, int(ren))
        ud = g.open(pad, eot)
        g.config(ud, IbcREADDR, 1)
        if clear:
            g.d.ibclr(ud)
            g.check("ibclr")
        note.append("REN line " + ("on" if g.lines().get("REN") else "off"))
        if data is not None:
            g.d.ibwrt(ud, data, len(data))
            note.append(f"wrote {g.check('ibwrt')}/{len(data)} bytes")
        if read:
            buf = ctypes.create_string_buffer(256)
            g.d.ibrd(ud, buf, 255)
            reply = buf.raw[:g.check("ibrd")]
            note.append(f"reply {reply!r}")
    except RuntimeError as e:
        note.append(str(e))

    # poll the address; losing it means the HP-IB chip was reset
    lost, polls, t0 = None, 0, time.time()
    while time.time() - t0 < watch:
        try:
            alive = g.listener(pad)
        except RuntimeError as e:
            note.append(str(e))
            alive = False
        polls += 1
        if not alive:
            lost = time.time() - t0
            break
        time.sleep(0.1)
    if ud is not None:
        if lost is None:
            g.d.ibclr(ud)  # flush any unfinished word so it cannot join the next test
        g.d.ibonl(ud, 0)

    if lost is not None:
        back = wait_recover(g, pad, 60)
        result = "CRASH"
        note.append(f"address lost after {lost:.1f} s, "
                    + (f"back {back:.1f} s later" if back is not None else "not back within 60 s"))
    elif read and not reply:
        result = "no reply"
    else:
        result = "ok"
    print(f"  {result}: " + "; ".join(note + [f"{polls} polls"]))
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--board", type=int, default=0)
    ap.add_argument("--pad", type=int, default=18, help="analyzer address (default 18)")
    ap.add_argument("--list", action="store_true", help="list tests and exit")
    ap.add_argument("--test", choices=TESTS, action="append", help="run this test (repeatable)")
    ap.add_argument("--all", action="store_true", help="run every test")
    args = ap.parse_args()

    if args.list:
        for n, t in TESTS.items():
            print(f"{n:12s} send={t[0]!r} EOI={t[1]} REN={t[2]} SDC={t[3]} T1={t[4]} read={t[5]}")
        return 0

    try:
        g = Gpib(args.board)
    except OSError as e:
        print(f"cannot load ni4882.dll: {e}\nNI-488.2 is not installed.")
        return 2

    try:
        g.reset_bus()
        print("Lines asserted:", [n for n, on in g.lines().items() if on] or "none")
        found = [p for p in range(1, 31) if g.listener(p)]
    except RuntimeError as e:
        print(f"board GPIB{args.board}: {e}")
        return 2
    print("Listeners     :", found or "none")

    names = list(TESTS) if args.all else (args.test or [])
    results = {}
    for n in names:
        try:
            results[n] = run_test(g, args.pad, n)
        except RuntimeError as e:  # adapter/driver trouble, not a verdict on the analyzer
            print(f"  bus error: {e}")
            results[n] = "bus error"
    if results:
        print("\nSummary")
        for n, r in results.items():
            print(f"  {n:12s} {r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
