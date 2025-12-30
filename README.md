# macOS: Identify NVMe SSD Inside USB Enclosure (Without Booting Linux)

**Finally! Reveal the real SSD hidden inside USB enclosures on macOS - no Linux required.**

## The Problem

You bought a USB NVMe enclosure (Fantom, Sabrent, ORICO, etc.) and want to know what SSD is actually inside. But every tool shows useless info:

```bash
$ diskutil info disk5
   Device / Media Name:      Fantom

$ system_profiler SPUSBDataType
   Product ID: 0x2362
   Manufacturer: FD
   # No model, no serial, nothing useful
   
$ smartctl -a /dev/disk5
   Model:     [No Information Found]
   Serial:    [No Information Found]
```

**The manufacturer deliberately hid the SSD identity in firmware.**

## The "Solution" Everyone Gives

Google this problem and you'll find the same answer everywhere:

> "Just boot into Linux and run `smartctl -d sntasmedia`"

But that's ridiculous for a simple identification task. **This tool solves it natively on macOS.**

## What This Tool Does

```bash
$ sudo python3 asm2362_identify.py

=================================================================
  REAL SSD IDENTITY  
=================================================================

  Model:         PNY CS2130 8TB SSD
  Serial:        PNY22012201040105A85
  Firmware:      CS213531
  
  Controller:    Phison (VID: 0x1987)
=================================================================
```

**The drive advertised as "Fantom 8TB" is actually a PNY CS2130!**

## Why This Was Hard

I spent hours trying every approach:

| Method | Result |
|--------|--------|
| `diskutil info` | Shows "Fantom" only |
| `system_profiler` | Empty model/serial fields |
| `smartctl -d sat` | "No Information Found" |
| `smartctl -d sntasmedia` | "Not a device of type 'scsi'" |
| DriveDx + SAT SMART Driver | Empty fields |
| Custom SCSI scripts | Blocked by kernel |
| IOKit deep dive | Firmware returns empty strings |
| Physical inspection | Label removed, chips re-etched |

**macOS blocks the vendor-specific SCSI commands that would reveal the identity.** Unlike Linux which has a permissive `sg` (SCSI generic) driver, macOS's `IOUSBMassStorageDriver` filters out non-standard commands.

## The Breakthrough: libusb

The solution was to **bypass the macOS kernel entirely** using `libusb`:

```
Standard approach (BLOCKED):
  App → /dev/diskX → Kernel Driver → "Invalid command, rejected"

This tool (WORKS):
  App → libusb → Direct USB access → ASM2362 bridge → NVMe SSD
```

By detaching the kernel driver and talking directly to the USB device, we can send ASMedia's vendor-specific `0xE6` NVMe passthrough command - the same command that `smartctl` uses on Linux.

## Requirements

```bash
brew install libusb
pip3 install pyusb
```

## Usage

```bash
# 1. Find your disk number
diskutil list external

# 2. Unmount the drive (required to release kernel driver)
sudo diskutil unmountDisk force /dev/diskN

# 3. Run the identifier
sudo python3 asm2362_identify.py

# 4. Remount when done
diskutil mountDisk /dev/diskN
```

## Supported Enclosures

Any USB-to-NVMe enclosure using **ASMedia ASM2362** or **ASM2364** bridge chips:

- Fantom Drives
- Sabrent Rocket
- ORICO
- SSK
- UGREEN
- Inateck
- Many Amazon/AliExpress generics

**Check your bridge chip:**
```bash
system_profiler SPUSBDataType | grep -i "174c"
# If you see "Vendor ID: 0x174c" → ASMedia, this tool will work
```

## How It Works

1. **Unmount drive** - Releases macOS's grip on the device
2. **Detach kernel driver** - Removes `IOUSBMassStorageDriver` 
3. **Claim USB interface** - We become the driver
4. **Send ASMedia 0xE6 command** - Vendor-specific NVMe passthrough
5. **Parse NVMe Identify response** - Extract model, serial, firmware, vendor ID

The magic bytes:
```python
cdb = bytes([
    0xE6,  # ASMedia passthrough opcode
    0x06,  # NVMe Identify command
    0x00,  # Reserved
    0x01,  # CNS=1 (Identify Controller)
    ...
])
```

## Known Controller Vendors

| VID | Manufacturer |
|-----|--------------|
| 0x1987 | Phison |
| 0x144d | Samsung |
| 0x15b7 | SanDisk/Western Digital |
| 0x1e0f | Kioxia |
| 0x1c5c | SK Hynix |
| 0x126f | Silicon Motion |
| 0x1e4b | Maxio |
| 0x8086 | Intel |
| 0x1344 | Micron |

## Troubleshooting

**"No supported device found"**
- Verify ASMedia bridge: `system_profiler SPUSBDataType | grep -i 174c`
- Other bridges (JMicron, Realtek) need different protocols

**"Access denied" or timeout**
- Make sure you ran `diskutil unmountDisk` first
- Must use `sudo`

**Script hangs**
- Unplug and replug the drive
- Run immediately after connecting

## Linux Alternative

On Linux this is trivial:
```bash
sudo smartctl -d sntasmedia -i /dev/sdX
```

Linux's `sg` driver allows raw SCSI passthrough. This tool exists because macOS doesn't.

## Why Manufacturers Hide SSD Identity

1. **Prevent "shucking"** - Buying external drives to extract and resell the internal SSD
2. **Hide cheap components** - The external "premium brand" might contain budget SSDs
3. **Avoid warranty claims** - Can't prove what was originally inside
4. **Supply chain flexibility** - Swap components without updating marketing

## License

MIT - Use freely, contributions welcome.

## Credits

- **smartmontools** - Documented the ASMedia 0xE6 protocol
- **libusb/pyusb** - Made kernel bypass possible
- Developed with assistance from **Claude** (Anthropic)

## Keywords

macOS identify SSD USB enclosure, ASM2362 identify drive, smartctl sntasmedia mac, USB NVMe enclosure real SSD, Fantom Sabrent ORICO identify internal drive, macOS libusb NVMe, bypass SSD identity obfuscation
