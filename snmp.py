#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import print_function
import os, sys, time, datetime, re, argparse, socket
import tempfile, subprocess, traceback
from math import ceil

DEBUG = False

BIN_EMAIL = "/usr/bin/msmtp_safe"

ROUTER_HOST = "192.168.0.1"
ROUTER_PORT = 5001

DAEMON_HOST = "localhost"
DAEMON_PORT = ROUTER_PORT

EMULATE64BIT = True
LASTCOMMAND = None
LASTRESULT = None

COUNTER32 = (2**32)-1
COUNTER64 = (2**64)-1

def log(msg):
  if DEBUG:
    print("%s: %s" % (datetime.datetime.now(), msg))
    sys.stdout.flush()

def runcmd(args, command):
  global LASTCOMMAND, LASTRESULT

  if args.daemon and args.verbose:
    log("SENDING to %s: %s" % (args.host, command))

  LASTCOMMAND = command
  LASTRESULT  = None
  s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
  s.connect((args.host, args.port))
  s.send("%s" % command)
  alldata = ""
  while True:
    data = s.recv(1024)
    if not data: break
    alldata += data
  s.close()

  LASTRESULT = alldata[:-1]

  return alldata[:-1]

def grep(match_string, input_string, field=None, fields=None, head=None, tail=None, split_char=" ", case_sensitive=True, defaultvalue=None, after=None, toint=False, tofloat=False):
  re_flags = 0 if case_sensitive else re.IGNORECASE

  lines = []

  if after:
    found = False
    count = 0
    for line in [x for x in input_string.split("\n")]:
      if not found:
        found = (re.search(match_string, line, flags=re_flags) != None)
      if found:
        if count >= after: break
        count += 1
        values = re.sub("%s+" % split_char, split_char, line.strip()).split(split_char)
        if field != None:
          if len(values) > field:
            if toint:
              lines.append(int(values[field]))
            elif tofloat:
              lines.append(float(values[field]))
            else:
              lines.append(values[field])
        elif fields != None:
          if toint:
            lines.append([int(values[x]) for x in fields])
          elif tofloat:
            lines.append([float(values[x]) for x in fields])
          else:
            lines.append([values[x] for x in fields])
        else:
          lines.append(split_char.join(values))
  else:
    for line in [x for x in input_string.split("\n") if re.search(match_string, x, flags=re_flags)]:
      values = re.sub("%s+" % split_char, split_char, line.strip()).split(split_char)
      if field != None:
        if len(values) > field:
          if toint:
            lines.append(int(values[field]))
          elif tofloat:
            lines.append(float(values[field]))
          else:
            lines.append(values[field])
      elif fields != None:
        if toint:
          lines.append([int(values[x]) for x in fields])
        elif tofloat:
          lines.append([float(values[x]) for x in fields])
        else:
          lines.append([values[x] for x in fields])
      else:
        lines.append(split_char.join(values))

      # Don't process any more lines than we absolutely have to
      if head and not tail and len(lines) >= head:
        break

  if head: lines = lines[:head]
  if tail: lines = lines[-tail:]

  if defaultvalue and lines == []:
    return defaultvalue
  else:
    if fields or (field != None and (toint or tofloat)):
      return lines
    else:
      return "\n".join(lines)

# grep -v - return everything but the match string
def grepv(match_string, input_string, field=None, fields=None, head=None, tail=None, split_char=" ", case_sensitive=False, toint=False):
  return grep(r"^((?!%s).)*$" % match_string, input_string, field, fields, head, tail, split_char, case_sensitive)

#Fix network counter wrap - bump counter each time a counter wraps
#and add restore the accumulated to-date figures based on prior wraps.
def counterwrap(args, dTime, storage, old, new, key=None, item1=None, item2=None):
  if args.wrap and storage:
    if key:
      if item1:
        oldwrap = storage.get(item1, {}).get("wrap", {}).get(key, 0)
      elif item2:
        oldwrap = storage.get("wrap", {}).get(item2, {}).get(key, 0)
      else:
        oldwrap = storage.get("wrap", {}).get(key, 0)
    else:
      if item1:
        oldwrap = storage.get(item1, {}).get("wrap", 0)
      elif item2:
        oldwrap = storage.get("wrap", {}).get(item2, 0)
      else:
        oldwrap = storage.get("wrap", 0)
  else:
    oldwrap = 0

  if new < old:
    #if wrap is improbably large don't wrap, and ignore new actual
    if (old - new) < 100e6:
      newwrap = oldwrap
      old = new
    else:
      newwrap = oldwrap + 1
  else:
    newwrap = oldwrap

  # DO wrap at 64-bit boundary
  c1 = old + (oldwrap * COUNTER32)
  if c1 > COUNTER64:
    c1 -= COUNTER64

  c2 = new + (newwrap * COUNTER32)
  if c2 > COUNTER64:
    newwrap = 0
    c2 -= COUNTER64

  return c1, c2, newwrap

def calc_rate(dtime, value):
  return int(ceil(float(value) / dtime))

