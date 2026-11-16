import io
import json

import openpyxl
import pytest
from shapely.geometry import LineString, Point, Polygon, box, mapping, shape
from shapely.strtree import STRtree

from partition_app.engine import plan, publication_geometry, normalise_published_edges
from partition_app.geography import FORWARD, REVERSE, subdivide
from partition_app.geography import road_evidence, promote_divided_roads, alley_frontage_candidates, segment_roads_at_barriers
from partition_app.engine import enclosed_owners, seam_dividers
from partition_app.geography import Geography
from partition_app.preferences import address_preferences
from partition_app.inputs import InputError, parse_upload


def csv_data(body, header="AddressId,Address,Latitude,Longitude,Day,CoordinateStatus,SiteId"):
    return (header + "\n" + body).encode()


def test_selected_day_and_distinct_source_ids():
    data = parse_upload(csv_data("0001,100 TEST ST,49.85,-97.2,MONDAY,Exact address,\n0002,100 TEST ST,49.85,-97.2,MONDAY,Exact address,\n0003,200 TEST ST,bad,bad,TUESDAY,,"), "list.csv", collection_day="MONDAY")
    assert [r["id"] for r in data.rows] == ["0001", "0002"]
    assert data.excluded == 1
    assert data.preview()["distinct_coordinates"] == 1


def test_friendly_excel_garbage_day_header_is_recognised():
    data=parse_upload(csv_data('1,A,49.85,-97.2,MONDAY\n2,B,49.85,-97.2,TUESDAY','AddressId,Address,Latitude,Longitude,Garbage day'),'list.csv',collection_day='MONDAY')
    assert [r['id'] for r in data.rows]==['1'] and data.excluded==1


@pytest.mark.parametrize("body", ["1,A,NaN,-97.2,MONDAY,,", "1,A,49.85,-97.2,, ,", "1,A,49.85,-97.2,MONDAY,,\n1,B,49.86,-97.2,MONDAY,,", "1,A,-97.2,49.85,MONDAY,,"])
def test_bad_monday_rows_fail_without_partial_acceptance(body):
    with pytest.raises(InputError):
        parse_upload(csv_data(body), "list.csv")


def test_no_day_column_requires_explicit_confirmation():
    content=csv_data("id001,100 TEST,49.85,-97.2", "ID,Address,Lat,Lng")
    with pytest.raises(InputError, match="Choose a collection day"):
        parse_upload(content,"list.csv")
    assert len(parse_upload(content,"list.csv",confirm_monday=True).rows)==1
    assert parse_upload(content,"list.csv",collection_day="TUESDAY").day=="TUESDAY"


@pytest.mark.parametrize("value,expected", [("Monday","MONDAY"),(" tue ","TUESDAY"),("Tues.","TUESDAY"),
    ("Wednesday","WEDNESDAY"),("Thurs","THURSDAY"),("Fri","FRIDAY"),("Sat","SATURDAY"),("Sun","SUNDAY")])
def test_weekday_is_detected_from_rows(value,expected):
    data=parse_upload(csv_data(f"0001,A,49.85,-97.2,{value},,"),"upload.csv")
    assert data.day==expected and data.day_source=="column" and data.excluded==0
    assert data.preview()["day"]==expected and data.rows[0]["day"]==expected
    assert data.rows[0]["id"]=="0001" and data.rows[0]["raw"]["Day"]==value


def test_day_column_beats_a_misleading_filename():
    data=parse_upload(csv_data("1,A,49.85,-97.2,TUESDAY,,"),"Monday_upload.csv")
    assert data.day=="TUESDAY" and data.excluded==0
    assert any("name suggests Monday" in w for w in data.warnings)


def test_mixed_days_require_choice_and_report_exclusions():
    content=csv_data("1,A,49.85,-97.2,MONDAY,,\n2,B,49.85,-97.2,TUESDAY,,\n3,B,49.85,-97.2,TUESDAY,,")
    with pytest.raises(InputError,match="multiple collection days") as exc:
        parse_upload(content,"Monday.csv")
    assert exc.value.available_days=={"MONDAY":1,"TUESDAY":2}
    data=parse_upload(content,"upload.csv",collection_day="Tue")
    assert data.day=="TUESDAY" and data.excluded==1
    assert [r["id"] for r in data.rows]==["2","3"]
    assert data.preview()["available_days"]=={"MONDAY":1,"TUESDAY":2}
    with pytest.raises(InputError,match="No Friday address rows"):
        parse_upload(content,"upload.csv",collection_day="FRIDAY")


def test_filename_fallback_and_day_sensitive_input_identity():
    content=csv_data("1,A,49.85,-97.2","AddressId,Address,Latitude,Longitude")
    data=parse_upload(content,"Tuesday_addresses_lat_long.csv")
    assert data.day=="TUESDAY" and data.day_source=="filename"
    other=parse_upload(content,"Tuesday_addresses_lat_long.csv",collection_day="MONDAY")
    assert other.digest!=data.digest and other.day_source=="selection"


def test_multiple_day_sheets_are_selected_once_not_concatenated():
    workbook=openpyxl.Workbook();workbook.active.title="Monday"
    workbook.create_sheet("Tuesday");workbook.create_sheet("Notes").append(["Read me"])
    for name in ["Monday","Tuesday"]:
        workbook[name].append(["AddressId","Address","Latitude","Longitude"])
        workbook[name].append([1,"SAME ADDRESS",49.85,-97.2])
    buffer=io.BytesIO();workbook.save(buffer);content=buffer.getvalue()
    with pytest.raises(InputError,match="multiple address sheets") as exc:
        parse_upload(content,"addresses.xlsx")
    assert exc.value.available_sheets==["Monday","Tuesday"]
    for kwargs in [{"sheet":"Tuesday"},{"collection_day":"Tue"}]:
        data=parse_upload(content,"addresses.xlsx",**kwargs)
        assert data.day=="TUESDAY" and data.sheet=="Tuesday" and len(data.rows)==1
    assert parse_upload(content,"Tuesday_addresses.xlsx").day=="TUESDAY"


def test_unknown_days_and_corrupt_workbooks_fail_with_input_messages():
    with pytest.raises(InputError,match="Choose a valid collection day"):
        parse_upload(csv_data("1,A,49.85,-97.2,TUESDAY,,"),"x.csv",collection_day="Tomorrow")
    with pytest.raises(InputError,match="invalid Tuesday row") as exc:
        parse_upload(csv_data("1,A,49.85,-97.2,TUESDAY,,\n2,B,49.85,-97.2,SOMEDAY,,"),"x.csv")
    assert "unrecognised" in exc.value.errors[0]["message"]
    with pytest.raises(InputError,match="Could not read"):
        parse_upload(b"not an xlsx","Tuesday.xlsx")


def test_late_escaped_quotes_and_raw_source_spaces_are_preserved():
    import csv
    stream=io.StringIO(newline="")
    writer=csv.writer(stream)
    writer.writerow(["AddressId","Latitude","Longitude","Day","Note"])
    for i in range(400):writer.writerow([str(i),49.85,-97.2,"MONDAY","ordinary note"])
    note='  User supplied: 49°51\'00.3"N 97°13\'29.8"W  '
    writer.writerow(["DMS",49.85,-97.2,"MONDAY",note])
    data=parse_upload(stream.getvalue().encode(),"quoted.csv")
    assert data.rows[-1]["raw"]["Note"]==note


def test_xlsx_selects_monday_once_and_preserves_physical_source_rows():
    workbook=openpyxl.Workbook()
    workbook.active.title="Sheet1"
    workbook.active.append(["AddressId","Address","Latitude","Longitude"])
    workbook.active.append([1,"OTHER",49.85,-97.2])
    monday=workbook.create_sheet("Monday")
    monday.append(["Monday delivery"])
    for _ in range(6):monday.append([])
    monday.append(["AddressId","Address","Latitude","Longitude"])
    monday.append([42,"MONDAY ONLY",49.85,-97.2])
    buffer=io.BytesIO();workbook.save(buffer);original=buffer.getvalue()
    data=parse_upload(original,"intake.xlsx")
    assert data.sheet=="Monday" and len(data.rows)==1 and data.rows[0]["id"]=="42"
    assert data.rows[0]["source_row"]==9
    assert original==buffer.getvalue()


def test_finite_divider_is_never_extended():
    parent=box(0,0,100,100)
    assert len(subdivide(parent,[LineString([(50,25),(50,75)])]))==1
    assert len(subdivide(parent,[LineString([(50,0),(50,100)])]))==2


