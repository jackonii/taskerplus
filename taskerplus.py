#!/usr/bin/python3

import asyncio
import shlex
import subprocess
from threading import Thread
import argparse
import logging
import sys
import time
import datetime
import pychromecast  # https://github.com/home-assistant-libs/pychromecast
from pychromecast.controllers.youtube import YouTubeController
from pychromecast.controllers.spotify import SpotifyController
import spotify_token as st
import spotipy
import json
import zeroconf
import random

try:
    from pylgtv import WebOsClient  # https://github.com/TheRealLink/pylgtv
except ModuleNotFoundError as e:
    print(e, '\n')
    sys.exit()

# Set tuner CanalSatHD or CanalSat on WeOS TV / magic remote

# Denon IR commands globals
GAP = '20000'  # Set gap between scancodes in microseconds
IRCTL_SEND = "ir-ctl -d //dev//lirc0"

# Strings are file names with scancodes for Denon AVR 1311
DENOFF = 'denonoff'
DENTV = 'denontv'
DENSAT = 'denonsat'
DENVOLUP = 'denonvolup'
DENVOLDN = 'denonvoldn'

# Command line args for ir blaster
# cmd_tv = shlex.split(IRCTL_SEND + f" -s{DENTV} --gap={GAP} -s{DENTV} --gap={GAP} -s{DENTV} --gap={GAP}")
# cmd_off = shlex.split(IRCTL_SEND + f" -s{DENOFF} --gap={GAP} -s{DENOFF} --gap={GAP} -s{DENOFF} --gap={GAP}")
# cmd_sat = shlex.split(IRCTL_SEND + f" -s{DENSAT} --gap={GAP} -s{DENSAT} --gap={GAP} -s{DENSAT} --gap={GAP}")
# cmd_volup = shlex.split(IRCTL_SEND + f" -s{DENVOLUP} --gap={GAP} -s{DENVOLUP} --gap={GAP} -s{DENVOLUP} --gap={GAP}" * 3)
# cmd_voldn = shlex.split(IRCTL_SEND + f" -s{DENVOLDN} --gap={GAP} -s{DENVOLDN} --gap={GAP} -s{DENVOLDN} --gap={GAP}" * 3)

# Command line for ir reader
cmd_ir_read = shlex.split("ir-ctl -d //dev//lirc1 -r")
cmd_denon = shlex.split("tvservice -n")

# Globals for WebOsClientMod class
EP_SET_AUDIO_OUTPUT = "com.webos.service.apiadapter/audio/changeSoundOutput"  # Additional commands for WebOsClient
EP_GET_AUDIO_OUTPUT = "com.webos.service.apiadapter/audio/getSoundOutput"
EP_GET_TV_POWER = "com.webos.service.tvpower/power/getPowerState"
EP_POWER_OFF = "system/turnOff"
"""
Other for future use:
system/getSystemInfo
com.webos.service.tvpower/power/turnOnScreen
"""

# Globals values setup through config file: 'tasker.conf'
# IP Globals
HOST = None
WEBOS = None
UDP_PORT = 0
TCP_PORT = 0
AP1 = None
AP2 = None

# Mac monitor monitored users
MAC_LIST = {}

# Scheduler for Play Youtube
START_TIME = datetime.timedelta(hours=6, minutes=50, seconds=00)  # Time to start playing YT on Denon + Chromecast
WEEKDAY = [0, 1, 2, 3, 4]  # Scheduler working days. ) 0-Monday, 1-Tuesday ... 6-Sunday
VIDEO_ID = ["5qap5aO4i9A"]  # Youtube Video ID
CAST_NAME = None  # Chromecast device Name

# Return home function Globals
# Time interval during which program checks if the user shows up at home
START_HOUR = 15
STOP_HOUR = 20
# User MAC for Return Home functionality. Must be within MAC Monitor users list
RH_MAC = None

# Spotify globals
URI = "spotify:playlist:2K8yefvBUtiZNidagTIeca"  # Chillout_session

# Cookies
SP_DC = None
SP_KEY = None


def get_globals():
    global HOST, WEBOS, UDP_PORT, TCP_PORT, SP_KEY, SP_DC, AP1, AP2, CAST_NAME, MAC_LIST, VIDEO_ID, WEEKDAY, \
        START_TIME, RH_MAC, START_HOUR, STOP_HOUR, URI
    try:
        with open(r'tasker.conf', 'r') as file:
            for f in file.readlines():
                if not len(f.strip()):
                    continue
                elif f.strip()[0] == '#':
                    continue
                elif 'HOST' in f:
                    HOST = f.strip('HOST').strip()
                elif 'WEBOS' in f:
                    WEBOS = f.strip('WEBOS').strip()
                elif 'UDP_PORT' in f:
                    UDP_PORT = int(f.strip('UDP_PORT').strip())
                elif 'TCP_PORT' in f:
                    TCP_PORT = int(f.strip('TCP_PORT').strip())
                elif 'SP_DC' in f:
                    SP_DC = f.strip('SP_DC').strip()
                elif 'SP_KEY' in f:
                    SP_KEY = f.strip('SP_KEY').strip()
                elif 'AP1' in f:
                    AP1 = f.strip('AP1').strip()
                elif 'AP2' in f:
                    AP2 = f.strip('AP2').strip()
                elif 'CAST_NAME' in f:
                    CAST_NAME = f.strip('CAST_NAME').strip()
                elif 'USER_CRED' in f:
                    MAC_LIST[f.strip('USER_CRED').strip().split()[0]] = [f.strip('USER_CRED').strip().split()[1], 0]
                elif 'VIDEO_ID' in f:
                    VIDEO_ID = f.strip('VIDEO_ID').strip().split()
                elif 'WEEKDAY' in f:
                    WEEKDAY = list(map(int, f.strip('WEEKDAY').strip().split()))
                elif 'SCHED_TIME' in f:
                    h = int(f.strip('SCHED_TIME').split(":")[0])
                    m = int(f.strip('SCHED_TIME').split(":")[1])
                    s = int(f.strip('SCHED_TIME').split(":")[2])
                    START_TIME = datetime.timedelta(hours=h, minutes=m, seconds=s)
                elif 'RH_MAC' in f:
                    RH_MAC = f.strip('RH_MAC').strip()
                elif 'START_HOUR' in f:
                    START_HOUR = int(f.strip('START_HOUR').strip())
                elif 'STOP_HOUR' in f:
                    STOP_HOUR = int(f.strip('STOP_HOUR').strip())
                elif 'SPOTIFY_URI' in f:
                    URI = f.strip('SPOTIFY_URI').strip()


    except Exception as e:
        print(e)
        sys.exit()


