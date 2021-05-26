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
    
Socket server:

You can control devices through socket client. It can by ncat on linux, or socket widget on android. You need to put server IP, Port (UDP or TCP) and command.

Available commands:
denonvolup
denonvoldn
denonsat
denontv
denonoff
webosoff

Dependencies:
=

    requirements.txt



Tested with python 3.7.3 on Raspbian

