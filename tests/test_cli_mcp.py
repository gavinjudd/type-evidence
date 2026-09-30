import io
import json
import subprocess
import sys

from type_evidence.mcp import serve
from test_catalog import build


def test_mcp_initialization_discovery_and_errors(tmp_path):
    _,path,_=build(tmp_path)
    requests=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-06-18'}},
              {'jsonrpc':'2.0','method':'notifications/initialized'},
              {'jsonrpc':'2.0','id':2,'method':'tools/list'},
              {'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'font_stats','arguments':{}}},
              {'jsonrpc':'2.0','id':4,'method':'tools/call','params':{'name':'font_resolve','arguments':{'id':'not-an-id'}}},
              {'jsonrpc':'2.0','id':5,'method':'unknown'}]
    output=io.StringIO()
    serve(path,tmp_path/'renders',io.StringIO('\n'.join(json.dumps(x) for x in requests)),output)
    replies=[json.loads(x) for x in output.getvalue().splitlines()]
    assert len(replies)==5
    assert replies[0]['result']['protocolVersion']=='2025-06-18'
    assert {tool['name'] for tool in replies[1]['result']['tools']} == {'font_search','font_inspect','font_resolve','font_family','font_compare','font_compose','font_stats','font_project','font_image','font_issues','font_visual_status'}
    assert json.loads(replies[2]['result']['content'][0]['text'])['faces']==1
    assert replies[3]['result']['isError'] is True
    assert replies[4]['error']['code']==-32601


def test_cli_stats_and_missing_id(tmp_path):
    _,path,_=build(tmp_path)
    base=[sys.executable,'-m','type_evidence','--catalog',str(path)]
    result=subprocess.run(base+['stats'],capture_output=True,text=True)
    assert result.returncode==0
    assert json.loads(result.stdout)['faces']==1
    bad=subprocess.run(base+['resolve','bad'],capture_output=True,text=True)
    assert bad.returncode==2 and not bad.stdout
    assert 'error' in json.loads(bad.stderr)