class UDPServerProtocol:
    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        if addr[0] == AP1 or addr[0] == AP2:
            message = data.decode().strip().rstrip(';')
            mac_monitor.dispatcher(message, addr)
        else:
            message = data.decode().strip()
            logging.info(f'[UDPSV] UDP datagram from {addr} - Received: {message}')
            # self.transport.sendto('Response message', addr)  #  Uncomment to send response to the client
            # if args.sync:
            #    task_dispatcher_sync(message)
            # else:
            asyncio.create_task(task_dispatcher(message))


class TCPServerProtocol(asyncio.Protocol):
    def connection_made(self, transport):
        peername = transport.get_extra_info('peername')
        logging.info(f'[TCPSV] TCP connection from {peername}')
        self.transport = transport

    def data_received(self, data):
        message = data.decode().strip()
        logging.info(f'[TCPSV] TCP packet received: {message}')
        # self.transport.write(b'Response message')  #  Uncomment to send response to the client
        # if args.sync:
        #    task_dispatcher_sync(message)
        # else:
        asyncio.create_task(task_dispatcher(message))
        logging.debug('[TCPSV] Close the client socket')
        self.transport.close()


async def sock_server():
    logging.info("[FLAGS] Starting UDP and TCP servers")

    # Get a reference to the event loop as we plan to use
    # low-level APIs.
    loop = asyncio.get_running_loop()

    # One protocol instance will be created to serve all
    # client requests.
    transport, protocol = await loop.create_datagram_endpoint(lambda: UDPServerProtocol(),
                                                              local_addr=(HOST, UDP_PORT))
    server = await loop.create_server(lambda: TCPServerProtocol(), HOST, TCP_PORT)
    # try:
    async with server:
        await server.serve_forever()
    # try:
    #     await asyncio.sleep(3600)  # Serve for 1 hour - for standalone UDP server (without TCP server)
    # finally:
    #    transport.close()


class MacMonitor:
    """Describe an object that gather and check MAC addresses attached do APs"""

    # command for access points in cron every 1min or less with extra script
    # ((echo "mac_list_ap1 ago" && (iwinfo wlan0 assoclist & iwinfo wlan1 assoclist))
    # | grep ago | cut -d " " -f1 | tr "\n" ";") | xargs -I ARG echo ARG | ncat -u HOST_IP UDP_PORT
    # ((echo "mac_list_ap2 ago" && (iwinfo wlan0 assoclist & iwinfo wlan1 assoclist))
    # | grep ago | cut -d " " -f1 | tr "\n" ";") | xargs -I ARG echo ARG | ncat -u HOST_IP UDP_PORT

    # Creates 2 list - one for each AP.
    def __init__(self):
        self.ap1_mac_list = []
        self.ap2_mac_list = []

    # Dispatch according to APs IP
    def dispatcher(self, message, addr):
        if addr[0] == AP1:
            self.ap1(message)
        elif addr[0] == AP2:
            self.ap2(message)

    # Fill the list with MAC addressees attached to AP1
    def ap1(self, message):
        self.ap1_mac_list[:] = []
        self.ap1_mac_list = message.split(';')[1:]
        logging.debug(f"[MAC_M] {self.ap1_mac_list}")

    # Fill the list with MAC addressees attached to AP2
    def ap2(self, message):
        self.ap2_mac_list[:] = []
        self.ap2_mac_list = message.split(';')[1:]
        logging.debug(f"[MAC_M] {self.ap2_mac_list}")

    # Combine both AP1 and AP2 MAC addresses lists, a remove duplicates (set())
    def show_all_mac(self):
        return list(set(self.ap1_mac_list + self.ap2_mac_list))

    # Check if MAC is present on merged AP1 and AP2 lists
    def is_mac_up(self, mac, mac_list):
        if mac in self.show_all_mac():  # if MAC is spotted
            if mac_list[mac][1] == 0:  # if MAC is spotted for the first time
                mac_list[mac][1] = time.time()  # Put timestamp when MAC was spotted
                logging.info(f"[MAC_M] {mac} : {mac_list.get(mac)[0]} is up")
            return True
        else:  # if MAC is absent
            if mac_list[mac][1] != 0:  # check if MAC was present before (recent status change)
                mac_list[mac][1] = 0  # If no longer present change status to 0
                logging.info(f"[MAC_M] {mac} : {mac_list.get(mac)[0]} is down")
            return False

    def check_mac_status(self, mac_list):
        for mac in mac_list.keys():
            self.is_mac_up(mac, mac_list)


async def device_monitor():
    """Check MAC status. Run as coroutine task"""
    logging.info("[MAC_M] Starting MAC monitor")
    while True:
        await asyncio.sleep(10)  # Time interval
        mac_monitor.check_mac_status(MAC_LIST)


