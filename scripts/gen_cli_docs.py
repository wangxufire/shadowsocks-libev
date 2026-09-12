#!/usr/bin/env python3
"""Generate man-page CLI sections from getopt declarations and CLI_DOC comments.

This intentionally parses a small, checked subset of C, not arbitrary expressions.
Unsupported parser declarations fail instead of silently dropping options. Source
is read without preprocessing so cross-builds document all platform variants.
"""

import argparse
from pathlib import Path
import re
import sys
import textwrap


ROOT = Path(__file__).resolve().parents[1]
PROGRAMS = ("local", "server", "tunnel", "redir", "manager", "nat")
C_COMMENT = re.compile(r'/\*.*?\*/|//[^\n]*', re.S)
TERM = re.compile(r'(-{1,2}[A-Za-z0-9][A-Za-z0-9-]*)(?: (<[^>]+>))?::')


def descriptions(source):
    blocks = re.findall(r'/\* CLI_DOC\n(.*?)\*/', source, re.S)
    for block in re.findall(r'^# CLI_DOC\n(.*?)^# END_CLI_DOC$', source, re.M | re.S):
        blocks.append(re.sub(r'^# ?', '', block, flags=re.M))
    result = {}
    for block in blocks:
        for entry in re.split(r'\n\s*\n(?=-)', block.strip()):
            term, separator, body = entry.partition('\n')
            match = TERM.fullmatch(term)
            if not match or not separator or not body.strip():
                raise ValueError(f"Invalid CLI_DOC entry: {term}")
            flag, argument = match.groups()
            if flag in result:
                raise ValueError(f"Duplicate CLI_DOC entry: {flag}")
            result[flag] = (argument, body.strip())
    return result


def short_options(spec):
    result = {}
    spec = spec.lstrip(':+-')
    while spec:
        match = re.match(r'([A-Za-z0-9])(:?)', spec)
        if not match:
            raise ValueError(f"Unsupported getopt string: {spec}")
        flag, argument = match.groups()
        if '-' + flag in result:
            raise ValueError(f"Duplicate short option: {flag}")
        result['-' + flag] = bool(argument)
        spec = spec[match.end():]
    return result


def options(source, shell=False):
    result = {}
    if shell:
        specs = re.findall(r'^while getopts "([^"]+)" \w+; do$', source, re.M)
        if len(specs) != 1:
            raise ValueError("Expected one literal shell getopts declaration")
    else:
        source = C_COMMENT.sub('', source)
        specs = re.findall(r'getopt_long\(argc,\s*argv,\s*"([^"]+)"\s*,\s*long_options,\s*NULL\)', source)
        if not specs or len(specs) != len(re.findall(r'\bgetopt_long\s*\(', source)):
            raise ValueError("Expected literal getopt_long declarations")
    for spec in specs:
        for flag, argument in short_options(spec).items():
            if flag in result and result[flag] != argument:
                raise ValueError(f"Inconsistent argument across platform variants: {flag}")
            result[flag] = argument
    if shell:
        return result
    tables = re.findall(r'static struct option long_options\[\]\s*=\s*\{(.*?)\};', source, re.S)
    if len(tables) != 1:
        raise ValueError("Expected one long_options table")
    table = re.sub(r'^\s*#.*$', '', tables[0], flags=re.M)
    entry = re.compile(r'\{\s*"([a-z0-9-]+)"\s*,\s*(no_argument|required_argument)\s*,\s*NULL\s*,\s*GETOPT_VAL_[A-Z0-9_]+\s*\}\s*,', re.S)
    for match in entry.finditer(table):
        flag, argument = match.groups()
        if '--' + flag in result:
            raise ValueError(f"Duplicate long option: {flag}")
        result['--' + flag] = argument == 'required_argument'
    remainder = entry.sub('', table)
    if not re.fullmatch(r'\s*\{\s*NULL\s*,\s*0\s*,\s*NULL\s*,\s*0\s*\}\s*', remainder):
        raise ValueError(f"Unsupported long_options entry: {remainder.strip()}")
    return result


def cipher_names(root, kind):
    source = C_COMMENT.sub('', (root / f'src/{kind}.c').read_text())
    match = re.search(r'const char \*supported_' + kind + r'_ciphers\[[^]]+\]\s*=\s*\{(.*?)\};', source, re.S)
    if not match:
        raise ValueError(f"Missing {kind} cipher table")
    table = re.sub(r'^\s*#.*$', '', match[1], flags=re.M)
    names = re.findall(r'"([a-z0-9-]+)"', table)
    if not names or re.sub(r'"[a-z0-9-]+"|[\s,]', '', table):
        raise ValueError(f"Unsupported {kind} cipher table")
    return ', '.join(names)


