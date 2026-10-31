"""PR attribution shared by CI and the future JEG-1429 ledger.

The retired lanes.protocol.KNOWN_LANES contains only minimax and describes
outbox adapters, not today's builder lanes. Keep that contract unchanged.
"""
from dataclasses import dataclass
import re

LANE_PREFIXES = {
    'Claude': 'claude/', 'Codex': 'codex/', 'OpenCode': 'opencode/',
    'Pi': 'pi/', 'Muse': 'muse/', 'Console worker': 'console/',
}

@dataclass(frozen=True)
class Attribution:
    builder: str
    model: str
    coordinator: str


def parse_lane(body: str) -> Attribution:
    # Examples inside Markdown comments or fenced code are not declarations.
    body = re.sub(r'<!--.*?-->', '', body, flags=re.S)
    lines = []
    fence = None
    for line in body.splitlines():
        marker = re.match(r'^\s*(`{3,}|~{3,})', line)
        if marker:
            char = marker[1][0]
            if fence is None:
                fence = char
            elif fence == char:
                fence = None
            continue
        if fence is None and re.match(r'^Lane:', line):
            lines.append(line)
    if len(lines) != 1:
        raise ValueError('Exactly one visible Lane: line is required.')
    match = re.fullmatch(
        r'Lane: built by (Claude|Codex|OpenCode|Pi|Muse|Console worker) '
        r'\(([^();\n]+)\); coordinated by ([^;\n]+); review ([^;\n]+)\.',
        lines[0].strip(),
    )
    if not match or any(not value.strip() or '<' in value or '>' in value
                        for value in match.groups()[1:] if match):
        raise ValueError('Use Lane: built by BUILDER (MODEL); coordinated by COORDINATOR; review STATUS.')
    return Attribution(*(value.strip() for value in match.groups()[:3]))


def check_prefix(attribution: Attribution, branch: str) -> None:
    prefix = LANE_PREFIXES[attribution.builder]
    if not branch.startswith(prefix) or not branch[len(prefix):].strip():
        raise ValueError(f'Builder {attribution.builder} requires branch prefix {prefix}')
