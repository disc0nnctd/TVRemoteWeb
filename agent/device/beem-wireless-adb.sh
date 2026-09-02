#!/system/bin/sh
# Device-specific Magisk service.d helper for the Beem 470 experiment unit.
# Keeps saved Wi-Fi enabled and legacy authenticated ADB listening on TCP 5555.

settings put global wifi_sleep_policy 2
cmd wifi set-wifi-enabled enabled >/dev/null 2>&1
cmd wifi start-scan >/dev/null 2>&1
setprop persist.adb.tcp.port 5555
setprop service.adb.tcp.port 5555

# Some firmware builds drop the WLAN association while the display is asleep.
# Keep this helper tiny: only request a saved-network scan when wlan0 has no IP.
state_dir=/data/adb/tvremoteweb
pid_file="$state_dir/wifi-watchdog.pid"
mkdir -p "$state_dir"

watchdog_running=0
if [ -s "$pid_file" ]; then
    old_pid="$(cat "$pid_file" 2>/dev/null)"
    case "$old_pid" in
        ''|*[!0-9]*) ;;
        *)
            if kill -0 "$old_pid" 2>/dev/null && \
                tr '\000' ' ' < "/proc/$old_pid/cmdline" 2>/dev/null | \
                    grep -q 'beem-wireless-adb.sh'; then
                watchdog_running=1
            fi
            ;;
    esac
fi

if [ "$watchdog_running" -eq 0 ]; then
    (
        while true; do
            if ! ip -o -4 addr show wlan0 2>/dev/null | grep -q ' inet '; then
                cmd wifi set-wifi-enabled enabled >/dev/null 2>&1
                cmd wifi start-scan >/dev/null 2>&1
            fi
            sleep 15
        done
    ) >/dev/null 2>&1 &
    echo "$!" > "$pid_file"
    chmod 600 "$pid_file"
fi
