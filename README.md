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

---

## Currently Supported Bridge Chips

| Bridge Chip | Vendor ID | Status | Passthrough Opcode |
|-------------|-----------|--------|-------------------|
| **ASMedia ASM2362** | `0x174c:0x2362` | ✅ **Supported** | `0xE6` |
| **ASMedia ASM2364** | `0x174c:0x2364` | ✅ **Supported** | `0xE6` |
| JMicron JMS583 | `0x152d:0x0583` | ❌ Not yet | `0xDF` |
| JMicron JMS580 | `0x152d:0x0580` | ❌ Not yet | `0xDF` |
| Realtek RTL9210 | `0x0bda:0x9210` | ❌ Not yet | `0xE0` (unconfirmed) |
| Realtek RTL9210B | `0x0bda:0x9210` | ❌ Not yet | `0xE4` (unconfirmed) |
| VIA VL716 | `0x2109:0x0716` | ❌ Not yet | Unknown |

**Check what bridge YOUR enclosure uses:**
```bash
system_profiler SPUSBDataType | grep -E "Vendor ID|Product ID"
```

### Want to Help Add Support for Other Chips?

See the [Contributing](#contributing-adding-support-for-other-bridge-chips) section below! Each bridge chip uses a different vendor-specific SCSI opcode, but the overall approach is the same.

---

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
  App → libusb → Direct USB access → Bridge chip → NVMe SSD
```

By detaching the kernel driver and talking directly to the USB device, we can send vendor-specific passthrough commands - the same commands that `smartctl` uses on Linux.

---

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

---

## How It Works

1. **Unmount drive** - Releases macOS's grip on the device
2. **Detach kernel driver** - Removes `IOUSBMassStorageDriver` 
3. **Claim USB interface** - We become the driver
4. **Send vendor passthrough command** - Bridge-specific NVMe passthrough
5. **Parse NVMe Identify response** - Extract model, serial, firmware, vendor ID

The key bytes for ASMedia:
```python
cdb = bytes([
    0xE6,  # ASMedia passthrough opcode
    0x06,  # NVMe Identify command
    0x00,  # Reserved
    0x01,  # CNS=1 (Identify Controller)
    ...
])
```

---

## Contributing: Adding Support for Other Bridge Chips

**The core libusb approach works for ANY USB-NVMe bridge** - only the passthrough opcode and CDB structure differ per manufacturer.

### How to Add a New Bridge Chip

1. **Find the passthrough opcode** - Check smartmontools source code:
   - [scsinvme.cpp](https://github.com/smartmontools/smartmontools/blob/master/smartmontools/scsinvme.cpp)
   - Search for your chip (e.g., "jmicron", "realtek")

2. **Identify the CDB structure** - Each vendor packs the NVMe command differently:

   **ASMedia (0xE6):**
   ```python
   cdb = bytes([0xE6, 0x06, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00,
                0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
   ```

   **JMicron (0xDF):** *(needs testing)*
   ```python
   cdb = bytes([0xDF, 0x10, 0x00, 0x00, 0x00, 0x00, 0x01, 0x00,
                0x00, 0x00, 0x06, 0x00, 0x00, 0x00, 0x00, 0x00])
   ```

   **Realtek (0xE0 or 0xE4):** *(needs testing)*
   ```python
   # Structure unknown - check smartmontools source
   ```

3. **Add to SUPPORTED_DEVICES** in the script:
   ```python
   SUPPORTED_DEVICES = [
       (0x174c, 0x2362, "ASMedia ASM2362", build_asm_cdb),
       (0x174c, 0x2364, "ASMedia ASM2364", build_asm_cdb),
       (0x152d, 0x0583, "JMicron JMS583", build_jmicron_cdb),  # NEW
   ]
   ```

4. **Test and submit a PR!**

### Research Resources

- **smartmontools source** - The definitive reference for passthrough protocols:
  - https://github.com/smartmontools/smartmontools/blob/master/smartmontools/scsinvme.cpp
  
- **USB IDs database** - Find your bridge chip:
  - https://devicehunt.com/
  - `system_profiler SPUSBDataType`

- **Linux testing** - If you have Linux available, test with smartctl first:
  ```bash
  # Find the right -d option for your bridge
  sudo smartctl --scan
  sudo smartctl -d <type> -i /dev/sdX
  ```

### Chips That Need Testing

If you have hardware with these bridges, please help test!

| Bridge | Vendor:Product | smartctl option | Status |
|--------|---------------|-----------------|--------|
| JMicron JMS583 | `152d:0583` | `-d sntjmicron` | Need tester |
| JMicron JMS580 | `152d:0580` | `-d sntjmicron` | Need tester |
| Realtek RTL9210 | `0bda:9210` | `-d sntrealtek` | Need tester |
| Realtek RTL9210B | `0bda:9210` | `-d sntrealtek` | Need tester |

**To contribute:**
1. Fork this repo
2. Add your bridge chip support
3. Test with your hardware
4. Submit a PR with the chip name in the title

---

## Known NVMe Controller Vendors

Once you get the identify data, the VID tells you who made the controller:

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

---

## Troubleshooting

**"No supported device found"**
- Check your bridge chip: `system_profiler SPUSBDataType | grep -i "Vendor ID"`
- If it's not ASMedia (`0x174c`), the script needs modification for your chip
- See [Contributing](#contributing-adding-support-for-other-bridge-chips) section

**"Access denied" or timeout**
- Make sure you ran `diskutil unmountDisk` first
- Must use `sudo`

**Script hangs**
- Unplug and replug the drive
- Run immediately after connecting

---

## Linux Alternative

On Linux this is trivial (if you know the right `-d` option):
```bash
sudo smartctl -d sntasmedia -i /dev/sdX  # ASMedia
sudo smartctl -d sntjmicron -i /dev/sdX  # JMicron
sudo smartctl -d sntrealtek -i /dev/sdX  # Realtek
```

Linux's `sg` driver allows raw SCSI passthrough. This tool exists because macOS doesn't.

---

## Why Manufacturers Hide SSD Identity

1. **Prevent "shucking"** - Buying external drives to extract and resell the internal SSD
2. **Hide cheap components** - The external "premium brand" might contain budget SSDs
3. **Avoid warranty claims** - Can't prove what was originally inside
4. **Supply chain flexibility** - Swap components without updating marketing

---

## License

MIT - Use freely, contributions welcome.

## Credits

- **smartmontools** - Documented the vendor passthrough protocols
- **libusb/pyusb** - Made kernel bypass possible
- Developed with assistance from **Claude** (Anthropic)

---

## Keywords

macOS identify SSD USB enclosure, ASM2362 identify drive, smartctl sntasmedia mac, USB NVMe enclosure real SSD, Fantom Sabrent ORICO identify internal drive, macOS libusb NVMe, bypass SSD identity obfuscation, JMicron JMS583 macOS, Realtek RTL9210 macOS
