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
  waitsecs=${3:-1}

  res=1
  count=0
  while [ : ]; do
    count=$(($count+1))
    TXT="$($command 2>&1)" && res=0 || res=1
    [ $res = 0 ] && MSG="SUCCESS" || MSG="FAIL"
    [ $LOGLEVEL = VERBOSE ] && log "Executing command [$command] ($MSG)"
    [ $LOGLEVEL = DEBUG ] && log "RESULT for command [$command] ($MSG):\n${TXT}\n-------"
    [ $res = 0 -o $count -ge $retries ] && break
    [ $waitsecs != 0 ] && sleep $waitsecs
  done
  [ $res = 1 ] && log "Failed to execute [$command] - $retries retries exceeded"
  return $res
}

installexec() {
  DAEMONIZE=$1
  PID=$2
  SOURCE=$3
  TARGET=$4
  ARGS=$5

  RESULT=0
  
  if [ "${PID}" = "" ]; then
    if [ ! -f ${TARGET} ]; then
      succeed "wget ${SOURCE} -O ${TARGET}" $RETRIES 1 || return 1
      chmod +x ${TARGET}
    fi

    if [ -x ${TARGET} ]; then
      log "Starting ${TARGET} ${ARGS}..."
      if [ $DAEMONIZE = "Y" ]; then
        ${TARGET} ${ARGS} &
      else
        OUTPUT="$(${TARGET} ${ARGS})"
        RESULT=$?
        [ -n "${OUTPUT}" ] && log "${OUTPUT}"
      fi
    fi
  fi

  return ${RESULT}
}

level=${1:-quiet}
LOGLEVEL=QUIET
[ "${level}" = "debug"   ] && LOGLEVEL=DEBUG
[ "${level}" = "verbose" ] && LOGLEVEL=VERBOSE

# Remove old logfile unless debugging or continuation of previous connection attempt
[ ${LOGLEVEL} != DEBUG -a ! -f /tmp/keep_log ] && rm -f ${LOGFILE}

log "Called, presumably from ip-up with the following arguments:"
log "  Args: [$*]"

#Firstly, enable "debug" by starting utelnetd
if [ -z "$(pidof utelnetd)" ]; then
  /usr/sbin/utelnetd -d -l /usr/sbin/login&
  log "telnet now enabled"
fi

log "ADSL State:\n$(adslctl info --state)\n$(adslctl info --show|grep dB)\n$(adslctl profile --show)"

# See: http://www.kitz.co.uk/routers/dg834GT_targetsnr.htm
#      http://wiki.kitz.co.uk/index.php?title=Broadcom_CLI
# for target SNR details.
# When SNR is changed, connection will be dropped so exit and hopefully resync with new SNR.
# Specify a parameter of 100 to avoid changing SNR.
touch /tmp/keep_log
installexec "N" "" "${WEBHOST}/targetsnr.sh" ${BINDIR}/targetsnr.sh "120" || exit
rm -f /tmp/keep_log

installexec "N" "" "${WEBHOST}/optimise.sh" ${BINDIR}/optimise.sh "" || exit
installexec "N" "" "${WEBHOST}/trafficshaper.sh" ${BINDIR}/trafficshaper.sh "c ppp1 1000 450 550" || exit
log "Router optimised and iptables/traffic control settings configured!"

#Install and execute "snmp" server
if [ -n "${SNMP}" ]; then
  installexec "Y" "$(pidof ${SNMP})" "${WEBHOST}/${SNMP}" ${BINDIR}/${SNMP} "5001" || exit
fi

log "ADSL Connection Stats:\n$(adslctl info --show)"