def test_complete_finite_diagonal_is_noded_before_clipping():
    # A public-geometry numerical regression reduced to a quadrilateral and a
    # straight finite line. Pre-clipping missed this genuine through-divider.
    parent=Polygon([(630975.76,5519910.3),(631152.18,5519469.82),
                    (628116.52,5517891.08),(627976.81,5519509.74)])
    line=LineString([(629636.28,5523363.93),(625268.7,5506185.99)])
    pieces=subdivide(parent,[line])
    assert len(pieces)==2
    assert sum(p.area for p in pieces)==pytest.approx(parent.area,abs=1e-6)


def test_broad_municipal_corridor_uses_evidence_instead_of_a_road_name():
    from types import SimpleNamespace
    from partition_app.corridors import discover_corridors
    line=LineString([(CX,CY),(CX+2000,CY)])
    neighbourhood=box(CX,CY,CX+2000,CY+100)
    parcels=[{'id':'north','geometry':box(CX,CY+12,CX+2000,CY+100)},
             {'id':'south','geometry':box(CX,CY-100,CX+2000,CY-12)}]
    for name in ['Example Road','Different Road']:
        features=[{'id':'arterial','name':name,'category':'road_reference','geometry':line,'tags':{'highway':'secondary','lanes':'2'}},
                  {'id':'multi-lane','name':name,'category':'wide_road','geometry':LineString([(CX,CY),(CX+350,CY)]),'tags':{'highway':'secondary','lanes':'4'}}]
        geo=SimpleNamespace(features=features,roads=[{'id':'city','name':name,'geometry':line}],
            parcels=parcels,parcel_tree=STRtree([p['geometry'] for p in parcels]),
            neighbourhoods=[{'geometry':neighbourhood}],neighbourhood_tree=STRtree([neighbourhood]))
        found=discover_corridors(geo)
        assert len(found)==1 and found[0]['category']=='municipal_corridor'
        assert found[0]['median_right_of_way_m']==pytest.approx(24)
        assert found[0]['municipal_alignment']==1


def test_publication_removes_zero_area_spike_without_dropping_polygonal_area():
    native=Polygon([(CX,CY),(CX+100,CY),(CX+100,CY+100),(CX+50,CY+100),
                    (CX+50,CY+50),(CX+50,CY+100),(CX,CY+100)])
    published=publication_geometry(native)
    assert published.is_valid and published.geom_type=="Polygon" and not published.interiors
    assert published.area>0


def test_publication_shared_edges_remove_only_numeric_overlaps():
    a=box(-97.2,49.85,-97.199,49.851)
    b=box(-97.19900001,49.85,-97.198,49.851)
    features=[{"geometry":mapping(a)},{"geometry":mapping(b)}]
    removed=normalise_published_edges(features)
    assert 0<removed<1
    assert shape(features[0]["geometry"]).intersection(shape(features[1]["geometry"])).area==0
    for f in features:assert shape(f["geometry"]).is_valid
    # A genuinely overlapping area cannot be disguised as numeric cleanup.
    material=[{"geometry":mapping(a)},{"geometry":mapping(a)}]
    assert normalise_published_edges(material)==0
    assert shape(material[0]["geometry"]).intersection(shape(material[1]["geometry"])).area>0


CX,CY=FORWARD.transform(-97.2,49.85)


class SmallGeography:
    digest="test-frozen-geography"
    manifest={"sources":[]}
    features=[]
    parcels=[]
    roads=[]
    parcel_tree=STRtree([])
    road_tree=STRtree([])
    def __init__(self, road=False, parcel=False, disconnected=False):
        self.seen=[]
        self.cells=[{"name":"West","source_id":"1","geometry":box(CX-100,CY-100,CX,CY+100)},
                    {"name":"East","source_id":"2","geometry":box(CX+(5 if disconnected else 0),CY-100,CX+100,CY+100)}]
        if road:
            self.roads=[{"id":"one-segment","name":"TEST ST","type":"STREET","geometry":LineString([(CX,CY-100),(CX,CY+100)])}]
            self.road_tree=STRtree([self.roads[0]["geometry"]])
        if parcel:
            self.parcels=[{"id":"one-site","geometry":box(CX-40,CY-40,CX+40,CY+40)}]
            self.parcel_tree=STRtree([self.parcels[0]["geometry"]])
    def geography_cells(self,points,target=None,**kwargs):
        self.seen=list(points)
        return self.cells,[]
    def nearby_features(self,geometry,categories):return []


def sample_dataset(points):
    lines=[]
    for identity,x,y,quality,site in points:
        lon,lat=REVERSE.transform(CX+x,CY+y)
        lines.append(f"{identity},{identity} TEST ST,{lat},{lon},MONDAY,{quality},{site}")
    return parse_upload(csv_data("\n".join(lines)),"fixture.csv")


def test_partition_and_assignment_export_keep_the_selected_day():
    import csv
    from partition_app.engine import assignments_csv
    content=csv_data("0001,A,49.85,-97.2,TUESDAY,,old-value",
                     "AddressId,Address,Latitude,Longitude,Day,CoordinateStatus,PartitionCollectionDay")
    data=parse_upload(content,"Tuesday.csv")
    result=plan(data,SmallGeography())
    assert result["day"]=="TUESDAY" and result["validation"]["exactly_once"]
    assert result["areas"]["features"][0]["id"]=="TUE-001"
    exported=list(csv.DictReader(io.StringIO(assignments_csv(data,result).lstrip("\ufeff"))))
    assert len(exported)==1 and exported[0]["AddressId"]=="0001"
    assert exported[0]["PartitionCollectionDay"]=="old-value"
    day_column=result["assignment_columns"]["PartitionCollectionDay"]
    assert day_column!="PartitionCollectionDay" and exported[0][day_column]=="TUESDAY"


def test_ordinary_segment_keeps_both_curbs_without_merging_source_rows():
    data=sample_dataset([(1,-20,0,"Exact address",""),(2,20,0,"Exact address","")])
    result=plan(data,SmallGeography(road=True))
    assert result["summary"]["addresses"]==2 and result["summary"]["areas"]==1
    assert {r["id"] for r in result["points"]}=={"1","2"}
    assert result["validation"]["split_protected_groups"]==0


def test_material_serviced_parcel_is_not_cut():
    result=plan(sample_dataset([(1,-20,0,"Exact address",""),(2,20,0,"Exact address","")]),SmallGeography(parcel=True))
    assert result["summary"]["areas"]==1
    assert result["validation"]["material_parcel_cuts"]==0


def test_estimates_do_not_create_or_move_boundaries_but_retain_count():
    geo=SmallGeography()
    result=plan(sample_dataset([(1,-20,0,"Exact address","site"),(2,20,0,"Approximate site centre","site")]),geo)
    assert len(geo.seen)==1
    assert result["summary"]["addresses"]==2 and result["summary"]["estimated"]==1
    assert len({p["section"] for p in result["points"]})==1
    assert result["validation"]["estimated_points_drive_boundaries"] is False


def test_oversized_protected_site_stays_whole_and_reports_target_conflict():
    rows=[(i,-20,0,"Exact address","same-site") for i in range(70)]
    result=plan(sample_dataset(rows),SmallGeography(),target=50)
    assert result["summary"]["areas"]==1 and result["summary"]["addresses"]==70
    assert any(f["code"]=="PROTECTED_GROUP_ABOVE_TARGET" for f in result["findings"])


def test_disconnected_site_fails_instead_of_creating_a_buffer_bridge():
    result=plan(sample_dataset([(1,-20,0,"Exact address","site"),(2,20,0,"Exact address","site")]),SmallGeography(disconnected=True))
    assert result["status"]=="FAILED"
    assert any(f["code"]=="TOPOLOGY" for f in result["findings"])
    assert result["validation"]["exactly_once"]


def test_source_order_does_not_change_partition():
    data=sample_dataset([(1,-20,0,"Exact address",""),(2,20,0,"Exact address","")])
    first=plan(data,SmallGeography())
    data.rows.reverse()
    second=plan(data,SmallGeography())
    assert first["partition_hash"]==second["partition_hash"]


def test_address_bands_and_minimum_tolerance():
    p=address_preferences(600)
    assert (p["preferred_minimum"],p["maximum_addresses"])==(510,690)
    assert address_preferences(1000,10)["maximum_addresses"]==1100
    p=address_preferences(600,5)
    assert p["range_adjusted"] and (p["preferred_minimum"],p["maximum_addresses"])==(540,660)
    p=address_preferences(minimum=590,maximum=610)
    assert p["preference_input"]=="range" and p["range_adjusted"]
    assert (p["preferred_minimum"],p["maximum_addresses"])==(540,660)
    p=address_preferences(minimum=500,maximum=700)
    assert (p["preferred_minimum"],p["maximum_addresses"])==(500,700)
    assert address_preferences()["mode"]=="natural"
    edge=address_preferences(minimum=50,maximum=51)
    assert (edge['target_addresses'],edge['preferred_minimum'],edge['maximum_addresses'])==(51,46,56)