def timetosecs(timetxt):
  multipliers = {"sec": 1, "min": 60, "hours": 3600, "days": 86400}

  # Process the elements in reverse word order
  next_multiplier = 0
  seconds = 0
  for e in timetxt.split()[::-1]:
    if next_multiplier:
      seconds += (int(e) * next_multiplier)
      next_multiplier = 0
    else:
      if e in multipliers:
        next_multiplier = multipliers[e]
      else:
        break

  return seconds

def getuptimegauge(args, storage):
  uptime = grep("", runcmd(args, "cat /proc/uptime"), field=0, head=1, tofloat=True)[0]

  storage[2] = storage[1]
  storage[1] = (time.time(), {"uptime": uptime})
  storage[0] =   storage[1]

def formatuptimegauge(args, storage, filter=None, verbose=False):
  if not storage[0][1]: return

  output = []

  if verbose:
    output.append("uptime: %d" % storage[0][1]["uptime"])
  else:
    output.append("uptime:%d" % storage[0][1]["uptime"])

  return "\n".join(output) if verbose else " ".join(output)

def getcpugauge(args, storage):
  storage[2] = storage[1]
  storage[1] = (time.time(), grep("", runcmd(args, "cat /proc/stat"), head=1))

  if storage[2][0] == 0:
    time.sleep(1.0)
    getcpugauge(args, storage)
    return

  new = storage[1]
  old = storage[2]
  dTime = new[0] - old[0]
  dTime = 1.0 if dTime <= 0 else dTime

  c1 = new[1].split(" ")
  c2 = old[1].split(" ")
  c = []
  for i in range(1, 8):
    c.append((int(c1[i]) - int(c2[i])) / dTime / 2)
  storage[0] = (dTime, {"01usr": c[0], "02nic": c[1], "03sys": c[2],
                        "04idle":c[3], "05io":  c[4], "06irq": c[5],
                        "07sirq":c[6], "08tot": 100 - c[3]})

def formatcpugauge(args, storage, filter=None, verbose=False):
  if not storage[0][1]: return

  output = []

  for c in sorted(storage[0][1]):
    key = "cpu%s" % c[2:]
    if not filter or filter == key:
      if verbose:
        output.append("%-7s: %5.2f" % (key, storage[0][1][c]))
      else:
        output.append("%s:%.2f" % (key, storage[0][1][c]))

  return "\n".join(output) if verbose else " ".join(output)

def getloadgauge(args, storage):
  storage[2] = storage[1]
  storage[1] = (time.time(), runcmd(args, "cat /proc/loadavg"))

  if storage[2][0] == 0:
    storage[2] = storage[1]

  new = storage[1]
  old = storage[2]
  dTime = new[0] - old[0]
  dTime = 1.0 if dTime <= 0 else dTime
  LOAD = new[1].split(" ")
  storage[0] = (dTime, {"011min": LOAD[0], "025min": LOAD[1], "0315min": LOAD[2]})

def formatloadgauge(args, storage, filter=None, verbose=False):
  if not storage[0][1]: return

  output = []

  loads = storage[0][1]
  for l in sorted(loads):
    key = l[2:]
    if not filter or filter == key:
      output.append("%s:%s" % (key, loads[l]))

  return "\n".join(output) if verbose else " ".join(output)

def getmemgauge(args, storage):
  storage[2] = storage[1]
  storage[1] = (time.time(), grep("^[ ]*Mem:", runcmd(args, "free"), head=1))

  if storage[2][0] == 0:
    storage[2] = storage[1]

  new = storage[1]
  old = storage[2]
  dTime = new[0] - old[0]
  dTime = 1.0 if dTime <= 0 else dTime
  MEMORY = new[1].split(" ")
  storage[0] = (dTime, {"total": int(MEMORY[1]), "used": int(MEMORY[2]), "free": int(MEMORY[3])})

def formatmemgauge(args, storage, filter=None, verbose=False):
  if not storage[0][1]: return

  output = []

  if verbose:
    output.append("memused: %-10d" % storage[0][1]["used"])
    output.append("memfree: %-10d" % storage[0][1]["free"])
  else:
    output.append("memused:%d" % storage[0][1]["used"])
    output.append("memfree:%d" % storage[0][1]["free"])

  return "\n".join(output) if verbose else " ".join(output)

def getconngauge(args, storage):
  storage[2] = storage[1]
  storage[1] = (time.time(), int(runcmd(args, "cat /proc/sys/net/netfilter/nf_conntrack_count")))

  if storage[2][0] == 0:
    storage[2] = storage[1]

  new = storage[1]
  old = storage[2]
  dTime = new[0] - old[0]
  dTime = 1.0 if dTime <= 0 else dTime
  storage[0] = (dTime, {"total": new[1], "delta": new[1] - old[1], "rate": calc_rate(dTime, new[1] - old[1]) })

def formatconngauge(args, storage, filter=None, verbose=False):
  if not storage[0][1]: return

  output = []

  for key in ["total", "delta", "rate"]:
    if not filter or filter == key:
      if verbose:
        output.append("%s: %-6d" % (key, storage[0][1][key]))
      else:
        output.append("%s:%d" % (key, storage[0][1][key]))

  return "\n".join(output) if verbose else " ".join(output)