async def return_home(mac, mac_list):
    """Check in given time if user appeared at home. If so - start youtube video"""
    logging.info("[AGENT] Starting return home function")
    while True:
        logging.debug("[AGENT] Starting while loop")
        now = datetime.datetime.now()
        if START_HOUR <= now.hour <= STOP_HOUR:  # if within given hours
            logging.debug(f"[AGENT] Time is in between {START_HOUR - STOP_HOUR}")
            if (now.timestamp() - mac_list[mac][1]) < 60 and mac_monitor.is_mac_up(mac, mac_list):  # if user is up
                # and is up for not longer than 60s. It prevents from running if user was up before given time period
                logging.info(f"[AGENT] User: {mac_list[mac][0]} returned home. Maybe some music ...")
                # await play_yt(wakeup=False)
                if not await is_denon_on(): 
                    play_sp_task_seeker()
                asyncio.create_task(play_sp())
                await asyncio.sleep(3600)  # No often than once in every 1h
            else:
                logging.debug("[AGENT] User is not present or on for longer time, start sleep for 15s")
                await asyncio.sleep(15)  # Check for user every 15 sec.
        elif now.hour < START_HOUR:  # if hours between 00:00 and START_HOUR
            logging.debug(f"[AGENT] Hour smaller then {START_HOUR}")
            current_time = datetime.timedelta(hours=now.hour, minutes=now.minute, seconds=now.second)
            border_time = datetime.timedelta(hours=START_HOUR, minutes=00, seconds=00)
            logging.debug(f"[AGENT] Start sleep for {border_time.seconds - current_time.seconds} sec")
            await asyncio.sleep(border_time.seconds - current_time.seconds)  # Wait till START_HOUR

        elif now.hour > STOP_HOUR:  # if hours between STOP_HOUR and 23:59
            logging.debug(f"[AGENT] Hour greater then {STOP_HOUR}")
            current_time = datetime.timedelta(hours=now.hour, minutes=now.minute, seconds=now.second)
            midnight = datetime.timedelta(seconds=86399)  # Seconds from 00:00 till 23:59
            logging.debug(f"[AGENT] Start sleep for {midnight.seconds - current_time.seconds} sec")
            await asyncio.sleep(midnight.seconds - current_time.seconds + 2)  # Wait till 00:01


async def timer(start, my_func):
    """Run scheduled task at given time. Run as coroutine task."""
    logging.info("[SCHED] Starting task scheduler")
    while True:
        now = datetime.datetime.now()  # Check current time
        current_time = datetime.timedelta(hours=now.hour, minutes=now.minute, seconds=now.second)
        if current_time > start:  # If true means that given time has past
            logging.debug("[SCHED] Start time is greater than actual time. Waiting.")
            await asyncio.sleep(86400 - current_time.seconds)  # Wait until midnight
        else:  # it means that to start time is less then (from midnight to start time) sec
            if now.weekday() not in WEEKDAY:  # Check if current day is on working list
                logging.debug("[SCHED] Won't start today")
                await asyncio.sleep(86400 - current_time.seconds)  # if not go to sleep
            else:  # Set the timer
                logging.debug(f'[SCHED] Waiting for {start.seconds - current_time.seconds} sec before start')
                await asyncio.sleep(start.seconds - current_time.seconds)  # go to sleep
                logging.info(f"[SCHED] Starting scheduled task: {my_func}")
                await my_func()  # Start func after sleep
                await asyncio.sleep(2)  # Prevent from running my_func multiple times within sec.


async def play_yt(wakeup=True, force=False):
    """Search and connet to chromecast and cast Youtube Video"""
    if await is_denon_on() and not force:  # Check if AVR denon is off (assuming nobody is using it)
        logging.info("[YTUBE] Denon is on. Casting rescheduled.")
        return

    if wakeup:
        logging.info("[YTUBE] Casting Youtube Video to Chromecast in wakeup mode")
    else:
        logging.info("[YTUBE] Casting Youtube Video to Chromecast")

    chromecasts, browser = pychromecast.get_listed_chromecasts(friendly_names=[CAST_NAME])
    if not chromecasts:
        logging.info(f'[YTUBE] No chromecast with name "{CAST_NAME}" discovered')
        pychromecast.discovery.stop_discovery(browser)
    else:

        cast = chromecasts[0]
        # Start socket client's worker thread and wait for initial status update
        cast.wait()

        yt = YouTubeController()
        cast.register_handler(yt)
        yt.play_video(random.choice(VIDEO_ID)) # pick random track
        await asyncio.sleep(1)
        # cast.set_volume(0.4)

        # Shut down discovery
        pychromecast.discovery.stop_discovery(browser)
        # cast.disconnect()
        await asyncio.sleep(1)
        await denon_send('sat')
        await asyncio.sleep(3)
        if not await is_denon_on():
            logging.info("[YTUBE] Denon is still off. Resending...")
            await denon_send('sat')
            await asyncio.sleep(3)
            if not await is_denon_on():
                logging.info("[YTUBE] Denon is still off. Aborting")
        if wakeup:
            cast.set_volume(0.4)
            await asyncio.sleep(1200)
            cast.set_volume(0.5)
            await asyncio.sleep(1200)
            cast.set_volume(0.7)
            await asyncio.sleep(1200)
            cast.set_volume(1)
            cast.disconnect()
        else:
            cast.set_volume(1)
            cast.disconnect()




