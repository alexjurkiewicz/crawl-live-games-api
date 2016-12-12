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
import collections
import json

from webtiles import WebTilesConnection
import aiohttp
import aiohttp.server

import asyncio

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
            await self.connect(
                self.websocket_url, protocol_version=self.protocol_version)

        if self.protocol_version > 1:
            await self.send({"msg": "lobby"})
            full_lobby = False

        while True:
            messages = await self.read()

            if not messages:
                break

            for message in messages:
                if self.protocol_version > 1 and message[
                        'msg'] == 'lobby_html':
                    full_lobby = True
                await self.handle_message(message)

            if (self.protocol_version == 1 and self.lobby_complete) or (
                    self.protocol_version > 1 and full_lobby):
                return self.lobby_entries


DATABASE = {}


async def update_lobby_data(lister):
    while True:
        data = await lister.start()
        print("Lobby data collected from {server}".format(
            server=lister.server_abbr, games=data))
        await asyncio.sleep(5)
        DATABASE[lister.server_abbr] = data


class ApiRequestHandler(aiohttp.server.ServerHttpProtocol):
    async def handle_request(self, message, payload):
        response = aiohttp.Response(
            self.writer, 200, http_version=message.version)
        data = json.dumps(DATABASE)
        response.add_header('Content-Type', 'application/json')
        response.add_header('Content-Length', str(len(data)))
        response.send_headers()
        response.write(data.encode())
        await response.write_eof()


async def lobby_data():
    return web.json_response(DATABASE)


def main():
    loop = asyncio.get_event_loop()
    for server in SERVERS:
        lobby_lister = LobbyList(server.name, server.ws_url, server.ws_proto)
        loop.create_task(update_lobby_data(lobby_lister))

    f = loop.create_server(
        lambda: ApiRequestHandler(debug=True, keep_alive=75),
        'localhost', '5678')
    loop.create_task(f)
    loop.run_forever()
    loop.close()


main()
