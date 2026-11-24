# HP 8562A restarts on GPIB commands: the 85620A module

**Cause:** the HP 85620A Mass Memory Module on the rear OPTION MODULE connector.
**Fix:** switch the analyzer off and remove the module. Found 2026-11-24.

## Symptom

With the module attached, the analyzer restarted whenever a GPIB command word was completed
(`ID?;`, for example). It never replied. Front-panel operation was normal.

The first diagnosis, from the Linux PC, blamed the A2 controller board. That was wrong: removing the
module fixed it, with no change to the analyzer itself.

## Equipment

| Item | Version |
|---|---|
| HP 8562A | firmware `REV?` = 870312, GPIB address 18 |
| HP 85620A module | label: Revision B, battery installed 9/90 |
| Adapter | NI GPIB-USB-HS (USB `3923:709b`) |
| Windows PC | Windows 11, NI-488.2 25.0 |

## Evidence

Same adapter and `win_gpib_diag.py` in both columns (NI-488.2 on Windows):

| Test | Module attached | Module removed |
|---|---|---|
| Address only, no data (`addr_only`) | ok | ok |
| Device clear (`clear_only`) | ok | ok |
| `I`, incomplete word (`partial`) | ok | ok |
| `;` alone (`semicolon`) | ok | ok |
| `ID?;` (`id_semi`) | **crash**: 4/4 bytes accepted, no reply | ok, `HP8562A` |
| Other command tests (`crlf`, `unknown`, `id_eoi`, `id_crlf`, `id_noread`, `id_fast`, `id_clear`, `set_cf`) | not run | ok |
| Remote-enable off (`id_local`) | not run | inconclusive, see below |
| 600 queries (`ID?` and `CF?`) | not run | no errors, 21.8 s |
| 10 traces of 601 points | not run | all complete, about 2.07 s each |

In the crash, the analyzer had stopped answering its address by the end of the 3 s read timeout and came
back 19 s later. The Linux PC saw the same crash through linux-gpib, so neither the driver nor the PC is
the cause.

The query and trace tests ran `hp8562a.py` unchanged, using a small stand-in for the linux-gpib Python
module on top of `ni4882.dll`. The stand-in is not in this repo.

`id_local` is inconclusive because the write failed with ENOL before any data was sent. On Linux, the
analyzer ignored commands with remote-enable off and did not crash.

## Why the module causes it

Table 1-1 of the [85620A manual][mmm] (page 1-4) lists the 8562A firmware each module revision needs:

| Module revision | 8562A firmware needed |
|---|---|
| A (890214), B (890524), C (910116) | 870728 and later |

This analyzer has 870312, which is older, so the pairing is unsupported. Per the same manual, with host
firmware 941028 or earlier the module's own firmware runs the module functions.

**Not proven:** a faulty module could cause the same thing. Its backup battery is from 1990, against a
quoted worst-case life of 1 year. To tell the two apart, try the module on an analyzer with supported
firmware. A new battery probably won't help here, because the firmware mismatch would remain.

## Removing the module

1. Check the module for anything you need (MODULE key). With a dead battery, its contents are lost at
   power-off.
2. **Switch the analyzer off.** HP warns that attaching or removing the module with the power on can
   damage both.
3. Turn the fastener a quarter turn and pull the module straight off. Do not touch the connector pins;
   they are static-sensitive.

## If it happens again

1. Check that no option module has been refitted.
2. Run `python win_gpib_diag.py` (sends no data), then `--test id_semi`. `--all` runs every test; note
   that `set_cf` changes the center frequency to 1 GHz.
3. If it crashes with no module attached, suspect the A2 controller board.

## Reading traces: sweep first

`trace()` without a fresh sweep returned exactly -100 dBm at all 601 points (bottom of the screen, with
reference level 0 dBm and 10 dB/div). After `single_sweep()` the same span read -96.5 to -46.16 dBm.
Why the trace was blank was not investigated.

- `hp8562a.py --trace` sweeps first and is not affected.
- `hp8562a.py` with no options does not sweep, so its peak reading may be wrong.
- In your own code, call `single_sweep()` before `trace()` or `peak()`.

## Windows setup notes (NI-488.2)

- NI-VISA alone does not include the adapter driver. Without NI-488.2, Device Manager shows
  GPIB-USB-HS with error code 28.
- Installed with NI Package Manager from an administrator prompt:

  ```
  nipkg feed-add "--name=ni-488-2-2025 Q1-released" https://download.ni.com/support/nipkg/products/ni-4/ni-488.2/25.0/released
  nipkg update
  nipkg install --accept-eulas ni-488.2
  ```

  Feed names cannot contain a dot.
- nipkg exits with -125071 (reboot needed). The adapter worked without one after starting the
  `gpibenumsvc` service (`sc start gpibenumsvc`, as administrator) and waiting a few seconds. Until then
  calls fail with EDVR (`0xE0140025`).
- The PC also has Keysight IO Libraries. The install left Keysight's `System32\gpib-32.dll` in place.
- `win_gpib_diag.py` needs only Python and `ni4882.dll`. `hp8562a.py` still needs linux-gpib and does not
  run on Windows as is.

## References

- [HP 85620A Mass Memory Module manual][mmm]: compatibility table p. 1-4, removal caution p. 1-2,
  battery test p. 5-2, error codes from p. 1-18 (850 is "Symbol Table Corrupt")
- [HP 8562A/B Installation and Verification Manual][iv]: GPIB address p. 2-9, error codes in appendix A

[mmm]: https://xdevs.com/doc/HP_Agilent_Keysight/HP%2085620A%20Mass%20Memory%20Module%20Installation,%20Operation,%20Programming%20&%20Service.pdf
[iv]: https://atecorp.com/getmedia/53e43e7c-54ff-4f2d-a2d1-fda01fb5a728/hp-agilent-8562a-b_manual_1.pdf