async def play_sp(force=False):
    if await is_denon_on() and not force:
        logging.info("[SPOTI] Denon was on. Casting rescheduled.")
        return

    class Error(Exception):
        pass

    class NoValidToken(Error):
        """Raised if no valid token is found"""
        pass

    def get_token(sp_dc, sp_key, force=False):
        #  Check for file with token and time
        try:
            if force:
                raise NoValidToken
            with open('sp_token', 'r') as file:
                data_file = json.load(file)
                sp_access_token = data_file['access_token']
                sp_expires = data_file['expires']
                if sp_expires - time.time() < 0:  # If token expired - go to generating of a new token
                    raise NoValidToken
        # If token is out-of-date or no file found
        except (NoValidToken, FileNotFoundError):
            if force:
                logging.info("[TOKEN] Generating new token forced")
            else:
                logging.info("[TOKEN] Valid token not found. Generating new token.")
            data = st.start_session(sp_dc, sp_key)  # Get new token from Cookies
            sp_access_token = data[0]
            sp_expires = data[1]
            with open('sp_token', 'w') as file:  # Write new token and expiration time in file
                json.dump(
                    {
                        "access_token": sp_access_token,
                        "expires": sp_expires
                    }, file
                )
        logging.info(f"[TOKEN] New Spotify token valid until: {time.ctime(sp_expires)}")
        return sp_access_token, sp_expires

    def progressbar(time_s, interval=40):
        period = time_s / interval
        for i in range(interval):
            if i == 0:
                sys.stdout.write('\r')
                text = '[' + '-' * interval + ']' + ' ' + '0.0%'
                sys.stdout.write(text)
                sys.stdout.flush()
            time.sleep(period)
            sys.stdout.write('\r')
            text = '[' + '#' * (i + 1) + '-' * ((interval - 1) - i) + ']' + ' ' + str(100 / interval * (i + 1)) + "%"
            sys.stdout.write(text)
            sys.stdout.flush()
        print()

    def current_track(sp_client):
        sp_play = sp_client.current_playback()
        print()
        print("is playing: ", sp_play['is_playing'])
        if "playlist" in sp_play['context']['uri']:
            print("Playlist: ", sp_client.playlist(sp_play['context']['uri'], fields='name')['name'])
        print("Artists: ", end='')
        for i in range(len(sp_play['item']['artists'])):
            print(sp_play['item']['artists'][i]['name'], end='')
            if i == len(sp_play['item']['artists']) - 1:
                print()
            else:
                print(',', end=' ')
        print("Title: ", sp_play['item']['name'])
        print("progress: ", time.strftime('%H:%M:%S', time.gmtime(sp_play['progress_ms'] // 1000)))
        print("duration: ", time.strftime('%H:%M:%S', time.gmtime(sp_play['item']['duration_ms'] // 1000)))
        print("time_left: ", time.strftime('%H:%M:%S', time.gmtime(
            (int(sp_play['item']['duration_ms']) - int(sp_play['progress_ms'])) // 1000)))
        print("repeat state: ", sp_play['repeat_state'])
        print("shuffle state: ", sp_play['shuffle_state'])
        print()

    chromecasts, browser = pychromecast.get_listed_chromecasts(friendly_names=[CAST_NAME])
    cast = None
    for _cast in chromecasts:
        if _cast.name == CAST_NAME:
            cast = _cast
            break

    if not cast:
        logging.info(f'No chromecast with name "{CAST_NAME}" discovered')
        return

    # Wait for connection to the chromecast
    cast.wait()
    cast.set_volume(1)  # Set volume to 100%
    cast.quit_app()  # Quit current app on chromecast
    await asyncio.sleep(1)  # Wait for app to quit

    spotify_device_id = None

    # Get token from Cookies
    access_token, expires = get_token(SP_DC, SP_KEY)

    # Create a spotify client
    client = spotipy.Spotify(auth=access_token)

    # Launch the spotify app on the cast we want to cast to
    sp = SpotifyController(access_token, expires)
    cast.register_handler(sp)
    sp.launch_app()

    if not sp.is_launched and not sp.credential_error:
        logging.info("[SPOTI] Failed to launch spotify controller due to timeout")
        cast.disconnect()
        return
    if not sp.is_launched and sp.credential_error:
        logging.info("[SPOTI] Failed to launch spotify controller due to credential error")
        cast.disconnect()
        return

    # Query spotify for active devices
    devices_available = client.devices()

    # Match active spotify devices with the spotify controller's device id
    for device in devices_available["devices"]:
        if device["id"] == sp.device:
            spotify_device_id = device["id"]
            break

    if not spotify_device_id:
        logging.info(f'[SPOTI] No device with id "{sp.device}" known by Spotify')
        logging.info(f'[SPOTI] Known devices: {devices_available["devices"]}')
        cast.disconnect()
        return

    # Start playback
    client.start_playback(device_id=spotify_device_id, context_uri=URI)
    await asyncio.sleep(1)
    client.repeat('context')  # Repeat whole playlist

    # Shut down discovery
    pychromecast.discovery.stop_discovery(browser)

    # Turning on denon avr
    await asyncio.sleep(1)
    await denon_send('sat')
    await asyncio.sleep(3)
    if not await is_denon_on():
        logging.info("[SPOTI] Denon is still off. Resending...")
        await denon_send('sat')
        await asyncio.sleep(3)
        if not await is_denon_on():
            logging.info("[SPOTI] Denon is still off. Aborting")
            cast.quit_app()
            cast.disconnect()
            return

    while True:
        token_refresh_interval = expires - time.time()  # token expires
        if token_refresh_interval < 0:
            token_refresh_interval = 0
        logging.info(f"[TOKEN] Waiting until {time.ctime(time.time() + token_refresh_interval)} to refresh token")
        # progressbar(token_refresh_interval)
        await asyncio.sleep(token_refresh_interval)
        # Checking Denon AVR status
        if not await is_denon_on():
            logging.info("[SPOTI] Denon is off. Refreshing Spotify token aborted")
            if cast.status.app_id == 'CC32E753':
                cast.quit_app()
                cast.disconnect()
                return
            else:
                cast.disconnect()
                return
        # Checking chromecast status
        if cast.status is not None:
            logging.info(f"[SPOTI] Active app ID on Chromecast: {cast.status.app_id}")
            if cast.status.app_id is None:
                logging.info("[SPOTI] No app connected to Chromecast. Exiting")
                cast.disconnect()
                return
            elif cast.status.app_id != 'CC32E753':
                logging.info("[SPOTI] Another app connected to Chromecast. Exiting")
                cast.disconnect()
                return
        else:
            logging.info("[SPOTI] No connection to Chromecast. Exiting")
            return
        # Getting new token
        logging.info("[TOKEN] Generating new Spotify token")
        access_token, expires = get_token(SP_DC, SP_KEY, force=True)
        # logging.info(f"[TOKEN] New Spotify token valid until: {time.ctime(expires)}")
        # Recreating Spotify client with a new token
        client = spotipy.Spotify(auth=access_token)
        # Getting current playback status
        play = client.current_playback()
        # Checking player status
        if play:
            if play['device']['name'] != CAST_NAME:
                logging.info(f"[SPOTI] Spotify app is not connected to Chromecast {CAST_NAME}. Exiting")
                cast.disconnect()
                return
        else:
            logging.info("[SPOTI] No player found. Exiting")
            cast.disconnect()
            return
        # Checking current playback status
        time_left = (int(play['item']['duration_ms']) - int(play['progress_ms'])) / 1000
        if time_left and play['is_playing'] is True:  # Track is in the middle of playing and is not paused
            logging.info(f"[SPOTI] Waiting until current track ends: {time_left} sec")
            await asyncio.sleep(time_left + 0.5)  # Sleep until track ends

        # Getting current player status
        play = client.current_playback()

        # Quitting current app on Chromecast
        logging.info("[SPOTI] Quitting current app on Chromecast")
        cast.quit_app()
        await asyncio.sleep(1)  # Waiting until app stops
        logging.info(f"[SPOTI] App status on Chromecast: {cast.status.app_id}")

        # Launch the spotify app on the cast we want to cast to
        logging.info("[SPOTI] Starting Spotify app on Chromecast")
        sp = SpotifyController(access_token, expires)
        cast.register_handler(sp)
        sp.launch_app()
        cast.wait()
        logging.info(f"[SPOTI] Current app on chromecast: {cast.status.app_id}")

        if not sp.is_launched and not sp.credential_error:
            logging.info("[SPOTI] Failed to launch spotify controller due to timeout")
            cast.disconnect()
            return
        if not sp.is_launched and sp.credential_error:
            logging.info("[SPOTI] Failed to launch spotify controller due to credential error")
            cast.disconnect()
            return

        # Query spotify for active devices
        devices_available = client.devices()

        # Match active spotify devices with the spotify controller's device id
        for device in devices_available["devices"]:
            if device["id"] == sp.device:
                spotify_device_id = device["id"]
                break

        if not spotify_device_id:
            logging.info(f'[SPOTI] No device with id "{sp.device}" known by Spotify')
            logging.info(f'[SPOTI] Known devices: {devices_available["devices"]}')
            cast.disconnect()
            return

        # Transfer of current playback to app on Chromecast
        if not play['is_playing']:  # If track is paused
            client.transfer_playback(device_id=spotify_device_id, force_play=False)  # transfer as paused
        else:
            client.transfer_playback(device_id=spotify_device_id)  # transfer and force playback
        # current_track(client)


def play_sp_task_seeker():
    for task in asyncio.all_tasks():
        if "play_sp" in str(task):
            task.cancel()
            logging.info("[SPOTI] Previous play_sp() task detected - cancelling ...")
            break


class WebOsClientMod(WebOsClient):
    """This child class adds new commands to WebOsClient and new coroutines for asyncio task use purpose"""

    def set_audio_output(self, output):
        """New method. Set Audio Output in WebOS TV: 'external_optical', 'tv_speaker' """
        self.request(EP_SET_AUDIO_OUTPUT, {
            'output': output
        })

    def get_audio_output(self):
        """New method. Get the current audio output"""
        self.request(EP_GET_AUDIO_OUTPUT)
        return {} if self.last_response is None else self.last_response.get('payload')

    def get_power_status(self):
        """New method. Get the current power status: Active, Active Standby, Screen Saver"""
        self.request(EP_GET_TV_POWER)
        return {} if self.last_response is None else self.last_response.get('payload')

    async def set_audio_output_as(self, output):
        """New coroutine. Set Audio Output in WebOS TV: 'external_optical', 'tv_speaker' """
        await self.request_as(EP_SET_AUDIO_OUTPUT, {
            'output': output
        })

    async def get_audio_output_as(self):
        """New coroutine. Get the current audio output"""
        await self.request_as(EP_GET_AUDIO_OUTPUT)
        return {} if self.last_response is None else self.last_response.get('payload')

    async def get_power_status_as(self):
        """New method. Get the current power status: Active, Active Standby, Screen Saver"""
        await self.request_as(EP_GET_TV_POWER)
        return {} if self.last_response is None else self.last_response.get('payload')

    async def power_off_as(self):
        """Play media."""
        await self.request_as(EP_POWER_OFF)

    async def command_as(self, request_type, uri, payload):
        """New coroutine base on def command(). Build and send a command."""
        self.command_count += 1

        if payload is None:
            payload = {}

        message = {
            'id': "{}_{}".format(type, self.command_count),
            'type': request_type,
            'uri': "ssap://{}".format(uri),
            'payload': payload,
        }
        self.last_response = None

        try:
            # await asyncio.wait_for(self._command(message), self.timeout_connect)
            await asyncio.wait_for(self._command(message), 1)
        except asyncio.TimeoutError:
            raise

    async def request_as(self, uri, payload=None):
        """New coroutine base on def request(). Send a request."""
        await self.command_as('request', uri, payload)


async def task_dispatcher(message):  # For commands received through sockets
    if 'denon' in message:
        await denon_send(message)
    elif 'webos' in message:
        await webos_control_as(message)
    elif 'castsp' in message:
        play_sp_task_seeker()
        asyncio.create_task(play_sp(force=True))
    elif 'castyt' in message:
        play_sp_task_seeker()
        await play_yt(wakeup=False, force=True)


async def webos_control_as(cmd: str) -> None:
    if cmd.strip() == 'webosoff':
        logging.info("[WEBOS] Sending WebOS power off message")
        await webos_cmd_handler(webos_client.power_off_as)
    else:
        logging.info(f"[WEBOS] Unknown message received: {cmd.strip()}")


async def webos_cmd_handler(method, cmd=None, silent=False):
    try:
        if cmd is None:
            result = await method()
            return result if result else None
        else:
            result = await method(cmd)
            return result if result else None

    except asyncio.TimeoutError:
        if not silent:
            logging.info("[WEBOS] Error connecting to TV")


async def webos_snd_out_control_as(output) -> None:
    """This coroutine uses modified version of pylgtv module to control audio output of LG WebOS TV"""
    # Available outputs list to check:
    # "tv_speaker" - confirmed
    # "external_speaker"
    # "external_optical" - confirmed
    # "external_arc"
    # "lineout"
    # "headphone"
    # "tv_external_speaker"
    # "tv_speaker_headphone"
    # "bt_soundbar"

    audio_output = await webos_cmd_handler(webos_client.get_audio_output_as)
    if audio_output:
        logging.info(f"[WEBOS] Current WebOS Audio Output: {audio_output.get('soundOutput')}")
        if audio_output.get('soundOutput').strip() != output:
            logging.info("[WEBOS] Switching to Optical Out")
            await webos_cmd_handler(webos_client.set_audio_output_as, output)


async def is_denon_on() -> bool:
    """This coroutine check status of AVR device by running external program ir-ctl"""
    logging.info("[DENON] Checking denon status")
    p = await asyncio.create_subprocess_exec(*cmd_denon, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    await p.wait()  # Wait for p to finish
    status = await p.stdout.read()
    err = await p.stderr.read()
    if 'DON-DENON-AVAMP' in status.decode().strip():
        logging.info('[DENON] Denon is on')
        return True
    else:
        logging.info(f'[DENON] Denon is off - {err.decode().strip()}')
        return False


async def webos_watch():
    """This coroutine checks every 1min for webos tv power state. Use as task """
    while True:
        await is_webos_on()
        await asyncio.sleep(60)


async def is_webos_on(on_time=[]):
    """This coroutine check WebOS current power state. """
    # Noticed 3 possible states so far: 'Active', 'Active Standby', 'Screen Saver'.
    # State 'Active Standby' is when TV is turned off, but there are still some background task running.
    # on_time list stores time when webos tv was spotted in state power on
    # try:

    check = await webos_cmd_handler(webos_client.get_power_status_as, cmd=None,
                                    silent=True)  # return dict with 'state' key
    if check:
        if check.get('state') == 'Active' or check.get('state') == 'Screen Saver':  # if webos tv is on
            if not on_time:  # tv wasn't spotted in state power on yet
                on_time.append(time.time())  # set timestamp
                logging.info("[WEBOS] WebOS TV is on")
            return on_time[0]  # return timestamp as float
        else:  # if webos tv is in active standby state
            if on_time:  # if the is some old timestamp
                on_time[:] = []  # clear timestamp
                logging.info("[WEBOS] WebOS TV is off")
            return False
    else:
        if on_time:  # if the is some old timestamp
            on_time[:] = []  # clear timestamp
            logging.info("[WEBOS] WebOS TV is off")
        return False
    # except asyncio.TimeoutError:  # this accrues when tv is off
    #     if on_time:  # if the is some old timestamp
    #         on_time[:] = []  # clear timestamp
    #         logging.info("[WEBOS] WebOS TV is off")
    #     return False


async def is_denon_off_required(func_timeout=[]):
    """Coroutine contains logic that based on 2 conditions dispatch info: denon should be off or input change to tv"""
    # This was created because Denon is not only used as TV sound output. Other output are used e.g. SAT
    # Problem: there is only one custom button on webos remote (STB PWR) to power on, power off other device
    # and the only info I can get from denon is power state (no current input set)
    # Example: TV is off, Denon is on with input SAT. I want to start watching TV. Turn TV on and press STB PWR on
    # TV remote. Without additional logic Denon will go off (if Denon is power on: turn off)
    # Solution: Based on users habits some conditions were created
    # Condition 0: Denon is on (if you are here it means condition was met)
    # Condition 1: TV must by ON
    # Condition 2: TV was turn on recently - default within 180s
    # If cond 1 and 2 are met denon do not go off only input is change to tv
    #
    # func_timeout - stores timestamp while running coroutine. It gives period (default 10s) in witch you can bypass
    # logic (additional STD PWR press) if it doesn't meet expectations
    logic_free_delay = 10  # Logic free period
    webos_up_cond = 180  # period in which tv is considered to be turned on recently
    if func_timeout:
        if time.time() - func_timeout[0] > logic_free_delay:  # Check if logic free period has expired
            func_timeout[:] = []  # if condition is met timestamp is deleted
    if not func_timeout:  # when there is no logic free period
        logging.info(f"[LOGIC] Checking Denon power no/off conditions")
        func_timeout.append(time.time())  # set new timestamp for logic free period
        result = await is_webos_on()  # check webos tv power state
        if result:  # timestamp - webos tv was spotted in state power on
            logging.info("[LOGIC] WebOS TV is on: PASS")
            if time.time() - result < webos_up_cond:  # checks if tv uptime is smaller then value set in logic
                logging.info(f"[LOGIC] WebOS TV was on for {int(time.time() - result)}s (<{str(webos_up_cond)}s): PASS")
                # func_timeout.append(time.time())
                return False
            else:  # tv uptime is greater then value set in logic (tv is running for longer time)
                logging.info(f"[LOGIC] WebOS TV was on for {int(time.time() - result)}s (<{str(webos_up_cond)}s): FAIL")
                return True
        else:  # result is False - tv is off
            logging.info(f"[LOGIC] WebOS TV is on: FAIL")
            return True
    else:  # in logic free period
        if time.time() - func_timeout[0] < logic_free_delay:  # Should work without this if statement
            logging.info("[LOGIC] Force Denon power on/off according to current power state")
            func_timeout[:] = []
            return True


def is_button_pressed(binary: str) -> bool:
    """This func check if the received signal is the right one"""
    binary = hex(int(binary, 2))
    # print(binary)
    if str(binary) == '0x13c24':
        logging.info(f"[IRCTL] Magic Remote STB PWR signal detected: {binary}")
        return True
    else:
        return False


async def denon_send(cmd: str) -> None:
    """This coroutine delegate ir commands """
    if cmd == 'tv' or cmd == 'denontv':
        logging.info("[IRCTL] Sending power on with TV input")
        await ir_blaster(DENTV)

    elif cmd == 'off' or cmd == 'denonoff':
        logging.info("[IRCTL] Sending power off")
        await ir_blaster(DENOFF)

    elif cmd == 'sat' or cmd == 'denonsat':
        logging.info("[IRCTL] Sending power on with SAT input")
        await ir_blaster(DENSAT)

    elif cmd == 'volup' or cmd == 'denonvolup':
        logging.info("[IRCTL] Sending volume up")
        await ir_blaster(DENVOLUP, repeat=3)

    elif cmd == 'voldn' or cmd == 'denonvoldn':
        logging.info("[IRCTL] Sending volume down")
        await ir_blaster(DENVOLDN, repeat=3)


async def ir_blaster(scancode: str, repeat=1) -> None:
    """Send IR signals with with external program: ir-ctl"""
    cmd = shlex.split(
        IRCTL_SEND + f" -s{scancode} --gap={GAP} -s{scancode} --gap={GAP} -s{scancode} --gap={GAP}" * repeat)
    if args.sync:  # IR Blaser sync mode
        res = subprocess.run(cmd, stderr=subprocess.PIPE, text=True)
        if res.stderr:
            logging.error(res.stderr)
    else:
        res = await asyncio.create_subprocess_exec(*cmd)
        _, stderr = await res.communicate()
        if stderr:
            logging.error(stderr)
        await res.wait()  # Wait res to finish


async def count_and_run(count: int) -> None:
    """This coroutine run tasks according to the value of count - number of key pressed """
    logging.info(f'[COUNT] Total {count} button press detected')

    if count == 1:
        if not await is_denon_on():
            await denon_send('tv')
            asyncio.create_task(webos_snd_out_control_as('external_optical'))
        else:
            if await is_denon_off_required():
                await denon_send('off')
            else:
                asyncio.create_task(webos_snd_out_control_as('external_optical'))
                await denon_send('tv')

    elif count > 1:
        if await is_webos_on():
            await denon_send('tv')
            asyncio.create_task(webos_snd_out_control_as('external_optical'))
        else:
            await denon_send('sat')


# ''' Functions used in sync mode. For testing purpose. Use flag '-s'. Lines below.'''


# def task_dispatcher_sync(message):
#    if 'denon' in message:
#        denon_send_sync(message)
#    elif 'webos' in message:
#        webos_control(message)
#

# def webos_control(message):
#    pass
#
#
# def webos_snd_control(output):
#    """This func uses pylgtv module with modified WebOsClientMod class to control audio output of LG WebOS TV"""
#    # Available outputs list to check:
#    # "tv_speaker" - confirmed
#    # "external_speaker"
#    # "external_optical" - confirmed
#    # "external_arc"
#    # "lineout"
#    # "headphone"
#    # "tv_external_speaker"
#    # "tv_speaker_headphone"
#    # "bt_soundbar"
#    # logging.basicConfig(stream=sys.stdout, level=logging.INFO)
#    try:
#        # webos_client = WebOsClientMod(WEBOS)
#        audio_output = webos_client.get_audio_output()  # Check current audio output
#        logging.info(f"[WEBOS] Current WebOS Audio Output: {audio_output.get('soundOutput')}")
#        if audio_output.get('soundOutput').strip() != 'external_optical':
#            logging.info("[WEBOS] Switching to Optical Out")
#            webos_client.set_audio_output(output)
#        # webos_client.launch_app('netflix')
#        # for app in webos_client.get_apps():
#        # print(app)
#    except Exception as e:
#        logging.info("[WEBOS] Error connecting to TV ", e)
#
#
# def is_denon_on_sync() -> bool:
#    """This func check status of AVR device by running external program. It can by used for sync mode"""
#    logging.info("[DENON] Checking denon status")
#    status = subprocess.run(cmd_denon, capture_output=True, text=True)
#    if 'DON-DENON-AVAMP' in status.stdout:
#        logging.info("[DENON] Denon is on")
#        return True
#    else:
#        logging.info(f"[DENON] Denon is off - {status.stderr.strip()}")
#        return False
#
#
# def count_and_run_sync(count: int) -> None:
#    """This func run tasks according to the value of count - number of key pressed. It can by used in sync mode. """
#    logging.info(f"[COUNT] Total {count} button press detected")
#
#    if count == 1:
#        if not is_denon_on_sync():
#            denon_send_sync('tv')
#            try:
#                t = Thread(target=webos_snd_control, args=('external_optical',))  # Run in thread because pylgtv module
#                t.start()  # has its own internal asyncio loop
#            except RuntimeError:  # Check if the func in Thread is done
#                logging.debug('[COUNT] Tread is still running')
#
#        else:
#            denon_send_sync('off')
#
#    elif count > 1:
#        denon_send_sync('tv')
#
#
# def denon_send_sync(cmd: str) -> None:
#    """This func send ir signal with external program: ir-ctl. It can by uses in sync mode """
#    if cmd == 'tv' or cmd == 'denontv':
#        logging.info("[IRCTL] Sending power on with TV input")
#        ir_blaster_sync(DENTV)
#    elif cmd == 'off' or cmd == 'denonoff':
#        logging.info("[IRCTL] Sending power off")
#        ir_blaster_sync(DENOFF)
#    elif cmd == 'sat' or cmd == 'denonsat':
#        logging.info("[IRCTL] Sending power on with SAT input")
#        ir_blaster_sync(DENSAT)
#    elif cmd == 'volup' or cmd == 'denonvolup':
#        logging.info("[IRCTL] Sending volume up")
#        ir_blaster_sync(DENVOLUP, repeat=3)
#    elif cmd == 'voldn' or cmd == 'denonvoldn':
#        logging.info("[IRCTL] Sending volume down")
#        ir_blaster_sync(DENVOLDN, repeat=3)
#
#
# def ir_blaster_sync(scancode: str, repeat=1) -> None:
#    cmd = shlex.split(
#        IRCTL_SEND + f" -s{scancode} --gap={GAP} -s{scancode} --gap={GAP} -s{scancode} --gap={GAP}" * repeat)
#    res = subprocess.run(cmd, stderr=subprocess.PIPE, text=True)
#    if res.stderr:
#        logging.error(res.stderr)


# ''' Functions used in sync mode. For testing purpose. Use flag '-s'. Lines above.'''


async def reading() -> None:
    logging.info("[MAIN]  Ready to listen")
    if args.sync:
        logging.info("[FLAGS] IR Blaster in sync mode")
    if args.listen:
        asyncio.create_task(sock_server())  # Starts TCP/UDP Socket servers as task
    asyncio.create_task(webos_watch())  # Starts task which check every 1m webos power state
    # asyncio.to_thread(webos_watch())
    if args.monitor:
        asyncio.create_task(device_monitor())  # Start MAC monitoring
        asyncio.create_task(return_home(RH_MAC, MAC_LIST))
    if args.scheduler:
        asyncio.create_task(timer(START_TIME, play_yt))  # Start timer - runs YT on Denon at given time
    # result = await is_webos_on()
    # print(result)
    p = await asyncio.subprocess.create_subprocess_exec(*cmd_ir_read, stdout=asyncio.subprocess.PIPE)
    binary = ''
    count = 0  # Add 1 after receiving right ir signal
    noise = 0  # Meaningful noise indicator - add 1 after receiving unknown ir signal or noise, but only when count > 0
    button_press_time = 0  # For STB PWR button press timestamp
    while True:
        data = await p.stdout.readline()
        if data.decode().split()[0] != 'timeout':  # Reads ir signal and convert it to ones and zeros until timeout
            if 700 < int(data.decode().split()[1]) < 1150:
                binary += '0'
            elif 1300 < int(data.decode().split()[1]) < 2100:
                binary += '1'
            else:
                continue
        else:
            if noise > 4 and count > 0:  # Prevent endless loop caused by too much noise by running coroutine run()
                logging.info('[MAIN]  Noise detected - running tasks')
                # if args.sync:  # if program started with --sync flag
                #    count_and_run_sync(count)
                # else:
                await count_and_run(count)
                count = 0
                noise = 0
            elif not binary and count == 0:  # Ignore meaningless noise
                continue
            elif not binary and count > 0:  # Handle noise after right ir signal situation
                noise += 1
                binary = ''
                try:
                    await asyncio.wait_for(p.stdout.readline(), 0.5)  # Wait some time for additional signal
                except asyncio.TimeoutError:  # After timeout run() func is awaited with current count value
                    # if args.sync:  # if program started with --sync flag
                    #    count_and_run_sync(count)
                    # else:
                    await count_and_run(count)
                    count = 0
                    noise = 0
            elif is_button_pressed(binary):  # Handle right ir signal received situation
                binary = ''
                if time.time() - button_press_time < 1:  # For unwanted echo ir signals sometimes generated by remote
                    logging.info(f"[IRCTL] Magic Remote STB PWR signal ignored: delay 1 sec")
                    continue  # if the unwanted signal is generated within 1 sec it will be ignored
                count += 1  # Add 1 after detecting the right ir signal
                try:
                    await asyncio.wait_for(p.stdout.readline(), 0.5)  # Wait some time for additional signal
                except asyncio.TimeoutError:  # After timeout run() coroutine is awaited with current count value
                    button_press_time = time.time()
                    # if args.sync:  # if program started with --sync flag
                    #    count_and_run_sync(count)
                    # else:
                    await count_and_run(count)
                    count = 0
            else:  # Handle unknown ir signals
                logging.debug(f"[MAIN]  Unknown signal detected: {hex(int(binary, 2))}")
                binary = ''
                if count > 0:  # Handle receiving unknown ir signals after receiving the right ir signal situation
                    noise += 1
                    try:
                        await asyncio.wait_for(p.stdout.readline(), 0.5)  # Wait some time for additional signal
                    except asyncio.TimeoutError:  # After timeout run() coroutine is awaited with current count value
                        # if args.sync:
                        #    count_and_run_sync(count)
                        # else:
                        await count_and_run(count)
                        count = 0
                        noise = 0


if __name__ == '__main__':
    get_globals()

    # logging.basicConfig(format='%(asctime)s %(levelname)s: %(message)s', datefmt='%b %d %H:%M:%S', level=logging.INFO,
    #                    handlers=[logging.FileHandler("my_log.log"), logging.StreamHandler()])
    logging.basicConfig(format='%(asctime)s %(levelname)s: %(message)s', datefmt='%b %d %H:%M:%S', level=logging.INFO,
                        handlers=[logging.FileHandler("my_log.log")])

    parser = argparse.ArgumentParser(prog='./ir_tasker', description="Raspberry Pi IR Blaster and WebOS controller"
                                                                     "triggered with received IR signal and TCP/UDP "
                                                                     "Socket commands. Python 3.7+ required")
    parser.add_argument('run', help="Run this program.")
    parser.add_argument('-s', '--sync', help="IR Blaster in sync mode", action="store_true")
    parser.add_argument('-l', '--listen', help="runs TCP/UDP socket server", action="store_true")
    parser.add_argument('-m', '--monitor', help="runs MAC monitor", action="store_true")
    parser.add_argument('-t', '--scheduler', help="runs task scheduler", action="store_true")
    args = parser.parse_args()
    webos_client = WebOsClientMod(WEBOS)
    if args.monitor:
        mac_monitor = MacMonitor()
    try:
        asyncio.run(reading())
    except KeyboardInterrupt:
        print("\nHave a Nice Day!")