def getnetcounters(args, storage):
  def getrxtx(iface, data):
    line = grep("^[ ]*%s:" % iface, data)
    if line:
      line = line.split(":")[1].strip().split(" ")
      if iface in ["ppp1"]:
        return (int(line[8]), int(line[0]))
      else:
        return (int(line[0]), int(line[8]))
    else:
      return (0, 0)

  storage[2] = storage[1]

  netdev = runcmd(args, "cat /proc/net/dev")
  now = time.time()

  if storage[2][0] == 0:
    dTime = 1.0
  else:
    dTime = now - storage[2][0]
    dTime = 1.0 if dTime <= 0 else dTime

  current = {}
  info = {}
#  for i in ["eth0",  "eth1",  "eth2",  "eth3", "wl0", "wl1", "nas1"]:
  for i in ["eth0",  "eth1",  "eth2",  "eth3", "wl0", "wl1", "nas1", "ppp1"]:
    (rx, tx) = getrxtx(i, netdev)
    current[i] = {"rx": rx, "tx": tx}

    if storage[2][0] != 0:
      (oldrx, newrx, wraprx) = counterwrap(args, dTime, storage[0][1], storage[2][1][i]["rx"], rx, key="rx", item1=i)
      (oldtx, newtx, wraptx) = counterwrap(args, dTime, storage[0][1], storage[2][1][i]["tx"], tx, key="tx", item1=i)
    else:
      (oldrx, newrx, wraprx) = counterwrap(args, dTime, storage[0][1], rx, rx, key="rx", item1=i)
      (oldtx, newtx, wraptx) = counterwrap(args, dTime, storage[0][1], tx, tx, key="tx", item1=i)

    info[i] = {"actual": {"rx": newrx, "tx": newtx},
               "delta":  {"rx": (newrx - oldrx), "tx": (newtx - oldtx)},
               "wrap":   {"rx": wraprx, "tx": wraptx}}

  storage[1] = (now, current)
  storage[0] = (dTime, info)

def formatnetcounters(args, storage, filter=None, verbose=False):
  if not storage[0][1]: return

  output = []
  dtime = storage[0][0]

  for i in sorted(storage[0][1]):
    if not filter or filter == i:
      data = storage[0][1][i]
      if verbose:
        output.append("%-6s: RX: %18s (%13s, %11s) bytes, TX: %18s (%13s, %11s) bytes [rx: %3d, tx: %3d]" %
          (i, format(data["actual"]["rx"], ",d"),
              format(data["delta"]["rx"], ",d"),
              format(calc_rate(dtime, data["delta"]["rx"]), ",d"),
              format(data["actual"]["tx"], ",d"),
              format(data["delta"]["tx"], ",d"),
              format(calc_rate(dtime, data["delta"]["tx"]), ",d"),
              data["wrap"]["rx"],
              data["wrap"]["tx"]))

      else:
        if filter:
          output.append("rx:%d tx:%d" % (data["actual"]["rx"], data["actual"]["tx"]))
        else:
          output.append("%s_rx:%d %s_tx:%d" % (i, data["actual"]["rx"], i, data["actual"]["tx"]))

  return "\n".join(output) if verbose else " ".join(output)

