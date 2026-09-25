#!/bin/bash
# Upload the Midea M-Thermal integration to Home Assistant - restart required
PI="makro@192.168.178.107"
DEST="/root/homeassistant/config/custom_components"
tar -C custom_components --exclude=__pycache__ -cf - midea_m_thermal \
  | ssh $PI "sudo mkdir -p $DEST && sudo rm -rf $DEST/midea_m_thermal && sudo tar -C $DEST -xf -"
echo "Done! Restart HA: ssh $PI \"sudo docker restart home-assistant\""
