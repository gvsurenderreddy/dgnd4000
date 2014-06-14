#!/bin/sh

#http://www.funtoo.org/Traffic_Control
#http://blog.edseek.com/~jasonb/articles/traffic_shaping/scenarios.html
#http://luxik.cdi.cz/~devik/qos/htb/manual/userg.htm

BINDIR=/home

MODEMIF=ppp1
FORCE=N
REMOVE=N
CEIL_PA=1000
CEIL_HI=450
CEIL_LO=550

while [ -n "${1}" ]; do
  case ${1} in
    f) FORCE=Y;;
    r) REMOVE=Y;;
    c) MODEMIF=$2
       CEIL_PA=$3
       CEIL_HI=$4
       CEIL_LO=$5
       shift 4;;
  esac
  shift
done

#tc classes will be "lost" whenever pppX is dropped
[ -z "$(tc class show dev $MODEMIF 2>/dev/null)" ] && FORCE=Y

[ $FORCE = N ] && exit

#Download kernel modules
for f in xt_CLASSIFY.ko xt_hashlimit.ko xt_length.ko;
do
  if [ ! -f ${BINDIR}/$f ]; then
    wget http://nmacleod.com/public/netgear_bin/$f -O ${BINDIR}/$f && chmod +x ${BINDIR}/$f
    if [ -n "$(echo "${f}" | grep "\.ko$")" ]; then
      insmod ${BINDIR}/$f
    fi
  fi
done

# Reset to default
echo "Clearing existing rules..."
iptables -t mangle -F POSTROUTING 2>/dev/null
iptables -t mangle -F ackprio 2>/dev/null
iptables -t mangle -X ackprio 2>/dev/null
iptables -t mangle -F tosfix  2>/dev/null
iptables -t mangle -X tosfix  2>/dev/null
tc qdisc del dev $MODEMIF root handle 1: 2>/dev/null

[ $REMOVE = Y ] && exit

echo "Applying new rules..."

# SSH - fix TOS flags that are incorrectly flagged as high priority
iptables -t mangle -N tosfix
iptables -t mangle -A tosfix -p tcp -m length --length 0:512 -j RETURN
# Allow screen redraws under interactive SSH sessions to be fast:
iptables -t mangle -A tosfix -m hashlimit --hashlimit 20/sec --hashlimit-burst 20 \
  --hashlimit-mode srcip,srcport,dstip,dstport --hashlimit-name minlat -j RETURN
iptables -t mangle -A tosfix -j TOS --set-tos Maximize-Throughput
iptables -t mangle -A tosfix -j RETURN

iptables -t mangle -A POSTROUTING -p tcp -m tos --tos Minimize-Delay -j tosfix

# ACK Priority
# Do nothing with packets where type of service (TOS) is already set
# Small packets should be prioritized
# Large packets (those with a payload) should not be prioritized
iptables -t mangle -N ackprio
iptables -t mangle -A ackprio -m tos ! --tos Normal-Service -j RETURN
iptables -t mangle -A ackprio -p tcp -m length --length 0:128 -j TOS --set-tos Minimize-Delay
iptables -t mangle -A ackprio -p tcp -m length --length 128: -j TOS --set-tos Maximize-Throughput
iptables -t mangle -A ackprio -j RETURN

iptables -t mangle -A POSTROUTING -p tcp -m tcp --tcp-flags FIN,SYN,RST,ACK ACK -j ackprio

# Add postrouting chain, with DNS/HTTP(s)/RTMP/FTP as high priority
# Port 21 (control) and 20 (data) is ftp (uploading xbmc images etc.)
# Port 1935 is rtmp (Flash/iPlayer etc.)
# Port 53 is dns
iptables -t mangle -A POSTROUTING -o $MODEMIF -p tcp  -m tos --tos Minimize-Delay -j CLASSIFY --set-class 1:10
iptables -t mangle -A POSTROUTING -o $MODEMIF -p tcp  --dport 80   -j CLASSIFY --set-class 1:10
iptables -t mangle -A POSTROUTING -o $MODEMIF -p tcp  --dport 443  -j CLASSIFY --set-class 1:10
iptables -t mangle -A POSTROUTING -o $MODEMIF -p tcp  --dport 20   -j CLASSIFY --set-class 1:10
iptables -t mangle -A POSTROUTING -o $MODEMIF -p tcp  --dport 21   -j CLASSIFY --set-class 1:10
iptables -t mangle -A POSTROUTING -o $MODEMIF -p tcp  --dport 1935 -j CLASSIFY --set-class 1:10
iptables -t mangle -A POSTROUTING -o $MODEMIF -p udp  --dport 53   -j CLASSIFY --set-class 1:10
iptables -t mangle -A POSTROUTING -o $MODEMIF -p tcp  --dport 53   -j CLASSIFY --set-class 1:10
iptables -t mangle -A POSTROUTING -o $MODEMIF -p icmp              -j CLASSIFY --set-class 1:10

# Enable traffic control queues, classes and filter (udp -> 1:10)
tc qdisc  add dev $MODEMIF root handle 1: htb default 12
tc class  add dev $MODEMIF parent 1: classid 1:1 htb rate ${CEIL_PA}kbit ceil ${CEIL_PA}kbit burst 10k
tc class  add dev $MODEMIF parent 1:1 classid 1:10 htb rate ${CEIL_HI}kbit ceil ${CEIL_PA}kbit prio 1 burst 10k
tc class  add dev $MODEMIF parent 1:1 classid 1:12 htb rate ${CEIL_LO}kbit ceil ${CEIL_PA}kbit prio 2
# UDP high priority (currently commented out as bittorrent uses udp - udp port 53 is prioritised instead)
#tc filter add dev $MODEMIF protocol ip parent 1:0 prio 1 u32 match ip protocol 0x11 0xff flowid 1:10
tc qdisc  add dev $MODEMIF parent 1:10 handle 20: sfq perturb 10
tc qdisc  add dev $MODEMIF parent 1:12 handle 30: sfq perturb 10

echo "Finished"

exit 0
