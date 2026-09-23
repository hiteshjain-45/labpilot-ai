from app.seed.snippets import SNIPPETS


def code(exp: str, variant: str) -> str:
    return SNIPPETS[exp][variant]


def submit(client, headers, exp_id, source):
    r = client.post(f"/api/experiments/{exp_id}/submit", json={"code": source}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def run(client, headers, exp_id, source):
    r = client.post(f"/api/experiments/{exp_id}/run", json={"code": source}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()
