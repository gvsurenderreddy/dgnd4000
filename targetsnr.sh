#!/bin/sh

Q4SNR="$(adslctl profile --show | grep "Training Margin" | awk '{print $5}')"

echo "Current Target SNR Margin (Q4 in dB): ${Q4SNR}"

[ "x${Q4SNR}" = "x-1(DEFAULT)" ] && Q4SNR="100"

if [ "x${Q4SNR}" != "x$1" ]; then
  echo "Setting new Target SNR Margin (Q4 in dB): $1"
  adslctl configure --snr $1
  exit 1
else
  exit 0
fi
