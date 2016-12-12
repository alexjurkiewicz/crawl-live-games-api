#!/usr/bin/env python3

"""Serve a simple API showing currently active games."""

import argparse
import asyncio
import getpass
import logging
import os
import os.path
import re
import sys
from urllib.parse import urlparse
from webtiles import WebTilesConnection
import collections

Server = collections.namedtuple("Server", ('name', 'ws_url', 'ws_proto'))

SERVERS = [
    Server("cao", "ws://crawl.akrasiac.org:8080/socket", 1),
    Server("cbro", "ws://crawl.berotato.org:8080/socket", 1),
    Server("cjr", "wss://crawl.jorgrun.rocks:8081/socket", 1),
    Server("cpo", "wss://crawl.project357.org/socket", 2),
    Server("cue", "ws://www.underhound.eu:8080/socket", 1),
    Server("cwz", "ws://webzook.net:8080/socket", 1),
    Server("cxc", "ws://crawl.xtahua.com:8080/socket", 1),
    Server("lld", "ws://lazy-life.ddo.jp:8080/socket", 1),
]

_log = logging.getLogger()
_log.setLevel(logging.INFO)
_log.addHandler(logging.StreamHandler())

class LobbyList(WebTilesConnection):

    def __init__(self, server_abbr, websocket_url, protocol_version):
        super().__init__()
        self.server_abbr = server_abbr
        self.websocket_url = websocket_url
        self.protocol_version = protocol_version

    async def start(self):
        """Connect to the WebTiles server, then proceed to read and handle
        messages.

        """

        if not self.connected():
            await self.connect(self.websocket_url, protocol_version=self.protocol_version)

        if self.protocol_version > 1:
            await self.send({"msg" : "lobby"})
            full_lobby = False

        while True:
            messages = await self.read()

            if not messages:
                break

            for message in messages:
                if self.protocol_version > 1 and message['msg'] == 'lobby_html':
                    full_lobby = True
                await self.handle_message(message)

            if (self.protocol_version == 1 and self.lobby_complete) or (self.protocol_version > 1 and full_lobby):
                return self.lobby_entries


DATABASE = {}


async def update_lobby_data(lister):
    while True:
        data = await lister.start()
        print("Lobby data collected from {server}".format(server=lister.server_abbr, games=data))
        await asyncio.sleep(1)
        DATABASE[lister.server_abbr] = data


async def print_lobby_data():
    while True:
        for server, games in DATABASE.items():
            print("{}: {} games".format(server, len(games)))
        await asyncio.sleep(1)


def main():
    ioloop = asyncio.get_event_loop()
    for server in SERVERS:
        lobby_lister = LobbyList(server.name, server.ws_url, server.ws_proto)
        ioloop.create_task(update_lobby_data(lobby_lister))
    ioloop.create_task(print_lobby_data())
    ioloop.run_forever()
    ioloop.close()


main()
