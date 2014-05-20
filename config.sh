#!/bin/sh

BINDIR=/home
SELF=${BINDIR}/config.sh
LOGFILE=/tmp/ppp_log
RETRIES=300
SNMP=njmserver

WEBHOST=http://nmacleod.com/public/netgear_bin

log() {
  if [ $LOGLEVEL != QUIET ]; then
    printf "$(date): %s\n" "$(echo "$1" | sed "s/\\\\n/\n/g")" >>${LOGFILE}
  fi
}

# Execute a command until success or retries exhausted
succeed() {
  command="$1"
  retries=$2
  waitsecs=${3:-0}
  res=1
  count=0
  while [ : ]; do
    count=$(($count+1))
    TXT="$($command 2>&1)" && res=0 || res=1
    [ $LOGLEVEL = VERBOSE ] && log "Executing command [$command]"
    [ $LOGLEVEL = DEBUG ] && log "RESULT for command [$command]:\n${TXT}\n-------"
    [ $res = 0 -o $count -ge $retries ] && break
    [ $waitsecs != 0 ] && sleep $waitsecs
  done
  [ $res = 1 ] && log "Failed to execute [$command] - $retries retries exceeded"
  return $res
}

installexec() {
  DAEMONIZE=$1
  RUNNING=$2
  SOURCE=$3
  TARGET=$4
  ARGS=$5

  if [ "${RUNNING}" = "" ]; then
    if [ ! -f ${TARGET} ]; then
      succeed "wget ${SOURCE} -O ${TARGET}" $RETRIES 1 || return 1
      chmod +x ${TARGET}
    fi

    if [ -x ${TARGET} ]; then
      log "Starting ${TARGET} ${ARGS}..."
      [ $DAEMONIZE  = "Y" ] && ${TARGET} ${ARGS} &
      [ $DAEMONIZE != "Y" ] && ${TARGET} ${ARGS}
    fi
  fi

  return 0
}

level=${1:-quiet}
LOGLEVEL=QUIET
[ "${level}" = "debug"   ] && LOGLEVEL=DEBUG
[ "${level}" = "verbose" ] && LOGLEVEL=VERBOSE

# Remove old logfile unless debugging
[ ${LOGLEVEL} != DEBUG ] && rm -f ${LOGFILE}

log "Called, presumably from ip-up with the following arguments:"
log "  Args: [$*]"

#Grab primary DNS from info file - use Google DNS if primary DNS not found
DNS=$(awk '/dns/ {print $2; exit}' /tmp/w/info_1)
DNS=${DNS:-8.8.4.4}

succeed "ping ${DNS} -w1 -c1" $RETRIES 1 && log "WAN connection is alive!" || exit

installexec "N" "" "${WEBHOST}/optimise.sh" ${BINDIR}/optimise.sh "" || exit
installexec "N" "" "${WEBHOST}/trafficshaper.sh" ${BINDIR}/trafficshaper.sh "c ppp1 1000 450 550" || exit
log "Router optimised and iptables/traffic control settings configured!"

#Install and execute "snmp" server
if [ -n "${SNMP}" ]; then
  installexec "Y" "$(pidof ${SNMP})" "${WEBHOST}/${SNMP}" ${BINDIR}/${SNMP} "5001" || exit
fi

#Lastly, enable "debug" by starting utelnetd
if [ -z "$(pidof utelnetd)" ]; then
  /usr/sbin/utelnetd -d -l /usr/sbin/login&
  log "telnet now enabled"
fi
