My own media center based on Raspberry Pi.
=

Elements that are part of the system:
1. Raspberry Pi
2. LG WebOS4 TV
3. AVR Denon 1311
4. Chromecast
5. OpenWRT router

What this script can do:
1. Reading IR signal from LG's remote additional power button destined for SAT tuner and convert it into Denon AVR IR power signal.
2. Changing WebOS TV sound output to Optical Out, if not already changed.
3. It runs TCP and UDP server to that allows to control WebOS and Denon AVR through socket client.
4. Running predefined youtube videos or playlists on Chromecast.
5. Running tracks or playlists on Chromecast.
6. Monitoring selected users if they are connected to local Access Point. It requires routers with openwrt or other linux based.
7. Scheduler can run tasks on specific time. Task like start youtube video or spotify on chromecast.
8. Return home function checks within given time if monitored user is back home. If yes script is running Spotify playlist on Chromecast.


Configuration is stored inside tasker.conf file.
    
Socket server
=

You can control devices through socket client. It can by ncat on linux, or socket widget on android. You need to put server IP, Port (UDP or TCP) and command.

Available commands:

1. denonvolup
2. denonvoldn
3. denonsat
4. denontv
5. denonoff
6. webosoff

MAC Monitor
=
    Command for access points in cron every 1min or less with extra script
    wlan0 and wlan1 are an example wifi interfaces. You should adequate for your router.
    
    ((echo "mac_list_ap1 ago" && (iwinfo wlan0 assoclist & iwinfo wlan1 assoclist)) | grep ago | cut -d " " -f1 | tr "\n" ";") | xargs -I ARG echo ARG | ncat -u HOST_IP UDP_PORT
    ((echo "mac_list_ap2 ago" && (iwinfo wlan0 assoclist & iwinfo wlan1 assoclist)) | grep ago | cut -d " " -f1 | tr "\n" ";") | xargs -I ARG echo ARG | ncat -u HOST_IP UDP_PORT

Power button logic and additional function
=
<b>Denon on/off logic:</b>

This was created because Denon is not only used as TV sound output. Other output are used e.g. SAT.

Problem: there is only one custom button on webos remote (STB PWR) to power on, power off other device
and the only info I can get from denon is power state (no current input set)
Example: TV is off, Denon is on with input SAT. I want to start watching TV. Turn TV on and press STB PWR on
TV remote. Without additional logic Denon will go off (if Denon is power on: turn off)
Solution: Based on users habits some conditions were created

Condition 0: Denon is on (if you are here it means condition was met)

Condition 1: TV must by ON

Condition 2: TV was turn on recently - default within 180s

If cond 1 and 2 are met denon do not go off only input is change to tv

There is period (default 10s) in which you can bypass
logic (additional STD PWR press) if it doesn't meet expectations

<b>Additional functions:</b>

If TV is ON and you will press power buttom twice denon output will be changed to TV.

If TV is OFF and you will press power buttom twice denon output will be changed to SAT.

Dependencies:
=

    requirements.txt



Tested with python 3.7.3 on Raspbian

