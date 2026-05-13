"""
Baut das Parallelweg-Netz in einem sauberen 3-Schritte-Prozess:

1. Modifiziert plain/orig.edg.xml:
   Jede subway-Edge bekommt zusätzliche Lane 1 mit allow="pedestrian".
   Lane 0 bleibt subway (wie bisher) — Zug-Referenzen und busStops unverändert.

2. Modifiziert plain/orig.con.xml:
   Für jede Subway-Connection wird eine parallele Pedestrian-Connection
   (fromLane=1, toLane=1) angelegt.

3. Netconvert baut aus den modifizierten Plain-Files das Netz neu.
   walking-areas werden automatisch angelegt, weil Pedestrian-Connections
   jetzt in der Plain-con.xml existieren.
"""

import xml.etree.ElementTree as ET
import copy
import os
import subprocess
from collections import defaultdict

PLAIN_DIR = '/Users/moritzhorsthemke/Documents/Masterarbeit/GitHub/sumo-masterarbeit-parallelweg/network/plain'
NET_DIR = '/Users/moritzhorsthemke/Documents/Masterarbeit/GitHub/sumo-masterarbeit-parallelweg/network'
ROUTE_FILE = '/Users/moritzhorsthemke/Documents/Masterarbeit/GitHub/sumo-masterarbeit-parallelweg/routes/route_u4_long.rou.xml'
EDG_IN = f'{PLAIN_DIR}/orig.edg.xml'
CON_IN = f'{PLAIN_DIR}/orig.con.xml'
EDG_OUT = f'{PLAIN_DIR}/parallelweg.edg.xml'
CON_OUT = f'{PLAIN_DIR}/parallelweg.con.xml'
NET_OUT = f'{NET_DIR}/osm_parallelweg.net.xml'

# === Schritt 1: Edges modifizieren ===
tree = ET.parse(EDG_IN)
root = tree.getroot()

# Gleiswechsel-Edges (name="GW ...") sind kurze Crossover-Tracks fuer
# Zug-Spurwechsel. Pedestrians duerfen sie NICHT begehen — sonst nimmt der
# Router sie als Shortcut und kreuzt mitten auf der Strecke vom HIN- aufs
# RUECK-Gleis. Ohne ped-Lane bleibt der Walker auf dem HIN-Through-Track.
gw_edges = set()
for edge in root.findall('edge'):
    name = edge.get('name', '')
    if name.startswith('GW '):
        gw_edges.add(edge.get('id'))

# U4-Edge-Set: alle Edges, die in der U4-Zugroute (r_1) vorkommen.
# Die OSM-Daten enthalten parallele Tunnelroehren (B-Strecke fuer U6/U7),
# die geometrisch dicht an der U4 liegen und subway-Edges sind. Wenn wir
# ped-Lanes auf ALLE subway-Edges legen, nimmt der Pedestrian-Router die
# parallele B-Strecke als Shortcut und laeuft am Hbf-U4-Bahnsteig vorbei
# (262540238 statt 262540239#1). Fix: ped-Lanes nur auf U4-Edges.
u4_edges = set()
route_tree = ET.parse(ROUTE_FILE)
for route in route_tree.iter('route'):
    for eid in route.get('edges', '').split():
        u4_edges.add(eid)

# Sammle alle subway-Edges der U4-Route (r_1), abzueglich Gleiswechsel.
# Dieser Filter erzwingt, dass der Walker im U4-Korridor bleibt.
# Zusaetzlich werden bidi-Schienen-Reverses (`-X` einer U4-Edge X) aufgenommen,
# damit U-Turn-/Mirror-Connections in Schritt 4 nicht ins Leere zeigen.
# Der bidi-Reverse `-X` ist geometrisch derselbe Tunnel/Bahnsteig wie X, also
# unkritisch fuer den Walker (kein B-Strecke-Detour).
target_edges = set()
for edge in root.findall('edge'):
    eid = edge.get('id')
    if edge.get('type') != 'railway.subway':
        continue
    if eid in gw_edges:
        continue
    if eid in u4_edges:
        target_edges.add(eid)
    elif eid.startswith('-') and eid[1:] in u4_edges and eid[1:] not in gw_edges:
        target_edges.add(eid)

