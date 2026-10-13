import io
import json

import pytest

from type_evidence.cli import parser, run
from type_evidence.mcp import call, serve, _LazyCatalog


def test_directory_cli_mcp_parity_without_local_catalog(tmp_path):
    args = ['--catalog',str(tmp_path / 'absent.sqlite'),'directory','--query','Inter','--limit','4']
    cli = run(parser().parse_args(args))
    mcp = call(None,tmp_path,'font_directory',{'query':'Inter','limit':4})
    assert cli == mcp
    assert cli['results']
    first = cli['results'][0]
    assert first['id'].startswith('directory:')
    assert first['renderable'] is False
    assert run(parser().parse_args(['directory','--id',first['id']])) == call(None,tmp_path,'font_directory_detail',{'id':first['id']})


def test_mcp_starts_and_recovers_before_catalog_creation(tmp_path):
    requests = [
        {'jsonrpc':'2.0','id':1,'method':'initialize','params':{}},
        {'jsonrpc':'2.0','method':'notifications/initialized'},
        {'jsonrpc':'2.0','id':2,'method':'tools/list'},
        {'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'font_stats'}},
        {'jsonrpc':'2.0','id':4,'method':'tools/call','params':{'name':'font_directory','arguments':{'query':'Inter','limit':2}}},
        {'jsonrpc':'2.0','id':5,'method':'tools/call','params':{'name':'font_packs'}},
    ]
    output = io.StringIO()
    serve(tmp_path / 'missing.sqlite', tmp_path / 'out', io.StringIO('\n'.join(map(json.dumps,requests))), output)
    responses = {r['id']:r for r in map(json.loads,output.getvalue().splitlines())}
    assert responses[1]['result']['serverInfo']['version'] == '0.3.0'
    assert responses[3]['result']['isError'] is True
    assert 'Catalog not found' in responses[3]['result']['content'][0]['text']
    assert responses[4]['result']['isError'] is False
    assert responses[5]['result']['isError'] is False
    assert not (tmp_path / 'missing.sqlite').exists()


def test_lazy_catalog_retries_after_user_creates_catalog(tmp_path):
    from test_catalog import build
    proxy = _LazyCatalog(tmp_path / 'catalog.sqlite')
    with pytest.raises(ValueError, match='Catalog not found'):
        proxy.stats()
    build(tmp_path)
    assert proxy.stats()['faces'] == 1
    proxy.close()


def test_directory_parameter_errors_are_bounded(tmp_path):
    for args in [{'limit':True}, {'limit':101}, {'offset':-1}, {'surprise':True}]:
        with pytest.raises(ValueError):
            call(None,tmp_path,'font_directory',args)


def test_connected_mcp_observes_catalog_rebuild_between_requests(tmp_path):
    from test_catalog import build, make_font
    from type_evidence.catalog import index_sources
    source, path, _ = build(tmp_path)
    def requests():
        yield json.dumps({'jsonrpc':'2.0','id':1,'method':'initialize','params':{}})
        yield json.dumps({'jsonrpc':'2.0','method':'notifications/initialized'})
        yield json.dumps({'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':'font_stats'}})
        make_font(source / 'new.ttf', family='Newly Acquired')
        index_sources([{'id':'fixture','root':str(source)}], path, workers=1)
        yield json.dumps({'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'font_stats'}})
        yield json.dumps({'jsonrpc':'2.0','id':4,'method':'tools/call','params':{'name':'font_search','arguments':{'family':'Newly Acquired','text':'abc','visual':'off'}}})
    output = io.StringIO()
    serve(path,tmp_path / 'previews',requests(),output)
    replies = {r['id']:r['result'] for r in map(json.loads,output.getvalue().splitlines())}
    assert json.loads(replies[2]['content'][0]['text'])['faces'] == 1
    assert json.loads(replies[3]['content'][0]['text'])['faces'] == 2
    assert json.loads(replies[4]['content'][0]['text'])['candidates'][0]['family'] == 'Newly Acquired'
