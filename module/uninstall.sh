#!/system/bin/sh
# Leave the token and settings alone so a reinstall keeps the same URL.
# Remove /data/adb/tvremoteweb by hand for a completely clean slate.
pkill -f 'tvremoteweb/www' 2>/dev/null
pkill -f mousedaemon 2>/dev/null
pm uninstall com.tvremoteweb.qr 2>/dev/null
exit 0
