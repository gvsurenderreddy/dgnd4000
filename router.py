#!/usr/bin/env python
# -*- coding: utf-8 -*-

#
# See: http://subsecret.dk/wiki/Netgear_DGND4000_Optimizer
#

from __future__ import print_function
import os, sys
import socket, base64, hashlib, time
import argparse
import telnetlib

if sys.version_info >= (3, 0):
  import http.client as httplib
  import urllib.request as urllib2
  basestring = (str, bytes)
else:
  import httplib, urllib2

def EnableTelnet(args):
  def query(text):
    if args.verbose:
      print("ROUTER > %s" % text)
    url.request("GET", text, None, headers)
    response = url.getresponse()
    if sys.version_info >= (3, 0):
      data = response.read().decode("utf-8")
    else:
      data = response.read()
    if args.verbose:
      print("STATUS < %d" % response.status)
      for line in data.split("\n"):
        if args.verbose:
          print("ROUTER < %s" % line)
    if response.status not in [httplib.OK, httplib.FOUND]:
      raise httplib.HTTPException("Status %d" % response.status)
    return data

  print("Enabling telnet on router")

  try:
    url = httplib.HTTPConnection(args.ipaddress, 80, False, 5.0)
    if args.verbose > 1: url.set_debuglevel(1)
    url.connect()
  except Exception as e:
    print("Failed to connect. %s" % str(e))
    return False

  token = "%s:%s" % (args.username, args.password)
  if sys.version_info >= (3, 0):
    WEB_AUTH_TOKEN = base64.encodestring(bytes(token, "utf-8")).decode()
  else:
    WEB_AUTH_TOKEN = base64.encodestring(token)
  WEB_AUTH_TOKEN = WEB_AUTH_TOKEN.replace("\n", "")

  headers = {"Authorization": "Basic %s" % WEB_AUTH_TOKEN}

  attempt = 0
  while attempt <= 2:
    attempt += 1
    try:
      # Enable telnet
      data = query("/setup.cgi?todo=debug")

      if data == "Debug Enable!":
        # Clean up after ourselves
        data = query("/setup.cgi?todo=logout")
        print("Telnet is now active")
        return True
      elif data.find("You are currently logged in from another device.") != -1:
        print("Already logged in on another device - logging out other user")
        # Logout the currently logged in user, and try again
        data = query("/setup.cgi?todo=login&this_file=multi_login.html")

    except socket.timeout:
      print("Router is not responding to web request")
      return False

    except Exception as e:
      if attempt > 1:
        print("ERROR, HTTP Exception: %s" % str(e))

  print("Unable to enable telnet")
  return False

def HasTelnet(args):
  try:
    telnet = telnetlib.Telnet(args.ipaddress)
    telnet.close()
    return True
  except:
    return False

def ConfigureRouter(args):
  def read(text):
    if args.verbose:
      print("TELNET < %s" % text)
    telnet.read_until(text)

  def write(text, delay=None):
    if args.verbose:
      print("TELNET > %s" % text)
    telnet.write("%s\n" % text)
    if delay:
      telnet.write("sleep %d\n" % delay)

  def killall(procname):
    write("[ -n \"$(pidof %s)\" ] && killall %s" % (procname, procname))

  def dload(path, output, executable=False):
    print("Installing: %s..." % path)
    write("[ ! -f %s ] && wget %s -O %s" % (output, path, output))
    if executable:
      write("[ ! -x %s ] && chmod +x %s" % (output, output))

  def copyfile(source, target, executable=False):
    path = os.path.realpath(__file__)
    dir = os.path.dirname(path)
    if not os.path.exists(source):
      source = os.path.join(dir, source)

    write('rm -f "%s"' % target)
    for l in open(source, "r").read().split("\n"):
      write('echo "%s" >> %s' % (l.replace('"', '\\\"').replace("$","\\$"), target))
    write("chmod +x %s" % target)

  # Sleep, to allow previous connection to close?
  time.sleep(1.0)

  telnet = telnetlib.Telnet(args.ipaddress)
  if args.verbose > 1: telnet.set_debuglevel(1)

  read("login: ")
  write(args.username)
  read("Password: ")
  write(args.password, 1)

  BOOTSTRAP="/home/config.sh"
#  copyfile("config.sh", BOOTSTRAP, True)
#  write("[ -z \"$(grep %s /etc/ppp/ip-up)\" ] && echo \"[ \\$pppIF = ppp1 ] && %s verbose \\\"\\$@\\\" &\" >>/etc/ppp/ip-up" % (BOOTSTRAP, BOOTSTRAP))

  print("Restarting wan interface to apply QoS settings...")
#  write("/usr/sbin/rc wan restart")

  write("exit")

  # Read lines or nothing is executed...
  for line in telnet.read_all().split("\n"):
    if args.verbose:
      print("TELNET < %s" % line)

  telnet.close()

  print("Router successfully re-configured")

  return True

def init():
  parser = argparse.ArgumentParser(description="Enable telnet and re-configure Netgear router", \
                    formatter_class=lambda prog: argparse.HelpFormatter(prog,max_help_position=25,width=90))

  parser.add_argument("-u", "--username", metavar="USERNAME", default="admin", help="Username with which to authenticate")
  parser.add_argument("-p", "--password", metavar="PASSWORD", required=True, help="Password with which to authenticate")
  parser.add_argument("-i", "--ipaddress", metavar="IPADDRESS", default="192.168.0.1", help="IP address of router")
  parser.add_argument("-f", "--force", action="store_true", help="Reconfigure even when telnet already active")
  parser.add_argument("-v", "--verbose", action="count", default=0, help="Verbose")

  args = parser.parse_args()

  return args

def main(args):
  if HasTelnet(args):
    print("Telnet already activated!")
    if args.force:
      ConfigureRouter(args)
  elif EnableTelnet(args):
    ConfigureRouter(args)

try:
  main(init())
except (KeyboardInterrupt, SystemExit) as e:
  if type(e) == SystemExit: sys.exit(int(str(e)))