@pytest.mark.parametrize("args", [{"target":True},{"target":600,"tolerance":float('nan')},{"minimum":700,"maximum":500},{"target":600,"tolerance":51},{"minimum":500}])
def test_invalid_preferences_reject_before_work(args):
    with pytest.raises(ValueError):address_preferences(**args)


def test_ordinary_speed_40_or_50_and_road_class_are_not_dividers():
    for speed in ('40','50'):
        assert road_evidence({"highway":"secondary","maxspeed":speed}) is None
        assert road_evidence({"highway":"residential","maxspeed":speed}) is None
    assert road_evidence({"highway":"secondary","maxspeed":"50","lanes":"4"})
    assert road_evidence({"highway":"tertiary","width":"16 m"})
    assert road_evidence({"highway":"motorway"})


def test_confirmed_collection_access_is_separate_from_rear_load():
    header="AddressId,Address,Latitude,Longitude,Day,CollectionAccess,TruckType"
    data=parse_upload(csv_data('1,A,49.85,-97.2,MONDAY,alley,ASL\n2,B,49.85,-97.2,MONDAY,,rear-load',header),'list.csv')
    assert [r['access'] for r in data.rows]==['alley','unknown']


def test_under_100_city_pockets_merge_across_administrative_line_alone():
    data=sample_dataset([(i,-20 if i<10 else 20,0,"Exact address","") for i in range(21)])
    result=plan(data,SmallGeography(),target=50)
    assert result['summary']['areas']==1
    assert sorted(f['properties']['addresses'] for f in result['areas']['features'])==[21]
    assert all(f['properties']['size_status']=='SMALL_NATURAL_AREA' for f in result['areas']['features'])
    assert result['validation']['address_limit_met']


def test_count_limit_includes_estimates_and_is_never_reported_met_if_exceeded():
    data=sample_dataset([(i,-20,0,'Exact address' if i<57 else 'Approximate site centre','same-site') for i in range(58)])
    result=plan(data,SmallGeography(),target=50,tolerance=15)
    assert result['summary']['largest']==58 and result['settings']['maximum_addresses']==57
    assert result['summary']['areas_above_limit']==1
    assert not result['validation']['address_limit_met']
    assert result['areas']['features'][0]['properties']['oversize_reason']


def test_paired_two_lane_carriageways_and_city_name_abbreviations():
    features=[{'id':'way-1','name':'Example Avenue','category':'road_reference','eligible':False,'tags':{'highway':'secondary','maxspeed':'50','lanes':'2','oneway':'yes'},'geometry':LineString([(0,10),(200,10)])},
              {'id':'way-2','name':'Example Avenue','category':'road_reference','eligible':False,'tags':{'highway':'secondary','maxspeed':'50','lanes':'2','oneway':'yes'},'geometry':LineString([(200,-10),(0,-10)])}]
    roads=[{'id':'city-1','name':'Example Ave','type':'STREET','geometry':LineString([(0,0),(200,0)])}]
    additions=promote_divided_roads(features,roads)
    assert all(f['eligible'] for f in features)
    assert len(additions)==1 and additions[0]['evidence_ids']==['way-1','way-2']


def test_mapped_alleys_require_parallel_evidence_on_both_sides():
    road={'id':'city-1','name':'Example St','type':'STREET','geometry':LineString([(0,0),(200,0)])}
    alleys=[{'id':'alley-1','category':'alley','geometry':LineString([(0,30),(200,30)])},
            {'id':'alley-2','category':'alley','geometry':LineString([(200,-30),(0,-30)])}]
    assert alley_frontage_candidates(alleys[:1],[road])==[]
    result=alley_frontage_candidates(alleys,[road])
    assert len(result)==1 and not result[0]['pickup_access_confirmed']


def test_owned_enclave_is_not_an_unassigned_gap():
    outer=Polygon([(0,0),(100,0),(100,100),(0,100)], [[(40,40),(60,40),(60,60),(40,60)]])
    inner=box(40,40,60,60)
    assert enclosed_owners(outer,[outer,inner],STRtree([outer,inner]))==([1],[])
    assert enclosed_owners(outer,[outer],STRtree([outer]))[1]==[400]


def test_mapped_alley_evidence_cannot_override_unknown_pickups():
    data=sample_dataset([(1,-20,0,'Exact address',''),(2,20,0,'Exact address','')])
    assert plan(data,SmallGeography(road=True),target=50)['summary']['areas']==1
    with pytest.raises(ValueError,match='until pickups are confirmed'):
        plan(data,SmallGeography(road=True),target=50,use_mapped_alleys=True)


def test_alley_collection_does_not_automatically_create_a_street_divider():
    data=sample_dataset([(i,-20 if i<120 else 20,0,'Exact address','') for i in range(240)])
    geo=SmallGeography(road=True)
    alley={'id':'alley','category':'alley','rank':6,'geometry':LineString([(CX-40,CY-100),(CX-40,CY+100)])}
    geo.nearby_features=lambda geometry,categories:[alley] if 'alley' in categories else []
    for row in data.rows[:-1]:row['access']='alley'
    assert plan(data,geo,target=300)['summary']['areas']==1
    data.rows[-1]['access']='alley'
    assert plan(data,geo,target=300)['summary']['areas']==1


def test_frontage_refinement_uses_finite_junction_and_parcel_anchors():
    geo=Geography.__new__(Geography)
    geo.roads=[{'id':str(i),'name':'Test','type':'STREET','geometry':LineString([a,b])} for i,(a,b) in enumerate([
        ((CX-100,CY),(CX,CY)),((CX,CY),(CX+100,CY)),((CX,CY-100),(CX,CY)),((CX,CY),(CX,CY+100))])]
    geo.road_tree=STRtree([r['geometry'] for r in geo.roads])
    geo.parcels=[{'id':str(i),'geometry':box(CX+x1,CY+y1,CX+x2,CY+y2)} for i,(x1,y1,x2,y2) in enumerate([
        (-100,-100,-20,-20),(20,-100,100,-20),(-100,20,-20,100),(20,20,100,100)])]
    geo.parcel_tree=STRtree([p['geometry'] for p in geo.parcels])
    cell={'source_id':'1','name':'Test City area','geometry':box(CX-100,CY-100,CX+100,CY+100)}
    cells,ledger,evidence=geo.refine_frontage_cells([cell],{0})
    from shapely.ops import unary_union
    assert unary_union([c['geometry'] for c in cells]).symmetric_difference(cell['geometry']).area<.001
    assert len(ledger)==1 and len(ledger[0]['junction_connectors'])==4
    for item in ledger[0]['junction_connectors']:
        assert item['junction']==[round(CX,2),round(CY,2)]
        assert item['parcel'] in {'0','1','2','3'}
    assert all(c['frontage_refined'] for c in cells)


def test_regular_whole_group_growth_prefers_the_address_band():
    geo=SmallGeography()
    geo.cells=[{'name':'One city area','source_id':'1','geometry':box(CX+x,CY-100,CX+x+100,CY+100)} for x in (-150,-50,50)]
    data=sample_dataset([(i,(-100 if i<240 else 0 if i<480 else 100),0,'Exact address','') for i in range(720)])
    result=plan(data,geo,target=500,tolerance=15)
    assert sorted(f['properties']['addresses'] for f in result['areas']['features'])==[240,480]
    assert result['validation']['address_limit_met'] and result['validation']['split_protected_groups']==0
    data.rows.reverse()
    assert plan(data,geo,target=500)['partition_hash']==result['partition_hash']


def test_protected_curbs_take_real_connecting_block_before_count_balancing():
    geo=SmallGeography()
    geo.cells=[{'name':name,'source_id':str(i),'geometry':box(CX+x1,CY-100,CX+x2,CY+100)}
               for i,(name,x1,x2) in enumerate([('West',-100,-10),('Middle',-10,10),('East',10,100)])]
    data=sample_dataset([(1,-50,0,'Exact address','linked'),(2,50,0,'Exact address','linked'),(3,0,0,'Exact address','')])
    result=plan(data,geo,target=50)
    assert result['status']=='PROVISIONAL',result['findings']
    assert result['summary']['areas']==1 and result['summary']['addresses']==3
    assert result['areas']['features'][0]['properties']['components']==1
    assert result['merge_reasons']['City line yields to protected frontage']==1
    # A real physical barrier cannot be removed to repair a linked group.
    water={'id':'water','category':'waterway','rank':1,'geometry':LineString([(CX-10,CY-100),(CX-10,CY+100)])}
    geo.nearby_features=lambda geometry,categories:[water] if 'waterway' in categories and geometry.intersects(water['geometry']) else []
    blocked=plan(data,geo,target=50)
    assert blocked['status']=='FAILED'
    assert any(f['code']=='TOPOLOGY' for f in blocked['findings'])


