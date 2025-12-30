#!/usr/bin/env python3
"""
macOS: Identify NVMe SSD Inside USB Enclosure

Reveals the REAL NVMe SSD hidden inside USB enclosures that use ASMedia ASM2362/2364
bridge chips - even when the manufacturer has deliberately obfuscated the identity.

This bypasses macOS kernel limitations by using libusb to send the ASMedia
vendor-specific 0xE6 NVMe passthrough command directly over USB.

REQUIREMENTS:
    brew install libusb
    pip3 install pyusb

USAGE:
    # First unmount the drive (replace diskN with your disk number)
    sudo diskutil unmountDisk force /dev/diskN
    
    # Then run this script
    sudo python3 asm2362_identify.py

WHY THIS EXISTS:
    On macOS, standard tools (smartctl, diskutil, system_profiler) cannot identify
    SSDs inside USB enclosures when the manufacturer has hidden the identity.
    
    The usual advice is "boot into Linux" - but that's overkill for a simple ID check.
    
    This tool uses libusb to bypass the macOS kernel's storage driver and send
    commands directly to the USB device, achieving the same result as Linux's
    "smartctl -d sntasmedia" without rebooting.

SUPPORTED DEVICES:
    Any USB-to-NVMe enclosure using ASMedia ASM2362 or ASM2364 bridge chips.
    Common brands: Sabrent, ORICO, SSK, UGREEN, Fantom, and many Amazon generics.
    
    Check yours: system_profiler SPUSBDataType | grep -i "174c"

LICENSE: MIT
"""

import sys
import struct
import time

try:
    import usb.core
    import usb.util
except ImportError:
    print("ERROR: pyusb not installed")
    print()
    print("Install with:")
    print("  brew install libusb")
    print("  pip3 install pyusb")
    sys.exit(1)

# ASMedia USB-NVMe bridge chips
SUPPORTED_DEVICES = [
    (0x174c, 0x2362, "ASMedia ASM2362"),
    (0x174c, 0x2364, "ASMedia ASM2364"),
]

# Known NVMe controller vendors (PCI Vendor IDs)
VENDORS = {
    0x1987: "Phison",
    0x144d: "Samsung",
    0x15b7: "SanDisk/Western Digital",
    0x1e0f: "Kioxia",
    0x1c5c: "SK Hynix",
    0x126f: "Silicon Motion",
    0x1179: "Toshiba",
    0x2646: "Kingston",
    0x1dee: "Biwin",
    0x1e4b: "Maxio",
    0x1d97: "Shenzhen Longsys",
    0x025e: "Solidigm",
    0x8086: "Intel",
    0x1344: "Micron",
    0x1cc1: "ADATA",
    0xc0a9: "Micron",
    0x1d79: "Transcend",
}

CBW_SIGNATURE = 0x43425355  # USB Mass Storage signature


def find_device():
    """Find a supported ASMedia bridge device"""
    for vid, pid, name in SUPPORTED_DEVICES:
        dev = usb.core.find(idVendor=vid, idProduct=pid)
        if dev:
            return dev, name
    return None, None


def find_bulk_endpoints(dev):
    """Find bulk IN and OUT endpoints"""
    cfg = dev.get_active_configuration()
    ep_in = ep_out = None
    
    for intf in cfg:
        for ep in intf:
            if usb.util.endpoint_type(ep.bmAttributes) == 2:  # Bulk
                if usb.util.endpoint_direction(ep.bEndpointAddress) == usb.util.ENDPOINT_IN:
                    ep_in = ep_in or ep
                else:
                    ep_out = ep_out or ep
    return ep_in, ep_out


def send_nvme_identify(ep_out, ep_in):
    """Send ASMedia 0xE6 NVMe Identify Controller command"""
    tag = int(time.time() * 1000) & 0xFFFFFFFF
    
    # ASMedia 0xE6 passthrough: NVMe Identify Controller (opcode 0x06, CNS=1)
    cdb = bytes([0xE6, 0x06, 0x00, 0x01] + [0x00] * 12)
    
    # USB Mass Storage Command Block Wrapper
    cbw = struct.pack('<IIIBBB', CBW_SIGNATURE, tag, 4096, 0x80, 0, len(cdb))
    cbw += cdb + bytes(16 - len(cdb))
    
    try:
        ep_out.write(cbw, timeout=5000)
        data = bytes(ep_in.read(4096, timeout=5000))
        ep_in.read(13, timeout=5000)  # Command Status Wrapper
        return data
    except usb.core.USBError as e:
        print(f"USB Error: {e}")
        return None


