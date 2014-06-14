#!/bin/sh

dokill() {
  killall $1 2>/dev/null
}

#dokill nas            # required for wifi
#dokill eapd           # required for wifi
#dokill swmdk          # required for ethernet
#dokill nmbd           # netbios (required for samba share)

#dokill syslogd
#dokill klogd
#dokill netgear_ntp
#dokill sh
#dokill mini_httpd      # webinterface

dokill checkleafp2p.sh  # restarts leafp2p
dokill checkleafnets.sh # restarts smb and ftpd
dokill leafp2p          # Netgear remote storage daemon
dokill bftpd            # FTP daemon
dokill afpd             # netatalk/AppleVolumes.system
dokill multi_pb_app     # monitors push button (WPS, reset etc.)
dokill cmd_agent_ap
dokill lld2             # link-layer topology discovery daemon
dokill wan_monitor
dokill wps_monitor
dokill rc_check_fw

#dokill avahi-daemon

#dokill ft_tool
#dokill sc_igmp
#dokill wlevt
#dokill crond
#dokill rcd

#Disable cron jobs we don't need
sed -i '/^[^#]/s/\(.*check_fw.*\)/#\1/g' /etc/crontab

echo 3 > /proc/sys/vm/drop_caches

if [ 1 = 0 ]; then
  echo 'server          192.168.0.1' > /etc/udhcpd.conf1
  echo 'start           192.168.0.2' >> /etc/udhcpd.conf1
  echo 'end             192.168.0.254' >> /etc/udhcpd.conf1
  echo 'interface       group1' >> /etc/udhcpd.conf1
  echo 'group_id        1' >> /etc/udhcpd.conf1
  echo 'option  subnet  255.255.255.0' >> /etc/udhcpd.conf1
  echo 'option  router  192.168.0.1' >> /etc/udhcpd.conf1
  echo 'option  dns     8.8.8.8 8.8.4.4' >> /etc/udhcpd.conf1
  echo 'option  lease   86400' >> /etc/udhcpd.conf1
  dokill udhcpd_1
  /var/udhcpd_1 /etc/udhcpd.conf1 &
fi

echo 4096  > /sys/module/nf_conntrack/parameters/hashsize
echo 32768 > /proc/sys/kernel/pid_max

ifconfig bcmsw txqueuelen 10000
ifconfig eth0 txqueuelen 10000
ifconfig eth1 txqueuelen 10000
ifconfig eth2 txqueuelen 10000
ifconfig eth3 txqueuelen 10000
echo 10000 > /proc/sys/net/core/netdev_max_backlog

echo '8196'               > /proc/sys/net/ipv4/udp_wmem_min
echo 1                    > /proc/sys/net/ipv4/tcp_no_metrics_save
echo '32940 43920 65880'  > /proc/sys/net/ipv4/udp_mem
echo '10980 14640 21960'  > /proc/sys/net/ipv4/tcp_mem
echo '8192 174760 468480' > /proc/sys/net/ipv4/tcp_rmem
echo '8192 32768 468480'  > /proc/sys/net/ipv4/tcp_wmem

echo 2000    > /proc/sys/net/core/netdev_max_backlog
echo 16384   > /proc/sys/net/netfilter/nf_conntrack_max
echo 1048576 > /proc/sys/net/core/wmem_max
echo 1048576 > /proc/sys/net/core/rmem_max
echo 1048576 > /proc/sys/net/core/rmem_default
echo 1048576 > /proc/sys/net/core/wmem_default

echo 1       > /proc/sys/net/ipv4/route/flush

# Stop "nas1: no IPv6 routers present" being written to dmesg every 30 seconds
echo 1 > /proc/sys/net/ipv6/conf/nas1/disable_ipv6
ifconfig nas1 down
ifconfig nas1 up

exit 0