def getadslcounters(args, storage):
  storage[2] = storage[1]

  adsl = runcmd(args, "adslctl info --stats").replace("\t", " ")
  now = time.time()

  sync = grep("^Bearer:", adsl, fields=[10,5], head=1, toint=True)[0]
  snr  = grep("^SNR \(dB\):", adsl, fields=[2,3], head=1, tofloat=True)[0]
  att  = grep("^Attn\(dB\):", adsl, fields=[1,2], head=1, tofloat=True)[0]
  pwr  = grep("^Pwr\(dBm\):", adsl, fields=[1,2], head=1, tofloat=True)[0]

  #http://www.kitz.co.uk/adsl/linestats_errors.htm
  #SF:    Super Frames. A superframe consists of 68 adsl frames plus a synchronisation frame.
  #       The adsl modem generates 4000 frames per second. The global duration of an adsl superframe is 17ms.
  #SFErr: Count of the Super Frames received which had an error.
  #ES:    Errored Seconds - number of seconds that have had CRC errors
  #SES:   Severely Errored Seconds - after 10 seconds of ES we start counting SES
  #UAS:   Unavailable Seconds (sync problem)
  #AS:    Available Seconds
  #LCD:   Lost Cell Delineation
  #OCD:   Out-of Cell Delineation
  #LOF:   Loss of Framing - DSL frames don't line up
  #LOS:   Loss of Signal/Sync
  SF       = grep("^SF:", adsl, fields=[1,2], head=1, toint=True)[0]
  SFErr    = grep("^SFErr:", adsl, fields=[1,2], head=1, toint=True)[0]
  RS       = grep("^RS:", adsl, fields=[1,2], head=1, toint=True)[0]
  RSCorr   = grep("^RSCorr:", adsl, fields=[1,2], head=1, toint=True)[0]
  RSUnCorr = grep("^RSUnCorr:", adsl, fields=[1,2], head=1, toint=True)[0]
  ES       = grep("^ES:", adsl, fields=[1,2], head=1, toint=True)[0]

  link     = grep("^Since Link time =", adsl, after=9)
  CRC      = grep("^CRC:", link, fields=[1,2], head=1, toint=True)[0]

  uptime   = timetosecs(link.split("\n")[0])

  storage[2] = storage[1]
  storage[1] = (time.time(), {"01sync":     {"type": "i", "down": sync[0],     "up": sync[1]},
                              "02snr":      {"type": "f", "down": snr[0],      "up": snr[1]},
                              "03att":      {"type": "f", "down": att[0],      "up": att[1]},
                              "04pwr":      {"type": "f", "down": pwr[0],      "up": pwr[1]},
                              "05SF":       {"type": "i", "down": SF[0],       "up": SF[1]},
                              "06SFErr":    {"type": "i", "down": SFErr[0],    "up": SFErr[1]},
                              "07RS":       {"type": "i", "down": RS[0],       "up": RS[1]},
                              "08RSCorr":   {"type": "i", "down": RSCorr[0],   "up": RSCorr[1]},
                              "09RSUnCorr": {"type": "i", "down": RSUnCorr[0], "up": RSUnCorr[1]},
                              "10ES":       {"type": "i", "down": ES[0],       "up": ES[1]},
                              "11CRC":      {"type": "i", "down": CRC[0],      "up": CRC[1]},
                              "12uptime":   {"type": "i", "down": uptime,      "up": uptime}})

  delta = {}
  for k in storage[1][1]:
    if storage[2][0] != 0:
      down = storage[1][1][k]["down"] - storage[2][1][k]["down"]
      up = storage[1][1][k]["up"] - storage[2][1][k]["up"]
    else:
      down = 0
      up = 0
    delta[k] = {"down": down, "up": up}

  if storage[2][0] == 0:
    dTime = 1.0
  else:
    dTime = now - storage[2][0]
    dTime = 1.0 if dTime <= 0 else dTime
  storage[0] = (dTime, {"actual": storage[1][1], "delta": delta})

def formatadslcounters(args, storage, filter=None, verbose=False):
  if not storage[0][1]: return

  output = []

  dtime = storage[0][0]
  actual = storage[0][1]["actual"]
  delta = storage[0][1]["delta"]

  for i in sorted(actual):
    key = i[2:]
    if not filter or filter == key:
      if verbose:
        if actual[i]["type"] == "f":
          output.append("%-8s - down: %13s (%9s, %7s), up: %13s (%9s, %7s)" %
                        (key, actual[i]["down"], delta[i]["down"], 0.0,
                              actual[i]["up"],   delta[i]["up"], 0.0))
        else:
          output.append("%-8s - down: %13s (%9s, %7s), up: %13s (%9s, %7s)" %
                        (key, format(actual[i]["down"], ",d"), format(delta[i]["down"], ",d"), format(calc_rate(dtime, delta[i]["down"]), ",d"),
                              format(actual[i]["up"], ",d"),   format(delta[i]["up"], ",d"), format(calc_rate(dtime, delta[i]["up"]), ",d")))
      else:
        if filter:
          output.append("down:%s up:%s" % (actual[i]["down"], actual[i]["up"]))
        else:
          output.append("%s_down:%s %s_up:%s" % (key, actual[i]["down"], key, actual[i]["up"]))

  return "\n".join(output) if verbose else " ".join(output)

