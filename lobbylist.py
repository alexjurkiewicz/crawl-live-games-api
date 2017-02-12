#!/usr/bin/env python3
"""Serve a simple API showing currently active games."""

import asyncio
import logging
import urllib.parse
import collections
import json

from webtiles import WebTilesConnection, WebTilesGameConnection
import aiohttp
import aiohttp.server
import websockets

Server = collections.namedtuple("Server",
                                ('name', 'ws_url', 'ws_proto', 'base_url'))

SERVERS = [
    Server("cao", "ws://crawl.akrasiac.org:8080/socket", 1,
           'http://crawl.akrasiac.org:8080/'),
    Server("cbro", "ws://crawl.berotato.org:8080/socket", 1,
           'http://crawl.berotato.org:8080/'),
    Server("cjr", "wss://crawl.jorgrun.rocks:8081/socket", 1,
           'https://crawl.jorgrun.rocks:8081/'),
    Server("cpo", "wss://crawl.project357.org/socket", 2,
           'https://crawl.project357.org/'),
    Server("cue", "ws://www.underhound.eu:8080/socket", 1,
           'http://underhound.eu:8080/'),
    Server("cwz", "ws://webzook.net:8080/socket", 1,
           'http://webzook.net:8080/'),
    Server("cxc", "ws://crawl.xtahua.com:8080/socket", 1,
           'http://crawl.xtahua.com:8080/'),
    Server("lld", "ws://lazy-life.ddo.jp:8080/socket", 1,
           'http://lazy-life.ddo.jp:8080/'),
]
DATABASE = []
BRANCH_NAMES = {
    'D': 'Dungeon',
    'Orc': 'Orcish Mines',
    'Elf': 'Elven Halls',
    'Lair': 'Lair of the Beasts',
    'Depths': 'Depths',
    'Swamp': 'Swamp',
    'Shoals': 'Shoals',
    'Spider': 'Spider Nest',
    'Snake': 'Snake Pit',
    'Slime': 'Slime Pits',
    'Vaults': 'Vaults',
    'Crypt': 'Crypt',
    'Tomb': 'Tomb of the Ancients',
    'Dis': 'Iron City of Dis',
    'Geh': 'Gehenna',
    'Coc': 'Cocytus',
    'Tar': 'Tartarus',
    'Zot': 'Realm of Zot',
    'Abyss': 'Abyss',
    'Zig': 'Ziggurat',
    'Lab': 'Labyrinth',
    'Bazaar': 'Bazaar',
    'WizLab': 'Wizard\'s Laboratory',
    'Sewer': 'Sewer',
    'Bailey': 'Bailey',
    'Ossuary': 'Ossuary',
    'IceCv': 'Ice Cave',
    'Volcano': 'Volcano',
    'Hell': 'Vestibule of Hell',
    'Temple': 'Ecumenical Temple',
    'Pan': 'Pandemonium',
    'Trove': 'Treasure Trove'
}
SPECIES_NAMES = {
    'Ba': 'Barachian',
    'Mf': 'Merfolk',
    'Ke': 'Kenku',
    'MD': 'Mountain Dwarf',
    'Og': 'Ogre',
    'Na': 'Naga',
    'DD': 'Deep Dwarf',
    'DE': 'Deep Elf',
    'Tr': 'Troll',
    'Mu': 'Mummy',
    'GE': 'Grey Elf',
    'VS': 'Vine Stalker',
    'HO': 'Hill Orc',
    'Sp': 'Spriggan',
    'Te': 'Tengu',
    'HD': 'Hill Dwarf',
    'HE': 'High Elf',
    'El': 'Elf',
    'OM': 'Ogre-Mage',
    'Dj': 'Djinni',
    'Gr': 'Gargoyle',
    'Ko': 'Kobold',
    'Dg': 'Demigod',
    'Gh': 'Ghoul',
    'Fo': 'Formicid',
    'Ce': 'Centaur',
    'Hu': 'Human',
    'Vp': 'Vampire',
    'Op': 'Octopode',
    'Mi': 'Minotaur',
    'Pl': 'Plutonian',
    'LO': 'Lava Orc',
    'Gn': 'Gnome',
    'Ha': 'Halfling',
    'Dr': 'Draconian',
    'Ds': 'Demonspawn',
    'SE': 'Sludge Elf',
    'Fe': 'Felid'
}
BACKGROUND_NAMES = {
    'Pr': 'Priest',
    'CK': 'Chaos Knight',
    'AE': 'Air Elementalist',
    'DK': 'Death Knight',
    'Cj': 'Conjurer',
    'EE': 'Earth Elementalist',
    'Mo': 'Monk',
    'AM': 'Arcane Marksman',
    'Ne': 'Necromancer',
    'Su': 'Summoner',
    'VM': 'Venom Mage',
    'Sk': 'Skald',
    'Re': 'Reaver',
    'Pa': 'Paladin',
    'FE': 'Fire Elementalist',
    'Th': 'Thief',
    'Cr': 'Crusader',
    'St': 'Stalker',
    'IE': 'Ice Elementalist',
    'Be': 'Berserker',
    'En': 'Enchanter',
    'Wn': 'Wanderer',
    'Jr': 'Jester',
    'Hu': 'Hunter',
    'AK': 'Abyssal Knight',
    'As': 'Assassin',
    'Ar': 'Artificer',
    'Wr': 'Warper',
    'Fi': 'Fighter',
    'Gl': 'Gladiator',
    'Tm': 'Transmuter',
    'Wz': 'Wizard',
    'He': 'Healer'
}