def test_target_does_not_atomise_a_natural_area_along_ordinary_streets():
    geo=Geography.__new__(Geography)
    geo.digest='junction-fixture';geo.manifest={'sources':[]};geo.prepared_road_revision=3
    geo.features=[];geo.feature_tree=STRtree([])
    geo.roads=[{'id':str(i),'name':name,'type':'STREET','geometry':LineString([(CX+x1,CY+y1),(CX+x2,CY+y2)])}
               for i,(name,x1,y1,x2,y2) in enumerate([
                   ('TEST ST',0,-100,0,0),('TEST ST',0,0,0,100),('CROSS AVE',-100,0,0,0),('CROSS AVE',0,0,100,0)])]
    geo.road_tree=STRtree([r['geometry'] for r in geo.roads])
    geo.parcels=[{'id':str(i),'geometry':box(CX+x1,CY+y1,CX+x2,CY+y2)} for i,(x1,y1,x2,y2) in enumerate([
        (-100,-100,-20,-10),(20,-100,100,-10),(-100,10,-20,100),(20,10,100,100)])]
    geo.parcel_tree=STRtree([p['geometry'] for p in geo.parcels])
    coarse=[{'source_id':'town','name':'Town','geometry':box(CX+x1,CY-100,CX+x2,CY+100)} for x1,x2 in [(-100,-10),(-10,10),(10,100)]]
    geo.geography_cells=lambda points,target=None,**kwargs:(coarse,[])
    data=sample_dataset([(i,-30 if i%2==0 else 30,-50 if i<300 else 50,'Exact address','') for i in range(600)])
    result=plan(data,geo,target=500)
    assert result['status']=='PROVISIONAL',result['findings']
    assert sorted(f['properties']['addresses'] for f in result['areas']['features'])==[600]
    assert result['summary']['areas_above_limit']==1
    assert all(f['properties']['components']==1 for f in result['areas']['features'])
    assert result['validation']['split_protected_groups']==0


def test_rail_crossing_ends_frontage_protection_and_blocks_small_merge():
    rail={'id':'rail','category':'railway','rank':1,'geometry':LineString([(CX,CY-100),(CX,CY+100)])}
    road={'id':'road','name':'TEST ST','type':'STREET','geometry':LineString([(CX-100,CY),(CX+100,CY)])}
    pieces=segment_roads_at_barriers([road],[rail])
    assert len(pieces)==2 and sum(r['geometry'].length for r in pieces)==pytest.approx(200)
    geo=SmallGeography();geo.roads=pieces;geo.road_tree=STRtree([r['geometry'] for r in pieces])
    geo.nearby_features=lambda g,categories:[rail] if 'railway' in categories and g.intersects(rail['geometry']) else []
    data=sample_dataset([(1,-20,0,'Exact address',''),(2,20,0,'Exact address','')])
    result=plan(data,geo,target=600)
    assert result['status']=='PROVISIONAL' and result['summary']['areas']==2


def test_nearby_small_pocket_shares_list_without_inventing_land_or_crossing_water():
    geo=SmallGeography()
    geo.cells=[{'name':'Pocket','source_id':'1','geometry':box(CX-100,CY-100,CX-20,CY+100)},
               {'name':'Larger','source_id':'2','geometry':box(CX+80,CY-100,CX+250,CY+100)}]
    data=sample_dataset([(1,-50,0,'Exact address','')]+[(i,150,0,'Exact address','') for i in range(2,122)])
    result=plan(data,geo,target=600)
    assert result['status']=='PROVISIONAL',result['findings']
    assert result['summary']['areas']==1 and result['summary']['addresses']==121
    area=result['areas']['features'][0]
    assert area['geometry']['type']=='MultiPolygon' and area['properties']['nearby_small_area_group']
    assert area['properties']['nearby_merge_links'][0]['distance_m']==100
    # Compare projected area: the gap is never included in the exported shape.
    from partition_app.geography import project
    assert project(shape(area['geometry'])).area==pytest.approx(sum(c['geometry'].area for c in geo.cells),abs=1)
    water={'id':'water','category':'waterway','rank':1,'geometry':LineString([(CX+30,CY-200),(CX+30,CY+200)])}
    geo.nearby_features=lambda g,categories:[water] if 'waterway' in categories and g.intersects(water['geometry']) else []
    blocked=plan(data,geo,target=600)
    assert blocked['status']=='PROVISIONAL' and blocked['summary']['areas']==2


def test_detached_unserved_component_changes_owner_without_splitting_parcel():
    from partition_app.engine import assign_unserved_components
    from collections import Counter
    from shapely.geometry import MultiPolygon
    left=box(0,0,10,10);patch=box(20,0,22,10);middle=box(10,0,20,10)
    current={0:MultiPolygon([left,patch]),1:middle}
    assert assign_unserved_components(current,{0:[Point(5,5)],1:[Point(15,5)]},{},Counter())==1
    assert all(g.geom_type=='Polygon' for g in current.values())
    assert current[0].equals(left) and current[1].equals(middle.union(patch))
    current={0:MultiPolygon([left,patch]),1:middle}
    # One mapped parcel has material pieces in both detached components.
    parcel=MultiPolygon([box(5,0,10,10),patch])
    assert assign_unserved_components(current,{0:[Point(5,5)],1:[Point(15,5)]},{'site':{'geometry':parcel}},Counter())==0
    assert current[0].geom_type=='MultiPolygon'


def test_road_crossing_at_a_parcel_corner_is_not_a_parallel_divider():
    geo=SmallGeography()
    shared=LineString([(CX,CY),(CX,CY+10)])
    rail={'id':'rail','category':'railway','rank':1,'geometry':LineString([(CX-100,CY+5),(CX+100,CY+5)])}
    geo.nearby_features=lambda g,c:[rail]
    assert seam_dividers(shared,geo)==[]
    rail['geometry']=shared
    assert seam_dividers(shared,geo)==[rail]


def test_a_small_facility_joins_nearby_neighbourhood_but_not_beyond_a_remote_park():
    data=sample_dataset([(1,-20,0,'Exact address','')]+[(i,20,0,'Exact address','') for i in range(2,122)])
    geo=SmallGeography()
    park={'id':'park','category':'park','rank':3,'geometry':geo.cells[0]['geometry']}
    geo.nearby_features=lambda g,c:[park] if 'park' in c and g.intersects(park['geometry']) else []
    assert plan(data,geo,target=600)['summary']['areas']==1
    geo.cells=[{'name':n,'source_id':str(i),'geometry':box(CX+x1,CY-100,CX+x2,CY+100)}
               for i,(n,x1,x2) in enumerate([('West',-100,0),('Park',0,10),('East',10,100)])]
    park['geometry']=geo.cells[1]['geometry']
    # A nearby tiny pocket can join the neighbourhood across ordinary open
    # space; a remote pocket beyond the same corridor remains an exception.
    result=plan(data,geo,target=600)
    assert result['status']=='PROVISIONAL' and result['summary']['areas']==1
    assert result['areas']['features'][0]['properties']['small_area_status'] is None
    geo.cells=[{'name':n,'source_id':str(i),'geometry':box(CX+x1,CY-100,CX+x2,CY+100)}
               for i,(n,x1,x2) in enumerate([('West',-100,0),('Park',0,600),('East',600,1000)])]
    park['geometry']=geo.cells[1]['geometry']
    remote=sample_dataset([(1,-20,0,'Exact address','')]+[(i,620,0,'Exact address','') for i in range(2,122)])
    result=plan(remote,geo,target=600)
    assert result['summary']['areas']==2
    assert result['areas']['features'][0]['properties']['small_area_status']=='IMPORTANT_BOUNDARY'


def test_small_pocket_can_join_larger_neighbour_above_the_soft_preference():
    geo=SmallGeography()
    data=sample_dataset([(1,-20,0,'Exact address','')]+[(i,20,0,'Exact address','') for i in range(2,1502)])
    result=plan(data,geo,target=600)
    assert result['status']=='PROVISIONAL',result['findings']
    assert result['summary']['areas']==1 and result['summary']['largest']==1501
    assert result['settings']['larger_areas_require_review']
    assert result['summary']['target_met'] is False
    assert result['validation']['split_protected_groups']==0
    assert any(f['code']=='ABOVE_TARGET' and 'Larger planning exception' in f['message'] for f in result['findings'])