def getiptablecounters(args, storage):
  iptables1 = runcmd(args, "iptables -t mangle -L POSTROUTING -vx")
  TOTAL = grep("^Chain ", iptables1, fields=[4,6], head=1, toint=True)[0]
  tosfix = grep(" tosfix ", iptables1, fields=[0,1], head=1, toint=True)[0]
  ackprio = grep(" ackprio ", iptables1, fields=[0,1], head=1, toint=True)[0]
  mindelay = grep(" Minimize-Delay CLASSIFY ", iptables1, fields=[0,1], head=1, toint=True)[0]
  dns_udp = grep(" udp dpt:53 ", iptables1, fields=[0,1], head=1, toint=True)[0]
  dns_tcp = grep(" tcp dpt:53 ", iptables1, fields=[0,1], head=1, toint=True)[0]
  http = grep(" tcp dpt:80 ", iptables1, fields=[0,1], head=1, toint=True)[0]
  https = grep(" tcp dpt:443 ", iptables1, fields=[0,1], head=1, toint=True)[0]
  ftp_data = grep(" tcp dpt:20 ", iptables1, fields=[0,1], head=1, toint=True)[0]
  ftp_ctrl = grep(" tcp dpt:21 ", iptables1, fields=[0,1], head=1, toint=True)[0]
  rtmp = grep(" tcp dpt:1935 ", iptables1, fields=[0,1], head=1, toint=True)[0]
  icmp = grep(" icmp ", iptables1, fields=[0,1], head=1, toint=True)[0]

  dns = [dns_udp[0] + dns_tcp[0], dns_udp[1] + dns_tcp[1]]
  ftp = [ftp_ctrl[0] + ftp_data[0], ftp_ctrl[1] + ftp_data[1]]

  iptables2 = runcmd(args, "iptables -t mangle -L ackprio -vx")
  ackprio_ign = grep(" !Normal-Service ", iptables2, fields=[0,1], head=1, toint=True)[0]
  ackprio_min = grep(" set Minimize-Delay ", iptables2, fields=[0,1], head=1, toint=True)[0]
  ackprio_max = grep(" set Maximize-Throughput ", iptables2, fields=[0,1], head=1, toint=True)[0]

  count_p = 0
  count_b = 0
  for fields in grep("anywhere", iptables1, fields=[2,0,1]):
    if fields[0] == "CLASSIFY":
      count_p += int(fields[1])
      count_b += int(fields[2])
  count_p += ackprio_min[0]
  count_b += ackprio_min[1]

  bulk = [TOTAL[0] - count_p, TOTAL[1] - count_b]

  # If bulk starts reporting negative packets or bytes
  # then its time to reset the counters
  if bulk[0] < 0 or bulk[1] < 0:
    runcmd(args, "iptables -t mangle -Z POSTROUTING")
    runcmd(args, "iptables -t mangle -Z ackprio")
    runcmd(args, "iptables -t mangle -Z tosfix")
    bulk = [0, 0]

  storage[2] = storage[1]
  storage[1] = (time.time(), {"01tosfix":      {"pkts": tosfix[0],      "bytes": tosfix[1]},
                              "02ackprio":     {"pkts": ackprio[0],     "bytes": ackprio[1]},
                              "03mindelay":    {"pkts": mindelay[0],    "bytes": mindelay[1]},
                              "04http":        {"pkts": http[0],        "bytes": http[1]},
                              "05https":       {"pkts": https[0],       "bytes": https[1]},
                              "06ftp":         {"pkts": ftp[0],         "bytes": ftp[1]},
                              "07rtmp":        {"pkts": rtmp[0],        "bytes": rtmp[1]},
                              "08icmp":        {"pkts": icmp[0],        "bytes": icmp[1]},
                              "09dns":         {"pkts": dns[0],         "bytes": dns[1]},
                              "10bulk":        {"pkts": bulk[0],        "bytes": bulk[1]},
                              "11TOTAL":       {"pkts": TOTAL[0],       "bytes": TOTAL[1]},
                              "12ackprio_ign": {"pkts": ackprio_ign[0], "bytes": ackprio_ign[1]},
                              "13ackprio_min": {"pkts": ackprio_min[0], "bytes": ackprio_min[1]},
                              "14ackprio_max": {"pkts": ackprio_max[0], "bytes": ackprio_max[1]}})

  if storage[2][0] == 0:
    storage[2] = storage[1]

  new = storage[1]
  old = storage[2]
  dTime = new[0] - old[0]
  dTime = 1.0 if dTime <= 0 else dTime
  actual = {}
  delta = {}
  wrap = {}
  if storage[0][1] == None:
    storage[0] = (0, {})
  for i in new[1]:
    np = new[1][i]["pkts"]
    op = old[1][i]["pkts"]
    (op, np, wrapp) = counterwrap(args, dTime, storage[0][1], old[1][i]["pkts"], new[1][i]["pkts"], key="pkts", item2=i)
    (ob, nb, wrapb) = counterwrap(args, dTime, storage[0][1], old[1][i]["bytes"], new[1][i]["bytes"], key="bytes", item2=i)
    actual[i] = {"pkts": np, "bytes": nb}
    delta[i] = {"pkts": np - op, "bytes": nb - ob}
    wrap[i] = {"pkts": wrapp, "bytes": wrapb}

  storage[0] = (dTime, {"actual": actual, "delta": delta, "wrap": wrap})

def formatiptablecounters(args, storage, filter=None, verbose=False):
  if not storage[0][1]: return

  output = []
  dtime = storage[0][0]
  actual = storage[0][1]["actual"]
  delta  = storage[0][1]["delta"]

  for i in sorted(actual):
    key = i[2:]
    if not filter or filter == key:
      if verbose:
        output.append("%-11s: %15s (%10s, %8s) bytes, %12s (%8s, %8s) pkts" %
                      (key,
                        format(actual[i]["bytes"], ",d"),
                        format(delta[i]["bytes"], ",d"),
                        format(calc_rate(dtime, delta[i]["bytes"]), ",d"),
                        format(actual[i]["pkts"], ",d"),
                        format(delta[i]["pkts"], ",d"),
                        format(calc_rate(dtime, delta[i]["pkts"]), ",d")
                        ))
      else:
        if filter:
          output.append("bytes:%d pkts:%d" % (actual[i]["bytes"], actual[i]["pkts"]))
        else:
          output.append("%s_bytes:%d %s_pkts:%d" % (key, actual[i]["bytes"], key, actual[i]["pkts"]))

  return "\n".join(output) if verbose else " ".join(output)