_log = logging.getLogger()
_log.setLevel(logging.INFO)
_log.addHandler(logging.StreamHandler())


def parse_location(location):
    """Parse raw location string and return (branch, branchlevel, humanreadable).

    Example strings: 'D:8', 'Lair:1', 'Temple', 'Pan', 'Tar:4'

    The human readable string is quite complex. There are six forms:
    * On level 1 of the Dungeon/Abyss/...
    * On level 1 of Tartarus/Cocytus/Gehenna
    * On level 1 of a Ziggurat
    * In a Labyrinth/Wizard Lab/...
    * In an Ice Cave/Ossuary
    * In the Vestibule of Hell/Ecumenical Temple
    * In Pandemonium
    """
    if ':' in location:
        br = location.split(':', 1)[0]
        branchlevel = location.split(':')[1]
    else:
        br = location
        branchlevel = '0'
    branch = BRANCH_NAMES.get(br, br)

    if br in ('D', 'Orc', 'Elf', 'Lair', 'Depths', 'Swamp', 'Shoals', 'Slime',
              'Snake', 'Spider', 'Vaults', 'Crypt', 'Tomb', 'Dis', 'Zot',
              'Abyss'):
        if branchlevel != '0':
            humanreadable = "on level {} of the {}".format(branchlevel, branch)
        else:
            # zot defense or sprint
            humanreadable = "in the {}".format(branch)
    elif br in ('Tar', 'Geh', 'Coc'):
        humanreadable = "on level {} of {}".format(branchlevel, branch)
    elif br in ('Zig', ):
        humanreadable = "on level {} of a {}".format(branchlevel, branch)
    elif br in ('Lab', 'Bazaar', 'WizLab', 'Sewer', 'Bailey', 'Volcano',
                'Trove', 'Salt'):
        humanreadable = "in a {}".format(branch)
    elif br in ('Ossuary', 'IceCv'):
        humanreadable = "in an {}".format(branch)
    elif br in ('Hell', 'Temple'):
        humanreadable = "in the {}".format(branch)
    elif br in ('Pan', ):
        humanreadable = "in {}".format(branch)
    else:
        humanreadable = 'at {}'.format(location)

    return (branch, branchlevel, humanreadable)


class LobbyList(WebTilesConnection):
    def __init__(self, server_abbr, websocket_url, protocol_version, base_url):
        super().__init__()
        self.server_abbr = server_abbr
        self.websocket_url = websocket_url
        self.protocol_version = protocol_version
        self.base_url = base_url

    def watchlink(self, username):
        if self.protocol_version == 1:
            return self.base_url + '#watch-' + username
        else:
            return self.base_url + 'watch/' + username

    async def ensure_connected(self):
        """Connect to the WebTiles server if needed."""
        if not self.connected():
            _log.info("%s: Connecting", self.server_abbr)
            await self.connect(
                self.websocket_url, protocol_version=self.protocol_version)
            if self.protocol_version > 1:
                _log.info("%s: Requesting initial lobby", self.server_abbr)
                await self.send({"msg": "lobby"})

    async def get_lobby_entries(self):
        """Read and handle messages."""
        while True:
            await self.ensure_connected()
            messages = await self.read()

            if not messages:
                # XXX Not sure why this could happen. Websocket timeout?
                print("{}: No messages?!".format(self.server_abbr))
                break

            for message in messages:
                await self.handle_message(message)

            if self.protocol_version == 1 and not self.lobby_complete:
                continue

            return self.lobby_entries