def test_export_cache_identity_keeps_input_order_access_and_column_mapping():
    body='1,1 TEST ST,Other,49.85,-97.2,MONDAY,alley,curbside\n2,2 TEST ST,Other2,49.851,-97.201,MONDAY,alley,curbside'
    payload=csv_data(body,'AddressId,Address,OtherAddress,Latitude,Longitude,Day,CollectionAccess,OtherAccess')
    first=parse_upload(payload,'upload.csv')
    mapped=parse_upload(payload,'upload.csv',mapping={'address':'OtherAddress','access':'OtherAccess'})
    assert first.digest!=mapped.digest
    identity=first.digest;first.rows.reverse()
    assert first.digest!=identity


def test_a_park_outline_cannot_break_an_ordinary_street_frontage():
    park={'id':'park','category':'park','rank':3,'geometry':box(CX-10,CY-100,CX+10,CY+100)}
    road={'id':'road','name':'TEST ST','type':'STREET','geometry':LineString([(CX-100,CY),(CX+100,CY)])}
    pieces=segment_roads_at_barriers([road],[park])
    assert len(pieces)==1 and sum(r['geometry'].length for r in pieces)==pytest.approx(200)
    geo=SmallGeography();geo.roads=pieces;geo.road_tree=STRtree([r['geometry'] for r in pieces])
    geo.cells=[{'name':n,'source_id':str(i),'geometry':box(CX+x1,CY-100,CX+x2,CY+100)}
               for i,(n,x1,x2) in enumerate([('West',-100,-10),('Park',-10,10),('East',10,100)])]
    geo.nearby_features=lambda g,c:[park] if 'park' in c and g.intersects(park['geometry']) else []
    data=sample_dataset([(1,-20,-15,'Exact address',''),(2,-20,15,'Exact address',''),
                         (3,20,-15,'Exact address',''),(4,20,15,'Exact address','')])
    result=plan(data,geo,target=900,tolerance=12)
    assert result['status']=='PROVISIONAL',result['findings']
    assert sorted(f['properties']['addresses'] for f in result['areas']['features'])==[4]
    owners={p['id']:p['section'] for p in result['points']}
    assert len(set(owners.values()))==1


def test_under_100_point_touching_pocket_can_share_a_nearby_address_list():
    geo=SmallGeography()
    geo.cells=[{'name':'Small','source_id':'1','geometry':box(CX-100,CY-100,CX,CY)},
               {'name':'Large','source_id':'2','geometry':box(CX,CY,CX+100,CY+100)}]
    data=sample_dataset([(1,-50,-50,'Exact address','')]+[(i,50,50,'Exact address','') for i in range(2,122)])
    result=plan(data,geo,target=900,tolerance=12)
    assert result['status']=='PROVISIONAL',result['findings']
    assert result['summary']['areas']==1
    assert result['areas']['features'][0]['properties']['nearby_small_area_group']


def test_wide_road_support_stops_at_its_finite_span_with_reference_offset():
    road={'id':'road','name':'Test St','type':'STREET','geometry':LineString([(CX-100,CY),(CX+100,CY)])}
    wide={'id':'wide','name':'Test Street','category':'wide_road','rank':3,'geometry':LineString([(CX-20,CY+3),(CX+20,CY+3)])}
    pieces=segment_roads_at_barriers([road],[wide])
    assert len(pieces)==3 and sum(p['geometry'].length for p in pieces)==pytest.approx(200)
    assert pieces[1]['geometry'].within(wide['geometry'].buffer(8.001))


def test_explicit_whole_site_connectivity_can_take_real_block_across_park_edge():
    geo=SmallGeography()
    geo.cells=[{'name':name,'source_id':str(i),'geometry':box(CX+x1,CY-100,CX+x2,CY+100)}
               for i,(name,x1,x2) in enumerate([('West',-100,-10),('Middle',-10,10),('East',10,100)])]
    park={'id':'park','category':'park','rank':3,'geometry':geo.cells[1]['geometry']}
    geo.nearby_features=lambda g,c:[park] if 'park' in c and g.intersects(park['geometry']) else []
    data=sample_dataset([(1,-50,0,'Exact address','linked'),(2,50,0,'Exact address','linked'),(3,0,0,'Exact address','')])
    result=plan(data,geo,target=900,tolerance=12)
    assert result['status']=='PROVISIONAL',result['findings']
    assert result['summary']['areas']==1 and result['validation']['split_protected_groups']==0
    assert result['merge_reasons']['park/land-use edge yields to whole-group connectivity']


def test_nearby_rule_checks_all_pieces_of_small_and_larger_address_lists():
    geo=SmallGeography()
    geo.cells=[{'name':str(i),'source_id':str(i),'geometry':box(CX+x,CY-50,CX+x+100,CY+50)}
               for i,x in enumerate((-300,-150,0,150))]
    data=sample_dataset([(1,-250,0,'Exact address','same-site'),(2,-100,0,'Exact address','same-site')]
                        +[(i,50,0,'Exact address','') for i in range(3,123)]
                        +[(i,200,0,'Exact address','') for i in range(123,143)])
    result=plan(data,geo,target=900,tolerance=12)
    assert result['status']=='PROVISIONAL',result['findings']
    assert result['summary']['addresses']==142 and result['summary']['areas']==1
    p=result['areas']['features'][0]['properties']
    assert p['nearby_small_area_group'] and p['components']==4
    assert len(p['nearby_merge_links'])==3
    assert all(link['smaller_addresses']<100 and link['distance_m']<=500 for link in p['nearby_merge_links'])
    assert result['validation']['split_protected_groups']==0


@pytest.mark.parametrize('west_count',[2,120])
def test_a_railway_can_become_a_complete_divider_only_after_a_weak_seam_join(west_count):
    geo=SmallGeography()
    geo.cells=[{'name':'Same City area','source_id':'1','geometry':box(CX-100,CY+y,CX+100,CY+y+100)} for y in (-100,0)]
    # Exact source endpoints also need to meet after the shared 1 cm model is
    # applied; native floating-point intersections must not open a false slit.
    rail={'id':'rail','category':'railway','rank':1,'geometry':LineString([(CX,CY-100),(CX,CY+100)])}
    geo.nearby_features=lambda g,c:[rail] if 'railway' in c and g.intersects(rail['geometry']) else []
    data=sample_dataset([(i,-20,-50,'Exact address','') for i in range(west_count)]
                        +[(i,20,50,'Exact address','') for i in range(west_count,west_count+120)])
    result=plan(data,geo,target=900,tolerance=12)
    assert result['status']=='PROVISIONAL',result['findings']
    assert result['summary']['areas']==2
    assert result['validation']['railway_separation_preserved']
    if west_count<100:assert result['merge_reasons']['railway separation veto']>0
    else:assert result['range_balancing']['rejections']['important physical divider']>0
    if west_count<100:assert result['areas']['features'][0]['properties']['small_area_status']=='IMPORTANT_BOUNDARY'


def test_range_score_rewards_useful_sections_and_discourages_fragmentation():
    from partition_app.balancing import count_cost
    assert count_cost(650,900,1200)<2*count_cost(300,900,1200)
    assert 2*count_cost(650,900,1200)<count_cost(1300,900,1200)
    assert count_cost(950,900,1200)<count_cost(650,900,1200)<count_cost(300,900,1200)


def continuity_geography(roads=(),features=(),hoods=()):
    from types import SimpleNamespace
    return SimpleNamespace(roads=list(roads),base_roads=list(roads),features=list(features),neighbourhoods=list(hoods),
        nearby_features=lambda g,c:[f for f in features if f['category'] in c and f['geometry'].intersects(g)])


def test_street_and_opposite_alley_splits_receive_the_same_heavy_penalty():
    from partition_app.continuity import assess,BREAK_PENALTY
    points=[Point(-20,0),Point(20,0)];owners={0:0,1:1};cut=LineString([(0,-100),(0,100)])
    road={'id':'road','name':'Example St','geometry':LineString([(-100,0),(100,0)])}
    street=assess(cut,owners,points,{('ordinary segment','road'):[0,1]},continuity_geography([road]))
    alley={'id':'alley','category':'alley','geometry':cut}
    rear=assess(cut,owners,points,{},continuity_geography(features=[alley]))
    assert len(street['street_breaks'])==len(rear['alley_side_splits'])==1
    assert street['penalty']==rear['penalty']>=BREAK_PENALTY
    assert rear['penalty']>100*2
    together=assess(cut,{0:0,1:0},points,{},continuity_geography(features=[alley]))
    assert not together['alley_side_splits']
    transverse=assess(LineString([(-100,0),(100,0)]),owners,points,{},continuity_geography(features=[alley]))
    assert not transverse['alley_side_splits'],'Crossing an alley is different from assigning its opposite sides separately'