def gettrafficcounters(args, storage):
  storage[2] = storage[1]

  tc = runcmd(args, "tc -s class show dev ppp1")
  now = time.time()
  if storage[2][0] == 0:
    dTime = 1.0
  else:
    dTime = now - storage[2][0]
    dTime = 1.0 if dTime <= 0 else dTime

  groups = {}
  groups["01hiprio"] = grep("^class htb 1:10 ", tc, after=5)
  groups["02loprio"] = grep("^class htb 1:12 ", tc, after=5)
  groups["03parent"] = grep("^class htb 1:1 root", tc, after=5)

  current = {}
  info = {}

  for g in groups:
    data = groups[g]
    sent  = grep("^Sent ", data, field=1)
    #rate1 expressed as 1000Kbit when 1Mbit exceeded
    rate1 = grep("^rate ", data, field=1).replace("bit", "").replace("K", "000")
    rate2 = grep("^rate ", data, field=2).replace("pps", "")
    lended= grep("^lended: ", data, field=1)
    borrow= grep(" borrowed: ", data, field=3)
    dropped=grep("\(dropped ", data, field=6).replace(",", "")

    current[g] = {"01sent":    int(sent),
                  "02rate1":   int(rate1),
                  "03rate2":   int(rate2),
                  "04lended":  int(lended),
                  "05borrowed":int(borrow),
                  "06dropped": int(dropped)}

    actual = {}
    delta = {}
    wrap = {}
    for i in current[g]:
      if i not in ["02rate1", "03rate2"]:
        if storage[2][0] != 0:
          (ov, nv, wrapv) = counterwrap(args, dTime, storage[0][1], storage[2][1][g][i], current[g][i], item2=i)
        else:
          (ov, nv, wrapv) = counterwrap(args, dTime, storage[0][1], current[g][i], current[g][i], item2=i)
        delta[i] = nv - ov
        wrap[i] = wrapv
      else:
        ov = storage[2][1][g][i] if storage[2][0] != 0 else current[g][i]
        nv = current[g][i]
        wrapv = 0
      actual[i] = nv
    info[g] = {"actual": actual, "delta": delta, "wrap": wrap}

  storage[1] = (now, current)
  storage[0] = (dTime, info)

def formattrafficcounters(args, storage, filter=None, verbose=False):
  if not storage[0][1]: return

  output = []
  dtime = storage[0][0]

  keys = None
  for g in sorted(storage[0][1]):
    pkey = g[2:]
    if not filter or filter == pkey:
      group = storage[0][1][g]
      actual = group["actual"]
      delta = group["delta"]
      if not keys: keys = sorted(actual)
      line = " %s:" % pkey if verbose else ""
      for i in keys:
        ckey = i[2:]
        if verbose:
          if i.endswith("rate1"):
            line = "%s %s %7s" % (line, ckey[:-1], format(actual[i], ",d"))
          elif i.endswith("rate2"):
            line = "%s / %5s" % (line, format(actual[i], ",d"))
          else:
            if i.endswith("sent"):
              w = (15,9,7)
            elif i.endswith("dropped"):
              w = (6,4,2)
            else:
              w = (11,6,5)
            line = "%s %s %*s" % (line, ckey, w[0], format(actual[i], ",d"))
            if i in delta:
              line = "%s (%*s, %*s B/s)" % (line, w[1], format(delta[i], ",d"), w[2], format(calc_rate(dtime, delta[i]), ",d"))
        else:
          if filter:
            line = "%s %s:%d" % (line, ckey, actual[i])
          else:
            line = "%s %s_%s:%d" % (line, pkey, ckey, actual[i])

      output.append(line[1:])

  return "\n".join(output) if verbose else " ".join(output)

def getdoscounters(args, storage):
  dosdata = runcmd(args, "iptables -L DOS -vx")

  attacks = {}

  pname = ""
  for line in dosdata.split("\n"):
    drop = re.match(" *([0-9]*) *([0-9]*) *DROP .*", " %s" % line)
    if drop:
      if prefix:
        attacks[pname].update({"drop": {"pkts": int(drop.group(1)), "bytes": int(drop.group(2))}})
    else:
      prefix = re.match(" *([0-9]*) *([0-9]*) *DLOG .*prefix [`'](.*)'.*", " %s" % line)
      if prefix:
        pname = prefix.group(3).replace("Scan","").replace("Attack","").replace(" ","")
        attacks[pname] = {"log": {"pkts": int(prefix.group(1)), "bytes": int(prefix.group(2))}}

  storage[2] = storage[1]
  storage[1] = (time.time(), attacks)

  if storage[2][0] == 0:
    storage[2] = storage[1]
  if storage[0][1] == None:
    storage[0] = (0, {})

  new = storage[1]
  old = storage[2]
  dTime = new[0] - old[0]
  dTime = 1.0 if dTime <= 0 else dTime
  actual = {}
  delta = {}
  for i in new[1]:
    (op, np, wrapp) = counterwrap(args, dTime, storage[0][1], old[1][i]["drop"]["pkts"], new[1][i]["drop"]["pkts"], key="pkts", item2=i)
    (ob, nb, wrapb) = counterwrap(args, dTime, storage[0][1], old[1][i]["drop"]["bytes"], new[1][i]["drop"]["bytes"], key="bytes", item2=i)
    actual[i] = {"pkts": np, "bytes": nb}
    delta[i] = {"pkts": np - op, "bytes": nb - ob}

  storage[0] = (dTime, {"actual": actual, "delta": delta})