class GameWatcher(WebTilesGameConnection):
    def __init__(self, server_abbr, websocket_url, protocol_version, username):
        super().__init__()
        self.server_abbr = server_abbr
        self.websocket_url = websocket_url
        self.protocol_version = protocol_version
        self.target_game_id = -1
        self.target_username = username

    async def ensure_connected(self):
        """Connect to the WebTiles server if needed."""
        if not self.connected():
            _log.info("%s: Connecting", self.server_abbr)
            await self.connect(
                self.websocket_url, protocol_version=self.protocol_version)
            await self.send_watch_game(self.target_username,
                                       self.target_game_id)

    async def find_player_info(self):
        """Read and handle messages."""
        while True:
            await self.ensure_connected()
            messages = await self.read()

            if not messages:
                # XXX Not sure why this could happen. Websocket timeout?
                print("{}: No messages?!".format(self.server_abbr))
                break

            for message in messages:
                if message['msg'] == 'player':
                    return message
                await self.handle_message(message)


async def update_database(new_entries, server):
    global DATABASE
    # Remove existing entries for this server
    new_database = [g for g in DATABASE if g['server'] != server]
    # Add the new entries
    for entry in new_entries:
        new_database.append(entry)
    # Always sort in username order (split ties by server)
    new_database = sorted(
        new_database, key=lambda g: g['username'] + g['server'])
    DATABASE = new_database


async def update_lobby_data(lister):
    while True:
        try:
            entries = await lister.get_lobby_entries()
        except KeyboardInterrupt:
            print("Bye")
            break
        except websockets.exceptions.ConnectionClosed:
            continue
        # Add some data the lobby doesn't provide
        for entry in entries:
            entry['server'] = lister.server_abbr
            entry['watchlink'] = lister.watchlink(entry['username'])
            entry['idle'] = bool(entry['idle_time'] != 0)
            if 'place' in entry:
                entry['branch'], entry['branchlevel'], entry[
                    'place_human_readable'] = parse_location(entry['place'])
            if 'char' in entry:
                sp = entry['char'][:2]
                bg = entry['char'][2:]
                entry['species'] = SPECIES_NAMES.get(sp, sp)
                entry['background'] = BACKGROUND_NAMES.get(bg, bg)
        # Crud from webtiles lib
        if 'msg' in entries and entries['msg'] == 'lobby_entry':
            del (entries['msg'])
        await update_database(entries, lister.server_abbr)
        _log.debug("%s: Updated lobby data", lister.server_abbr)


async def game_info(server_abbr, player):
    server = [s for s in SERVERS if s.name == server_abbr]
    if not server:
        return None
    server = server[0]

    watcher = GameWatcher(server_abbr, server.ws_url, server.ws_proto, player)
    return await watcher.find_player_info()


class ApiRequestHandler(aiohttp.server.ServerHttpProtocol):
    async def handle_request(self, message, payload):
        routes = {
            '/games': self.list_games,
            '/gameinfo': self.game_info,
        }
        url = urllib.parse.urlsplit(message.path)
        args = urllib.parse.parse_qs(url.query)
        if url.path in routes.keys():
            return await routes[url.path](message, payload, url, args)
        else:
            return await self.error_page(404, message, payload, url, args)

    async def list_games(self, message, payload, url, args):
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

    async def game_info(self, message, payload, url, args):
        json_args = {
            'indent': 2,
            'sort_keys': True
        } if 'pretty' in args else {}
        if not args.get('player') or not args.get('server'):
            return await self.error_page(400, message, payload, url, args)
        player = args['player'][0]
        server = args['server'][0]
        if not [g for g in DATABASE if g['username'] == player]:
            return await self.error_page(404, message, payload, url, args)

        response = aiohttp.Response(
            self.writer, 200, http_version=message.version)
        info = await game_info(server, player)
        data = json.dumps(info, **json_args)
        response.add_header('Content-Type', 'application/json')
        response.add_header('Content-Length', str(len(data)))
        response.send_headers()
        response.write(data.encode())
        await response.write_eof()

    async def error_page(self, code, message, payload, url, args):
        response = aiohttp.Response(
            self.writer, code, http_version=message.version)
        response.send_headers()
        await response.write_eof()


def main():
    loop = asyncio.get_event_loop()
    for server in SERVERS:
        lobby_lister = LobbyList(server.name, server.ws_url, server.ws_proto,
                                 server.base_url)
        loop.create_task(update_lobby_data(lobby_lister))

    httpd = loop.create_server(lambda: ApiRequestHandler(), 'localhost',
                               '5678')
    loop.create_task(httpd)
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    loop.close()


main()
