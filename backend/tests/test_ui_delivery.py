"""The SPA entry must select the current build after a normal navigation."""
import pytest
from agentscope_app import main

@pytest.mark.parametrize('route',['/','/index.html','/connections'])
def test_html_entry_revalidates_and_reads_the_current_deployment(client,tmp_path,monkeypatch,route):
    monkeypatch.setattr(main,'UI_DIST',tmp_path)
    index=tmp_path/'index.html'
    index.write_text('<script src="/assets/index-old.js"></script>')
    first=client.get(route)
    assert first.status_code==200
    assert first.headers['cache-control']=='no-cache, max-age=0, must-revalidate'
    index.write_text('<script src="/assets/index-current.js"></script>')
    current=client.get(route,headers={'If-None-Match':first.headers['etag']})
    assert current.status_code==200
    assert 'index-current.js' in current.text
    assert 'index-old.js' not in current.text

def test_html_cache_policy_preserves_direct_asset_delivery(client,tmp_path,monkeypatch):
    monkeypatch.setattr(main,'UI_DIST',tmp_path)
    assets=tmp_path/'assets';assets.mkdir()
    (assets/'index-current.js').write_text('export const current=true;')
    response=client.get('/assets/index-current.js')
    assert response.status_code==200
    assert response.text=='export const current=true;'
