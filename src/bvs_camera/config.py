"""Read/validate air-side link identifiers and frequencies."""
import re

def validate(config):
    if config['bandwidth_mhz']!=20:raise ValueError('Only HT20 is configured')
    drones=config['drones']
    if not 1<=len(drones)<=3:raise ValueError('Use 1..3 links')
    for key in ('id','link_id','frequency_mhz'):
        if len({d[key] for d in drones})!=len(drones):raise ValueError('Duplicate '+key)
    for d in drones:
        if not re.fullmatch('[A-Za-z0-9_.-]+',d['id']):raise ValueError('Invalid id')
        if type(d['link_id']) is not int or not 1<=d['link_id']<=0xffffff:raise ValueError('Invalid link id')
        if type(d['frequency_mhz']) is not int or not 2400<=d['frequency_mhz']<=2500:raise ValueError('Invalid frequency')
    for i,a in enumerate(drones):
        for b in drones[i+1:]:
            if abs(a['frequency_mhz']-b['frequency_mhz'])<25:raise ValueError('Overlapping channels')
    return config