def test_a_supporting_park_edge_can_explain_a_street_run_break():
    from partition_app.continuity import assess
    cut=LineString([(0,-100),(0,100)])
    road={'id':'road','name':'Example St','geometry':LineString([(-100,0),(100,0)])}
    park={'id':'park','category':'park','geometry':box(0,-100,10,100)}
    result=assess(cut,{0:0,1:1},[Point(-20,0),Point(20,0)],{('ordinary segment','road'):[0,1]},continuity_geography([road],[park]))
    assert not result['street_breaks']


@pytest.mark.parametrize('follows_road',[True,False])
def test_intersection_boundary_is_valid_but_mid_block_cut_is_not(follows_road):
    from partition_app.continuity import assess,BREAK_PENALTY
    through={'id':'residential','name':'Residential St','geometry':LineString([(-150,0),(150,0)])}
    boundary={'id':'cross-street','name':'Cross Avenue','geometry':LineString([(0,-150),(0,150)])}
    # Shift the same boundary into the residential block, between homes.
    x=0 if follows_road else 60
    cut=LineString([(x,-100),(x,100)])
    points=[Point(x-20,0),Point(x+20,0)]
    q=assess(cut,{0:0,1:1},points,{('ordinary segment','residential'):[0,1]},continuity_geography([through,boundary]))
    assert len(q['street_breaks'])==(0 if follows_road else 1)
    assert len(q['road_following_intersections'])==(1 if follows_road else 0)
    assert (q['penalty']>=BREAK_PENALTY) is (not follows_road)


def test_posted_speed_boundary_evidence_is_numeric_and_unit_aware():
    from partition_app.geography import posted_speed_kmh,road_evidence
    assert posted_speed_kmh({'maxspeed':'signals'}) is None
    assert posted_speed_kmh({'maxspeed':'60 km/h'})==60
    assert posted_speed_kmh({'maxspeed':'40 mph'})>60
    assert posted_speed_kmh({'maxspeed:forward':'50','maxspeed:backward':'70'})==70
    assert road_evidence({'highway':'residential','maxspeed':'70'})=='Mapped posted speed above 60 km/h'
    assert road_evidence({'highway':'residential','maxspeed':'60'}) is None


def test_long_neighbourhood_seam_has_a_shape_cost_not_a_street_cut_violation():
    from partition_app.continuity import neighbourhood_division_cost,BREAK_PENALTY
    footprint=box(0,0,1000,1000)
    long=LineString([(0,200),(800,200),(800,800),(0,800),(0,900),(1000,900)])
    short=LineString([(0,500),(500,500),(500,1000)])
    assert neighbourhood_division_cost(long,footprint)>neighbourhood_division_cost(short,footprint)+5
    assert neighbourhood_division_cost(long,footprint)<BREAK_PENALTY


def test_continuous_broad_candidate_does_not_require_municipal_alignment():
    from partition_app.continuity import improve
    road={'id':'city-road','name':'Example Boulevard','geometry':LineString([(0,-500),(0,500)])}
    alley={'id':'rear-lane','category':'alley','geometry':LineString([(20,-200),(20,200)])}
    broad={**road,'category':'wide_road'}
    geo=continuity_geography([road],[alley,broad],[])
    points=[Point(-20,0)]*1000+[Point(40,0)]*1000
    regions=[{'geometry':box(-200,-200,20,200),'members':set(range(1000)),'parents':{'natural'},'boundaries':[],'links':[],'last_resort':True},
             {'geometry':box(20,-200,200,200),'members':set(range(1000,2000)),'parents':{'natural'},'boundaries':[],'links':[],'last_resort':True}]
    _,audit=improve(regions,points,{}, {},geo,900,1100,[],{},lambda *_:None)
    assert audit['changes'] and audit['changes'][0]['municipal_alignment']==0
    assert audit['changes'][0]['quality_before']['alley_side_splits']
    assert not audit['changes'][0]['quality_after']['alley_side_splits']


def test_local_opposite_alley_splits_cannot_cancel_out_along_a_long_lane():
    from partition_app.continuity import assess,BREAK_PENALTY
    alley={'id':'long-lane','category':'alley','geometry':LineString([(0,-300),(0,300)])}
    # At the serviced boundary the west/east houses differ. Beyond that
    # boundary their ownership reverses, so aggregate side sets both equal
    # {0,1}; that must not hide the local opposing-pickup split.
    points=[Point(-20,0),Point(20,0),Point(-20,250),Point(20,250)]
    q=assess(LineString([(0,-100),(0,100)]),{0:0,1:1,2:1,3:0},points,{},continuity_geography(features=[alley]))
    assert len(q['alley_side_splits'])==1 and q['penalty']>=BREAK_PENALTY


@pytest.mark.parametrize('site_protected',[False,True])
def test_continuous_city_division_replaces_an_alley_seam_but_never_splits_a_site(site_protected):
    from partition_app.continuity import improve
    road={'id':'city-road','name':'A generically named street','geometry':LineString([(0,-500),(0,500)])}
    alley={'id':'rear-lane','category':'alley','geometry':LineString([(20,-200),(20,200)])}
    geo=continuity_geography([road],[alley],[{'geometry':box(-200,-200,0,200)},{'geometry':box(0,-200,200,200)}])
    points=[Point(-20,0) for _ in range(1000)]+[Point(40,0) for _ in range(1000)]
    regions=[{'geometry':box(-200,-200,20,200),'members':set(range(1000)),'parents':{'natural'},'boundaries':[],'links':[],'last_resort':True},
             {'geometry':box(20,-200,200,200),'members':set(range(1000,2000)),'parents':{'natural'},'boundaries':[],'links':[],'last_resort':True}]
    groups={('ordinary segment','city-road'):list(range(2000))}
    if site_protected:groups[('site','campus')]=list(range(2000))
    ledger=[];evidence={}
    after,audit=improve(regions,points,groups,{},geo,900,1100,ledger,evidence,lambda *_:None)
    assert bool(audit['changes']) is not site_protected
    if not site_protected:
        assert len(audit['changes'])==1,'A chosen continuous seam must not be selected repeatedly'
        assert all(len(r['members'])==1000 for r in after)
        assert audit['changes'][0]['quality_before']['alley_side_splits']
        assert not audit['changes'][0]['quality_after']['alley_side_splits']
        assert ledger[0]['waived_ordinary_segments']==['city-road']
        assert after[0]['geometry'].union(after[1]['geometry']).equals(box(-200,-200,200,200))
        repeated,again=improve(after,points,groups,{},geo,900,1100,[],{},lambda *_:None)
        assert not again['changes'],'Re-evaluating the accepted seam must be stable'


