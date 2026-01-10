#!/bin/bash
# Automatically connect to CM4 USB Ethernet

# Detect the first CM4 USB interface starting with "enx"
USB_IFACE=$(ip link show | grep -Eo '^[0-9]+: enx[0-9a-f]+' | head -n1 | awk '{print $2}')

if [ -z "$USB_IFACE" ]; then
    echo "No CM4 USB interface found!"
    exit 1
fi

echo "Detected interface: $USB_IFACE"

# Wait until interface has carrier
echo "Waiting for CM4 USB link..."
while true; do
    CARRIER=$(cat /sys/class/net/$USB_IFACE/carrier 2>/dev/null)
    if [ "$CARRIER" == "1" ]; then
        echo "Link is up!"
        break
    fi
    sleep 0.5
done

# Assign IP and bring the interface up
sudo ip addr add 192.168.7.2/24 dev "$USB_IFACE" 2>/dev/null
sudo ip link set "$USB_IFACE" up

echo "Interface $USB_IFACE is up. Pinging CM4..."
ping 192.168.7.2

