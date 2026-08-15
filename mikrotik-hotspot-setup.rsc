# Tafar WiFi — basic Hotspot setup
# Paste this complete file into MikroTik Winbox > New Terminal.
# Assumptions:
#   * ether1 is the WAN/uplink and is intentionally not changed.
#   * 192.168.88.0/24 is the existing LAN/DHCP subnet.
#   * Existing DHCP servers on ether2, ether3, ether4, or wlan1 should serve
#     the bridge after those LAN ports are joined together.

# -----------------------------------------------------------------------------
# 1. LAN bridge: combine wired client ports and the WiFi radio.
# -----------------------------------------------------------------------------
:if ([:len [/interface bridge find where name="hotspot-bridge"]] = 0) do={
    /interface bridge add name=hotspot-bridge comment="Hotspot LAN bridge (ether2-4 + wlan1)"
}

:foreach portName in={"ether2";"ether3";"ether4";"wlan1"} do={
    :if ([:len [/interface find where name=$portName]] = 0) do={
        :log warning ("Hotspot setup: interface " . $portName . " was not found; skipped")
    } else={
        :if ([:len [/interface bridge port find where interface=$portName]] = 0) do={
            /interface bridge port add bridge=hotspot-bridge interface=$portName
        }
    }
}

# -----------------------------------------------------------------------------
# 2. Put the existing Hotspot LAN address on the bridge.
#    If 192.168.88.1/24 already exists on a LAN port, move it to the bridge.
# -----------------------------------------------------------------------------
:local hotspotAddress [/ip address find where address="192.168.88.1/24"]
:if ([:len $hotspotAddress] = 0) do={
    /ip address add address=192.168.88.1/24 interface=hotspot-bridge comment="Hotspot gateway"
} else={
    /ip address set $hotspotAddress interface=hotspot-bridge comment="Hotspot gateway"
}

# Move any existing DHCP server bound directly to one of the LAN ports onto
# the bridge. Its pool, lease settings, and network definition are retained.
:foreach lanPort in={"ether2";"ether3";"ether4";"wlan1"} do={
    :foreach dhcpServer in=[/ip dhcp-server find where interface=$lanPort] do={
        /ip dhcp-server set $dhcpServer interface=hotspot-bridge
    }
}

# -----------------------------------------------------------------------------
# 3. Hotspot server. address-pool=none means the existing DHCP server remains
#    responsible for client addresses; Hotspot only authenticates those clients.
# -----------------------------------------------------------------------------
:if ([:len [/ip hotspot profile find where name="hotspot-server-profile"]] = 0) do={
    /ip hotspot profile add name=hotspot-server-profile hotspot-address=192.168.88.1 login-by=http-chap,cookie comment="Tafar WiFi Hotspot server profile"
} else={
    /ip hotspot profile set [find where name="hotspot-server-profile"] hotspot-address=192.168.88.1 login-by=http-chap,cookie comment="Tafar WiFi Hotspot server profile"
}

:if ([:len [/ip hotspot find where name="hotspot1"]] = 0) do={
    /ip hotspot add name=hotspot1 interface=hotspot-bridge address-pool=none profile=hotspot-server-profile disabled=no comment="Tafar WiFi Hotspot"
} else={
    /ip hotspot set [find where name="hotspot1"] interface=hotspot-bridge address-pool=none profile=hotspot-server-profile disabled=no comment="Tafar WiFi Hotspot"
}

# -----------------------------------------------------------------------------
# 4. Voucher profiles. Names exactly match the backend PlanConfig values.
#    Pilot shaping is 4M/4M, with the agreed 8M burst, 3M threshold, and 8s
#    burst time. shared-users=1 allows one concurrent device per voucher.
# -----------------------------------------------------------------------------
:if ([:len [/ip hotspot user profile find where name="day-pass"]] = 0) do={
    /ip hotspot user profile add name=day-pass rate-limit="4M/4M 8M/8M 3M/3M 8s/8s" shared-users=1 session-timeout=1d comment="DAY PASS — 24 hours"
} else={
    /ip hotspot user profile set [find where name="day-pass"] rate-limit="4M/4M 8M/8M 3M/3M 8s/8s" shared-users=1 session-timeout=1d comment="DAY PASS — 24 hours"
}

:if ([:len [/ip hotspot user profile find where name="week-pass"]] = 0) do={
    /ip hotspot user profile add name=week-pass rate-limit="4M/4M 8M/8M 3M/3M 8s/8s" shared-users=1 session-timeout=7d comment="WEEK PASS — 7 days"
} else={
    /ip hotspot user profile set [find where name="week-pass"] rate-limit="4M/4M 8M/8M 3M/3M 8s/8s" shared-users=1 session-timeout=7d comment="WEEK PASS — 7 days"
}

:if ([:len [/ip hotspot user profile find where name="month-pass"]] = 0) do={
    /ip hotspot user profile add name=month-pass rate-limit="4M/4M 8M/8M 3M/3M 8s/8s" shared-users=1 session-timeout=30d comment="MONTH PASS — 30 days"
} else={
    /ip hotspot user profile set [find where name="month-pass"] rate-limit="4M/4M 8M/8M 3M/3M 8s/8s" shared-users=1 session-timeout=30d comment="MONTH PASS — 30 days"
}

# No DNS name or walled-garden rules are configured here by design.
# End of Tafar WiFi Hotspot setup.