def formatdoscounters(args, storage, filter=None, verbose=False):
  if not storage[0][1]: return

  output = []
  dtime = storage[0][0]
  actual = storage[0][1]["actual"]
  delta  = storage[0][1]["delta"]

  for i in sorted(actual):
    key = i
    if not filter or filter == key:
      if verbose:
        output.append("%-15s: %15s (%10s, %8s) bytes, %12s (%8s, %8s) pkts" %
                      (key,
                        format(actual[i]["bytes"], ",d"),
                        format(delta[i]["bytes"], ",d"),
                        format(calc_rate(dtime, delta[i]["bytes"]), ",d"),
                        format(actual[i]["pkts"], ",d"),
                        format(delta[i]["pkts"], ",d"),
                        format(calc_rate(dtime, delta[i]["pkts"]), ",d")
                        ))
      else:
        if filter:
          output.append("bytes:%d pkts:%d" % (actual[i]["bytes"], actual[i]["pkts"]))
        else:
          output.append("%s_bytes:%d %s_pkts:%d" % (key, actual[i]["bytes"], key, actual[i]["pkts"]))

  return "\n".join(output) if verbose else " ".join(output)

def init():
  global DEBUG

  UPT = [(0, None), (0, None), (0, None)]
  CPU = [(0, None), (0, None), (0, None)]
  LOAD= [(0, None), (0, None), (0, None)]
  MEM = [(0, None), (0, None), (0, None)]
  NET = [(0, None), (0, None), (0, None)]
  ADSL= [(0, None), (0, None), (0, None)]
  IPT = [(0, None), (0, None), (0, None)]
  TC  = [(0, None), (0, None), (0, None)]
  CONN= [(0, None), (0, None), (0, None)]
  DOS = [(0, None), (0, None), (0, None)]

  SENSORS = {"uptime":{"storage": UPT, "get": getuptimegauge,    "format": formatuptimegauge},
             "cpu":   {"storage": CPU, "get": getcpugauge,       "format": formatcpugauge},
             "load":  {"storage": LOAD,"get": getloadgauge,      "format": formatloadgauge},
             "mem":   {"storage": MEM, "get": getmemgauge,       "format": formatmemgauge},
             "conn":  {"storage": CONN,"get": getconngauge,      "format": formatconngauge},
             "net":   {"storage": NET, "get": getnetcounters,    "format": formatnetcounters},
             "adsl":  {"storage": ADSL,"get": getadslcounters,   "format": formatadslcounters},
             "ipt":   {"storage": IPT, "get": getiptablecounters,"format": formatiptablecounters},
             "tc":    {"storage": TC,  "get": gettrafficcounters,"format": formattrafficcounters},
             "dos":   {"storage": DOS, "get": getdoscounters,    "format": formatdoscounters}
             }

  parser = argparse.ArgumentParser(description="Extract SNMP-type counters from router", \
                    formatter_class=lambda prog: argparse.HelpFormatter(prog,max_help_position=25,width=90))

  parser.add_argument("-v", "--verbose", action="store_true", help="Display diagnostic output")
  parser.add_argument("-a", "--host", type=str, help="Hostname or ip address of router or daemon (default %s and %s respectively)" % (ROUTER_HOST, DAEMON_HOST))
  parser.add_argument("-p", "--port", type=int, help="Listening port on router or daemon server (default %d and %d respectively)" % (ROUTER_PORT, DAEMON_PORT))
  parser.add_argument("-e", "--email", metavar="from-address", default=None, help="Send email on error/failure, at least once a day")
  parser.add_argument("-c", "--cache", type=int, default=30, help="Cache period in seconds (default 30)")

  group = parser.add_argument_group("daemon")
  group.add_argument("-d", "--daemon", action="store_true", help="Run as a daemon")
  parser.add_argument("-l", "--listen", type=int, default=DAEMON_PORT, help="Port on which daemon should listen (default %d)" % DAEMON_PORT)
  mutex = group.add_mutually_exclusive_group()
  mutex.add_argument("-64", "--wrap", action="store_const", dest="wrap", const=True, help="Emulate 64-bit counters by accumulating counter wraps")
  mutex.add_argument("-32", "--nowrap", action="store_const", dest="wrap", const=False, help="Allow counters to wrap at 32-bit boundaries")

  group = parser.add_argument_group("client")
  group.add_argument("-D", "--proxy", action="store_true", help="Proxy request via the SNMPD daemon")
  group.add_argument("-s", "--sensor", nargs="+", metavar="SENSOR", choices=SENSORS, default=SENSORS.keys(), help="Name of sensors to be retrieved")
  group.add_argument("-i", "--interval", type=int, default=0, help="Interval in seconds between updates.")
  group.add_argument("-n", "--count", type=int, default=None, help="Display count. Default is 1, unless interval is specified in which case infinite")
  group.add_argument("-f", "--filter", type=str, help="Filter")
  group.add_argument("-nc", "--noclear", action="store_true", help="Do not clear display on each update")

  parser.set_defaults(wrap=EMULATE64BIT)

  args = parser.parse_args()

  if args.filter and len(args.sensor) != 1:
    parser.exit(2, "ERROR: Must specify a single sensor name if specifying a filter!\n")

  if args.daemon or not args.proxy:
    args.host = args.host if args.host else ROUTER_HOST
    args.port = args.port if args.port else ROUTER_PORT
  else:
    args.host = args.host if args.host else DAEMON_HOST
    args.port = args.port if args.port else DAEMON_PORT

  if not args.count:
    args.count = 0 if args.interval != 0 else 1

  DEBUG = args.verbose

  return (args, SENSORS)

