import importlib.util
from pathlib import Path
import zipfile

import pytest

spec=importlib.util.spec_from_file_location('bundle',Path(__file__).parents[1]/'scripts/review_bundle.py')
bundle=importlib.util.module_from_spec(spec); spec.loader.exec_module(bundle)


def test_review_excludes_library_and_verifies_content(tmp_path):
    root=tmp_path/'repo'; root.mkdir()
    (root/'README.md').write_text('Example review')
    (root/'library').mkdir(); (root/'library/font.ttf').write_bytes(b'\0\1\0\0binary')
    (root/'type_evidence').mkdir(); (root/'type_evidence/main.py').write_text('print(1)\n')
    result=bundle.build(root,tmp_path/'review.zip')
    assert result['manifest_files_verified']==2
    with zipfile.ZipFile(tmp_path/'review.zip') as z:
        assert not any('library' in name for name in z.namelist())


def test_disguised_font_and_symlink_refused(tmp_path):
    (tmp_path/'README.md').write_bytes(b'OTTOdisguised')
    with pytest.raises(ValueError,match='Font'):
        bundle.build(tmp_path,tmp_path/'out.zip')
    (tmp_path/'README.md').unlink()
    (tmp_path/'README.md').symlink_to(tmp_path/'missing')
    # Broken root-file links are outside the ordinary exists() list; directory
    # links inside an included evidence tree are always refused.
    (tmp_path/'evidence').mkdir(); (tmp_path/'evidence/link.md').symlink_to(tmp_path/'missing')
    with pytest.raises(ValueError,match='Symlink'):
        bundle.build(tmp_path,tmp_path/'out.zip')


def test_review_keeps_license_contribution_guide_and_static_site(tmp_path):
    root = tmp_path / 'repo'
    (root / 'docs').mkdir(parents=True)
    payloads = {'LICENSE': 'MIT License\n', 'CONTRIBUTING.md': '# Contribute\n',
                'docs/.nojekyll': '', 'docs/index.html': '<h1>Type Evidence</h1>'}
    for name, body in payloads.items():
        (root / name).write_text(body, encoding='utf-8')
    result = bundle.build(root, tmp_path / 'review.zip')
    assert result['manifest_files_verified'] == len(payloads)
    with zipfile.ZipFile(tmp_path / 'review.zip') as archive:
        for name, body in payloads.items():
            assert archive.read('type-evidence/' + name) == body.encode('utf-8')
