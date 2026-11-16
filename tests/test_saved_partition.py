import json
import pytest
from partition_app import server


@pytest.mark.parametrize('status,alley,restore',[('PROVISIONAL',False,True),('FAILED',False,False),('PROVISIONAL',True,False)])
def test_upgrade_preserves_the_accepted_saved_view_and_its_actual_engine(tmp_path,monkeypatch,status,alley,restore):
    key='a'*64
    saved={'engine':'winnipeg-geography-4.5','day':'TUESDAY','status':status,'settings':{'use_mapped_alley_evidence':alley}}
    (tmp_path/'current.json').write_text(json.dumps({'key':key}))
    (tmp_path/f'{key}.result.json').write_text(json.dumps(saved))
    state={'current':None,'day':None};monkeypatch.setattr(server,'STATE',state);monkeypatch.setattr(server,'CACHE',tmp_path)
    server.restore_current()
    assert (state['current']==key)==restore
    result=server.load_result(key)
    assert result['engine']=='winnipeg-geography-4.5' and result['requires_recalculation']
    assert json.loads((tmp_path/f'{key}.result.json').read_text())==saved