changed = 0
for edge in root.findall('edge'):
    eid = edge.get('id')
    if eid not in target_edges:
        continue
    # 1) Permissions auf Edge-Level bereinigen
    #    Keine Mischung mehr — Zug bleibt auf Lane 0, Pedestrian auf Lane 1.
    if 'allow' in edge.attrib:
        del edge.attrib['allow']
    # numLanes auf 2 setzen
    edge.set('numLanes', '2')
    # Lane-Definitionen sicherstellen
    existing_lanes = edge.findall('lane')
    if len(existing_lanes) == 0:
        lane0 = ET.SubElement(edge, 'lane')
        lane0.set('index', '0')
        lane0.set('allow', 'subway')
        lane1 = ET.SubElement(edge, 'lane')
        lane1.set('index', '1')
        lane1.set('allow', 'pedestrian')
        lane1.set('width', '2.0')
    elif len(existing_lanes) == 1:
        lane0 = existing_lanes[0]
        lane0.set('allow', 'subway')
        if 'disallow' in lane0.attrib:
            del lane0.attrib['disallow']
        lane1 = ET.SubElement(edge, 'lane')
        lane1.set('index', '1')
        lane1.set('allow', 'pedestrian')
        lane1.set('width', '2.0')
    else:
        lane0 = existing_lanes[0]
        lane0.set('allow', 'subway')
        if 'disallow' in lane0.attrib:
            del lane0.attrib['disallow']
    changed += 1

tree.write(EDG_OUT, xml_declaration=True, encoding='UTF-8')
print(f'Schritt 1: {changed} subway-Edges modifiziert (Lane 0=subway, Lane 1=pedestrian).')

tree = ET.parse(CON_IN)
root = tree.getroot()

# Sammle alle existierenden subway-to-subway Connections.
# Für jede füge eine parallele pedestrian-Connection hinzu.
# Wichtig: uncontrolled="1" setzen — sonst Segfault an rail_signal-Junctions
# (SUMO kann die Foes-Matrix nicht berechnen, wenn das Railsignal versucht,
#  Pedestrian-Lane mit zu steuern).
added = 0
skipped_uturn = 0
existing_conns = list(root.findall('connection'))
for conn in existing_conns:
    f = conn.get('from')
    t = conn.get('to')
    # Nur interessant, wenn beide Edges zu den target_edges gehören
    if f not in target_edges or t not in target_edges:
        continue
    # Auch nur, wenn fromLane=0 und toLane=0 (das ist die Subway-Connection)
    if conn.get('fromLane') != '0' or conn.get('toLane') != '0':
        continue
    # U-Turn-Connections (X <-> -X) NICHT duplizieren — das sind Zug-Wenden
    # an Buffer-Stop-Enden. Fußgänger brauchen das nicht, und es bricht
    # SUMOs Junction-Logic (Segfault).
    if (('-' + f) == t) or (f == ('-' + t)):
        skipped_uturn += 1
        continue
    # Dupliziere: Füge parallele pedestrian-Connection hinzu
    new_conn = copy.deepcopy(conn)
    new_conn.set('fromLane', '1')
    new_conn.set('toLane', '1')
    # uncontrolled=1 ist zwingend: ohne das crasht SUMO an
    # rail_signal-Junctions (Foes-Matrix-Fehler für Pedestrian+Subway).
    new_conn.set('uncontrolled', '1')
    # Original-Attribut 'keepClear' ist bei Pedestrian nicht nötig
    if 'keepClear' in new_conn.attrib:
        del new_conn.attrib['keepClear']
    # Schlüssel-Attribute für Pedestrian
    if 'dir' in new_conn.attrib:
        del new_conn.attrib['dir']
    if 'state' in new_conn.attrib:
        del new_conn.attrib['state']
    root.append(new_conn)
    added += 1

tree.write(CON_OUT, xml_declaration=True, encoding='UTF-8')
print(f'Schritt 2: {added} Ped-Connections hinzugefügt '
      f'(uncontrolled=1), {skipped_uturn} U-Turns übersprungen.')

# === Schritt 3: Reverse-Pedestrian-Edges fuer isolierte Forward-Edges ===
# Damit Pedestrians auf Bahnsteigen in BEIDE Richtungen laufen koennen, brauchen
# wir auf jeder Forward-Subway-Edge OHNE bidi-Schiene-Partner eine Reverse-Edge,
# die nur eine Pedestrian-Lane hat. Schienen-bidi-Edges (z. B. an der
# Wendeschleife) sind bereits abgedeckt.
edg_tree = ET.parse(EDG_OUT)
edg_root = edg_tree.getroot()

