"""One pinned public Pi skill; no project or ambient skill discovery."""
import hashlib

NAME = 'policy-feedback'
MOUNT = '/pi/skills/policy-feedback/SKILL.md'


def skill(integration):
    path = integration / 'skills' / NAME / 'SKILL.md'
    text = path.read_text()
    frontmatter, body = text.removeprefix('---\n').split('\n---\n', 1)
    if 'name: ' + NAME not in frontmatter.splitlines() or not body.strip():
        raise ValueError('Pi feedback skill is malformed')
    return {'path': path, 'body': body.strip(), 'name': NAME,
            'metadata': {'name': NAME, 'sha256': hashlib.sha256(text.encode()).hexdigest(),
                         'invocation': '/skill:' + NAME, 'mount': MOUNT}}
