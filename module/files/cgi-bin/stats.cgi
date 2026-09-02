#!/system/bin/sh
# Live system stats + process list for beem470 remote pad.
# JSON, no external deps.
# ?top=N to include top N processes by CPU (default 0 = skip)

BB="/data/adb/magisk/busybox"
TOKEN_FILE="/data/adb/tvremoteweb/token"

urldecode() { "$BB" httpd -d "${1:-}"; }
get_param() {
  key="$1"; OLDIFS="$IFS"; IFS='&'
  for kv in $QUERY_STRING; do
    IFS="$OLDIFS"; k="${kv%%=*}"; v="${kv#*=}"
    [ "$k" = "$key" ] && { urldecode "$v"; return 0; }
    IFS='&'
  done
  IFS="$OLDIFS"; return 1
}

# token auth
token_full=""; pin=""
if [ -f "$TOKEN_FILE" ]; then
  token_full="$(cat "$TOKEN_FILE" 2>/dev/null)"
  [ -n "$token_full" ] && pin="$(printf '%s' "$token_full" | sha256sum | cut -c1-6)"
fi
qt="$(get_param token 2>/dev/null || true)"
if [ -n "$token_full" ] && [ "$qt" != "$token_full" ] && [ "$qt" != "$pin" ]; then
  echo "Status: 403 Forbidden"; echo "Content-Type: text/plain"; echo; echo "forbidden"; exit 0
fi

top_n="$(get_param top 2>/dev/null || echo 0)"
case "$top_n" in ''|*[!0-9]*) top_n=0 ;; esac
[ "$top_n" -gt 50 ] && top_n=50

read_int() { [ -r "$1" ] && cat "$1" 2>/dev/null || echo 0; }
temp_c()   { t=$(read_int "$1"); [ "$t" -gt 200 ] && awk "BEGIN{printf \"%.1f\", $t/1000}" || echo "$t.0"; }

cpu_temp="0.0"; gpu_temp="0.0"
for z in /sys/class/thermal/thermal_zone*; do
  [ -f "$z/type" ] || continue
  ty=$(cat "$z/type" 2>/dev/null)
  te=$(temp_c "$z/temp")
  case "$ty" in
    *cpu*)  cpu_temp="$te" ;;
    *gpu*)  gpu_temp="$te" ;;
  esac
done

cpu_sum=0; cpu_n=0
for f in /sys/devices/system/cpu/cpu[0-9]/cpufreq/scaling_cur_freq; do
  [ -r "$f" ] || continue
  v=$(cat "$f" 2>/dev/null); [ -z "$v" ] && continue
  cpu_sum=$((cpu_sum + v)); cpu_n=$((cpu_n + 1))
done
cpu_freq_mhz=0
[ "$cpu_n" -gt 0 ] && cpu_freq_mhz=$(awk "BEGIN{printf \"%d\", $cpu_sum/$cpu_n/1000}")

load_line=$(cat /proc/loadavg 2>/dev/null)
load_1m=$(echo "$load_line"  | awk '{print $1+0}')
load_5m=$(echo "$load_line"  | awk '{print $2+0}')
load_15m=$(echo "$load_line" | awk '{print $3+0}')
uptime_s=$(awk '{printf "%d", $1}' /proc/uptime 2>/dev/null)

mem_total=0; mem_avail=0; mem_free=0; swap_total=0; swap_free=0
while IFS=: read -r k v; do
  v=$(echo "$v" | awk '{print $1}')
  case "$k" in
    MemTotal)     mem_total=$v ;;
    MemAvailable) mem_avail=$v ;;
    MemFree)      mem_free=$v ;;
    SwapTotal)    swap_total=$v ;;
    SwapFree)     swap_free=$v ;;
  esac
done < /proc/meminfo

st_line=$(df /data 2>/dev/null | tail -1)
st_total=$(echo "$st_line" | awk '{print $2}')
st_used=$(echo  "$st_line" | awk '{print $3}')
st_avail=$(echo "$st_line" | awk '{print $4}')
st_pct=$(echo   "$st_line" | awk '{gsub("%","",$5); print $5}')

ip=$(ip -o -4 addr show wlan0 2>/dev/null | awk '{print $4}' | cut -d/ -f1 | head -1)
[ -z "$ip" ] && ip=$(ip -o -4 addr show 2>/dev/null | grep -v ' lo ' | awk '{print $4}' | cut -d/ -f1 | head -1)

cpu_cores=$(cat /sys/devices/system/cpu/online 2>/dev/null)
[ -z "$cpu_cores" ] && cpu_cores="0-3"

up_days=$((uptime_s / 86400))
up_hrs=$(( (uptime_s % 86400) / 3600 ))
up_min=$(( (uptime_s % 3600) / 60 ))

# ---- top processes ----
procs_json=""
if [ "$top_n" -gt 0 ]; then
  scan_n=$((top_n + 5))
  # `top -n 1 -b -m N -o %CPU` prints top N by CPU
  procs_json=$(top -n 1 -b -m "$scan_n" 2>/dev/null | awk -v n="$top_n" '
    /^ *PID/ { start=1; next }
    start && NF >= 12 && count < n {
      pid=$1; cpu=$9; mem=$10; time=$11;
      # ARGS is last field(s). Reconstruct name = everything from field 12
      name=""; for (i=12; i<=NF; i++) name = name (i>12?" ":"") $i
      # Do not present the one-shot measurement command as an app consuming
      # resources; it exits as soon as this response is generated.
      if (name ~ /^top( |$)/ || name ~ /stats\.cgi/) next
      # escape json
      gsub(/\\/, "\\\\", name); gsub(/"/, "\\\"", name)
      if (length(name) > 60) name = substr(name, 1, 60) "…"
      if (count > 0) printf ","
      printf "{\"pid\":%s,\"cpu\":%s,\"mem\":%s,\"name\":\"%s\"}", pid, cpu, mem, name
      count++
    }
  ')
fi

echo "Content-Type: application/json"
echo "Access-Control-Allow-Origin: *"
echo "Cache-Control: no-cache"
echo
printf '{'
printf '"cpu_temp":%s,'         "$cpu_temp"
printf '"gpu_temp":%s,'         "$gpu_temp"
printf '"cpu_freq_mhz":%s,'     "$cpu_freq_mhz"
printf '"cpu_cores":"%s",'      "$cpu_cores"
printf '"load_1m":%s,'          "$load_1m"
printf '"load_5m":%s,'          "$load_5m"
printf '"load_15m":%s,'         "$load_15m"
printf '"mem_total_kb":%s,'     "$mem_total"
printf '"mem_avail_kb":%s,'     "$mem_avail"
printf '"mem_free_kb":%s,'      "$mem_free"
printf '"swap_total_kb":%s,'    "$swap_total"
printf '"swap_free_kb":%s,'     "$swap_free"
printf '"storage_total_kb":%s,' "${st_total:-0}"
printf '"storage_used_kb":%s,'  "${st_used:-0}"
printf '"storage_avail_kb":%s,' "${st_avail:-0}"
printf '"storage_pct":%s,'      "${st_pct:-0}"
printf '"uptime_s":%s,'         "${uptime_s:-0}"
printf '"uptime_d":%s,'         "$up_days"
printf '"uptime_h":%s,'         "$up_hrs"
printf '"uptime_m":%s,'         "$up_min"
printf '"ip":"%s",'             "$ip"
printf '"procs":[%s]'           "$procs_json"
printf '}\n'
