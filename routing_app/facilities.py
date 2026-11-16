"""Reusable facility lists; each truck uses one selected depot/receiver pair."""
from copy import deepcopy
import math
import re
from partition_app.inputs import InputError

GROUPS = (('depots','depot_mode','yard'),('garbage_receivers','garbage_mode','garbage'),
          ('recycling_receivers','recycling_mode','recycling'))


def site_record(value):
    return {k:v for k,v in value.items() if k not in {'id','selected'}}


def default_options(config):
    output={}
    for group,mode,kind in GROUPS:
        site=config['yard'] if kind=='yard' else config[kind]['receiver']
        output[mode]='single'
        output[group]=[{'id':group+'-1','selected':True,**deepcopy(site)}]
    return output


def normalize(config):
    options=config.get('facility_options')
    if options is None:return config
    if not isinstance(options,dict):raise InputError('Facility choices must be an object.')
    expected={x for group,mode,_ in GROUPS for x in (group,mode)}
    if set(options)-expected:raise InputError('Unknown facility choice field.')
    result=default_options(config)
    result.update(deepcopy(options))
    from .settings import clock_seconds
    for group,mode,kind in GROUPS:
        if result[mode] not in {'single','multiple'}:raise InputError('Choose one or multiple locations.')
        entries=result[group]
        if not isinstance(entries,list) or not 1<=len(entries)<=25:
            raise InputError('Each facility group needs 1 to 25 saved locations.')
        ids=set()
        for entry in entries:
            if not isinstance(entry,dict):raise InputError('Each facility must be an object.')
            required={'id','selected','name','address','lat','lon','coordinate_source'}
            if kind!='yard':required|={'opens','closes','onsite_minutes'}
            if not required<=set(entry) or set(entry)-required-{'summer_opens','summer_closes'}:
                raise InputError('A facility has missing or unknown fields.')
            identity=entry['id']
            if not isinstance(identity,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',identity) or identity in ids:
                raise InputError('Facility IDs must be unique within each group.')
            ids.add(identity)
            if not isinstance(entry['selected'],bool):raise InputError('Facility selection must be true or false.')
            for key in ['name','address','coordinate_source']:
                if not isinstance(entry[key],str) or not 1<=len(entry[key].strip())<=400:
                    raise InputError('Enter a name, address and coordinate source for every saved facility.')
            for key,lo,hi in [('lat',49.23,50.53),('lon',-98.25,-96.20)]:
                v=entry[key]
                if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or not lo<=v<=hi:
                    raise InputError('Facility coordinates must be within the current Winnipeg routing geography.')
            if kind!='yard':
                if clock_seconds(entry['opens'])>=clock_seconds(entry['closes']):
                    raise InputError('Receiver closing time must be after opening time.')
                value=entry['onsite_minutes']
                if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not 0<=value<=180:
                    raise InputError('Receiver onsite minutes must be between 0 and 180.')
        selected=[site_record(v) for v in entries if v['selected']]
        if not selected:raise InputError(f'Select at least one location for {group.replace("_"," ")}.')
        if result[mode]=='single' and len(selected)!=1:raise InputError('Single-location mode needs exactly one selected location.')
        if kind=='yard':config['yard']=selected[0]
        else:config[kind]['receiver']=selected[0]
    config['facility_options']=result
    return config


def pairs(config,stream):
    options=config.get('facility_options') or default_options(config)
    depots=[v for v in options['depots'] if v['selected']]
    receivers=[v for v in options[stream+'_receivers'] if v['selected']]
    return [(a,b) for a in depots for b in receivers]


def case_settings(config,stream,depot,receiver):
    result=deepcopy(config)
    result['facility_options']=None
    result['yard']=site_record(depot)
    result[stream]['receiver']=site_record(receiver)
    return result