forward_subway = {}     # eid -> element (alle subway-Forward-Edges)
all_edge_ids = set()
for edge in edg_root.findall('edge'):
    eid = edge.get('id')
    all_edge_ids.add(eid)
    if eid in target_edges and not eid.startswith('-'):
        forward_subway[eid] = edge

isolated = []           # Edges, die einen Reverse-Ped-Partner brauchen
for eid, edge in forward_subway.items():
    reverse_id = '-' + eid
    if reverse_id in all_edge_ids:
        # bidi-Schiene mit ped-Lane existiert (durch Schritt 1 sichergestellt)
        continue
    isolated.append((eid, edge))

reverse_added = 0
for eid, edge in isolated:
    new_id = '-' + eid
    new_edge = ET.SubElement(edg_root, 'edge')
    new_edge.set('id', new_id)
    new_edge.set('from', edge.get('to'))
    new_edge.set('to', edge.get('from'))
    name = edge.get('name')
    if name is not None:
        new_edge.set('name', name)
    prio = edge.get('priority')
    if prio is not None:
        new_edge.set('priority', prio)
    typ = edge.get('type')
    if typ is not None:
        new_edge.set('type', typ)
    new_edge.set('numLanes', '1')
    new_edge.set('speed', edge.get('speed', '27.78'))
    shape = edge.get('shape')
    if shape:
        # Geometrie umkehren
        pts = shape.split()
        new_edge.set('shape', ' '.join(reversed(pts)))
    new_edge.set('spreadType', 'center')
    # bidi-Verknuepfung in beide Richtungen
    new_edge.set('bidi', eid)
    edge.set('bidi', new_id)

    lane = ET.SubElement(new_edge, 'lane')
    lane.set('index', '0')
    lane.set('allow', 'pedestrian')
    lane.set('width', '2.0')
    reverse_added += 1
    all_edge_ids.add(new_id)

edg_tree.write(EDG_OUT, xml_declaration=True, encoding='UTF-8')
print(f'Schritt 3: {reverse_added} Reverse-Ped-Edges fuer isolierte '
      f'Forward-Edges angelegt.')

# === Schritt 4: Reverse-Pedestrian-Connections + U-Turn-Connections ===
# Spiegele jede Forward-Pedestrian-Connection (fromLane=1, toLane=1) als
# Reverse-Connection. Die Lane-Indices haengen davon ab, ob die Reverse-Edge
# nur ped-Lane (Index 0) oder Schiene+Ped (Index 1) hat.
con_tree = ET.parse(CON_OUT)
con_root = con_tree.getroot()

# Welche Edges sind ped-Lane-only-Reverse (d.h. von uns frisch angelegt)?
ped_only_reverse = {'-' + eid for eid, _ in isolated}

def is_ped_edge(edge_id: str) -> bool:
    """Hat die Edge eine pedestrian-Lane (entweder Schienen+Ped oder ped-only)?"""
    return edge_id in target_edges or edge_id in ped_only_reverse

def ped_lane_index(edge_id: str) -> int:
    return 0 if edge_id in ped_only_reverse else 1

ped_conns = [c for c in con_root.findall('connection')
             if c.get('fromLane') == '1' and c.get('toLane') == '1']

def _reverse_id(eid: str) -> str:
    """Korrektes Inverse einer Edge-ID: -X <-> X (kein '--X')."""
    return eid[1:] if eid.startswith('-') else '-' + eid

reverse_conn_added = 0
existing_ped_pairs = {(c.get('from'), c.get('to')) for c in ped_conns}
for c in ped_conns:
    f, t = c.get('from'), c.get('to')
    rev_from = _reverse_id(t)
    rev_to   = _reverse_id(f)
    # Reverse-Edges muessen existieren (entweder Schienen-bidi oder frisch)
    if rev_from not in all_edge_ids:
        continue
    if rev_to not in all_edge_ids:
        continue
    # Beide Reverse-Edges muessen ped-faehig sein. Sonst zeigt die Connection
    # auf eine Lane, die nicht existiert (subway-only Edge ohne Lane 1).
    if not is_ped_edge(rev_from) or not is_ped_edge(rev_to):
        continue
    # Schon vorhanden? (z.B. bereits aus Schritt 2 fuer Schienen-bidi-Paare)
    if (rev_from, rev_to) in existing_ped_pairs:
        continue
    new_conn = copy.deepcopy(c)
    new_conn.set('from', rev_from)
    new_conn.set('to', rev_to)
    new_conn.set('fromLane', str(ped_lane_index(rev_from)))
    new_conn.set('toLane',   str(ped_lane_index(rev_to)))
    new_conn.set('uncontrolled', '1')
    con_root.append(new_conn)
    existing_ped_pairs.add((rev_from, rev_to))
    reverse_conn_added += 1

