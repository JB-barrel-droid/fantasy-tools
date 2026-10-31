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
    # Track fences before comments: comment markers in examples are literal.
    lines = []
    fence = None
    in_comment = False
    for line in body.splitlines():
        if fence is not None:
            closer = re.fullmatch(r' {0,3}([`~]+)[ \t]*', line)
            if (closer and set(closer[1]) == {fence[0]}
                    and len(closer[1]) >= fence[1]):
                fence = None
            continue
        if not in_comment:
            opener = re.match(r'^ {0,3}(`{3,}|~{3,})(.*)$', line)
            if opener and (opener[1][0] != '`' or '`' not in opener[2]):
                fence = (opener[1][0], len(opener[1]))
                continue
        visible = ''
        while line:
            if in_comment:
                end = line.find('-->')
                if end == -1:
                    break
                line = line[end + 3:]
                in_comment = False
            else:
                start = line.find('<!--')
                if start == -1:
                    visible += line
                    break
                visible += line[:start]
                line = line[start + 4:]
                in_comment = True
        if re.match(r'^ {0,3}Lane:', visible):
            lines.append(visible)
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
