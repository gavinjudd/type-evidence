import base64
import io
import json

import pytest
from PIL import Image

from test_catalog import build
from type_evidence.catalog import Catalog
from type_evidence.cli import parser, run
from type_evidence.mcp import call, serve, _image_content


def test_cli_mcp_discovery_field_parity(tmp_path):
    _,path,_=build(tmp_path)
    arguments=['--catalog',str(path),'search','--text','abc','--query','not condensed',
               '--audience','children','--size','16','--density','comfortable','--upright','--visual','off']
    cli=run(parser().parse_args(arguments))
    cat=Catalog(path)
    mcp=call(cat,tmp_path/'preview','font_search',{'text':'abc','query':'not condensed','audience':'children',
        'size':16,'density':'comfortable','italic':False,'visual':'off'})
    assert cli==mcp
    ident=cli['candidates'][0]['id']
    assert call(cat,tmp_path/'preview','font_family',{'id':ident})['total_faces']==1
    cat.close()


def test_mcp_returns_inline_image_and_compact_evidence(tmp_path):
    _,path,_=build(tmp_path)
    cat=Catalog(path);ident=cat.all()[0]['id'];cat.close()
    requests=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{}},
              {'jsonrpc':'2.0','method':'notifications/initialized'},
              {'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':'font_compare','arguments':{'ids':[ident],'text':'abc','sizes':[16]}}}]
    output=io.StringIO()
    serve(path,tmp_path/'previews',io.StringIO('\n'.join(json.dumps(x) for x in requests)),output)
    reply=json.loads(output.getvalue().splitlines()[-1])['result']
    assert reply['isError'] is False
    text,image=reply['content']
    assert len(text['text'])<5000 and image['type']=='image' and image['mimeType']=='image/png'
    png=Image.open(io.BytesIO(base64.b64decode(image['data'])))
    assert png.width<=1440 and png.height<=1800
    data=json.loads(text['text'])
    assert 'glyphs' not in text['text'] and data['manifest_path']
    cat=Catalog(path)
    reopen=call(cat,tmp_path/'previews','font_image',{'path':data['preview_image']})
    assert reopen['original_dimensions'][0]>0
    cat.close()


def test_generated_image_cannot_escape_output_root(tmp_path):
    outside=tmp_path/'secret.png';Image.new('RGB',(10,10)).save(outside)
    root=tmp_path/'previews';root.mkdir()
    (root/'link.png').symlink_to(outside)
    for value in ('../secret.png',str(outside),'link.png'):
        with pytest.raises(ValueError): _image_content(root,value)


def test_cli_json_is_utf8_even_with_legacy_pipe_encoding(tmp_path):
    import os,subprocess,sys
    _,path,_=build(tmp_path)
    env={**os.environ,'PYTHONIOENCODING':'ascii','PYTHONUTF8':'0'}
    result=subprocess.run([sys.executable,'-m','type_evidence','--catalog',str(path),'resolve','غير موجود'],env=env,capture_output=True)
    assert result.returncode==2
    data=json.loads(result.stderr.decode('utf-8'))
    assert 'غير موجود' in data['error']