# U-Turn-Pedestrian-Connections: an jedem Knoten, an dem Forward-Edge X endet
# und Reverse-Edge -X anfaengt, eine Verbindung X -> -X (und -X -> X).
# Damit kann der Fussgaenger an JEDER Stelle umkehren — wichtig fuer
# Bahnsteige, wo zwei Personas in beide Richtungen laufen koennen sollen.
uturn_added = 0
for eid, edge in forward_subway.items():
    rev_id = '-' + eid
    if rev_id not in all_edge_ids and rev_id not in {'-' + e for e, _ in isolated}:
        continue
    # X -> -X (am to-Knoten von X = from-Knoten von -X)
    c_uturn_a = ET.Element('connection')
    c_uturn_a.set('from', eid)
    c_uturn_a.set('to', rev_id)
    c_uturn_a.set('fromLane', '1')
    c_uturn_a.set('toLane', str(ped_lane_index(rev_id)))
    c_uturn_a.set('uncontrolled', '1')
    con_root.append(c_uturn_a)
    # -X -> X (am to-Knoten von -X = from-Knoten von X)
    c_uturn_b = ET.Element('connection')
    c_uturn_b.set('from', rev_id)
    c_uturn_b.set('to', eid)
    c_uturn_b.set('fromLane', str(ped_lane_index(rev_id)))
    c_uturn_b.set('toLane', '1')
    c_uturn_b.set('uncontrolled', '1')
    con_root.append(c_uturn_b)
    uturn_added += 2

con_tree.write(CON_OUT, xml_declaration=True, encoding='UTF-8')
print(f'Schritt 4: {reverse_conn_added} gespiegelte Ped-Connections + '
      f'{uturn_added} U-Turn-Ped-Connections angelegt.')

# === Schritt 5: netconvert ausfuehren ===
nod_in = f'{PLAIN_DIR}/orig.nod.xml'
tll_in = f'{PLAIN_DIR}/orig.tll.xml'
typ_in = f'{PLAIN_DIR}/orig.typ.xml'
netconvert_cmd = [
    'netconvert',
    '--node-files', nod_in,
    '--edge-files', EDG_OUT,
    '--connection-files', CON_OUT,
    '--tllogic-files', tll_in,
    '--type-files', typ_in,
    '--output-file', NET_OUT,
    '--walkingareas',
    '--no-turnarounds', 'true',
    '--offset.disable-normalization', 'true',
]
print('Schritt 5: netconvert ...')
result = subprocess.run(netconvert_cmd, capture_output=True, text=True)
if result.returncode != 0:
    print('netconvert FEHLER:')
    print(result.stderr)
    raise SystemExit(1)
print(f'Schritt 5: net.xml geschrieben ({NET_OUT}).')

# === Schritt 6: Walking-Areas an Gleiswechsel-Junctions konsolidieren ===
# An Gleiswechsel-Junctions (z.B. 4088981246 Festhalle/Messe) erzeugt
# netconvert mehrere isolierte Walking-Areas, die nicht alle ped-Lanes
# verbinden. Folge: "Disconnected walk" fuer Pedestrians, die quer durch
# das Gleiswechsel laufen wollen.
# Fix: Pro Junction ALLE Walking-Areas auf EINE master-WA umlenken,
# Geometrien zusammenfuehren.
net_tree = ET.parse(NET_OUT)
net_root = net_tree.getroot()


def _parse_wa_id(eid: str):
    """':4088981246_w2' -> ('4088981246', '2'); sonst None."""
    if not eid.startswith(':'):
        return None
    rest = eid[1:]
    jid, sep, suffix = rest.rpartition('_w')
    if not sep or not suffix.isdigit():
        return None
    return jid, suffix


wa_per_junction = defaultdict(list)
wa_lane_shapes = {}
wa_lane_lengths = {}
for edge in list(net_root.findall('edge')):
    if edge.get('function') != 'walkingarea':
        continue
    parsed = _parse_wa_id(edge.get('id', ''))
    if parsed is None:
        continue
    jid, _ = parsed
    eid = edge.get('id')
    wa_per_junction[jid].append(eid)
    lane = edge.find('lane')
    if lane is not None:
        wa_lane_shapes[eid] = lane.get('shape', '')
        try:
            wa_lane_lengths[eid] = float(lane.get('length', '0'))
        except ValueError:
            wa_lane_lengths[eid] = 0.0