def countdown(delay):
  while (delay > 0):
    print("Next update in %d second%s... " % (delay, "s"[delay==1:]), end="\r")
    sys.stdout.flush()
    time.sleep(1.0)
    delay -= 1

def emailrequired(args, lastemail):
  if args.email:
    if not lastemail or (time.time() - lastemail) >= 7200:
      return True

  return False

def sendemail(args, errors):
  if not os.access(BIN_EMAIL, os.X_OK):
    log("ERROR: Unable to send email, no email executable available!")
    return False

  RESULT = False

  f = tempfile.NamedTemporaryFile(mode="wb")

  try:
    f.write("To: %s\n" % args.email)
    f.write("Subject: Gateway is not responding to SNMP requests\n\n")
    f.write("\n".join(errors))
    f.flush()
    try:
      f.seek(0)
      subprocess.check_output((BIN_EMAIL), stdin=f)
      log("SUCCESS: Failure email has been sent")
      RESULT = True
    except Exception as e:
      log("ERROR: Email error2: %s" % str(e))
  except Exception as e:
    log("ERROR: Email error1: %s" % str(e))

  f.close()

  return RESULT

def readsensors(args, sensors, key=None):
  errors = []
  for s in args.sensor:
    if not key or s == key:
      try:
        if args.proxy:
          filter = args.filter if args.filter else ""
          verbose = "Y" if args.verbose else "N"
          sensors[s]["storage"][0] = (time.time(), runcmd(args, "%s|%s|%s|%d" % (s, filter, verbose, args.cache)))
        else:
          sensors[s]["get"](args, sensors[s]["storage"])
      except Exception as e:
        raise #FIXME
        errors.append("SENSOR: %s" % s)
        errors.append(traceback.format_exc())
        if LASTCOMMAND:
          errors.append("COMMAND:")
          errors.append(LASTCOMMAND)
          errors.append(">" * 50)
          if LASTRESULT: errors.append(LASTRESULT)
          errors.append("<" * 50)

  return errors

def runserver(args, sensors):
  s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
  s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
  # Bind to any interface ("") using the specified port
  s.bind(("", args.listen))

  lastemail = None
  while True:
    errors = []
    s.listen(1)
    conn, addr = s.accept()
    data = conn.recv(128)
    if data:
      try:
        items = data.split("|")
        key = items[0]
        filter = items[1]
        verbose = (items[2] == "Y")
        cache = int(items[3])
        t = sensors[key]["storage"][1][0]
        if (t == 0 or (time.time() - t) >= cache):
          log("Uncached request: [%s], [%s], [%s]" % (key, filter, verbose))
          sensors[key]["get"](args, sensors[key]["storage"])
        else:
          log("Using cached result: [%s], [%s], [%s]" % (key, filter, verbose))
        data = sensors[key]["format"](args, sensors[key]["storage"], filter, verbose)
        conn.send("%s\n" % data)
      except Exception as e:
        errors.append("SENSOR: %s" % key)
        errors.append(traceback.format_exc())
        if LASTCOMMAND:
          errors.append("COMMAND:")
          errors.append(LASTCOMMAND)
          errors.append(">" * 50)
          if LASTRESULT: errors.append(LASTRESULT)
          errors.append("<" * 50)
        if not args.email:
          log("\n".join(errors))
        elif emailrequired(args, lastemail):
          if sendemail(args, errors):
            lastemail = time.time()
    conn.close()

def runclient(args, sensors):
  count = 0
  lastemail = None
  while True:
    count += 1

    errors = readsensors(args, sensors)

    if errors:
      if not args.email:
        log("\n".join(errors))
      elif emailrequired(args, lastemail):
        if sendemail(args, errors):
          lastemail = time.time()
    else:
      if not args.noclear and args.interval != 0:
        os.system("cls" if os.name == "nt" else "clear")
      for s in args.sensor:
        if args.proxy:
          print(sensors[s]["storage"][0][1])
        else:
          print(sensors[s]["format"](args, sensors[s]["storage"], args.filter, args.verbose))

    if args.count != 0 and count >= args.count: break
    if args.interval != 0:
      countdown(args.interval)

def main((args, sensors)):
  if args.daemon:
    runserver(args, sensors)
  else:
    runclient(args, sensors)

if __name__ == "__main__":
  try:
    main(init())
  except (KeyboardInterrupt, SystemExit) as e:
    if type(e) == SystemExit: sys.exit(int(str(e)))