def sections(program, declared, docs):
    missing = declared.keys() - docs.keys()
    if missing:
        raise ValueError(f"{program}: missing CLI_DOC descriptions: {', '.join(sorted(missing))}")
    synopsis = [f'*{program}*']
    entries = []
    for flag, takes_argument in declared.items():
        argument, body = docs[flag]
        if bool(argument) != takes_argument:
            raise ValueError(f"{program}: argument mismatch for {flag}")
        term = flag + (' ' + argument if argument else '')
        synopsis.append(f'[{term}]')
        entries.append(f'{term}::\n{body}')
    return (textwrap.fill(' '.join(synopsis), width=78, subsequent_indent=' ',
                          break_long_words=False, break_on_hyphens=False),
            '\n\n'.join(entries))


def replace_section(document, heading, body):
    pattern = re.compile(r'(^' + heading + r'\n-+\n).*?(?=^[A-Z][A-Z /-]*\n-+\n|\Z)', re.M | re.S)
    document, count = pattern.subn(lambda m: m[1] + body + '\n\n', document)
    if count != 1:
        raise ValueError(f"Expected one {heading} section")
    return document


def generate(root):
    shared = descriptions((root / 'src/utils.c').read_text())
    replacements = {f'{{cli-{kind}-ciphers}}': cipher_names(root, kind)
                    for kind in ('aead', 'stream')}
    result = {}
    all_options = set()
    summary = []
    for module in PROGRAMS:
        program = 'ss-' + module
        path = 'src/ss-nat' if module == 'nat' else f'src/{module}.c'
        source = (root / path).read_text()
        declared = options(source, shell=module == 'nat')
        local = descriptions(source)
        if local.keys() - declared.keys():
            raise ValueError(f"{program}: stale CLI_DOC descriptions: {local.keys() - declared.keys()}")
        docs = local if module == 'nat' else {**shared, **local}
        if module != 'nat':
            all_options.update(declared)
        synopsis, body = sections(program, declared, docs)
        note = (f'// Generated by scripts/gen_cli_docs.py from {path}; do not edit this section.\n\n')
        document = (root / f'doc/{program}.asciidoc').read_text()
        document = replace_section(document, 'SYNOPSIS', note + synopsis)
        body = ('This section lists options across supported builds. Platform and feature\n'
                'restrictions are noted below; not every option is effective on every platform.\n\n' + body)
        document = replace_section(document, 'OPTIONS', note + body)
        for key, value in replacements.items():
            document = document.replace(key, value)
        result[f'{program}.asciidoc'] = document
        summary.append(f'`{program}`(1)::\nSee this command\'s generated SYNOPSIS and OPTIONS for its accepted arguments.')
    if shared.keys() - all_options:
        raise ValueError(f"Stale shared CLI_DOC descriptions: {shared.keys() - all_options}")
    document = (root / 'doc/shadowsocks-c.asciidoc').read_text()
    note = '// Generated by scripts/gen_cli_docs.py; do not edit this section.\n\n'
    document = replace_section(document, 'SYNOPSIS', note + '\n\n'.join(f'*ss-{p}* [options]' for p in PROGRAMS))
    document = replace_section(document, 'OPTIONS', note + '\n\n'.join(summary))
    result['shadowsocks-c.asciidoc'] = document
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--check', action='store_true', help='fail if checked-in pages are stale')
    mode.add_argument('--output-dir', type=Path, help='write assembled pages here instead of doc/')
    args = parser.parse_args()
    try:
        generated = generate(args.root)
        if args.check:
            stale = [name for name, text in generated.items()
                     if (args.root / 'doc' / name).read_text() != text]
            if stale:
                raise ValueError('Stale CLI docs: ' + ', '.join(stale) +
                                 '; run python3 scripts/gen_cli_docs.py')
        else:
            output = args.output_dir or args.root / 'doc'
            output.mkdir(parents=True, exist_ok=True)
            for name, text in generated.items():
                path = output / name
                if not path.exists() or path.read_text() != text:
                    path.write_text(text)
    except (ValueError, OSError) as error:
        parser.exit(1, f'{error}\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