# Sammle pro Junction alle ped-Lanes (IN und OUT) basierend auf Edge-Endpunkten
ped_in_per_junction = defaultdict(set)   # jid -> {(edge_id, lane_idx)}
ped_out_per_junction = defaultdict(set)
edge_lane_is_ped = {}  # (edge_id, lane_idx) -> True/False

for edge in net_root.findall('edge'):
    if edge.get('function') in ('internal', 'walkingarea', 'crossing'):
        continue
    eid = edge.get('id')
    f_node = edge.get('from')
    t_node = edge.get('to')
    if f_node is None or t_node is None:
        continue
    for lane in edge.findall('lane'):
        idx = lane.get('index', '0')
        allow = lane.get('allow', '')
        if 'pedestrian' in allow:
            edge_lane_is_ped[(eid, idx)] = True
            ped_out_per_junction[f_node].add((eid, idx))  # OUT vom from-Knoten
            ped_in_per_junction[t_node].add((eid, idx))   # IN am to-Knoten

fixed_junctions = 0
added_in_conns = 0
added_out_conns = 0
for jid in set(list(wa_per_junction.keys()) + list(ped_in_per_junction.keys())
               + list(ped_out_per_junction.keys())):
    wa_list = wa_per_junction.get(jid, [])
    if not wa_list:
        continue
    master_wa = sorted(wa_list)[0]
    other_was = set(wa_list) - {master_wa}

    # 1. Konsolidiere alle WAs zu master_wa
    if other_was:
        for conn in net_root.findall('connection'):
            if conn.get('from') in other_was:
                conn.set('from', master_wa)
            if conn.get('to') in other_was:
                conn.set('to', master_wa)

        master_edge = None
        for edge in net_root.findall('edge'):
            if edge.get('id') == master_wa:
                master_edge = edge
                break
        if master_edge is not None:
            master_lane = master_edge.find('lane')
            if master_lane is not None:
                pts = master_lane.get('shape', '').split()
                total_len = wa_lane_lengths.get(master_wa, 0.0)
                for other_wa in other_was:
                    pts.extend(wa_lane_shapes.get(other_wa, '').split())
                    total_len += wa_lane_lengths.get(other_wa, 0.0)
                master_lane.set('shape', ' '.join(pts))
                master_lane.set('length', f'{total_len:.2f}')

        for other_wa in list(other_was):
            for edge in list(net_root.findall('edge')):
                if edge.get('id') == other_wa:
                    net_root.remove(edge)

    # 2. Sammle bestehende WA-Connections nach Konsolidierung
    existing_in = set()   # ped-Lanes, die bereits IN zu master_wa haben
    existing_out = set()  # ped-Lanes, die bereits OUT von master_wa haben
    for conn in net_root.findall('connection'):
        if conn.get('to') == master_wa:
            existing_in.add((conn.get('from'), conn.get('fromLane')))
        if conn.get('from') == master_wa:
            existing_out.add((conn.get('to'), conn.get('toLane')))

    # 3. Fehlende ped-IN-Lanes nachtragen (Edge endet in junction, lane ist ped,
    #    aber es gibt keine Connection edge -> master_wa)
    for (eid, idx) in ped_in_per_junction.get(jid, set()):
        if (eid, idx) in existing_in:
            continue
        new_conn = ET.SubElement(net_root, 'connection')
        new_conn.set('from', eid)
        new_conn.set('to', master_wa)
        new_conn.set('fromLane', idx)
        new_conn.set('toLane', '0')
        new_conn.set('dir', 's')
        new_conn.set('state', 'M')
        added_in_conns += 1

    # 4. Fehlende ped-OUT-Lanes nachtragen
    for (eid, idx) in ped_out_per_junction.get(jid, set()):
        if (eid, idx) in existing_out:
            continue
        new_conn = ET.SubElement(net_root, 'connection')
        new_conn.set('from', master_wa)
        new_conn.set('to', eid)
        new_conn.set('fromLane', '0')
        new_conn.set('toLane', idx)
        new_conn.set('dir', 's')
        new_conn.set('state', 'M')
        added_out_conns += 1

    fixed_junctions += 1

net_tree.write(NET_OUT, xml_declaration=True, encoding='UTF-8')
print(f'Schritt 6: {fixed_junctions} Junctions konsolidiert '
      f'(+{added_in_conns} IN-, +{added_out_conns} OUT-WA-Connections).')
