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
import urllib.parse
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

    async def ensure_connected(self):
        """Connect to the WebTiles server if needed."""
        if not self.connected():
            _log.info("{}: Connecting".format(self.server_abbr))
            await self.connect(
                self.websocket_url, protocol_version=self.protocol_version)
            if self.protocol_version > 1:
                _log.info("{}: Requesting initial lobby".format(
                    self.server_abbr))
                await self.send({"msg": "lobby"})

    async def process(self):
        """Read and handle messages."""
        while True:
            messages = await self.read()

            if not messages:
                # XXX Not sure why this could happen. Websocket timeout?
                print("{}: No messages?!".format(self.server_abbr))
                break

            for message in messages:
                await self.handle_message(message)

            if (self.protocol_version == 1 and not self.lobby_complete):
                continue

            return self.lobby_entries


DATABASE = {}


async def update_lobby_data(lister):
    while True:
        try:
            await lister.ensure_connected()
            entries = await lister.process()
        except KeyboardInterrupt:
            print("Bye")
            break
        DATABASE[lister.server_abbr] = entries
        _log.debug("{}: Updated lobby data".format(lister.server_abbr))


class ApiRequestHandler(aiohttp.server.ServerHttpProtocol):
    async def handle_request(self, message, payload):
        url = urllib.parse.urlsplit(message.path)
        if url.path != '/':
            return await self.return_404(message, payload)

        args = urllib.parse.parse_qs(url.query)
        json_args = {
            'indent': 2,
            'sort_keys': True
        } if 'pretty' in args else {}
        response = aiohttp.Response(
            self.writer, 200, http_version=message.version)
        data = json.dumps(DATABASE, **json_args)
        response.add_header('Content-Type', 'application/json')
        response.add_header('Content-Length', str(len(data)))
        response.send_headers()
        response.write(data.encode())
        await response.write_eof()

    async def return_404(self, message, payload):
        response = aiohttp.Response(
            self.writer, 404, http_version=message.version)
        response.send_headers()
        await response.write_eof()


def main():
    loop = asyncio.get_event_loop()
    for server in SERVERS:
        lobby_lister = LobbyList(server.name, server.ws_url, server.ws_proto)
        loop.create_task(update_lobby_data(lobby_lister))

    f = loop.create_server(
        lambda: ApiRequestHandler(),
        'localhost', '5678')
    loop.create_task(f)
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    loop.close()


main()
