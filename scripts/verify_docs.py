#!/usr/bin/env python3
"""对照本地固定提交源码，验证指南的基线、结构事实和引用完整性。"""

import argparse
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET


def main():
    """只读核验源码与文档；错误全部输出后以非零状态退出。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    args = parser.parse_args()
    source = args.source_root.resolve()
    root = Path(__file__).resolve().parents[1]
    baseline = (root / 'SOURCE_BASELINE.md').read_text()
    sha = re.search(r'upstream-sha: ([0-9a-f]{40})', baseline).group(1)
    version = re.search(r'upstream-version: ([\w.-]+)', baseline).group(1)
    errors = []
    ns = {'m': 'http://maven.apache.org/POM/4.0.0'}

    def check(condition, message):
        if not condition:
            errors.append(message)

    def pom(path):
        return ET.parse(path / 'pom.xml').getroot()

    head = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    check(head == sha, f'Source HEAD mismatch: {head} != {sha}')
    dirty = subprocess.check_output(['git', '-C', str(source), 'status', '--porcelain', '--untracked-files=no'], text=True)
    check(not dirty, 'Source checkout has tracked modifications')
    check(pom(source).findtext('m:properties/m:revision', namespaces=ns) == version, 'Source POM version mismatch')

    def modules(path):
        return pom(path).findall('m:modules/m:module', ns)

    # 按 Maven 聚合关系递归，继承 deploy skip，不把目录数当作发布数。
    def walk_modules(path, inherited_skip=False):
        tree = pom(path)
        value = tree.findtext('m:properties/m:maven.deploy.skip', namespaces=ns)
        skip = inherited_skip if value is None else value.strip() == 'true'
        packaging = tree.findtext('m:packaging', default='jar', namespaces=ns)
        rows = [(packaging, skip)]
        for module in tree.findall('m:modules/m:module', ns):
            rows.extend(walk_modules(path / module.text.strip(), skip))
        return rows

    core = source / 'agentscope-core/src/main/java/io/agentscope/core'
    ext = source / 'agentscope-extensions'
    rows = walk_modules(ext)
    facts = {
        '根聚合模块': len(modules(source)),
        'core 直接子包': sum(p.is_dir() for p in core.iterdir()),
        'AgentEventType 枚举值': len(re.findall(r'^\s+[A-Z_]+\("[A-Z_]+"\)', (core / 'event/AgentEventType.java').read_text(), re.M)),
        'extensions 一级模块': len(modules(ext)),
        'extensions 聚合 POM': sum(kind == 'pom' for kind, _ in rows),
        'extensions jar 模块': sum(kind == 'jar' for kind, _ in rows),
        'extensions 可发布 jar': sum(kind == 'jar' and not skip for kind, skip in rows),
        'starters jar': sum(kind == 'jar' for kind, _ in walk_modules(ext / 'agentscope-spring-boot-starters')),
        'documentation2 子包': sum(p.is_dir() for p in (source / 'agentscope-examples/documentation/src/main/java/io/agentscope/examples/documentation2').iterdir()),
    }
    for name, count in facts.items():
        check(bool(re.search(r'\| ' + re.escape(name) + r' \| ' + str(count) + r' \|', baseline)), f'Baseline count mismatch: {name} = {count}')

    prefix = 'https://github.com/agentscope-ai/agentscope-java/blob/'
    source_links = set()
    for file in sorted(root.glob('*.md')):
        text = file.read_text()
        if file.name != 'SOURCE_BASELINE.md':
            check(sha[:8] in '\n'.join(text.splitlines()[:18]), f'{file.name}: missing current baseline near title')
        check(len(re.findall(r'^```', text, re.M)) % 2 == 0, f'{file.name}: unpaired code fences')
        for label, url in re.findall(r'\[([^\]\n]+)\]\(([^\s)]+)\)', text):
            if url.startswith(prefix):
                source_links.add(url)
                parts = url[len(prefix):].split('/', 1)
                check(parts[0] == sha, f'{file.name}: non-baseline source link: {url}')
                # 索引以 Class#method 命名时，声明行必须包含该方法。
                if file.name == 'SOURCE_BASELINE.md' and '#' in label:
                    method = label.split('#', 1)[1].strip('`')
                    parsed = urlsplit(url)
                    line = re.fullmatch(r'L(\d+)', parsed.fragment)
                    path = source / unquote(parts[1].split('#', 1)[0])
                    if path.is_file() and line:
                        data = path.read_text().splitlines()
                        number = int(line.group(1))
                        check(1 <= number <= len(data) and re.search(r'\b' + re.escape(method) + r'\(', data[number - 1]), f'{file.name}: method anchor mismatch: {label}')
            elif not urlsplit(url).scheme and not url.startswith('#'):
                path = file.parent / unquote(url.split('#', 1)[0])
                check(path.exists(), f'{file.name}: missing local target: {url}')

    svg_path = root / 'images/agent-call-chain.svg'
    svg = ET.parse(svg_path)
    check(sha in svg_path.read_text(), 'SVG missing current full SHA')
    for link in svg.iter('{http://www.w3.org/2000/svg}a'):
        url = link.get('{http://www.w3.org/1999/xlink}href') or link.get('href', '')
        if url.startswith(prefix):
            source_links.add(url)
            check(url[len(prefix):].startswith(sha + '/'), 'SVG uses a non-baseline source link')

    for url in sorted(source_links):
        tail = url[len(prefix):].split('/', 1)[1]
        parsed = urlsplit(tail)
        path = source / unquote(parsed.path)
        check(path.is_file(), f'Missing source: {tail}')
        if path.is_file() and parsed.fragment:
            anchor = re.fullmatch(r'L(\d+)(?:-L(\d+))?', parsed.fragment)
            check(anchor is not None, f'Invalid source anchor: {tail}')
            if anchor:
                start = int(anchor.group(1))
                end = int(anchor.group(2) or start)
                check(1 <= start <= end <= len(path.read_text().splitlines()), f'Out-of-range source anchor: {tail}')
    if errors:
        for error in errors:
            print('ERROR:', error, file=sys.stderr)
        return 1
    print(f'PASS: {sha[:8]} / {version}; {len(facts)} counts; {len(source_links)} unique source links; Markdown and SVG structure')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