@pytest.mark.parametrize('same_site',[False,True])
def test_last_resort_uses_complete_frontage_blocks_and_cannot_break_a_site(same_site):
    geo=SmallGeography()
    geo.cells=[{'name':'Town','source_id':'town','geometry':box(CX-100,CY-100,CX+100,CY+100)}]
    blocks=[{'name':'Town','source_id':str(j),'frontage_refined':True,
             'geometry':box(CX-100+j*50,CY-100,CX-50+j*50,CY+100)} for j in range(4)]
    # A tiny, real zero-demand face still needs an owner even though its shared
    # edge is below the old 10 cm adjacency threshold. Never discard its land.
    empty=box(CX+99.99,CY+99.99,CX+100,CY+100)
    blocks[-1]['geometry']=blocks[-1]['geometry'].difference(empty)
    blocks.append({'name':'Town','source_id':'empty','geometry':empty})
    geo.refine_frontage_cells=lambda *args:(blocks,[],{})
    data=sample_dataset([(i,-75+(i//500)*50,0,'Exact address','campus' if same_site else '') for i in range(2000)])
    result=plan(data,geo,minimum=900,maximum=1100)
    assert result['status']=='PROVISIONAL',result['findings']
    assert result['validation']['split_protected_groups']==0
    assert result['validation']['material_parcel_cuts']==0
    counts=sorted(f['properties']['addresses'] for f in result['areas']['features'])
    assert counts==([2000] if same_site else [1000,1000])
    assert bool(result['validation']['last_resort_boundary_review']) is not same_site
    if not same_site:
        assert result['range_balancing']['last_resort_splits']==1
        assert all(f['properties']['last_resort_boundary_review'] for f in result['areas']['features'])


def test_last_resort_is_not_used_for_a_moderate_oversize():
    geo=SmallGeography()
    geo.cells=[{'name':'Town','source_id':'town','geometry':box(CX-100,CY-100,CX+100,CY+100)}]
    def forbidden(*args):raise AssertionError('A modest oversize must not trigger frontage regrouping')
    geo.refine_frontage_cells=forbidden
    result=plan(sample_dataset([(i,-20,0,'Exact address','') for i in range(1500)]),geo,minimum=900,maximum=1100)
    assert result['status']=='PROVISIONAL' and result['summary']['areas']==1
    assert not result['validation']['last_resort_boundary_review']


def test_one_park_can_complete_a_road_without_cutting_at_unrelated_park_edges():
    geo=SmallGeography()
    geo.cells=[{'name':'Town','source_id':'town','geometry':box(CX-100,CY-100,CX+100,CY+100)}]
    road={'id':'finite-road','name':'Example broad road','category':'broad_corridor','rank':4,
        'geometry':LineString([(CX,CY-200),(CX,CY)])}
    park={'id':'connecting-park','name':'Connecting park','category':'park','rank':3,
        'geometry':box(CX-10,CY,CX+10,CY+200)}
    unrelated={'id':'unrelated-park','name':'Unrelated park','category':'park','rank':3,
        'geometry':box(CX+10,CY-2,CX+100,CY+2)}
    geo.features=[road,park,unrelated]
    geo.nearby_features=lambda g,c:[f for f in geo.features if f['category'] in c and g.intersects(f['geometry'])]
    data=sample_dataset([(i,-40 if i<650 else 40,-30 if i%2 else 30,'Exact address','east-site' if i>=650 else '') for i in range(1300)])
    result=plan(data,geo,minimum=900,maximum=1200)
    assert result['status']=='PROVISIONAL',result['findings']
    assert sorted(f['properties']['addresses'] for f in result['areas']['features'])==[650,650]
    assert result['validation']['split_protected_groups']==0
    chosen=[f for f in result['boundary_candidates'] if f.get('chosen_for_split')]
    assert any(set(f['source_ids'])=={'finite-road','connecting-park'} for f in chosen)


def test_an_undersized_natural_area_does_not_overload_a_satisfactory_neighbour():
    geo=SmallGeography()
    data=sample_dataset([(i,-20,0,'Exact address','') for i in range(330)]
                        +[(i,20,0,'Exact address','') for i in range(330,1280)])
    natural=plan(data,geo)
    result=plan(data,geo,minimum=900,maximum=1200)
    assert result['summary']['natural_areas']==natural['summary']['areas']==2
    assert sorted(f['properties']['addresses'] for f in result['areas']['features'])==[330,950]
    assert result['range_balancing']['rejections']['satisfactory neighbour would leave range']>0


def test_two_small_natural_areas_combine_instead_of_remaining_tiny():
    geo=SmallGeography()
    data=sample_dataset([(i,-20 if i<300 else 20,0,'Exact address','') for i in range(600)])
    result=plan(data,geo,minimum=900,maximum=1200)
    assert result['summary']['natural_areas']==2
    assert result['summary']['areas']==1 and result['summary']['largest']==600


def test_a_tiny_pocket_prefers_local_neighbour_over_closer_urban_highway_crossing():
    geo=SmallGeography()
    geo.cells=[{'name':name,'source_id':str(i),'geometry':box(CX+x1,CY-100,CX+x2,CY+100)}
               for i,(name,x1,x2) in enumerate([('Local',-100,0),('Pocket',0,10),('Across highway',10,100)])]
    road={'id':'primary-road','name':'Example arterial','category':'wide_road','rank':3,
          'tags':{'highway':'primary','lanes':'4','maxspeed':'50'},'geometry':LineString([(CX+10,CY-200),(CX+10,CY+200)])}
    geo.features=[road];geo.nearby_features=lambda g,c:[road] if 'wide_road' in c and g.intersects(road['geometry']) else []
    data=sample_dataset([(i,-80,0,'Exact address','') for i in range(1000)]
                        +[(i,5,0,'Exact address','') for i in range(1000,1050)]
                        +[(i,50,0,'Exact address','') for i in range(1050,2250)])
    result=plan(data,geo)
    owners={v['id']:v['section'] for v in result['points']}
    assert owners['1000']==owners['0'] and owners['1000']!=owners['1050']


@pytest.mark.parametrize('ordinary_frontage',[False,True])
def test_municipal_divide_can_follow_a_road_without_a_label_based_veto(ordinary_frontage):
    geo=SmallGeography(road=ordinary_frontage)
    geo.cells=[{'name':'Town','source_id':'1','geometry':box(CX-100,CY-100,CX+100,CY+100)}]
    division={'id':'official-division','name':'Official division','category':'community','rank':2,
              'geometry':LineString([(CX,CY-200),(CX,CY+200)])}
    geo.nearby_features=lambda g,c:[division] if 'community' in c and g.intersects(division['geometry']) else []
    data=sample_dataset([(i,-20 if i<650 else 20,0,'Exact address','') for i in range(1300)])
    result=plan(data,geo,minimum=900,maximum=1200)
    assert result['summary']['natural_areas']==1
    assert result['status']=='PROVISIONAL',result['findings']
    assert sorted(f['properties']['addresses'] for f in result['areas']['features'])==[650,650]
    assert result['validation']['split_protected_groups']==0
    assert result['range_balancing']['ordinary_or_alley_dividers']==0


def test_municipal_line_still_cannot_cut_across_an_ordinary_frontage():
    geo=SmallGeography(road=True)
    geo.cells=[{'name':'Town','source_id':'1','geometry':box(CX-100,CY-100,CX+100,CY+100)}]
    division={'id':'official','name':'Official','category':'community','rank':2,
              'geometry':LineString([(CX-200,CY),(CX+200,CY)])}
    geo.nearby_features=lambda g,c:[division] if 'community' in c and g.intersects(division['geometry']) else []
    # The points lie along one side of the vertical street; the municipal
    # line crosses between them, not along the road.
    data=sample_dataset([(i,-20,-20 if i<650 else 20,'Exact address','') for i in range(1300)])
    result=plan(data,geo,minimum=900,maximum=1200)
    assert [f['properties']['addresses'] for f in result['areas']['features']]==[1300]
    assert result['validation']['split_protected_groups']==0


@pytest.mark.parametrize('touches',[True,False])
def test_connected_corridor_may_end_at_boundary_but_cannot_extend_a_dead_end(touches):
    from partition_app.continuity import composite_corridors
    top=500 if touches else 480
    streets=[{'id':'a','name':'Vertical','key':'vertical','road_ids':['a'],
              'geometry':LineString([(0,0),(0,top)])},
             {'id':'b','name':'Horizontal','key':'horizontal','road_ids':['b'],
              'geometry':LineString([(0,0),(600,0)])}]
    parent=box(-500,-500,500,500)
    candidates=composite_corridors(streets,parent)
    assert bool(candidates) is touches
    if touches:
        parts=subdivide(parent,[candidates[0]['geometry']])
        assert sorted(p.area for p in parts)==[250000,750000]
        assert parts[0].intersection(parts[1]).area==0


def test_longitudinal_exception_preserves_other_members_of_same_street():
    from partition_app.continuity import split_frontage_buckets
    groups={('ordinary segment','road'):[0,1,2,3,4,5],('site','shared'):[2,3]}
    split_frontage_buckets(groups,{('ordinary segment','road')},{0:0,1:0,2:1,3:1})
    assert sorted(sorted(v) for k,v in groups.items() if k[0]=='ordinary segment')==[[0,1],[2,3],[4,5]]
    assert groups[('site','shared')]==[2,3]


def test_highway_evidence_reaches_offset_city_geometry():
    from partition_app.geography import major_speed_boundary
    assert major_speed_boundary({'highway':'primary','maxspeed':'60 km/h'})
    assert major_speed_boundary({'highway':'residential','maxspeed':'70'})
    assert not major_speed_boundary({'highway':'residential','maxspeed':'60'})
    assert not major_speed_boundary({'highway':'primary'})
    # The two source datasets differ by 15 m: still the same finite highway,
    # not permission to extrapolate or join an unrelated street.
    mapped={'id':'highway','name':'Generic Highway','category':'controlled_road',
        'tags':{'highway':'trunk','maxspeed':'60'},'geometry':LineString([(0,15),(200,15)])}
    city={'id':'city','name':'Generic Highway','type':'STREET','geometry':LineString([(0,0),(200,0)])}
    promoted=promote_divided_roads([mapped],[city])
    assert len(promoted)==1 and promoted[0]['category']=='controlled_road'
    assert promoted[0]['geometry'].equals(city['geometry'])


def test_final_quality_includes_natural_edges_and_not_only_last_repaired_edge():
    from partition_app.continuity import audit_boundaries,BREAK_PENALTY
    alley={'id':'lane','category':'alley','geometry':LineString([(0,-100),(0,100)])}
    geo=continuity_geography(features=[alley])
    regions=[{'geometry':box(-100,-100,0,100),'members':{0},'parents':{'left'},'boundary_quality':{'penalty':0}},
             {'geometry':box(0,-100,100,100),'members':{1},'parents':{'right'}}]
    problems=audit_boundaries(regions,[Point(-20,0),Point(20,0)],{},geo)
    assert len(problems)==1 and problems[0]['alley_side_splits']
    assert all(r['boundary_quality']['penalty']>=BREAK_PENALTY for r in regions)
    assert all(r['boundary_quality']['shared_edges_checked']==1 for r in regions)


def test_perfect_counts_do_not_pay_for_an_opposing_alley_split():
    geo=SmallGeography()
    geo.cells=[{'name':'Town','source_id':'town','geometry':box(CX-100,CY-100,CX+100,CY+100)}]
    blocks=[{'name':'Town','source_id':str(j),'frontage_refined':True,
        'geometry':box(CX-100+j*50,CY-100,CX-50+j*50,CY+100)} for j in range(4)]
    geo.refine_frontage_cells=lambda *args:(blocks,[],{})
    lane={'id':'rear-lane','name':'Lane','category':'alley','rank':7,
        'geometry':LineString([(CX,CY-100),(CX,CY+100)])}
    geo.features=[lane]
    geo.nearby_features=lambda g,c:[lane] if 'alley' in c and g.intersects(lane['geometry']) else []
    data=sample_dataset([(i,-75+(i//500)*50,0,'Exact address','') for i in range(2000)])
    result=plan(data,geo,minimum=900,maximum=1100)
    # Count-only scoring prefers 1,000/1,000. The same quality evaluator used
    # for ordinary candidates must reject that fallback's opposing lane split.
    assert [f['properties']['addresses'] for f in result['areas']['features']]==[2000]
    attempts=result['range_balancing']['frontage_attempts']
    assert attempts[0]['boundary_quality']['alley_side_splits']
    assert attempts[0]['reason']=='Street/alley quality outweighs count benefit'


def test_following_the_same_noded_street_is_not_a_mid_block_cut():
    from partition_app.continuity import assess
    # Several collinear input pieces and a slight source offset reproduce the
    # overlay vertices that used to look like cuts across the very same road.
    road={'id':'road','name':'Ordinary Street','geometry':LineString([(0,-200),(0,-50),(0,50),(0,200)])}
    seam=LineString([(0,-200),(.005,-50),(0,50),(0,200)])
    points=[Point(-20,-60),Point(20,-40),Point(-20,40),Point(20,60)]
    q=assess(seam,{0:0,1:1,2:0,3:1},points,{('ordinary segment','road'):[0,1,2,3]},continuity_geography([road]))
    assert not q['street_breaks'] and q['penalty']==0


def test_corner_contacts_do_not_become_shared_boundary_segments():
    from shapely.geometry import MultiPolygon
    from partition_app.geography import shared_boundary
    left=box(0,0,10,10)
    right=MultiPolygon([box(10,2,20,8),box(10,10,20,20)])
    shared=shared_boundary(left,right)
    assert shared.equals(LineString([(10,2),(10,8)]))
    assert shared.intersection(box(9,3,11,7),grid_size=0).length==4
    assert shared.distance(Point(10,10))==2


@pytest.mark.parametrize('left,right,expected',[(87,863,[950]),(585,2989,[585,2989])])
def test_derived_natural_corridors_do_not_create_tiny_remnants(left,right,expected):
    geo=SmallGeography()
    geo.cells=[{'name':'Town','source_id':'1','geometry':box(CX-100,CY-100,CX+100,CY+100)}]
    corridor={'id':'supported-corridor','name':'Example arterial','category':'municipal_corridor','rank':3,
        'municipal_alignment':.8,'geometry':LineString([(CX,CY-200),(CX,CY+200)])}
    geo.features=[corridor]
    geo.nearby_features=lambda g,c:[corridor] if 'municipal_corridor' in c and g.intersects(corridor['geometry']) else []
    data=sample_dataset([(i,-20 if i<left else 20,0,'Exact address','') for i in range(left+right)])
    result=plan(data,geo)
    assert result['status']=='PROVISIONAL',result['findings']
    assert sorted(f['properties']['addresses'] for f in result['areas']['features'])==expected
    assert result['validation']['split_protected_groups']==0


def test_one_address_can_join_nearby_thirty_without_a_hundred_address_partner():
    geo=SmallGeography()
    geo.cells=[{'name':'Pocket','source_id':'1','geometry':box(CX-100,CY-100,CX-20,CY+100)},
               {'name':'Neighbour','source_id':'2','geometry':box(CX+80,CY-100,CX+250,CY+100)}]
    data=sample_dataset([(1,-50,0,'Exact address','')]+[(i,150,0,'Exact address','') for i in range(2,32)])
    result=plan(data,geo,target=900,tolerance=12)
    assert result['status']=='PROVISIONAL',result['findings']
    assert result['summary']['areas']==1 and result['summary']['addresses']==31
    p=result['areas']['features'][0]['properties']
    assert p['nearby_small_area_group'] and p['nearby_merge_links'][0]['larger_addresses']==30


@pytest.mark.parametrize('opposite_banks',[False,True])
def test_nearby_corner_probe_distinguishes_an_external_railway_from_a_crossing(opposite_banks):
    from partition_app.engine import nearby_gap_connector
    from shapely.geometry import Polygon
    # Both northern triangles touch at a railway corner. The first triangle
    # moves south only in the opposite-bank case; their areas remain real.
    south=-100 if opposite_banks else 100
    a=Polygon([(CX,CY),(CX-100,CY+south),(CX,CY+south)])
    b=Polygon([(CX,CY),(CX,CY+100),(CX+100,CY+100)])
    rail=LineString([(CX-200,CY),(CX+200,CY)])
    probe=nearby_gap_connector(a,b)
    assert probe.length>0
    assert probe.intersects(rail)==opposite_banks
    assert probe.coords[0]!=probe.coords[-1]
    geo=SmallGeography()
    geo.cells=[{'name':'Pocket','source_id':'1','geometry':a},
               {'name':'Neighbour','source_id':'2','geometry':b}]
    feature={'id':'rail','category':'railway','rank':1,'geometry':rail}
    geo.nearby_features=lambda g,c:[feature] if 'railway' in c and g.intersects(rail) else []
    data=sample_dataset([(1,-10,south*.5,'Exact address','')]
                        +[(i,10,50,'Exact address','') for i in range(2,32)])
    result=plan(data,geo,target=900,tolerance=12)
    assert result['status']=='PROVISIONAL',result['findings']
    assert result['summary']['areas']==(2 if opposite_banks else 1)


@pytest.mark.parametrize('crossing',[False,True])
def test_nearby_connections_check_service_anchors_after_an_external_road_corner(crossing):
    from partition_app.engine import nearby_gap_connector
    geo=SmallGeography()
    a=box(CX-100,CY-100,CX-20,CY+100);b=box(CX+80,CY-100,CX+250,CY+100)
    y=nearby_gap_connector(a,b).coords[0][1]
    road=LineString([(CX+30,CY-200),(CX+30,CY+200)]) if crossing else LineString([(CX-30,y),(CX+90,y)])
    feature={'id':'wide','category':'wide_road','rank':3,'geometry':road}
    geo.cells=[{'name':'Pocket','source_id':'1','geometry':a},{'name':'Neighbour','source_id':'2','geometry':b}]
    geo.nearby_features=lambda g,c:[feature] if 'wide_road' in c and g.intersects(road) else []
    data=sample_dataset([(1,-50,0,'Exact address','')]+[(i,150,0,'Exact address','') for i in range(2,32)])
    result=plan(data,geo,target=900,tolerance=12)
    assert result['status']=='PROVISIONAL',result['findings']
    assert result['summary']['areas']==(2 if crossing else 1)
    if not crossing:
        link=result['areas']['features'][0]['properties']['nearby_merge_links'][0]
        assert link['probe_length_m']==pytest.approx(200)