def parse_identify(data):
    """Parse NVMe Identify Controller structure"""
    if not data or len(data) < 72:
        return None
    return {
        'vid': struct.unpack_from('<H', data, 0)[0],
        'ssvid': struct.unpack_from('<H', data, 2)[0],
        'serial': data[4:24].decode('ascii', errors='ignore').strip(),
        'model': data[24:64].decode('ascii', errors='ignore').strip(),
        'firmware': data[64:72].decode('ascii', errors='ignore').strip(),
    }


def main():
    print("=" * 65)
    print("  Identify NVMe SSD Inside USB Enclosure (macOS)")
    print("  https://github.com/UnknownInconnuSpace/asm2362-identify")
    print("=" * 65)
    
    import os
    if os.geteuid() != 0:
        print("\nERROR: Must run as root")
        print("  sudo python3 asm2362_identify.py")
        sys.exit(1)
    
    print("\nSearching for ASMedia USB-NVMe bridge...")
    dev, bridge_name = find_device()
    
    if not dev:
        print("\nERROR: No supported device found!")
        print("\nSupported: ASMedia ASM2362, ASM2364")
        print("\nCheck if your enclosure uses ASMedia:")
        print("  system_profiler SPUSBDataType | grep -i 174c")
        sys.exit(1)
    
    print(f"  Found: {bridge_name}")
    try:
        print(f"  Manufacturer: {dev.manufacturer}")
        print(f"  Product: {dev.product}")
    except:
        pass
    
    # Detach kernel driver
    print("\nDetaching macOS kernel driver...")
    try:
        for i in range(dev.get_active_configuration().bNumInterfaces):
            if dev.is_kernel_driver_active(i):
                dev.detach_kernel_driver(i)
        print("  Done")
    except Exception as e:
        print(f"  Note: {e}")
    
    try:
        usb.util.claim_interface(dev, 0)
    except:
        pass
    
    ep_in, ep_out = find_bulk_endpoints(dev)
    if not ep_in or not ep_out:
        print("\nERROR: Could not find USB endpoints")
        sys.exit(1)
    
    # Reset to clear stale state
    print("Resetting device...")
    try:
        dev.reset()
        time.sleep(1)
        dev, _ = find_device()
        for i in range(dev.get_active_configuration().bNumInterfaces):
            try:
                if dev.is_kernel_driver_active(i):
                    dev.detach_kernel_driver(i)
            except:
                pass
        usb.util.claim_interface(dev, 0)
        ep_in, ep_out = find_bulk_endpoints(dev)
    except Exception as e:
        print(f"  Note: {e}")
    
    print("\nSending NVMe Identify command...")
    data = send_nvme_identify(ep_out, ep_in)
    
    if not data:
        print("\nERROR: No response from drive")
        sys.exit(1)
    
    result = parse_identify(data)
    
    if not result or result['vid'] in (0, 0xFFFF):
        print("\nERROR: Invalid response - firmware may be blocking identify")
        sys.exit(1)
    
    # Success!
    vendor_name = VENDORS.get(result['vid'], "Unknown")
    
    print("\n" + "=" * 65)
    print("  REAL SSD IDENTITY")
    print("=" * 65)
    print(f"""
  Model:         {result['model']}
  Serial:        {result['serial']}
  Firmware:      {result['firmware']}
  
  Controller:    {vendor_name} (VID: 0x{result['vid']:04x})
  Subsystem:     0x{result['ssvid']:04x}
""")
    print("=" * 65)
    
    print("\nRaw data (first 80 bytes):")
    for i in range(0, 80, 16):
        hex_part = ' '.join(f'{data[j]:02x}' for j in range(i, min(i+16, len(data))))
        ascii_part = ''.join(chr(data[j]) if 32 <= data[j] < 127 else '.' for j in range(i, min(i+16, len(data))))
        print(f"  {i:04x}: {hex_part}  {ascii_part}")
    
    print("\nRemount drive with: diskutil mountDisk /dev/diskN")


if __name__ == '__main__':
    main()
